from __future__ import annotations

from decimal import Decimal

import pytest

from deleva.models import AAVE_MAX_UINT256, Position, RiskState, normalize_health_factor
from deleva.risk import InvalidHealthFactorError, RiskEvaluator


@pytest.fixture
def evaluator() -> RiskEvaluator:
    return RiskEvaluator(trigger_threshold=Decimal("1.50"))


class TestHealthyPosition:
    def test_health_factor_well_above_threshold_is_healthy(self, evaluator):
        assert evaluator.evaluate_health_factor(Decimal("2.0795")) == RiskState.HEALTHY

    def test_real_recorded_before_state_is_healthy(self, evaluator):
        # The real proof run's actual starting HF -- confirms it was genuinely
        # healthy, not an autonomous breach (see deleva.activity docstring).
        assert evaluator.evaluate_health_factor(Decimal("2.0795")) == RiskState.HEALTHY

    def test_aave_no_debt_sentinel_is_healthy(self, evaluator):
        normalized = normalize_health_factor(AAVE_MAX_UINT256)
        assert evaluator.evaluate_health_factor(normalized) == RiskState.HEALTHY


class TestThresholdBreach:
    def test_health_factor_below_threshold_is_breached(self, evaluator):
        assert evaluator.evaluate_health_factor(Decimal("1.08")) == RiskState.THRESHOLD_BREACHED

    def test_health_factor_just_below_threshold_is_breached(self, evaluator):
        assert evaluator.evaluate_health_factor(Decimal("1.4999")) == RiskState.THRESHOLD_BREACHED


class TestExactThresholdBehavior:
    def test_health_factor_exactly_at_threshold_is_healthy(self, evaluator):
        # Spec: "health_factor >= trigger_threshold -> HEALTHY" (inclusive).
        assert evaluator.evaluate_health_factor(Decimal("1.50")) == RiskState.HEALTHY


class TestRawValueNormalizationIsRequired:
    def test_raw_uint256_must_be_normalized_before_evaluation(self, evaluator):
        # This is the exact failure mode the task warned about: comparing a
        # raw 1e18-scaled value against a human threshold is meaningless
        # unless normalized first. Demonstrate the correct path.
        raw_onchain_value = 1_500_000_000_000_000_000  # == 1.5 once normalized
        normalized = normalize_health_factor(raw_onchain_value)
        assert normalized == Decimal("1.5")
        assert evaluator.evaluate_health_factor(normalized) == RiskState.HEALTHY


class TestMalformedValues:
    def test_none_health_factor_is_unknown_not_healthy(self, evaluator):
        assert evaluator.evaluate_health_factor(None) == RiskState.UNKNOWN

    def test_non_numeric_string_raises(self, evaluator):
        with pytest.raises(InvalidHealthFactorError):
            evaluator.evaluate_health_factor("not-a-number")

    def test_negative_health_factor_raises(self, evaluator):
        with pytest.raises(InvalidHealthFactorError):
            evaluator.evaluate_health_factor(Decimal("-1"))


class TestEvaluatePosition:
    def test_evaluate_reads_position_health_factor(self, evaluator):
        position = Position.from_aave_account_data(
            wallet="0xabc",
            chain="base",
            raw={
                "totalCollateralBase": "3000602397",
                "totalDebtBase": "199975914",
                "availableBorrowsBase": "2200506003",
                "currentLiquidationThreshold": "8300",
                "ltv": "8000",
                "healthFactor": "12453999782743835840",
            },
        )
        assert evaluator.evaluate(position) == RiskState.HEALTHY

    def test_evaluate_position_with_unretrieved_health_factor_is_unknown(self, evaluator):
        position = Position.from_aave_account_data(wallet="0xabc", chain="base", raw={})
        assert evaluator.evaluate(position) == RiskState.UNKNOWN
