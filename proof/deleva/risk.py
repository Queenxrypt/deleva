"""Deterministic risk-state evaluation.

This module answers exactly one question -- "what is the current risk
state?" -- and does nothing else. It never reads chain state, never calls
Almanak or KeeperHub, and never executes anything. Phase 2's autonomous loop
calls this after reading a Position and before deciding whether to act.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from deleva.models import Position, RiskState


class InvalidHealthFactorError(ValueError):
    """Raised when a health factor value is present but not a valid number."""


@dataclass(frozen=True)
class RiskEvaluator:
    """Evaluates a Position's health factor against a configured trigger threshold.

    Matches Aave's own convention: a health factor at or above the threshold
    is healthy; strictly below it is breached. The boundary is inclusive on
    the healthy side (health_factor == threshold -> HEALTHY), matching the
    spec this was built against.
    """

    trigger_threshold: Decimal

    def evaluate_health_factor(self, health_factor: Decimal | int | str | None) -> RiskState:
        if health_factor is None:
            return RiskState.UNKNOWN

        if isinstance(health_factor, Decimal):
            hf = health_factor
        else:
            try:
                hf = Decimal(health_factor)
            except (InvalidOperation, TypeError, ValueError) as exc:
                raise InvalidHealthFactorError(
                    f"health_factor={health_factor!r} is not a valid number. "
                    "If this came from a raw on-chain read, it must be normalized "
                    "with deleva.models.normalize_health_factor() first."
                ) from exc

        if hf < 0:
            raise InvalidHealthFactorError(f"health_factor={hf} cannot be negative")

        if hf < self.trigger_threshold:
            return RiskState.THRESHOLD_BREACHED
        return RiskState.HEALTHY

    def evaluate(self, position: Position) -> RiskState:
        return self.evaluate_health_factor(position.health_factor)
