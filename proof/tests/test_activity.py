from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from deleva.activity import (
    ActivityEvent,
    ActivityEventType,
    ActivityLog,
    real_deleva_proof_events,
)

REAL_PROOF_TX_HASH = "0xd36217b09ba81cea624e88e756514f2ebc0dc689a20dad4286d6f852f205ec57"


class TestActivityEvent:
    def test_to_dict_serializes_all_fields(self):
        event = ActivityEvent(
            event_type=ActivityEventType.POSITION_EVALUATED,
            timestamp=datetime(2026, 9, 16, 17, 35, 43, tzinfo=timezone.utc),
            description="test",
            health_factor=Decimal("2.08"),
            strategy="aave-v3-base-deleverage",
        )
        as_dict = event.to_dict()
        assert as_dict["event_type"] == "POSITION_EVALUATED"
        assert as_dict["health_factor"] == "2.08"
        assert as_dict["strategy"] == "aave-v3-base-deleverage"
        assert as_dict["timestamp"] == "2026-09-16T17:35:43+00:00"

    def test_optional_fields_default_to_none_or_empty(self):
        event = ActivityEvent(
            event_type=ActivityEventType.EXECUTION_FAILED,
            timestamp=datetime.now(timezone.utc),
            description="test",
        )
        assert event.health_factor is None
        assert event.execution_id is None
        assert event.transaction_hash is None
        assert event.metadata == {}


class TestActivityLog:
    def test_append_and_all(self):
        log = ActivityLog()
        event = ActivityEvent(
            event_type=ActivityEventType.POSITION_EVALUATED, timestamp=datetime.now(timezone.utc), description="x"
        )
        log.append(event)
        assert log.all() == [event]

    def test_seeded_with_initial_events(self):
        seed = [
            ActivityEvent(
                event_type=ActivityEventType.POSITION_EVALUATED, timestamp=datetime.now(timezone.utc), description="x"
            )
        ]
        log = ActivityLog(seed)
        assert log.all() == seed

    def test_to_dict_list(self):
        log = ActivityLog(
            [
                ActivityEvent(
                    event_type=ActivityEventType.POSITION_EVALUATED,
                    timestamp=datetime.now(timezone.utc),
                    description="x",
                )
            ]
        )
        as_list = log.to_dict_list()
        assert len(as_list) == 1
        assert as_list[0]["event_type"] == "POSITION_EVALUATED"

    def test_all_returns_a_copy_not_the_internal_list(self):
        log = ActivityLog()
        returned = log.all()
        returned.append("tampered")  # type: ignore[arg-type]
        assert log.all() == []


class TestRealDelevaProofEvents:
    """These tests pin the seed data to the real, verified proof -- any
    accidental drift back toward fabricated or substitute transaction data
    (e.g. the earlier WETH feasibility tx) fails here."""

    def test_returns_a_non_empty_real_sequence(self):
        events = real_deleva_proof_events()
        assert len(events) > 0

    def test_first_event_is_position_evaluated_with_real_health_factor(self):
        events = real_deleva_proof_events()
        assert events[0].event_type == ActivityEventType.POSITION_EVALUATED
        assert events[0].health_factor == Decimal("2.0795")

    def test_last_event_is_transaction_confirmed_with_the_real_proof_hash(self):
        events = real_deleva_proof_events()
        last = events[-1]
        assert last.event_type == ActivityEventType.TRANSACTION_CONFIRMED
        assert last.transaction_hash == REAL_PROOF_TX_HASH
        assert last.metadata["block_number"] == 51_395_399

    def test_no_risk_threshold_breached_event_is_fabricated(self):
        # The real HF (2.0795) was above the 1.50 trigger threshold -- this
        # was a manual demonstration, not an autonomous breach. Representing
        # it as a breach would misstate what actually happened.
        events = real_deleva_proof_events()
        event_types = {event.event_type for event in events}
        assert ActivityEventType.RISK_THRESHOLD_BREACHED not in event_types

    def test_every_execution_event_references_the_real_proof_hashes(self):
        events = real_deleva_proof_events()
        tx_hashes = {event.transaction_hash for event in events if event.transaction_hash}
        assert tx_hashes.issubset(
            {
                REAL_PROOF_TX_HASH,
                "0x12db82010410feb4339c41523ede3801968b5d51c50d4cf7047d880203ea011f",
            }
        )
        # The old WETH feasibility transaction must never appear here.
        assert not any("weth" in (h or "").lower() for h in tx_hashes)

    def test_events_are_chronologically_ordered(self):
        events = real_deleva_proof_events()
        timestamps = [event.timestamp for event in events]
        assert timestamps == sorted(timestamps)
