"""Post-execution verification.

After AutonomousEngine executes a deleverage ActionBundle, it re-reads the
position and asks one question: did the position actually move in the
expected direction? This module never requires an exact target health
factor -- market prices and accrued interest move between compile time and
confirmation, so the bar is directional, not exact, matching the real
observed result in DELEVA_TRANSACTION_PROOF.md (debt fell by ~$10, health
factor rose from 2.0795 to 12.454 -- nowhere near the compiled target_hf of
1.50, and that is still a fully successful, verified result).
"""

from __future__ import annotations

from dataclasses import dataclass

from deleva.models import Position


@dataclass(frozen=True)
class VerificationResult:
    success: bool
    debt_decreased: bool | None
    health_factor_improved: bool | None
    reason: str

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "debt_decreased": self.debt_decreased,
            "health_factor_improved": self.health_factor_improved,
            "reason": self.reason,
        }


def verify_deleverage(position_before: Position, position_after: Position) -> VerificationResult:
    """Verify a deleverage action had the expected directional effect.

    Primary signal: debt_usd must have decreased. Health-factor improvement
    is recorded as supporting evidence but is not independently required --
    debt reduction is the thing DELEVA actually did; health factor is a
    downstream consequence that also depends on collateral price, which
    DELEVA does not control.

    Never fabricates success: if either position is missing the fields
    needed to compare, the result is explicitly inconclusive.
    """
    if position_before.debt_usd is None or position_after.debt_usd is None:
        return VerificationResult(
            success=False,
            debt_decreased=None,
            health_factor_improved=None,
            reason="Cannot verify: debt_usd was not retrievable on one or both position reads.",
        )

    debt_decreased = position_after.debt_usd < position_before.debt_usd

    health_factor_improved: bool | None = None
    if position_before.health_factor is not None and position_after.health_factor is not None:
        health_factor_improved = position_after.health_factor > position_before.health_factor

    if not debt_decreased:
        return VerificationResult(
            success=False,
            debt_decreased=False,
            health_factor_improved=health_factor_improved,
            reason=(
                f"Debt did not decrease: before={position_before.debt_usd} after={position_after.debt_usd}. "
                "Execution reported success but had no verifiable effect -- treating as a verification failure."
            ),
        )

    return VerificationResult(
        success=True,
        debt_decreased=True,
        health_factor_improved=health_factor_improved,
        reason=(
            f"Debt decreased from {position_before.debt_usd} to {position_after.debt_usd}"
            + (
                f"; health factor moved from {position_before.health_factor} to {position_after.health_factor}"
                if health_factor_improved is not None
                else ""
            )
        ),
    )
