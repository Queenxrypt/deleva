"""Normalized internal models shared across DELEVA's backend components.

These types are the contract between the position service, the risk
evaluator, the strategy layer, and (eventually, in Phase 2) the autonomous
loop. Nothing in this module makes a network call or invents a value: fields
that cannot currently be retrieved reliably are ``None``, not a fabricated
zero.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum


# Aave V3's getUserAccountData() encodes collateral/debt/available-borrows in
# a "base currency" (USD on Base) with 8 decimals, and healthFactor as an
# 18-decimal fixed-point value. Both confirmed against the real deployment
# during this project's live investigation (see DELEVA_TRANSACTION_PROOF.md).
AAVE_BASE_CURRENCY_DECIMALS = 8
AAVE_HEALTH_FACTOR_DECIMALS = 18
AAVE_BPS_DECIMALS = 4  # ltv / liquidationThreshold are basis points (10000 = 100%)

# Aave's sentinel for "no debt" -- type(uint256).max. Confirmed directly
# on-chain against the real KeeperHub org wallet before it had a position.
AAVE_MAX_UINT256 = 2**256 - 1


def normalize_health_factor(raw_health_factor: int | str) -> Decimal:
    """Convert Aave's uint256 1e18-fixed-point healthFactor into a human Decimal.

    Example: the raw on-chain value ``1500000000000000000`` becomes
    ``Decimal("1.5")``. Comparing the raw integer directly against a human
    threshold like ``1.5`` would be silently wrong by 18 orders of magnitude
    -- this function is the one place that conversion happens.
    """
    return Decimal(int(raw_health_factor)) / (Decimal(10) ** AAVE_HEALTH_FACTOR_DECIMALS)


def normalize_base_currency(raw_value: int | str) -> Decimal:
    """Convert an Aave base-currency (8-decimal USD) value into a human Decimal."""
    return Decimal(int(raw_value)) / (Decimal(10) ** AAVE_BASE_CURRENCY_DECIMALS)


def normalize_bps(raw_value: int | str) -> Decimal:
    """Convert an Aave basis-points value (e.g. 8300 = 83.00%) into a human Decimal fraction (0.83)."""
    return Decimal(int(raw_value)) / (Decimal(10) ** AAVE_BPS_DECIMALS)


@dataclass(frozen=True)
class Position:
    """A normalized snapshot of one wallet's Aave V3 position on one chain.

    Every numeric field is ``Decimal | None``. ``None`` means "not
    retrieved" -- it is never silently defaulted to zero, because zero is a
    real, meaningful value (no collateral / no debt) and must not be
    confused with "unknown".
    """

    wallet: str
    chain: str
    protocol: str

    health_factor: Decimal | None
    collateral_usd: Decimal | None
    debt_usd: Decimal | None
    available_borrows_usd: Decimal | None
    ltv: Decimal | None
    liquidation_threshold: Decimal | None

    timestamp: datetime

    # The raw, unmodified provider response this was built from, kept for
    # debugging/audit -- never used for display in place of the normalized
    # fields above.
    raw: dict | None = field(default=None, repr=False, compare=False)

    @classmethod
    def from_aave_account_data(
        cls,
        *,
        wallet: str,
        chain: str,
        raw: dict,
        protocol: str = "aave_v3",
        timestamp: datetime | None = None,
    ) -> "Position":
        """Build a Position from a raw ``getUserAccountData`` result dict.

        Expects the six standard Aave V3 fields
        (totalCollateralBase, totalDebtBase, availableBorrowsBase,
        currentLiquidationThreshold, ltv, healthFactor). A missing field is
        left as ``None`` rather than assumed to be zero.
        """

        def _get(key: str):
            value = raw.get(key)
            return None if value in (None, "") else value

        collateral_raw = _get("totalCollateralBase")
        debt_raw = _get("totalDebtBase")
        available_raw = _get("availableBorrowsBase")
        ltv_raw = _get("ltv")
        liq_threshold_raw = _get("currentLiquidationThreshold")
        hf_raw = _get("healthFactor")

        return cls(
            wallet=wallet,
            chain=chain,
            protocol=protocol,
            health_factor=normalize_health_factor(hf_raw) if hf_raw is not None else None,
            collateral_usd=normalize_base_currency(collateral_raw) if collateral_raw is not None else None,
            debt_usd=normalize_base_currency(debt_raw) if debt_raw is not None else None,
            available_borrows_usd=normalize_base_currency(available_raw) if available_raw is not None else None,
            ltv=normalize_bps(ltv_raw) if ltv_raw is not None else None,
            liquidation_threshold=normalize_bps(liq_threshold_raw) if liq_threshold_raw is not None else None,
            timestamp=timestamp or datetime.now(timezone.utc),
            raw=raw,
        )

    def to_dict(self) -> dict:
        return {
            "wallet": self.wallet,
            "chain": self.chain,
            "protocol": self.protocol,
            "health_factor": str(self.health_factor) if self.health_factor is not None else None,
            "collateral_usd": str(self.collateral_usd) if self.collateral_usd is not None else None,
            "debt_usd": str(self.debt_usd) if self.debt_usd is not None else None,
            "available_borrows_usd": (
                str(self.available_borrows_usd) if self.available_borrows_usd is not None else None
            ),
            "ltv": str(self.ltv) if self.ltv is not None else None,
            "liquidation_threshold": (
                str(self.liquidation_threshold) if self.liquidation_threshold is not None else None
            ),
            "timestamp": self.timestamp.isoformat(),
        }


class RiskState(str, Enum):
    """The deterministic classification RiskEvaluator produces. Nothing more."""

    HEALTHY = "HEALTHY"
    THRESHOLD_BREACHED = "THRESHOLD_BREACHED"
    UNKNOWN = "UNKNOWN"
