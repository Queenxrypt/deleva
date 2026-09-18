from __future__ import annotations

from decimal import Decimal

from deleva.models import (
    AAVE_MAX_UINT256,
    Position,
    normalize_base_currency,
    normalize_bps,
    normalize_health_factor,
)


class TestNormalizeHealthFactor:
    def test_raw_1e18_value_normalizes_to_expected_decimal(self):
        # The exact example from the task: do not compare a raw uint256
        # against a human threshold without this conversion.
        assert normalize_health_factor(1_500_000_000_000_000_000) == Decimal("1.5")

    def test_raw_string_value_also_works(self):
        assert normalize_health_factor("1500000000000000000") == Decimal("1.5")

    def test_real_recorded_after_state_value(self):
        # From DELEVA_TRANSACTION_PROOF.md's real AFTER read.
        assert normalize_health_factor("12453999782743835840") == Decimal("12.45399978274383584")

    def test_aave_no_debt_sentinel_normalizes_to_a_huge_but_valid_decimal(self):
        # Confirmed live on-chain before the real position had any debt
        # (see the Phase 2 funding-verification session): healthFactor comes
        # back as type(uint256).max when totalDebtBase == 0.
        normalized = normalize_health_factor(AAVE_MAX_UINT256)
        assert normalized > Decimal("1.5")


class TestNormalizeBaseCurrency:
    def test_real_recorded_collateral_value(self):
        # From DELEVA_TRANSACTION_PROOF.md's real BEFORE read.
        assert normalize_base_currency("3006106093") == Decimal("30.06106093")

    def test_real_recorded_debt_value(self):
        assert normalize_base_currency("1199848584") == Decimal("11.99848584")


class TestNormalizeBps:
    def test_liquidation_threshold_8300_bps(self):
        assert normalize_bps("8300") == Decimal("0.83")

    def test_ltv_8000_bps(self):
        assert normalize_bps("8000") == Decimal("0.80")


class TestPositionFromAaveAccountData:
    REAL_AFTER_STATE = {
        "totalCollateralBase": "3000602397",
        "totalDebtBase": "199975914",
        "availableBorrowsBase": "2200506003",
        "currentLiquidationThreshold": "8300",
        "ltv": "8000",
        "healthFactor": "12453999782743835840",
    }

    def test_parses_real_recorded_position_correctly(self):
        position = Position.from_aave_account_data(
            wallet="0x02168b0be574a884bAe550F3D6b9F080670f8f7F",
            chain="base",
            raw=self.REAL_AFTER_STATE,
        )
        assert position.collateral_usd == Decimal("30.00602397")
        assert position.debt_usd == Decimal("1.99975914")
        assert position.available_borrows_usd == Decimal("22.00506003")
        assert position.liquidation_threshold == Decimal("0.83")
        assert position.ltv == Decimal("0.80")
        assert position.health_factor == Decimal("12.45399978274383584")
        assert position.protocol == "aave_v3"
        assert position.wallet == "0x02168b0be574a884bAe550F3D6b9F080670f8f7F"

    def test_missing_field_is_none_not_fabricated_zero(self):
        incomplete = dict(self.REAL_AFTER_STATE)
        del incomplete["availableBorrowsBase"]
        position = Position.from_aave_account_data(wallet="0xabc", chain="base", raw=incomplete)
        assert position.available_borrows_usd is None
        # Everything else still parses.
        assert position.debt_usd == Decimal("1.99975914")

    def test_empty_raw_dict_yields_all_none_fields(self):
        position = Position.from_aave_account_data(wallet="0xabc", chain="base", raw={})
        assert position.health_factor is None
        assert position.collateral_usd is None
        assert position.debt_usd is None
        assert position.available_borrows_usd is None
        assert position.ltv is None
        assert position.liquidation_threshold is None

    def test_to_dict_serializes_decimals_as_strings(self):
        position = Position.from_aave_account_data(
            wallet="0x02168b0be574a884bAe550F3D6b9F080670f8f7F", chain="base", raw=self.REAL_AFTER_STATE
        )
        as_dict = position.to_dict()
        assert as_dict["health_factor"] == "12.45399978274383584"
        assert as_dict["collateral_usd"] == "30.00602397"
        assert isinstance(as_dict["timestamp"], str)
