from __future__ import annotations

from decimal import Decimal

from deleva.config import DelevaConfig
from deleva.strategy import DelevaStrategy


class TestStrategyConfiguration:
    def test_default_strategy_matches_the_real_proven_shape(self):
        strategy = DelevaStrategy()
        assert strategy.protocol == "aave_v3"
        assert strategy.chain == "base"
        assert strategy.action == "deleverage"
        assert strategy.decision_layer == "almanak"
        assert strategy.execution_layer == "keeperhub"

    def test_default_thresholds(self):
        strategy = DelevaStrategy()
        assert strategy.trigger_health_factor == Decimal("1.50")
        assert strategy.target_health_factor == Decimal("1.50")

    def test_from_config_uses_config_thresholds(self):
        config = DelevaConfig(hf_trigger_threshold=Decimal("1.75"), hf_target=Decimal("2.00"), chain="base")
        strategy = DelevaStrategy.default(config)
        assert strategy.trigger_health_factor == Decimal("1.75")
        assert strategy.target_health_factor == Decimal("2.00")
        assert strategy.chain == "base"

    def test_to_dict_shape(self):
        strategy = DelevaStrategy()
        as_dict = strategy.to_dict()
        assert as_dict["trigger_health_factor"] == "1.50"
        assert as_dict["target_health_factor"] == "1.50"
        assert as_dict["protocol"] == "aave_v3"

    def test_strategy_is_pure_configuration_no_scheduler_attribute(self):
        # Guards against ever accidentally attaching scheduling state to this
        # object -- it must remain pure configuration data.
        strategy = DelevaStrategy()
        for forbidden in ("scheduler", "interval", "is_running", "last_run"):
            assert not hasattr(strategy, forbidden)
