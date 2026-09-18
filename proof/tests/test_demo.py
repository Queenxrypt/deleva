from __future__ import annotations

from decimal import Decimal

from deleva.activity import ActivityEventType
from deleva.execution_mode import ExecutionMode
from deleva.models import RiskState

from deleva.demo import run_local_demo

REAL_PROOF_TX_HASH = "0xd36217b09ba81cea624e88e756514f2ebc0dc689a20dad4286d6f852f205ec57"


class TestLocalDemo:
    def test_produces_exactly_three_cycles(self):
        results = run_local_demo()
        assert len(results) == 3

    def test_cycle_1_is_healthy_no_action(self):
        results = run_local_demo()
        assert results[0].risk_state == RiskState.HEALTHY
        assert results[0].triggered is False
        assert results[0].action_taken is False

    def test_cycle_2_is_breached_and_triggers_full_pipeline(self):
        results = run_local_demo()
        cycle2 = results[1]
        assert cycle2.risk_state == RiskState.THRESHOLD_BREACHED
        assert cycle2.triggered is True
        assert cycle2.action_taken is True
        assert cycle2.overall_success is True
        assert cycle2.verification is not None
        assert cycle2.verification.success is True

        event_types = [e.event_type for e in cycle2.activity_events]
        assert ActivityEventType.RISK_THRESHOLD_BREACHED in event_types
        assert ActivityEventType.ALMANAK_INTENT_CREATED in event_types
        assert ActivityEventType.ACTION_BUNDLE_COMPILED in event_types
        assert ActivityEventType.KEEPERHUB_SIMULATION in event_types
        assert ActivityEventType.KEEPERHUB_EXECUTION in event_types
        assert ActivityEventType.TRANSACTION_CONFIRMED in event_types
        assert ActivityEventType.POSITION_VERIFIED in event_types

    def test_cycle_3_is_healthy_no_action(self):
        results = run_local_demo()
        assert results[2].risk_state == RiskState.HEALTHY
        assert results[2].triggered is False

    def test_demo_uses_a_real_almanak_compiled_action_bundle(self):
        # The one real component this demo exercises: the ActionBundle is
        # genuinely compiled by the real Almanak SDK, not fabricated.
        results = run_local_demo()
        bundle = results[1].action_bundle
        assert bundle is not None
        assert bundle.intent_type == "REPAY"
        assert len(bundle.transactions) == 2
        assert bundle.transactions[1]["data"][:10] == "0x573ade81"  # real repay selector

    def test_demo_transaction_hashes_are_never_shaped_like_real_ones(self):
        results = run_local_demo()
        for result in results:
            for leg in result.leg_results:
                if leg.execution is not None and leg.execution.transaction_hash:
                    assert leg.execution.transaction_hash.startswith("0xDEMO")
                    assert leg.execution.transaction_hash != REAL_PROOF_TX_HASH

    def test_demo_never_produces_the_real_proof_hash(self):
        results = run_local_demo()
        all_hashes = {
            leg.execution.transaction_hash
            for result in results
            for leg in result.leg_results
            if leg.execution is not None
        }
        assert REAL_PROOF_TX_HASH not in all_hashes

    def test_demo_cycles_report_demo_execution_mode_not_live(self):
        # Regression test: the demo engine used to be constructed with
        # ExecutionMode.LIVE (control-flow-correct, since it needed to reach
        # the execute path against DemoKeeperHubClient, but a misleading
        # label -- a demo cycle must never claim it was a real LIVE
        # execution). See deleva/execution_mode.py::ExecutionMode.DEMO.
        results = run_local_demo()
        for result in results:
            assert result.execution_mode is ExecutionMode.DEMO
            assert result.execution_mode is not ExecutionMode.LIVE
