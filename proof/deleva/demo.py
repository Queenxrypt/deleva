"""Deterministic local demo mode.

Produces exactly the 3-cycle sequence requested for Phase 2 validation:

    Cycle 1: HF=2.08 -> HEALTHY -> no action
    Cycle 2: HF=1.48 -> THRESHOLD_BREACHED -> real Almanak compile ->
             mock KeeperHub simulate -> mock KeeperHub execute -> verify
    Cycle 3: HF=2.10 -> HEALTHY -> no action

IMPORTANT: this is a demonstration of the engine's control flow, not a
substitute for the real blockchain proof. Position data comes from
DemoPositionService (a fixed, scripted sequence -- not a real chain read),
and KeeperHub simulate/execute calls go through DemoKeeperHubClient (fully
in-memory, no network access, no real API key used). Every transaction hash
this produces is deliberately shaped so it cannot be mistaken for a real one
(``0xDEMO...``). The one real, verified transaction remains
``0xd36217b09ba81cea624e88e756514f2ebc0dc689a20dad4286d6f852f205ec57`` --
see DELEVA_TRANSACTION_PROOF.md.

The one real component this demo *does* exercise is Almanak itself: the
DeleverageIntent is compiled by the real, installed IntentCompiler (offline,
no RPC -- the same call used throughout this project). Only the KeeperHub
leg is mocked.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from deleva.activity import ActivityLog
from deleva.almanak_interface import AlmanakStrategyInterface
from deleva.config import DelevaConfig
from deleva.engine import AutonomousEngine, CycleResult
from deleva.execution_mode import ExecutionMode
from deleva.keeperhub_client import ExecutionResult, SimulationResult
from deleva.models import Position
from deleva.risk import RiskEvaluator
from deleva.runner import MonitoringRunner
from deleva.strategy import DelevaStrategy

# The same placeholder address used by every offline-compile proof script in
# this project (proof/run_proof.py, run_deleverage_proof.py, etc.) -- valid
# hex, but a well-known dead address, never funded, never the real
# monitored wallet.
DEMO_WALLET = "0x000000000000000000000000000000000000dEaD"


def _demo_position(health_factor: Decimal, *, collateral: Decimal, debt: Decimal) -> Position:
    return Position(
        wallet=DEMO_WALLET,
        chain="base",
        protocol="aave_v3",
        health_factor=health_factor,
        collateral_usd=collateral,
        debt_usd=debt,
        available_borrows_usd=None,
        ltv=Decimal("0.80"),
        liquidation_threshold=Decimal("0.83"),
        timestamp=datetime.now(timezone.utc),
        raw={"demo": True, "note": "scripted demo data, not a real chain read"},
    )


class DemoPositionService:
    """Returns a fixed, deterministic sequence of Positions, one per call.
    NOT a real Aave read -- see module docstring."""

    def __init__(self, positions: list[Position]) -> None:
        self._positions = list(positions)
        self._index = 0

    def get_position(self, wallet: str | None = None) -> Position:
        if self._index >= len(self._positions):
            return self._positions[-1]
        position = self._positions[self._index]
        self._index += 1
        return position


class DemoKeeperHubClient:
    """Stands in for KeeperHubClient during the demo. Every simulate/execute
    call returns a canned, clearly-fake success response. No network access
    is ever made -- see module docstring for why transaction hashes are
    shaped the way they are."""

    def __init__(self) -> None:
        self._exec_counter = 0

    def simulate_contract_call(self, request: dict) -> SimulationResult:
        return SimulationResult(
            success=True,
            would_revert=False,
            gas_estimate="100000",
            error=None,
            revert_reason=None,
            raw={"demo": True, "note": "mock simulation -- not a real KeeperHub API call"},
        )

    def execute_and_wait(self, request: dict, **_kwargs) -> ExecutionResult:
        self._exec_counter += 1
        return ExecutionResult(
            execution_id=f"demo-exec-{self._exec_counter}",
            status="completed",
            transaction_hash=f"0xDEMO{'0' * 55}{self._exec_counter:05d}",
            transaction_link=None,
            error=None,
            raw={"demo": True, "note": "mock execution -- NOT a real Base transaction"},
        )

    def get_execution_status(self, execution_id: str) -> ExecutionResult:
        return ExecutionResult(
            execution_id=execution_id,
            status="completed",
            transaction_hash=None,
            transaction_link=None,
            error=None,
            raw={"demo": True},
        )


def build_demo_engine() -> tuple[AutonomousEngine, DemoPositionService]:
    # execution_dry_run is left at its default (True) -- irrelevant here
    # since execution_mode is passed explicitly to AutonomousEngine below,
    # which always takes precedence over ExecutionMode.from_config(config).
    config = DelevaConfig(
        monitored_wallet=DEMO_WALLET,
        hf_trigger_threshold=Decimal("1.50"),
        hf_target=Decimal("1.50"),
    )
    strategy = DelevaStrategy.default(config)

    # Cycle 1 (healthy): 1 position read.
    # Cycle 2 (breached): 1 read before acting, 1 read after acting (verify).
    # Cycle 3 (healthy): 1 position read.
    positions = [
        _demo_position(Decimal("2.08"), collateral=Decimal("30.11"), debt=Decimal("12.00")),
        _demo_position(Decimal("1.48"), collateral=Decimal("30.00"), debt=Decimal("20.30")),
        _demo_position(Decimal("2.10"), collateral=Decimal("30.00"), debt=Decimal("10.30")),
        _demo_position(Decimal("2.10"), collateral=Decimal("30.00"), debt=Decimal("10.30")),
    ]
    position_service = DemoPositionService(positions)
    risk_evaluator = RiskEvaluator(trigger_threshold=strategy.trigger_health_factor)
    almanak_interface = AlmanakStrategyInterface(chain=strategy.chain, wallet_address=DEMO_WALLET)
    keeperhub_client = DemoKeeperHubClient()
    activity_log = ActivityLog()

    engine = AutonomousEngine(
        config=config,
        strategy=strategy,
        position_service=position_service,  # type: ignore[arg-type]
        risk_evaluator=risk_evaluator,
        almanak_interface=almanak_interface,
        keeperhub_client=keeperhub_client,  # type: ignore[arg-type]
        activity_log=activity_log,
        execution_mode=ExecutionMode.DEMO,
    )
    return engine, position_service


def run_local_demo() -> list[CycleResult]:
    """Run the deterministic 3-cycle demo and return every CycleResult.

    Never touches the network, never touches the real Aave position. See
    module docstring for exactly what is real (Almanak compilation) vs.
    mocked (position reads, KeeperHub calls) in this mode.
    """
    engine, _ = build_demo_engine()
    runner = MonitoringRunner(engine, interval_seconds=0, sleep_fn=lambda _seconds: None)
    return runner.start(max_cycles=3)
