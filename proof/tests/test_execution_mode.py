from __future__ import annotations

from deleva.config import DelevaConfig
from deleva.execution_mode import ExecutionMode


class TestExecutionModeFromConfig:
    def test_dry_run_is_the_default(self):
        config = DelevaConfig()
        assert config.execution_dry_run is True
        assert ExecutionMode.from_config(config) is ExecutionMode.DRY_RUN

    def test_live_requires_explicit_opt_out(self):
        config = DelevaConfig(execution_dry_run=False)
        assert ExecutionMode.from_config(config) is ExecutionMode.LIVE

    def test_from_config_never_returns_demo(self):
        # DEMO exists solely for deleva/demo.py to set explicitly -- no real
        # environment configuration should ever be able to produce it.
        assert ExecutionMode.from_config(DelevaConfig(execution_dry_run=True)) is not ExecutionMode.DEMO
        assert ExecutionMode.from_config(DelevaConfig(execution_dry_run=False)) is not ExecutionMode.DEMO


class TestDemoExecutionMode:
    def test_demo_is_a_distinct_value_from_live_and_dry_run(self):
        assert ExecutionMode.DEMO != ExecutionMode.LIVE
        assert ExecutionMode.DEMO != ExecutionMode.DRY_RUN
        assert ExecutionMode.DEMO.value == "DEMO"
