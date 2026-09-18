"""DELEVA's strategy configuration.

A Strategy is configuration data -- protocol, chain, trigger, target, which
layers decide vs. execute. It is not a running process. Nothing in this
module schedules, polls, or monitors anything; Phase 2's autonomous loop
reads a Strategy and acts on it, but that loop does not exist yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from deleva.config import DelevaConfig


@dataclass(frozen=True)
class DelevaStrategy:
    """Configuration for DELEVA's one supported strategy: Aave V3 deleverage on Base.

    This describes *what* DELEVA does and *when* it should decide to act --
    it does not, by itself, cause anything to happen. There is no scheduler
    attached to this object.
    """

    name: str = "aave-v3-base-deleverage"
    protocol: str = "aave_v3"
    chain: str = "base"
    action: str = "deleverage"

    # Health factor strictly below this triggers a THRESHOLD_BREACHED risk
    # state (see deleva.risk.RiskEvaluator).
    trigger_health_factor: Decimal = field(default_factory=lambda: Decimal("1.50"))

    # The health factor a deleverage action aims to restore the position to.
    # Used as DeleverageIntent.target_hf metadata, not enforced on-chain.
    target_health_factor: Decimal = field(default_factory=lambda: Decimal("1.50"))

    decision_layer: str = "almanak"
    execution_layer: str = "keeperhub"

    @classmethod
    def default(cls, config: DelevaConfig) -> "DelevaStrategy":
        """Build the default strategy from central configuration's thresholds."""
        return cls(
            chain=config.chain,
            trigger_health_factor=config.hf_trigger_threshold,
            target_health_factor=config.hf_target,
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "protocol": self.protocol,
            "chain": self.chain,
            "action": self.action,
            "trigger_health_factor": str(self.trigger_health_factor),
            "target_health_factor": str(self.target_health_factor),
            "decision_layer": self.decision_layer,
            "execution_layer": self.execution_layer,
        }
