"""Structured activity/audit model for DELEVA.

An ``ActivityLog`` is an ordered, appendable record of what actually
happened -- position reads, Almanak intents, KeeperHub simulations and
executions, confirmations, failures. Phase 2's autonomous loop appends to
this as it runs. Phase 1 seeds it with exactly one real sequence of events:
the actual, already-proven DELEVA transaction
(0xd36217b09ba81cea624e88e756514f2ebc0dc689a20dad4286d6f852f205ec57, Base
block 51,395,399 -- see ../DELEVA_TRANSACTION_PROOF.md). No other event is
fabricated.

Important honesty note (see ``real_deleva_proof_events`` docstring): the real
proof run's health factor was 2.0795, comfortably above the configured 1.50
trigger threshold. It was a manually-invoked demonstration of the execution
path, not an autonomous threshold breach. Accordingly there is no
RISK_THRESHOLD_BREACHED event in the seed data -- including one would
misrepresent what actually happened.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum


class ActivityEventType(str, Enum):
    POSITION_EVALUATED = "POSITION_EVALUATED"
    RISK_THRESHOLD_BREACHED = "RISK_THRESHOLD_BREACHED"
    ALMANAK_INTENT_CREATED = "ALMANAK_INTENT_CREATED"
    ACTION_BUNDLE_COMPILED = "ACTION_BUNDLE_COMPILED"
    KEEPERHUB_SIMULATION = "KEEPERHUB_SIMULATION"
    KEEPERHUB_EXECUTION = "KEEPERHUB_EXECUTION"
    TRANSACTION_CONFIRMED = "TRANSACTION_CONFIRMED"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    #: Added in Phase 2: Phase 1 proved the execution path but did not
    #: implement post-execution verification (see deleva.verification).
    #: Recorded after AutonomousEngine re-reads the position and compares
    #: it against the pre-action snapshot.
    POSITION_VERIFIED = "POSITION_VERIFIED"


@dataclass(frozen=True)
class ActivityEvent:
    event_type: ActivityEventType
    timestamp: datetime
    description: str
    health_factor: Decimal | None = None
    strategy: str | None = None
    execution_id: str | None = None
    transaction_hash: str | None = None
    status: str | None = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "description": self.description,
            "health_factor": str(self.health_factor) if self.health_factor is not None else None,
            "strategy": self.strategy,
            "execution_id": self.execution_id,
            "transaction_hash": self.transaction_hash,
            "status": self.status,
            "metadata": self.metadata,
        }


class ActivityLog:
    """An ordered, in-memory, appendable activity record.

    Deliberately the simplest possible implementation for Phase 1 -- an
    in-memory list. Phase 2 can swap this for a persisted store behind the
    same ``append``/``all`` interface without touching callers.
    """

    def __init__(self, events: list[ActivityEvent] | None = None) -> None:
        self._events: list[ActivityEvent] = list(events or [])

    def append(self, event: ActivityEvent) -> None:
        self._events.append(event)

    def all(self) -> list[ActivityEvent]:
        return list(self._events)

    def to_dict_list(self) -> list[dict]:
        return [event.to_dict() for event in self._events]


# --- The real, already-proven DELEVA execution, as an activity sequence ----
# Every value below is copied verbatim from DELEVA_TRANSACTION_PROOF.md.
# Timestamps are approximate to the recorded execution window (KeeperHub's
# own execution status reported completedAt "2026-09-16T17:35:48.174Z" for
# the repay); nothing here is invented data.

_PROOF_STRATEGY_NAME = "aave-v3-base-deleverage"
_PROOF_WALLET = "0x02168b0be574a884bAe550F3D6b9F080670f8f7F"
_PROOF_OBSERVED_HF = Decimal("2.0795")
_PROOF_REPAY_TX_HASH = "0xd36217b09ba81cea624e88e756514f2ebc0dc689a20dad4286d6f852f205ec57"
_PROOF_APPROVE_TX_HASH = "0x12db82010410feb4339c41523ede3801968b5d51c50d4cf7047d880203ea011f"
_PROOF_REPAY_EXECUTION_ID = "za25idtoxl42mtyfjmbks"
_PROOF_APPROVE_EXECUTION_ID = "q5t9cuj4qhsjcaex69eeh"


def real_deleva_proof_events() -> list[ActivityEvent]:
    """The real, verified activity sequence for the one DELEVA execution performed so far.

    Deliberately does NOT include a RISK_THRESHOLD_BREACHED event: the real
    position's health factor (2.0795) was above the configured 1.50 trigger
    threshold at the time. This was a manually-invoked demonstration of the
    real execution path, not an autonomous trigger -- representing it as a
    threshold breach would be a fabrication. Phase 2's autonomous loop will
    be able to produce a genuine RISK_THRESHOLD_BREACHED event once it
    actually observes health_factor < trigger_threshold.
    """
    ts = datetime(2026, 9, 16, 17, 35, 43, tzinfo=timezone.utc)

    return [
        ActivityEvent(
            event_type=ActivityEventType.POSITION_EVALUATED,
            timestamp=ts,
            description=(
                "Read live Aave V3 Base position for the KeeperHub organization wallet. "
                "Health factor 2.0795 was above the 1.50 trigger threshold -- this run was "
                "manually invoked to demonstrate the execution path, not an autonomous trigger."
            ),
            health_factor=_PROOF_OBSERVED_HF,
            strategy=_PROOF_STRATEGY_NAME,
            metadata={"wallet": _PROOF_WALLET},
        ),
        ActivityEvent(
            event_type=ActivityEventType.ALMANAK_INTENT_CREATED,
            timestamp=ts,
            description=(
                "Compiled a real DeleverageIntent(protocol=aave_v3, token=USDC, amount=10, "
                "repay_full=False, chain=base) via the real, installed Almanak IntentCompiler."
            ),
            health_factor=_PROOF_OBSERVED_HF,
            strategy=_PROOF_STRATEGY_NAME,
        ),
        ActivityEvent(
            event_type=ActivityEventType.ACTION_BUNDLE_COMPILED,
            timestamp=ts,
            description=(
                "Real ActionBundle (intent_type=REPAY) compiled to 2 transactions: "
                "USDC approve(Pool, 11 USDC), Aave V3 repay(USDC, 10 USDC, mode=2, "
                "onBehalfOf=organization wallet)."
            ),
            strategy=_PROOF_STRATEGY_NAME,
        ),
        ActivityEvent(
            event_type=ActivityEventType.KEEPERHUB_SIMULATION,
            timestamp=ts,
            description=(
                "Simulated both legs via KeeperHub (simulate: true). Approve leg: "
                "wouldRevert=false. Repay leg simulated before the approve landed correctly "
                "reverted (insufficient allowance, expected sequencing); re-simulated after "
                "the approve was confirmed: wouldRevert=false, gasEstimate=160745."
            ),
            strategy=_PROOF_STRATEGY_NAME,
            status="simulated",
        ),
        ActivityEvent(
            event_type=ActivityEventType.KEEPERHUB_EXECUTION,
            timestamp=ts,
            description="Broadcast leg 1 (USDC approve) via KeeperHub with a fresh idempotency key.",
            strategy=_PROOF_STRATEGY_NAME,
            execution_id=_PROOF_APPROVE_EXECUTION_ID,
            transaction_hash=_PROOF_APPROVE_TX_HASH,
            status="completed",
        ),
        ActivityEvent(
            event_type=ActivityEventType.KEEPERHUB_EXECUTION,
            timestamp=ts,
            description="Broadcast leg 2 (10 USDC Aave V3 repay) via KeeperHub with a fresh idempotency key.",
            strategy=_PROOF_STRATEGY_NAME,
            execution_id=_PROOF_REPAY_EXECUTION_ID,
            transaction_hash=_PROOF_REPAY_TX_HASH,
            status="completed",
        ),
        ActivityEvent(
            event_type=ActivityEventType.TRANSACTION_CONFIRMED,
            timestamp=datetime(2026, 9, 16, 17, 35, 48, tzinfo=timezone.utc),
            description=(
                "Base mainnet confirmation: block 51,395,399, receiptStatus=success, "
                "gasUsed=184531. Aave V3 debt reduced from $11.9985 to $1.9998; health factor "
                "rose from 2.0795 to 12.454."
            ),
            strategy=_PROOF_STRATEGY_NAME,
            execution_id=_PROOF_REPAY_EXECUTION_ID,
            transaction_hash=_PROOF_REPAY_TX_HASH,
            status="success",
            metadata={"block_number": 51_395_399, "gas_used": "184531"},
        ),
    ]
