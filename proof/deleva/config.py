"""Central configuration for DELEVA.

Every value that varies between environments (chain, addresses, thresholds,
the KeeperHub API base URL) lives here, read from environment variables with
explicit, documented defaults. The one value that must never have a default
is the KeeperHub API key -- it is a secret, environment-only, and this module
never embeds it in source.

See ``.env.example`` in this directory's parent for the full list of
supported environment variables with safe example values.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation


class ConfigError(Exception):
    """Raised when required configuration is missing or malformed."""


def _env_str(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _env_optional_str(name: str) -> str | None:
    value = os.environ.get(name)
    return value if value else None


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name}={raw!r} is not a valid integer") from exc


def _env_decimal(name: str, default: str) -> Decimal:
    raw = os.environ.get(name, default)
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise ConfigError(f"{name}={raw!r} is not a valid decimal") from exc


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class DelevaConfig:
    """DELEVA's runtime configuration.

    Addresses default to the real, already-proven Base mainnet values (see
    DELEVA_TRANSACTION_PROOF.md) so that Phase 2 code works out of the box
    against the same chain this was proven on, while remaining fully
    overridable via environment variables for any other deployment.
    """

    chain: str = "base"
    chain_id: int = 8453

    aave_pool_address: str = "0xA238Dd80C259a72e81d7e4664a9801593F98d1c5"
    usdc_address: str = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
    weth_address: str = "0x4200000000000000000000000000000000000006"

    # The wallet DELEVA monitors and (eventually, in Phase 2) executes on
    # behalf of. No safe default exists -- an unset value must be treated as
    # "not configured", never silently assumed.
    monitored_wallet: str | None = None

    # Strategy thresholds. Both default to the values used in the real proof
    # run's DeleverageIntent (see DELEVA_TRANSACTION_PROOF.md / strategy.py).
    hf_trigger_threshold: Decimal = field(default_factory=lambda: Decimal("1.50"))
    hf_target: Decimal = field(default_factory=lambda: Decimal("1.50"))

    keeperhub_api_base: str = "https://app.keeperhub.com"
    # Secret. Environment-only. No default -- see require_keeperhub_api_key().
    keeperhub_api_key: str | None = None

    # Phase 1/2 safety default: nothing in this codebase is allowed to
    # broadcast unless this is explicitly and deliberately set to False by
    # the caller assembling the execution path. Never flipped by this
    # codebase itself -- only by an operator's own environment.
    execution_dry_run: bool = True

    # How often MonitoringRunner should invoke a cycle, in seconds. A
    # reasonable development default; production would likely use something
    # closer to the docs-recommended cadence for a health-factor monitor.
    monitoring_interval_seconds: int = 30

    # How long AutonomousEngine waits after a triggered action (success or
    # failure) before it will attempt another one, even if the position is
    # still breached. Exists specifically to prevent a tight retry loop.
    retry_backoff_seconds: int = 300

    # The smallest deleverage repay AutonomousEngine will ever size, even if
    # the target-health-factor calculation says less is needed. Prevents a
    # "dust" repay that would cost more in gas than it accomplishes. Defaults
    # to 10 -- the exact amount already proven live (DELEVA_TRANSACTION_PROOF.md).
    min_deleverage_amount: Decimal = field(default_factory=lambda: Decimal("10"))

    @classmethod
    def from_env(cls) -> "DelevaConfig":
        """Build configuration from environment variables, with the defaults above."""
        return cls(
            chain=_env_str("DELEVA_CHAIN", "base"),
            chain_id=_env_int("DELEVA_CHAIN_ID", 8453),
            aave_pool_address=_env_str(
                "DELEVA_AAVE_POOL_ADDRESS", "0xA238Dd80C259a72e81d7e4664a9801593F98d1c5"
            ),
            usdc_address=_env_str("DELEVA_USDC_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"),
            weth_address=_env_str("DELEVA_WETH_ADDRESS", "0x4200000000000000000000000000000000000006"),
            monitored_wallet=_env_optional_str("DELEVA_MONITORED_WALLET"),
            hf_trigger_threshold=_env_decimal("DELEVA_HF_TRIGGER_THRESHOLD", "1.50"),
            hf_target=_env_decimal("DELEVA_HF_TARGET", "1.50"),
            keeperhub_api_base=_env_str("KEEPERHUB_API_BASE_URL", "https://app.keeperhub.com"),
            keeperhub_api_key=_env_optional_str("KEEPERHUB_API_KEY"),
            execution_dry_run=_env_bool("DELEVA_EXECUTION_DRY_RUN", True),
            monitoring_interval_seconds=_env_int("DELEVA_MONITORING_INTERVAL_SECONDS", 30),
            retry_backoff_seconds=_env_int("DELEVA_RETRY_BACKOFF_SECONDS", 300),
            min_deleverage_amount=_env_decimal("DELEVA_MIN_DELEVERAGE_AMOUNT", "10"),
        )

    def require_monitored_wallet(self) -> str:
        if not self.monitored_wallet:
            raise ConfigError(
                "DELEVA_MONITORED_WALLET is not set. DELEVA has no safe default wallet to "
                "monitor -- set the environment variable explicitly."
            )
        return self.monitored_wallet

    def require_keeperhub_api_key(self) -> str:
        if not self.keeperhub_api_key:
            raise ConfigError(
                "KEEPERHUB_API_KEY is not set. This is a secret and must be provided via "
                "the environment; it has no default and must never be hardcoded."
            )
        return self.keeperhub_api_key
