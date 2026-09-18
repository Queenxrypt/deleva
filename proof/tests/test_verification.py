from __future__ import annotations

from decimal import Decimal

from fakes import make_position

from deleva.verification import verify_deleverage


class TestVerifyDeleverage:
    def test_debt_decreased_is_success(self):
        before = make_position(health_factor=Decimal("1.49"), debt_usd=Decimal("12.00"))
        after = make_position(health_factor=Decimal("2.10"), debt_usd=Decimal("2.00"))
        result = verify_deleverage(before, after)
        assert result.success is True
        assert result.debt_decreased is True
        assert result.health_factor_improved is True

    def test_real_proof_values_verify_as_success(self):
        # The real recorded before/after debt from DELEVA_TRANSACTION_PROOF.md.
        before = make_position(health_factor=Decimal("2.0795"), debt_usd=Decimal("11.9985"))
        after = make_position(health_factor=Decimal("12.454"), debt_usd=Decimal("1.9998"))
        result = verify_deleverage(before, after)
        assert result.success is True
        # Note: health factor massively overshoots the compiled target_hf of
        # 1.50 -- still a fully successful, verified result (see module
        # docstring: the bar is directional, not an exact target).

    def test_debt_unchanged_is_verification_failure(self):
        before = make_position(health_factor=Decimal("1.20"), debt_usd=Decimal("12.00"))
        after = make_position(health_factor=Decimal("1.20"), debt_usd=Decimal("12.00"))
        result = verify_deleverage(before, after)
        assert result.success is False
        assert result.debt_decreased is False

    def test_debt_increased_is_verification_failure(self):
        before = make_position(health_factor=Decimal("1.20"), debt_usd=Decimal("12.00"))
        after = make_position(health_factor=Decimal("1.10"), debt_usd=Decimal("13.00"))
        result = verify_deleverage(before, after)
        assert result.success is False
        assert result.debt_decreased is False

    def test_missing_debt_data_is_inconclusive_not_fabricated_success(self):
        from dataclasses import replace

        before = make_position(health_factor=Decimal("1.20"), debt_usd=Decimal("12.00"))
        after_missing_debt = replace(before, health_factor=Decimal("2.0"), debt_usd=None)

        result = verify_deleverage(before, after_missing_debt)

        assert result.success is False
        assert result.debt_decreased is None
        assert "Cannot verify" in result.reason
