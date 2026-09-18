from __future__ import annotations

from decimal import Decimal

import pytest

from deleva.activity import ActivityEventType
from deleva.config import DelevaConfig
from deleva.engine import AutonomousEngine
from deleva.engine_state import EngineState
from deleva.execution_mode import ExecutionMode
from deleva.keeperhub_client import PollTimeoutError
from deleva.models import RiskState
from deleva.risk import RiskEvaluator
from deleva.strategy import DelevaStrategy

from fakes import (
    DUMMY_WALLET,
    FakeAlmanakInterface,
    FakeKeeperHubClient,
    FakePositionService,
    execution_failed,
    execution_ok,
    execution_unconfirmed,
    make_position,
    real_deleverage_bundle,
    simulation_ok,
    simulation_revert,
)


def make_engine(
    *,
    positions,
    almanak_interface=None,
    keeperhub_client=None,
    execution_mode=ExecutionMode.LIVE,
    retry_backoff_seconds=300,
    persistence=None,
):
    config = DelevaConfig(
        monitored_wallet=DUMMY_WALLET,
        hf_trigger_threshold=Decimal("1.50"),
        hf_target=Decimal("1.50"),
        retry_backoff_seconds=retry_backoff_seconds,
    )
    strategy = DelevaStrategy.default(config)
    engine = AutonomousEngine(
        config=config,
        strategy=strategy,
        position_service=FakePositionService(positions),
        risk_evaluator=RiskEvaluator(trigger_threshold=strategy.trigger_health_factor),
        almanak_interface=almanak_interface or FakeAlmanakInterface(),
        keeperhub_client=keeperhub_client or FakeKeeperHubClient(),
        execution_mode=execution_mode,
        persistence=persistence,
    )
    return engine


class TestHealthyPosition:
    """Scenario A: HF = 2.0 -> HEALTHY, no Almanak, no KeeperHub write, activity recorded."""

    def test_healthy_position_takes_no_action(self):
        almanak = FakeAlmanakInterface()
        keeperhub = FakeKeeperHubClient()
        engine = make_engine(
            positions=[make_position(health_factor=Decimal("2.0"))],
            almanak_interface=almanak,
            keeperhub_client=keeperhub,
        )

        result = engine.run_cycle()

        assert result.risk_state == RiskState.HEALTHY
        assert result.triggered is False
        assert result.action_taken is False
        assert almanak.calls == []
        assert keeperhub.simulate_calls == []
        assert keeperhub.execute_calls == []
        assert [e.event_type for e in result.activity_events] == [ActivityEventType.POSITION_EVALUATED]


class TestExactThreshold:
    """Scenario B: HF exactly 1.50 -> HEALTHY (inclusive boundary), no execution."""

    def test_exact_threshold_does_not_trigger(self):
        almanak = FakeAlmanakInterface()
        engine = make_engine(
            positions=[make_position(health_factor=Decimal("1.50"))],
            almanak_interface=almanak,
        )

        result = engine.run_cycle()

        assert result.risk_state == RiskState.HEALTHY
        assert result.triggered is False
        assert almanak.calls == []


class TestBreachedThresholdFullSuccess:
    """Scenario C: HF = 1.49 -> breached, real Almanak bundle, both legs
    simulate+execute in mocked LIVE mode, verification succeeds."""

    def test_full_triggered_cycle(self):
        bundle = real_deleverage_bundle()
        almanak = FakeAlmanakInterface(bundle=bundle)
        keeperhub = FakeKeeperHubClient(
            simulate_responses=[simulation_ok(), simulation_ok()],
            execute_responses=[execution_ok("exec-approve", "0xapprove"), execution_ok("exec-repay", "0xrepay")],
        )
        engine = make_engine(
            positions=[
                make_position(health_factor=Decimal("1.49"), debt_usd=Decimal("12.00")),
                make_position(health_factor=Decimal("2.10"), debt_usd=Decimal("2.00")),
            ],
            almanak_interface=almanak,
            keeperhub_client=keeperhub,
        )

        result = engine.run_cycle()

        assert result.risk_state == RiskState.THRESHOLD_BREACHED
        assert result.triggered is True
        assert result.action_taken is True
        assert result.overall_success is True
        assert len(almanak.calls) == 1
        assert len(keeperhub.simulate_calls) == 2
        assert len(keeperhub.execute_calls) == 2
        assert result.verification is not None
        assert result.verification.success is True
        assert result.verification.debt_decreased is True
        # Called engine.run_cycle() directly here, with no MonitoringRunner
        # involved -- the engine correctly settles back to STOPPED (its
        # default container state), not RUNNING, so a single manually
        # invoked cycle never claims ongoing autonomous monitoring that
        # isn't actually happening. See test_runner.py for the RUNNING case.
        assert result.engine_state == EngineState.STOPPED

        event_types = [e.event_type for e in result.activity_events]
        assert event_types == [
            ActivityEventType.POSITION_EVALUATED,
            ActivityEventType.RISK_THRESHOLD_BREACHED,
            ActivityEventType.ALMANAK_INTENT_CREATED,
            ActivityEventType.ACTION_BUNDLE_COMPILED,
            ActivityEventType.KEEPERHUB_SIMULATION,
            ActivityEventType.KEEPERHUB_EXECUTION,
            ActivityEventType.KEEPERHUB_SIMULATION,
            ActivityEventType.KEEPERHUB_EXECUTION,
            ActivityEventType.TRANSACTION_CONFIRMED,
            ActivityEventType.POSITION_VERIFIED,
        ]

    def test_almanak_is_invoked_with_the_strategys_target_hf(self):
        bundle = real_deleverage_bundle()
        almanak = FakeAlmanakInterface(bundle=bundle)
        keeperhub = FakeKeeperHubClient(
            simulate_responses=[simulation_ok(), simulation_ok()],
            execute_responses=[execution_ok(), execution_ok()],
        )
        engine = make_engine(
            positions=[
                make_position(health_factor=Decimal("1.49")),
                make_position(health_factor=Decimal("2.10"), debt_usd=Decimal("2.00")),
            ],
            almanak_interface=almanak,
            keeperhub_client=keeperhub,
        )
        engine.run_cycle()
        assert almanak.calls[0]["target_hf"] == Decimal("1.50")
        assert almanak.calls[0]["protocol"] == "aave_v3"


class TestSimulationFailure:
    """Scenario D: Almanak generates action, simulation fails, NO execution, failure recorded."""

    def test_simulation_failure_blocks_execution(self):
        bundle = real_deleverage_bundle()
        almanak = FakeAlmanakInterface(bundle=bundle)
        keeperhub = FakeKeeperHubClient(simulate_responses=[simulation_revert("insufficient allowance")])
        engine = make_engine(
            positions=[make_position(health_factor=Decimal("1.20"))],
            almanak_interface=almanak,
            keeperhub_client=keeperhub,
        )

        result = engine.run_cycle()

        assert result.triggered is True
        assert result.action_taken is False
        assert result.overall_success is False
        assert "Simulation failed" in result.error
        assert keeperhub.execute_calls == []  # never attempted to execute
        assert ActivityEventType.EXECUTION_FAILED in [e.event_type for e in result.activity_events]
        assert result.engine_state == EngineState.ERROR


class TestApprovalSucceedsRepaySimulationFails:
    """Scenario E: approval executes, repay's simulation fails -- repay must
    NOT execute, no false success."""

    def test_repay_never_executes_after_failed_simulation(self):
        bundle = real_deleverage_bundle()
        almanak = FakeAlmanakInterface(bundle=bundle)
        keeperhub = FakeKeeperHubClient(
            simulate_responses=[simulation_ok(), simulation_revert("ERC20: transfer amount exceeds allowance")],
            execute_responses=[execution_ok("exec-approve", "0xapprove")],
        )
        engine = make_engine(
            positions=[make_position(health_factor=Decimal("1.20"))],
            almanak_interface=almanak,
            keeperhub_client=keeperhub,
        )

        result = engine.run_cycle()

        assert result.action_taken is True  # approve really executed
        assert result.overall_success is False  # but the overall bundle did not complete
        assert len(keeperhub.execute_calls) == 1  # only the approve leg
        assert len(result.leg_results) == 2
        assert result.leg_results[0].execution is not None
        assert result.leg_results[0].execution.succeeded is True
        assert result.leg_results[1].execution is None  # repay never executed
        assert result.leg_results[1].simulation.success is False


class TestExecutionTimeout:
    """Scenario F: existing execution status is resolved before any new
    submission is attempted -- no blind duplicate transaction."""

    def test_timeout_is_recorded_and_not_retried_blindly(self):
        bundle = real_deleverage_bundle()
        almanak = FakeAlmanakInterface(bundle=bundle)
        keeperhub = FakeKeeperHubClient(
            simulate_responses=[simulation_ok()],
            execute_responses=[PollTimeoutError("timed out", body={"executionId": "exec-pending-1"})],
        )
        engine = make_engine(
            positions=[make_position(health_factor=Decimal("1.20"))],
            almanak_interface=almanak,
            keeperhub_client=keeperhub,
        )

        result = engine.run_cycle()

        assert result.overall_success is False
        assert "unresolved" in result.error.lower() or "timed out" in result.error.lower()
        assert engine._pending_execution_id == "exec-pending-1"  # noqa: SLF001
        assert len(keeperhub.execute_calls) == 1  # exactly one attempt, not retried within this cycle

    def test_next_cycle_resolves_pending_before_evaluating_anew(self):
        bundle = real_deleverage_bundle()
        almanak = FakeAlmanakInterface(bundle=bundle)
        keeperhub = FakeKeeperHubClient(
            simulate_responses=[simulation_ok()],
            execute_responses=[PollTimeoutError("timed out", body={"executionId": "exec-pending-1"})],
            status_responses=[execution_ok("exec-pending-1", "0xresolved")],
        )
        engine = make_engine(
            positions=[
                make_position(health_factor=Decimal("1.20")),
                make_position(health_factor=Decimal("1.20")),  # would-be 2nd cycle's fresh read, unused if resolution short-circuits
            ],
            almanak_interface=almanak,
            keeperhub_client=keeperhub,
        )

        first = engine.run_cycle()
        assert first.overall_success is False

        second = engine.run_cycle()

        assert keeperhub.status_calls == ["exec-pending-1"]
        assert len(almanak.calls) == 1  # NOT called again for the resolution cycle
        assert len(keeperhub.execute_calls) == 1  # no second execute attempt
        assert second.overall_success is True
        assert engine._pending_execution_id is None  # noqa: SLF001

    def test_still_unconfirmed_pending_skips_new_evaluation(self):
        bundle = real_deleverage_bundle()
        almanak = FakeAlmanakInterface(bundle=bundle)
        keeperhub = FakeKeeperHubClient(
            simulate_responses=[simulation_ok()],
            execute_responses=[PollTimeoutError("timed out", body={"executionId": "exec-pending-1"})],
            status_responses=[execution_unconfirmed("exec-pending-1")],
        )
        engine = make_engine(
            positions=[make_position(health_factor=Decimal("1.20"))],
            almanak_interface=almanak,
            keeperhub_client=keeperhub,
        )

        engine.run_cycle()
        second = engine.run_cycle()

        assert second.skipped_reason is not None
        assert "unconfirmed" in second.skipped_reason.lower()
        assert len(almanak.calls) == 1  # still not called again
        assert engine._pending_execution_id == "exec-pending-1"  # noqa: SLF001


class TestVerificationFailure:
    """Scenario G: execution succeeds but the position did not actually
    improve -- verification failure must be recorded, not fabricated success."""

    def test_debt_not_decreased_is_a_verification_failure(self):
        bundle = real_deleverage_bundle()
        almanak = FakeAlmanakInterface(bundle=bundle)
        keeperhub = FakeKeeperHubClient(
            simulate_responses=[simulation_ok(), simulation_ok()],
            execute_responses=[execution_ok("exec-approve", "0xapprove"), execution_ok("exec-repay", "0xrepay")],
        )
        engine = make_engine(
            positions=[
                make_position(health_factor=Decimal("1.20"), debt_usd=Decimal("12.00")),
                # Debt did NOT decrease despite a "successful" execution.
                make_position(health_factor=Decimal("1.20"), debt_usd=Decimal("12.00")),
            ],
            almanak_interface=almanak,
            keeperhub_client=keeperhub,
        )

        result = engine.run_cycle()

        assert result.action_taken is True
        assert result.verification is not None
        assert result.verification.success is False
        assert result.overall_success is False
        assert "Verification failed" in result.error
        assert ActivityEventType.POSITION_VERIFIED in [e.event_type for e in result.activity_events]


class TestRepeatedHealthyCycles:
    """Scenario H: repeated healthy cycles take no unnecessary actions."""

    def test_three_healthy_cycles_never_call_almanak_or_keeperhub(self):
        almanak = FakeAlmanakInterface()
        keeperhub = FakeKeeperHubClient()
        engine = make_engine(
            positions=[make_position(health_factor=Decimal("2.0"))],
            almanak_interface=almanak,
            keeperhub_client=keeperhub,
        )

        for _ in range(3):
            result = engine.run_cycle()
            assert result.triggered is False

        assert almanak.calls == []
        assert keeperhub.simulate_calls == []


class TestRepeatedBreachedStateGuardedByBackoff:
    """Scenario I: no uncontrolled duplicate execution on repeated breach."""

    def test_second_immediate_breach_is_skipped_by_backoff(self):
        bundle = real_deleverage_bundle()
        almanak = FakeAlmanakInterface(bundle=bundle)
        keeperhub = FakeKeeperHubClient(
            simulate_responses=[simulation_ok(), simulation_ok()],
            execute_responses=[execution_ok("exec-approve", "0xapprove"), execution_ok("exec-repay", "0xrepay")],
        )
        engine = make_engine(
            positions=[
                make_position(health_factor=Decimal("1.20"), debt_usd=Decimal("20.00")),
                make_position(health_factor=Decimal("1.49"), debt_usd=Decimal("10.00")),  # improved, still breached
                make_position(health_factor=Decimal("1.49"), debt_usd=Decimal("10.00")),  # 2nd cycle's read
            ],
            almanak_interface=almanak,
            keeperhub_client=keeperhub,
            retry_backoff_seconds=300,
        )

        first = engine.run_cycle()
        assert first.triggered is True
        assert len(almanak.calls) == 1

        second = engine.run_cycle()

        assert second.triggered is True
        assert second.skipped_reason is not None
        assert "backoff" in second.skipped_reason.lower()
        assert len(almanak.calls) == 1  # NOT called a second time
        assert len(keeperhub.execute_calls) == 2  # unchanged from the first cycle

class TestEngineStateContainerSemantics:
    """EngineState.RUNNING must only ever be claimed while a MonitoringRunner
    has genuinely marked the engine as actively looping (mark_running()) --
    never merely because a single cycle happened to succeed. And when a
    cycle fails, engine.state itself (not just the returned CycleResult)
    must show ERROR -- a real bug found and fixed during a semantics audit."""

    def test_bare_run_cycle_with_no_runner_settles_to_stopped(self):
        engine = make_engine(positions=[make_position(health_factor=Decimal("2.0"))])
        assert engine.state == EngineState.STOPPED  # never touched by a runner
        result = engine.run_cycle()
        assert result.engine_state == EngineState.STOPPED
        assert engine.state == EngineState.STOPPED

    def test_mark_running_makes_a_healthy_cycle_settle_to_running(self):
        engine = make_engine(positions=[make_position(health_factor=Decimal("2.0"))])
        engine.mark_running()
        result = engine.run_cycle()
        assert result.engine_state == EngineState.RUNNING
        assert engine.state == EngineState.RUNNING

    def test_mark_stopped_returns_to_stopped(self):
        engine = make_engine(positions=[make_position(health_factor=Decimal("2.0"))])
        engine.mark_running()
        engine.run_cycle()
        engine.mark_stopped()
        assert engine.state == EngineState.STOPPED
        result = engine.run_cycle()
        assert result.engine_state == EngineState.STOPPED

    def test_failed_simulation_sets_engine_state_error_not_just_the_result(self):
        # Regression test for a real bug: engine.state was previously left
        # stale (EXECUTING/SIMULATING) on this path even though the returned
        # CycleResult correctly reported ERROR.
        bundle = real_deleverage_bundle()
        almanak = FakeAlmanakInterface(bundle=bundle)
        keeperhub = FakeKeeperHubClient(simulate_responses=[simulation_revert()])
        engine = make_engine(
            positions=[make_position(health_factor=Decimal("1.20"))],
            almanak_interface=almanak,
            keeperhub_client=keeperhub,
        )
        engine.mark_running()

        result = engine.run_cycle()

        assert result.engine_state == EngineState.ERROR
        assert engine.state == EngineState.ERROR  # the live attribute, not just the result

    def test_error_clears_on_the_next_successful_cycle(self):
        bundle = real_deleverage_bundle()
        almanak = FakeAlmanakInterface(bundle=bundle)
        keeperhub = FakeKeeperHubClient(simulate_responses=[simulation_revert()])
        engine = make_engine(
            positions=[
                make_position(health_factor=Decimal("1.20")),
                make_position(health_factor=Decimal("2.0")),
            ],
            almanak_interface=almanak,
            keeperhub_client=keeperhub,
        )
        engine.mark_running()

        engine.run_cycle()
        assert engine.state == EngineState.ERROR

        second = engine.run_cycle()
        assert second.risk_state == RiskState.HEALTHY
        assert engine.state == EngineState.RUNNING  # cleared back to the container state, not stuck on ERROR


class TestDeleverageAmountSizing:
    """The repay amount must be derived from the strategy's target health
    factor, not a fixed constant -- otherwise a small breach and a severe
    breach would get an identical response, and a fixed amount could be
    entirely wrong for a differently-sized position."""

    def _engine_with_target_hf(self, target_hf: Decimal, min_amount: Decimal = Decimal("10")) -> AutonomousEngine:
        config = DelevaConfig(
            monitored_wallet=DUMMY_WALLET,
            hf_trigger_threshold=Decimal("1.50"),
            hf_target=target_hf,
            min_deleverage_amount=min_amount,
        )
        strategy = DelevaStrategy.default(config)
        return AutonomousEngine(
            config=config,
            strategy=strategy,
            position_service=FakePositionService([make_position(health_factor=Decimal("1.0"))]),
            risk_evaluator=RiskEvaluator(trigger_threshold=strategy.trigger_health_factor),
            almanak_interface=FakeAlmanakInterface(),
            keeperhub_client=FakeKeeperHubClient(),
        )

    def test_severe_breach_sizes_above_the_floor(self):
        engine = self._engine_with_target_hf(Decimal("1.50"))
        position = make_position(
            health_factor=Decimal("1.0"),
            collateral_usd=Decimal("100"),
            debt_usd=Decimal("90"),
            liquidation_threshold=Decimal("0.75"),
        )
        amount = engine._deleverage_amount(position)  # noqa: SLF001
        # debt_needed_for_target = 100*0.75/1.5 = 50; ideal_repay = 90-50 = 40
        assert amount == Decimal("40.000000")

    def test_minor_breach_is_clamped_to_the_floor(self):
        engine = self._engine_with_target_hf(Decimal("1.50"))
        position = make_position(
            health_factor=Decimal("1.49"),
            collateral_usd=Decimal("100"),
            debt_usd=Decimal("52"),
            liquidation_threshold=Decimal("0.75"),
        )
        amount = engine._deleverage_amount(position)  # noqa: SLF001
        # debt_needed_for_target = 50; ideal_repay = 2 -- below the 10 floor.
        assert amount == Decimal("10.000000")

    def test_amount_never_exceeds_actual_debt_even_below_the_floor(self):
        engine = self._engine_with_target_hf(Decimal("1.50"))
        position = make_position(
            health_factor=Decimal("0.9"),
            collateral_usd=Decimal("20"),
            debt_usd=Decimal("5"),
            liquidation_threshold=Decimal("0.75"),
        )
        amount = engine._deleverage_amount(position)  # noqa: SLF001
        assert amount == Decimal("5.000000")  # floor would say 10, but only 5 is actually owed

    def test_real_proof_position_would_size_to_exactly_ten_usdc(self):
        # The exact real BEFORE state from DELEVA_TRANSACTION_PROOF.md --
        # confirms the new formula reproduces the amount that was actually,
        # really executed, not a different number.
        engine = self._engine_with_target_hf(Decimal("1.50"))
        position = make_position(
            health_factor=Decimal("2.0795"),
            collateral_usd=Decimal("30.06106093"),
            debt_usd=Decimal("11.99848584"),
            liquidation_threshold=Decimal("0.83"),
        )
        amount = engine._deleverage_amount(position)  # noqa: SLF001
        assert amount == Decimal("10.000000")

    def test_missing_debt_raises(self):
        engine = self._engine_with_target_hf(Decimal("1.50"))
        position = make_position(health_factor=Decimal("1.0"), debt_usd=None)
        with pytest.raises(ValueError, match="no known outstanding debt"):
            engine._deleverage_amount(position)  # noqa: SLF001

    def test_missing_collateral_raises(self):
        engine = self._engine_with_target_hf(Decimal("1.50"))
        position = make_position(health_factor=Decimal("1.0"), collateral_usd=None)
        with pytest.raises(ValueError, match="collateral_usd"):
            engine._deleverage_amount(position)  # noqa: SLF001

    def test_missing_liquidation_threshold_raises(self):
        engine = self._engine_with_target_hf(Decimal("1.50"))
        position = make_position(health_factor=Decimal("1.0"), liquidation_threshold=None)
        with pytest.raises(ValueError, match="liquidation_threshold"):
            engine._deleverage_amount(position)  # noqa: SLF001


class TestRepeatedBreachedStateZeroBackoff:
    """Scenario I (contrast case): with backoff disabled, repeated breaches
    ARE allowed to act -- confirms the backoff guard in
    TestRepeatedBreachedStateGuardedByBackoff is doing real work, not a
    no-op."""

    def test_with_zero_backoff_a_second_breach_is_allowed_to_act(self):
        bundle = real_deleverage_bundle()
        almanak = FakeAlmanakInterface(bundle=bundle)
        keeperhub = FakeKeeperHubClient(
            simulate_responses=[simulation_ok(), simulation_ok(), simulation_ok(), simulation_ok()],
            execute_responses=[execution_ok(), execution_ok(), execution_ok(), execution_ok()],
        )
        engine = make_engine(
            positions=[
                make_position(health_factor=Decimal("1.20"), debt_usd=Decimal("20.00")),
                make_position(health_factor=Decimal("1.49"), debt_usd=Decimal("10.00")),
                make_position(health_factor=Decimal("1.20"), debt_usd=Decimal("20.00")),
                make_position(health_factor=Decimal("1.49"), debt_usd=Decimal("10.00")),
            ],
            almanak_interface=almanak,
            keeperhub_client=keeperhub,
            retry_backoff_seconds=0,
        )

        engine.run_cycle()
        engine.run_cycle()

        assert len(almanak.calls) == 2  # backoff disabled -- both breaches acted on
