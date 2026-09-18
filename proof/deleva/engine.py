"""AutonomousEngine: one deterministic monitoring/decision/execution cycle.

Composes Phase 1's components -- AavePositionService, RiskEvaluator,
AlmanakStrategyInterface, KeeperHubClient, the ActionBundle adapter,
ActivityLog -- into the real loop described in DELEVA's product thesis:

    Position -> RiskEvaluator -> Strategy -> Almanak DeleverageIntent
    -> IntentCompiler -> ActionBundle -> DELEVA adapter -> KeeperHub
    simulate -> KeeperHub execute -> verify -> record

Nothing in this module reimplements any of those components. It only
sequences calls to them and records what happened.

Safety: every branch below only ever checks ``execution_mode is DRY_RUN``;
anything else (``LIVE`` or ``DEMO``) proceeds to call
``KeeperHubClient.execute_contract_call`` / ``execute_and_wait`` on whatever
client this engine was constructed with. ``ExecutionMode.DRY_RUN`` stops
after simulation. The real safety boundary is therefore which
``KeeperHubClient`` was injected at construction, not the execution_mode
label -- ``api/state.py`` and ``deleva/cli.py`` (the two real paths) only
ever construct a real ``KeeperHubClient`` with a real API key; only
``deleva/demo.py`` ever constructs the in-memory ``DemoKeeperHubClient``, and
only ``deleva/demo.py`` ever passes ``ExecutionMode.DEMO``. See
``deleva/execution_mode.py`` for why DEMO exists (it used to be mislabeled
LIVE here, which was a misleading label, not a real safety gap).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from deleva.activity import ActivityEvent, ActivityEventType, ActivityLog
from deleva.almanak_interface import ActionBundleResult, AlmanakCompilationError, AlmanakStrategyInterface
from deleva.adapter import almanak_tx_to_keeperhub_request
from deleva.config import DelevaConfig
from deleva.engine_state import EngineState
from deleva.execution_mode import ExecutionMode
from deleva.keeperhub_client import ExecutionResult, KeeperHubClient, PollTimeoutError, SimulationResult
from deleva.models import Position, RiskState
from deleva.persistence import EnginePersistence, InMemoryPersistence
from deleva.position_service import AavePositionService
from deleva.risk import RiskEvaluator
from deleva.strategy import DelevaStrategy
from deleva.verification import VerificationResult, verify_deleverage


@dataclass(frozen=True)
class LegResult:
    """The outcome of one ActionBundle transaction moving through simulate (-> execute)."""

    tx_type: str
    keeperhub_request: dict[str, Any]
    simulation: SimulationResult
    execution: ExecutionResult | None  # None if never reached (sim failed, or DRY_RUN)


@dataclass(frozen=True)
class CycleResult:
    """The complete, structured outcome of one AutonomousEngine.run_cycle() call."""

    engine_state: EngineState
    risk_state: RiskState
    execution_mode: ExecutionMode
    position_before: Position
    position_after: Position | None = None
    triggered: bool = False
    action_bundle: ActionBundleResult | None = None
    leg_results: tuple[LegResult, ...] = field(default_factory=tuple)
    verification: VerificationResult | None = None
    overall_success: bool = True
    error: str | None = None
    skipped_reason: str | None = None
    activity_events: tuple[ActivityEvent, ...] = field(default_factory=tuple)

    @property
    def action_taken(self) -> bool:
        """True if any transaction was actually broadcast this cycle."""
        return any(leg.execution is not None for leg in self.leg_results)


class AutonomousEngine:
    """Orchestrates one monitoring/decision/execution cycle. Stateless between
    calls except for the small continuity state described in the module
    docstring (pending execution resolution, backoff timer) -- deliberately
    not a scheduler; see deleva.runner.MonitoringRunner for that."""

    def __init__(
        self,
        *,
        config: DelevaConfig,
        strategy: DelevaStrategy,
        position_service: AavePositionService,
        risk_evaluator: RiskEvaluator,
        almanak_interface: AlmanakStrategyInterface,
        keeperhub_client: KeeperHubClient,
        activity_log: ActivityLog | None = None,
        execution_mode: ExecutionMode | None = None,
        persistence: EnginePersistence | None = None,
    ) -> None:
        self._config = config
        self._strategy = strategy
        self._position_service = position_service
        self._risk_evaluator = risk_evaluator
        self._almanak_interface = almanak_interface
        self._keeperhub_client = keeperhub_client
        self.activity_log = activity_log or ActivityLog()
        self.execution_mode = execution_mode or ExecutionMode.from_config(config)
        self._persistence = persistence or InMemoryPersistence()

        # `state` is the live, current-phase answer to "what is DELEVA doing
        # right now" (transitions through EVALUATING/TRIGGERED/... during a
        # cycle). `_container_state` is the stable context a cycle settles
        # back to once it finishes without error: RUNNING only while a
        # MonitoringRunner has actually called mark_running() (an active
        # loop is genuinely underway); STOPPED otherwise -- including for a
        # bare, one-off `run_cycle()` call with no runner involved, so a
        # single manual check never claims ongoing autonomous monitoring
        # that isn't actually happening. See mark_running()/mark_stopped().
        self._container_state: EngineState = EngineState.STOPPED
        self.state: EngineState = self._container_state

        saved = self._persistence.load_state()
        self._pending_execution_id: str | None = saved.get("pending_execution_id")
        self._pending_tx_type: str | None = saved.get("pending_tx_type")
        last_action_raw = saved.get("last_action_at")
        self._last_action_at: datetime | None = (
            datetime.fromisoformat(last_action_raw) if last_action_raw else None
        )

    # -- container state (owned by MonitoringRunner) ------------------------

    def mark_running(self) -> None:
        """Called by MonitoringRunner when it begins an active monitoring
        loop. Cycles run after this settle back to RUNNING, honestly
        reflecting that DELEVA is actively, continuously monitoring."""
        self._container_state = EngineState.RUNNING
        self.state = EngineState.RUNNING

    def mark_stopped(self) -> None:
        """Called by MonitoringRunner on stop/shutdown, and is also this
        engine's own default at construction -- so a bare `run_cycle()` call
        with no runner ever involved settles back to STOPPED, not RUNNING."""
        self._container_state = EngineState.STOPPED
        self.state = EngineState.STOPPED

    # -- persistence -------------------------------------------------------

    def _save(self) -> None:
        self._persistence.save_state(
            {
                "pending_execution_id": self._pending_execution_id,
                "pending_tx_type": self._pending_tx_type,
                "last_action_at": self._last_action_at.isoformat() if self._last_action_at else None,
            }
        )

    # -- activity ------------------------------------------------------------

    def _record(self, event_type: ActivityEventType, description: str, **kwargs: Any) -> ActivityEvent:
        event = ActivityEvent(
            event_type=event_type,
            timestamp=datetime.now(timezone.utc),
            description=description,
            strategy=self._strategy.name,
            **kwargs,
        )
        self.activity_log.append(event)
        return event

    # -- cooldown --------------------------------------------------------

    def _in_cooldown(self) -> bool:
        if self._last_action_at is None:
            return False
        elapsed = (datetime.now(timezone.utc) - self._last_action_at).total_seconds()
        return elapsed < self._config.retry_backoff_seconds

    # -- the cycle -----------------------------------------------------------

    def run_cycle(self) -> CycleResult:
        """Run exactly one monitor -> evaluate -> decide -> compile -> simulate
        -> execute -> verify -> record cycle. Deterministic and side-effect
        bounded to: the injected position_service/keeperhub_client/
        almanak_interface calls, activity_log.append, and persistence.save."""
        events_before = len(self.activity_log.all())
        self.state = EngineState.EVALUATING

        # Resolve any execution left unresolved by a prior cycle BEFORE doing
        # anything else -- never blindly submit a new one while one is
        # genuinely unknown (see module docstring / Phase 2 task 9).
        pending_result = self._resolve_pending_if_any()
        if pending_result is not None:
            return self._with_new_events(pending_result, events_before)

        position_before = self._position_service.get_position()
        self._record(
            ActivityEventType.POSITION_EVALUATED,
            f"Read Aave V3 position for {position_before.wallet}: "
            f"health_factor={position_before.health_factor}.",
            health_factor=position_before.health_factor,
        )

        risk_state = self._risk_evaluator.evaluate(position_before)

        if risk_state != RiskState.THRESHOLD_BREACHED:
            self.state = self._container_state
            result = CycleResult(
                engine_state=self.state,
                risk_state=risk_state,
                execution_mode=self.execution_mode,
                position_before=position_before,
                triggered=False,
            )
            return self._with_new_events(result, events_before)

        self.state = EngineState.TRIGGERED
        self._record(
            ActivityEventType.RISK_THRESHOLD_BREACHED,
            f"Health factor {position_before.health_factor} is below trigger threshold "
            f"{self._strategy.trigger_health_factor}.",
            health_factor=position_before.health_factor,
        )

        if self._in_cooldown():
            self.state = self._container_state
            result = CycleResult(
                engine_state=self.state,
                risk_state=risk_state,
                execution_mode=self.execution_mode,
                position_before=position_before,
                triggered=True,
                skipped_reason=(
                    f"In backoff window ({self._config.retry_backoff_seconds}s) since the last triggered "
                    "action -- not attempting another action this cycle to avoid a tight retry loop."
                ),
            )
            return self._with_new_events(result, events_before)

        return self._with_new_events(self._act_on_breach(position_before, risk_state), events_before)

    def _with_new_events(self, result: CycleResult, events_before: int) -> CycleResult:
        new_events = tuple(self.activity_log.all()[events_before:])
        return CycleResult(
            engine_state=result.engine_state,
            risk_state=result.risk_state,
            execution_mode=result.execution_mode,
            position_before=result.position_before,
            position_after=result.position_after,
            triggered=result.triggered,
            action_bundle=result.action_bundle,
            leg_results=result.leg_results,
            verification=result.verification,
            overall_success=result.overall_success,
            error=result.error,
            skipped_reason=result.skipped_reason,
            activity_events=new_events,
        )

    # -- breach handling -------------------------------------------------------

    def _act_on_breach(self, position_before: Position, risk_state: RiskState) -> CycleResult:
        try:
            amount = self._deleverage_amount(position_before)
        except ValueError as exc:
            return self._fail(position_before, risk_state, stage="sizing", error=str(exc))

        self.state = EngineState.SIMULATING
        try:
            bundle = self._almanak_interface.generate_deleverage_action_bundle(
                protocol=self._strategy.protocol,
                token="USDC",
                amount=amount,
                repay_full=False,
                observed_hf=position_before.health_factor,
                target_hf=self._strategy.target_health_factor,
            )
        except AlmanakCompilationError as exc:
            return self._fail(
                position_before,
                risk_state,
                stage="almanak_compilation",
                error=str(exc),
            )

        self._record(
            ActivityEventType.ALMANAK_INTENT_CREATED,
            f"Compiled DeleverageIntent (intent_id={bundle.intent_id}) via the real Almanak IntentCompiler.",
            health_factor=position_before.health_factor,
        )
        self._record(
            ActivityEventType.ACTION_BUNDLE_COMPILED,
            f"Real ActionBundle compiled: {len(bundle.transactions)} transaction(s), "
            f"intent_type={bundle.intent_type}.",
        )

        leg_results, failure = self._simulate_and_execute_legs(bundle)

        if failure is not None:
            # engine.state must be kept in sync with the CycleResult it
            # returns -- leaving it at whatever _simulate_and_execute_legs
            # last set (EXECUTING/SIMULATING) would let a caller read a
            # stale, more-optimistic phase than what actually happened.
            self.state = EngineState.ERROR
            self._last_action_at = datetime.now(timezone.utc)
            self._save()
            return CycleResult(
                engine_state=EngineState.ERROR,
                risk_state=risk_state,
                execution_mode=self.execution_mode,
                position_before=position_before,
                triggered=True,
                action_bundle=bundle,
                leg_results=tuple(leg_results),
                overall_success=False,
                error=failure,
            )

        if self.execution_mode is ExecutionMode.DRY_RUN:
            self.state = self._container_state
            return CycleResult(
                engine_state=self.state,
                risk_state=risk_state,
                execution_mode=self.execution_mode,
                position_before=position_before,
                triggered=True,
                action_bundle=bundle,
                leg_results=tuple(leg_results),
                overall_success=True,  # a clean dry-run preview, nothing failed
            )

        # LIVE or DEMO, all legs executed successfully -- verify.
        self._last_action_at = datetime.now(timezone.utc)
        self.state = EngineState.VERIFYING
        position_after = self._position_service.get_position(wallet=position_before.wallet)
        verification = verify_deleverage(position_before, position_after)
        self._record(
            ActivityEventType.POSITION_VERIFIED,
            verification.reason,
            health_factor=position_after.health_factor,
        )

        self._pending_execution_id = None
        self._pending_tx_type = None
        self._save()

        self.state = self._container_state if verification.success else EngineState.ERROR
        return CycleResult(
            engine_state=self.state,
            risk_state=risk_state,
            execution_mode=self.execution_mode,
            position_before=position_before,
            position_after=position_after,
            triggered=True,
            action_bundle=bundle,
            leg_results=tuple(leg_results),
            verification=verification,
            overall_success=verification.success,
            error=None if verification.success else "Verification failed: " + verification.reason,
        )

    def _deleverage_amount(self, position: Position) -> Decimal:
        """Size the repay amount toward the strategy's target health factor.

        Derived directly from Aave's own health-factor formula:

            health_factor = (collateral_usd * liquidation_threshold) / debt_usd

        Solved for the debt level that would produce ``target_health_factor``,
        then repays the difference. Clamped to
        ``[config.min_deleverage_amount, debt_usd]``: never requests more
        than is actually owed (Aave itself would revert or short-fill), and
        never sends a trivially small "dust" repay that would cost more in
        gas than it accomplishes -- the floor defaults to 10 USDC, the exact
        amount already proven live (see DELEVA_TRANSACTION_PROOF.md).

        Raises ValueError if the position doesn't carry the fields this
        calculation needs -- never fabricates an amount from incomplete
        data.
        """
        if position.debt_usd is None or position.debt_usd <= 0:
            raise ValueError(
                f"Cannot size a deleverage repay for {position.wallet}: no known outstanding debt "
                f"(debt_usd={position.debt_usd})."
            )
        if position.collateral_usd is None or position.liquidation_threshold is None:
            raise ValueError(
                f"Cannot size a deleverage repay for {position.wallet}: collateral_usd and/or "
                "liquidation_threshold were not retrieved, so the target-health-factor calculation "
                "cannot run."
            )

        target_hf = self._strategy.target_health_factor
        if target_hf <= 0:
            raise ValueError(f"strategy.target_health_factor must be positive, got {target_hf}")

        debt_needed_for_target = (position.collateral_usd * position.liquidation_threshold) / target_hf
        ideal_repay = position.debt_usd - debt_needed_for_target

        amount = max(ideal_repay, self._config.min_deleverage_amount)
        amount = min(amount, position.debt_usd)
        return amount.quantize(Decimal("0.000001"))

    # -- per-leg simulate -> execute --------------------------------------

    def _simulate_and_execute_legs(self, bundle: ActionBundleResult) -> tuple[list[LegResult], str | None]:
        """Iterate the ActionBundle's transactions IN ORDER. Each is simulated;
        only once a leg's simulation is confirmed safe does the engine
        execute it (LIVE mode only). A failing simulation stops the whole
        bundle immediately -- later legs are never attempted."""
        leg_results: list[LegResult] = []

        for index, tx in enumerate(bundle.transactions):
            request = almanak_tx_to_keeperhub_request(tx, chain=self._strategy.chain, simulate=True)

            if self.execution_mode is ExecutionMode.DRY_RUN and index > 0:
                # A later leg (e.g. repay) genuinely depends on an earlier
                # leg (e.g. approve) having actually landed on-chain -- this
                # was directly observed during the real proof run (simulating
                # repay before approve had broadcast correctly reverted on
                # insufficient allowance). DRY_RUN never broadcasts anything,
                # so simulating leg N>0 against real, unmutated chain state
                # would report a misleading failure, not a true preview.
                # Record that honestly instead of calling KeeperHub.
                self._record(
                    ActivityEventType.KEEPERHUB_SIMULATION,
                    f"[DRY_RUN preview] tx[{index}] ({tx.get('tx_type')}) depends on tx[{index - 1}] "
                    "actually executing first -- not independently simulatable in DRY_RUN. Would be "
                    "simulated for real immediately before execution in LIVE mode.",
                )
                leg_results.append(
                    LegResult(tx_type=tx.get("tx_type", "unknown"), keeperhub_request=request, simulation=None, execution=None)  # type: ignore[arg-type]
                )
                continue

            simulation = self._keeperhub_client.simulate_contract_call(request)
            self._record(
                ActivityEventType.KEEPERHUB_SIMULATION,
                f"tx[{index}] ({tx.get('tx_type')}): success={simulation.success} "
                f"wouldRevert={simulation.would_revert}"
                + (f" -- {simulation.revert_reason}" if simulation.revert_reason else ""),
                status="simulated",
            )

            if not simulation.is_safe_to_execute:
                self._record(
                    ActivityEventType.EXECUTION_FAILED,
                    f"Simulation failed for tx[{index}] ({tx.get('tx_type')}); stopping bundle, "
                    "no transaction broadcast for this or any later leg.",
                    status="simulation_failed",
                )
                leg_results.append(
                    LegResult(tx_type=tx.get("tx_type", "unknown"), keeperhub_request=request, simulation=simulation, execution=None)
                )
                return leg_results, f"Simulation failed for tx[{index}] ({tx.get('tx_type')}): {simulation.error}"

            if self.execution_mode is ExecutionMode.DRY_RUN:
                leg_results.append(
                    LegResult(tx_type=tx.get("tx_type", "unknown"), keeperhub_request=request, simulation=simulation, execution=None)
                )
                continue

            self.state = EngineState.EXECUTING
            self._pending_execution_id = None  # set below once we have one
            self._pending_tx_type = tx.get("tx_type")
            self._save()
            try:
                execution = self._keeperhub_client.execute_and_wait(request)
            except PollTimeoutError as exc:
                execution_id = exc.body.get("executionId") if isinstance(exc.body, dict) else None
                self._pending_execution_id = execution_id
                self._save()
                self._record(
                    ActivityEventType.EXECUTION_FAILED,
                    f"tx[{index}] ({tx.get('tx_type')}) execution did not reach a terminal status in time "
                    f"(executionId={execution_id}). Will resolve this before attempting anything new.",
                    execution_id=execution_id,
                    status="unconfirmed",
                )
                leg_results.append(
                    LegResult(tx_type=tx.get("tx_type", "unknown"), keeperhub_request=request, simulation=simulation, execution=None)
                )
                return leg_results, f"tx[{index}] execution unresolved (timed out polling): {exc}"

            self._record(
                ActivityEventType.KEEPERHUB_EXECUTION,
                f"tx[{index}] ({tx.get('tx_type')}) executed: status={execution.status} "
                f"tx_hash={execution.transaction_hash}",
                execution_id=execution.execution_id,
                transaction_hash=execution.transaction_hash,
                status=execution.status,
            )

            leg_results.append(
                LegResult(tx_type=tx.get("tx_type", "unknown"), keeperhub_request=request, simulation=simulation, execution=execution)
            )

            if not execution.succeeded:
                self._record(
                    ActivityEventType.EXECUTION_FAILED,
                    f"tx[{index}] ({tx.get('tx_type')}) execution failed: {execution.error}",
                    execution_id=execution.execution_id,
                    status=execution.status,
                )
                self._pending_execution_id = None
                self._pending_tx_type = None
                self._save()
                return leg_results, f"tx[{index}] execution failed: {execution.error}"

            # This leg succeeded and is resolved -- clear the pending marker.
            self._pending_execution_id = None
            self._pending_tx_type = None
            self._save()

            if index == len(bundle.transactions) - 1:
                self._record(
                    ActivityEventType.TRANSACTION_CONFIRMED,
                    f"Final transaction confirmed: tx_hash={execution.transaction_hash}",
                    execution_id=execution.execution_id,
                    transaction_hash=execution.transaction_hash,
                    status=execution.status,
                )

        return leg_results, None

    def _resolve_pending_if_any(self) -> CycleResult | None:
        """If a prior cycle left an execution unresolved, resolve it (a single
        status check, not a long poll) before doing anything else. Returns a
        CycleResult (meaning: stop here, this cycle is just resolution) or
        None (meaning: nothing pending, proceed with a normal cycle)."""
        if self._pending_execution_id is None:
            return None

        status = self._keeperhub_client.get_execution_status(self._pending_execution_id)

        if not status.is_terminal:
            self.state = self._container_state
            return CycleResult(
                engine_state=self.state,
                risk_state=RiskState.UNKNOWN,
                execution_mode=self.execution_mode,
                # No position read this cycle -- resolving takes priority.
                position_before=self._position_service.get_position(),
                triggered=True,
                skipped_reason=(
                    f"Execution {self._pending_execution_id} ({self._pending_tx_type}) is still "
                    "unconfirmed -- not evaluating a new action until it resolves."
                ),
            )

        # Terminal now: record the true outcome, clear the marker, and let
        # this cycle end here. The NEXT cycle will read a fresh position and
        # decide fresh -- see engine.py module docstring for why this is
        # safe (approve is idempotent, repay amount is bounded by real debt).
        if status.succeeded:
            self._record(
                ActivityEventType.TRANSACTION_CONFIRMED,
                f"Previously-unresolved execution {self._pending_execution_id} ({self._pending_tx_type}) "
                f"has now confirmed: tx_hash={status.transaction_hash}",
                execution_id=status.execution_id,
                transaction_hash=status.transaction_hash,
                status=status.status,
            )
        else:
            self._record(
                ActivityEventType.EXECUTION_FAILED,
                f"Previously-unresolved execution {self._pending_execution_id} ({self._pending_tx_type}) "
                f"has now resolved to failure: {status.error}",
                execution_id=status.execution_id,
                status=status.status,
            )

        self._pending_execution_id = None
        self._pending_tx_type = None
        self._last_action_at = datetime.now(timezone.utc)
        self._save()

        self.state = self._container_state
        return CycleResult(
            engine_state=self.state,
            risk_state=RiskState.UNKNOWN,
            execution_mode=self.execution_mode,
            position_before=self._position_service.get_position(),
            triggered=True,
            overall_success=status.succeeded,
            error=None if status.succeeded else f"Resolved pending execution failed: {status.error}",
        )

    def _fail(self, position_before: Position, risk_state: RiskState, *, stage: str, error: str) -> CycleResult:
        self.state = EngineState.ERROR
        self._last_action_at = datetime.now(timezone.utc)
        self._save()
        self._record(
            ActivityEventType.EXECUTION_FAILED,
            f"Cycle failed at stage={stage}: {error}",
            status="failed",
        )
        return CycleResult(
            engine_state=self.state,
            risk_state=risk_state,
            execution_mode=self.execution_mode,
            position_before=position_before,
            triggered=True,
            overall_success=False,
            error=f"{stage}: {error}",
        )
