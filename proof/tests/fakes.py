"""Shared test doubles for Phase 2 engine/runner tests.

Not a test file itself (no test_ prefix, not collected by pytest). Fakes
mock only the boundary that would otherwise touch the network (KeeperHub) or
a scripted position read -- Almanak compilation is exercised for real
wherever practical (see ``real_deleverage_bundle`` below), matching the
project's established practice of using the real SDK everywhere it's safe
and free to do so (offline compile, no RPC, no broadcast).
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from decimal import Decimal

from deleva.almanak_interface import ActionBundleResult, AlmanakStrategyInterface
from deleva.keeperhub_client import ExecutionResult, SimulationResult
from deleva.models import Position

DUMMY_WALLET = "0x000000000000000000000000000000000000dEaD"


def make_position(
    *,
    health_factor: Decimal | None,
    debt_usd: Decimal | None = Decimal("12.00"),
    collateral_usd: Decimal | None = Decimal("30.00"),
    liquidation_threshold: Decimal | None = Decimal("0.83"),
) -> Position:
    return Position(
        wallet=DUMMY_WALLET,
        chain="base",
        protocol="aave_v3",
        health_factor=health_factor,
        collateral_usd=collateral_usd,
        debt_usd=debt_usd,
        available_borrows_usd=None,
        ltv=Decimal("0.80"),
        liquidation_threshold=liquidation_threshold,
        timestamp=datetime.now(timezone.utc),
        raw={"test": True},
    )


def real_deleverage_bundle() -> ActionBundleResult:
    """A genuine ActionBundleResult from the real, installed Almanak
    IntentCompiler (offline, no RPC, no broadcast) -- the same 2-transaction
    approve+repay shape as the real DELEVA proof transaction. Used so engine
    tests exercise the real adapter's decode/translate path against real
    calldata, not a hand-fabricated stand-in."""
    interface = AlmanakStrategyInterface(chain="base", wallet_address=DUMMY_WALLET)
    return interface.generate_deleverage_action_bundle(
        protocol="aave_v3",
        token="USDC",
        amount=Decimal("10"),
        repay_full=False,
        observed_hf=Decimal("1.49"),
        target_hf=Decimal("1.50"),
    )


class FakePositionService:
    """Returns a scripted sequence of Positions, one per call. Repeats the
    last one if called more times than scripted."""

    def __init__(self, positions: list[Position], *, usdc_balance: Decimal = Decimal("2.00")) -> None:
        self._positions: deque[Position] = deque(positions)
        self.calls: list[str | None] = []
        self.usdc_balance = usdc_balance

    def get_usdc_balance(self, wallet: str | None = None) -> Decimal:
        return self.usdc_balance

    def get_position(self, wallet: str | None = None) -> Position:
        self.calls.append(wallet)
        if len(self._positions) > 1:
            return self._positions.popleft()
        return self._positions[0]


class FakeAlmanakInterface:
    """Returns a fixed ActionBundleResult, or raises a fixed exception."""

    def __init__(self, bundle: ActionBundleResult | None = None, error: Exception | None = None) -> None:
        self._bundle = bundle
        self._error = error
        self.calls: list[dict] = []

    def generate_deleverage_action_bundle(self, **kwargs) -> ActionBundleResult:
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        assert self._bundle is not None
        return self._bundle


class FakeKeeperHubClient:
    """Scripted simulate/execute/status responses, queued in call order.
    Never touches the network. Raises AssertionError if a test calls it more
    times than it programmed -- surfaces test-design bugs immediately rather
    than silently returning stale data."""

    def __init__(
        self,
        *,
        simulate_responses: list[SimulationResult] | None = None,
        execute_responses: list[ExecutionResult | Exception] | None = None,
        status_responses: list[ExecutionResult] | None = None,
    ) -> None:
        self._simulate_queue: deque = deque(simulate_responses or [])
        self._execute_queue: deque = deque(execute_responses or [])
        self._status_queue: deque = deque(status_responses or [])
        self.simulate_calls: list[dict] = []
        self.execute_calls: list[dict] = []
        self.status_calls: list[str] = []

    def simulate_contract_call(self, request: dict) -> SimulationResult:
        self.simulate_calls.append(request)
        if not self._simulate_queue:
            raise AssertionError("FakeKeeperHubClient.simulate_contract_call called with no response queued")
        return self._simulate_queue.popleft()

    def execute_and_wait(self, request: dict, **_kwargs) -> ExecutionResult:
        self.execute_calls.append(request)
        if not self._execute_queue:
            raise AssertionError("FakeKeeperHubClient.execute_and_wait called with no response queued")
        result = self._execute_queue.popleft()
        if isinstance(result, Exception):
            raise result
        return result

    def get_execution_status(self, execution_id: str) -> ExecutionResult:
        self.status_calls.append(execution_id)
        if not self._status_queue:
            raise AssertionError("FakeKeeperHubClient.get_execution_status called with no response queued")
        return self._status_queue.popleft()


def simulation_ok(gas_estimate: str = "100000") -> SimulationResult:
    return SimulationResult(
        success=True, would_revert=False, gas_estimate=gas_estimate, error=None, revert_reason=None, raw={}
    )


def simulation_revert(reason: str = "execution reverted") -> SimulationResult:
    return SimulationResult(
        success=False, would_revert=True, gas_estimate=None, error=reason, revert_reason=reason, raw={}
    )


def execution_ok(execution_id: str = "exec-1", tx_hash: str = "0xabc") -> ExecutionResult:
    return ExecutionResult(
        execution_id=execution_id, status="completed", transaction_hash=tx_hash, transaction_link=None, error=None, raw={}
    )


def execution_failed(execution_id: str = "exec-1", error: str = "execution reverted") -> ExecutionResult:
    return ExecutionResult(
        execution_id=execution_id, status="failed", transaction_hash=None, transaction_link=None, error=error, raw={}
    )


def execution_unconfirmed(execution_id: str = "exec-1") -> ExecutionResult:
    return ExecutionResult(
        execution_id=execution_id, status="unconfirmed", transaction_hash=None, transaction_link=None, error=None, raw={}
    )
