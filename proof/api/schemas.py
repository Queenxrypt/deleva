"""Pydantic response models + the small, presentation-only formatting
helpers that shape them from real deleva objects. No strategy constants,
risk thresholds, or KeeperHub/Almanak logic are duplicated here -- every
value originates from an existing deleva model/service; this module only
renders it as JSON.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel

from deleva.activity import ActivityEvent
from deleva.engine import CycleResult
from deleva.models import Position
from deleva.strategy import DelevaStrategy

# Presentation-only display names. Not business logic -- changing these
# changes nothing about what DELEVA does, only how it's labeled.
_PROTOCOL_DISPLAY = {"aave_v3": "Aave V3"}
_CHAIN_DISPLAY = {"base": "Base"}
_LAYER_DISPLAY = {"almanak": "Almanak", "keeperhub": "KeeperHub"}
_ACTION_DISPLAY = {"deleverage": "Deleverage"}
_CHAIN_ID_TO_EXPLORER = {8453: "https://basescan.org"}

REAL_PROOF_TX_HASH = "0xd36217b09ba81cea624e88e756514f2ebc0dc689a20dad4286d6f852f205ec57"


def _decimal_str(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def explorer_tx_url(tx_hash: str, chain_id: int = 8453) -> str | None:
    base = _CHAIN_ID_TO_EXPLORER.get(chain_id)
    return f"{base}/tx/{tx_hash}" if base else None


# --- health -----------------------------------------------------------------


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


# --- position -----------------------------------------------------------


class PositionData(BaseModel):
    wallet: str
    chain: str
    chain_display: str
    protocol: str
    protocol_display: str
    collateral_usd: str | None
    debt_usd: str | None
    available_borrows_usd: str | None
    health_factor: str | None
    ltv: str | None
    liquidation_threshold: str | None
    usdc_balance: str | None
    timestamp: str


class PositionResponse(BaseModel):
    available: bool
    #: "live" only when a real position was actually retrieved this call.
    #: None when unavailable -- never fabricated, and never left defaulted
    #: to "live" for a response that carries no real data (see
    #: position_unavailable() below).
    source: Literal["live"] | None = None
    reason: str | None = None
    data: PositionData | None = None
    note: str | None = (
        "collateral_usd/debt_usd are Aave's own protocol-level base-currency values "
        "(the real read this position uses is account-level, not per-asset) -- "
        "per-asset token amounts (e.g. exact WETH supplied) are not exposed."
    )


def position_to_response(position: Position, usdc_balance: Decimal | None) -> PositionResponse:
    return PositionResponse(
        available=True,
        source="live",
        data=PositionData(
            wallet=position.wallet,
            chain=position.chain,
            chain_display=_CHAIN_DISPLAY.get(position.chain, position.chain),
            protocol=position.protocol,
            protocol_display=_PROTOCOL_DISPLAY.get(position.protocol, position.protocol),
            collateral_usd=_decimal_str(position.collateral_usd),
            debt_usd=_decimal_str(position.debt_usd),
            available_borrows_usd=_decimal_str(position.available_borrows_usd),
            health_factor=_decimal_str(position.health_factor),
            ltv=_decimal_str(position.ltv),
            liquidation_threshold=_decimal_str(position.liquidation_threshold),
            usdc_balance=_decimal_str(usdc_balance),
            timestamp=position.timestamp.isoformat(),
        ),
    )


def position_unavailable(reason: str) -> PositionResponse:
    return PositionResponse(available=False, reason=reason, data=None)


# --- strategy -----------------------------------------------------------


class StrategyResponse(BaseModel):
    name: str
    protocol: str
    protocol_display: str
    chain: str
    chain_display: str
    trigger: str
    trigger_health_factor: str
    target_health_factor: str
    action: str
    decision_engine: str
    execution_layer: str


def strategy_to_response(strategy: DelevaStrategy) -> StrategyResponse:
    return StrategyResponse(
        name=strategy.name,
        protocol=strategy.protocol,
        protocol_display=_PROTOCOL_DISPLAY.get(strategy.protocol, strategy.protocol),
        chain=strategy.chain,
        chain_display=_CHAIN_DISPLAY.get(strategy.chain, strategy.chain),
        trigger=f"health_factor < {strategy.trigger_health_factor}",
        trigger_health_factor=str(strategy.trigger_health_factor),
        target_health_factor=str(strategy.target_health_factor),
        action=_ACTION_DISPLAY.get(strategy.action, strategy.action),
        decision_engine=_LAYER_DISPLAY.get(strategy.decision_layer, strategy.decision_layer),
        execution_layer=_LAYER_DISPLAY.get(strategy.execution_layer, strategy.execution_layer),
    )


# --- engine status --------------------------------------------------------


class LegResultSummary(BaseModel):
    tx_type: str
    simulated: bool
    simulation_success: bool | None
    would_revert: bool | None
    executed: bool
    execution_status: str | None
    transaction_hash: str | None
    transaction_link: str | None


class CycleResultSummary(BaseModel):
    engine_state: str
    risk_state: str
    execution_mode: str
    triggered: bool
    action_taken: bool
    overall_success: bool
    skipped_reason: str | None
    error: str | None
    legs: list[LegResultSummary]
    verification_success: bool | None
    verification_reason: str | None


def cycle_result_to_summary(result: CycleResult) -> CycleResultSummary:
    legs = [
        LegResultSummary(
            tx_type=leg.tx_type,
            simulated=leg.simulation is not None,
            simulation_success=leg.simulation.success if leg.simulation else None,
            would_revert=leg.simulation.would_revert if leg.simulation else None,
            executed=leg.execution is not None,
            execution_status=leg.execution.status if leg.execution else None,
            transaction_hash=leg.execution.transaction_hash if leg.execution else None,
            transaction_link=(
                explorer_tx_url(leg.execution.transaction_hash)
                if leg.execution and leg.execution.transaction_hash
                else None
            ),
        )
        for leg in result.leg_results
    ]
    return CycleResultSummary(
        engine_state=result.engine_state.value,
        risk_state=result.risk_state.value,
        execution_mode=result.execution_mode.value,
        triggered=result.triggered,
        action_taken=result.action_taken,
        overall_success=result.overall_success,
        skipped_reason=result.skipped_reason,
        error=result.error,
        legs=legs,
        verification_success=result.verification.success if result.verification else None,
        verification_reason=result.verification.reason if result.verification else None,
    )


class EngineStatusResponse(BaseModel):
    configured: bool
    configuration_error: str | None
    container_state: str | None
    engine_state: str | None
    execution_mode: str | None
    pending_execution_id: str | None
    monitoring_interval_seconds: int | None
    last_cycle: CycleResultSummary | None = None
    #: Set only while the background loop is RUNNING and its most recent
    #: cycle raised an unexpected exception (e.g. a transient KeeperHub/
    #: network failure) -- the loop keeps running and will retry on its next
    #: scheduled cycle; this clears as soon as a cycle succeeds. None means
    #: either the loop isn't running, or its last cycle was clean.
    runner_error: str | None = None


# --- activity -----------------------------------------------------------

ActivitySource = Literal["live", "demo", "historical_proof"]


class ActivityEventResponse(BaseModel):
    event_type: str
    timestamp: str
    description: str
    health_factor: str | None
    strategy: str | None
    execution_id: str | None
    transaction_hash: str | None
    transaction_link: str | None
    status: str | None
    source: ActivitySource


def activity_event_to_response(event: ActivityEvent, *, source: ActivitySource) -> ActivityEventResponse:
    return ActivityEventResponse(
        event_type=event.event_type.value,
        timestamp=event.timestamp.isoformat(),
        description=event.description,
        health_factor=_decimal_str(event.health_factor),
        strategy=event.strategy,
        execution_id=event.execution_id,
        transaction_hash=event.transaction_hash,
        transaction_link=explorer_tx_url(event.transaction_hash) if event.transaction_hash else None,
        status=event.status,
        source=source,
    )


class ActivityResponse(BaseModel):
    events: list[ActivityEventResponse]
    real_proof_transaction_hash: str = REAL_PROOF_TX_HASH
    real_proof_transaction_link: str = explorer_tx_url(REAL_PROOF_TX_HASH) or ""


# --- demo -----------------------------------------------------------------


class DemoCycleResponse(BaseModel):
    cycle_number: int
    summary: CycleResultSummary
    events: list[ActivityEventResponse]


class DemoRunResponse(BaseModel):
    mode: Literal["demo"] = "demo"
    note: str = "Deterministic local demonstration. No network call is made; no real transaction is broadcast."
    cycles: list[DemoCycleResponse]
