from __future__ import annotations

from decimal import Decimal

import pytest

from deleva.config import ConfigError, DelevaConfig


class TestDefaults:
    def test_defaults_match_the_real_proven_deployment(self):
        config = DelevaConfig()
        assert config.chain == "base"
        assert config.chain_id == 8453
        assert config.aave_pool_address == "0xA238Dd80C259a72e81d7e4664a9801593F98d1c5"
        assert config.usdc_address == "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
        assert config.weth_address == "0x4200000000000000000000000000000000000006"
        assert config.hf_trigger_threshold == Decimal("1.50")
        assert config.hf_target == Decimal("1.50")
        assert config.keeperhub_api_base == "https://app.keeperhub.com"

    def test_no_default_wallet_or_api_key(self):
        config = DelevaConfig()
        assert config.monitored_wallet is None
        assert config.keeperhub_api_key is None

    def test_execution_dry_run_defaults_true(self):
        assert DelevaConfig().execution_dry_run is True

    def test_monitoring_interval_and_backoff_defaults(self):
        config = DelevaConfig()
        assert config.monitoring_interval_seconds == 30
        assert config.retry_backoff_seconds == 300


class TestEnvironmentOverrides:
    def test_from_env_reads_overrides(self, monkeypatch):
        monkeypatch.setenv("DELEVA_CHAIN", "arbitrum")
        monkeypatch.setenv("DELEVA_CHAIN_ID", "42161")
        monkeypatch.setenv("DELEVA_MONITORED_WALLET", "0x02168b0be574a884bAe550F3D6b9F080670f8f7F")
        monkeypatch.setenv("DELEVA_HF_TRIGGER_THRESHOLD", "1.75")
        monkeypatch.setenv("KEEPERHUB_API_KEY", "kh_test_key")
        monkeypatch.setenv("DELEVA_EXECUTION_DRY_RUN", "false")
        monkeypatch.setenv("DELEVA_MONITORING_INTERVAL_SECONDS", "60")
        monkeypatch.setenv("DELEVA_RETRY_BACKOFF_SECONDS", "120")

        config = DelevaConfig.from_env()

        assert config.chain == "arbitrum"
        assert config.chain_id == 42161
        assert config.monitored_wallet == "0x02168b0be574a884bAe550F3D6b9F080670f8f7F"
        assert config.hf_trigger_threshold == Decimal("1.75")
        assert config.keeperhub_api_key == "kh_test_key"
        assert config.execution_dry_run is False
        assert config.monitoring_interval_seconds == 60
        assert config.retry_backoff_seconds == 120

    def test_from_env_falls_back_to_defaults_when_unset(self, monkeypatch):
        for name in (
            "DELEVA_CHAIN",
            "DELEVA_CHAIN_ID",
            "DELEVA_MONITORED_WALLET",
            "DELEVA_HF_TRIGGER_THRESHOLD",
            "KEEPERHUB_API_KEY",
        ):
            monkeypatch.delenv(name, raising=False)

        config = DelevaConfig.from_env()

        assert config.chain == "base"
        assert config.chain_id == 8453
        assert config.monitored_wallet is None
        assert config.hf_trigger_threshold == Decimal("1.50")
        assert config.keeperhub_api_key is None

    def test_invalid_decimal_env_raises_config_error(self, monkeypatch):
        monkeypatch.setenv("DELEVA_HF_TRIGGER_THRESHOLD", "not-a-number")
        with pytest.raises(ConfigError):
            DelevaConfig.from_env()

    def test_invalid_int_env_raises_config_error(self, monkeypatch):
        monkeypatch.setenv("DELEVA_CHAIN_ID", "not-an-int")
        with pytest.raises(ConfigError):
            DelevaConfig.from_env()


class TestRequiredSecrets:
    def test_require_keeperhub_api_key_raises_when_unset(self):
        config = DelevaConfig(keeperhub_api_key=None)
        with pytest.raises(ConfigError):
            config.require_keeperhub_api_key()

    def test_require_keeperhub_api_key_returns_value_when_set(self):
        config = DelevaConfig(keeperhub_api_key="kh_real")
        assert config.require_keeperhub_api_key() == "kh_real"

    def test_require_monitored_wallet_raises_when_unset(self):
        config = DelevaConfig(monitored_wallet=None)
        with pytest.raises(ConfigError):
            config.require_monitored_wallet()

    def test_require_monitored_wallet_returns_value_when_set(self):
        config = DelevaConfig(monitored_wallet="0xabc")
        assert config.require_monitored_wallet() == "0xabc"

    def test_api_key_never_has_a_source_default(self):
        # Guards against ever accidentally hardcoding a real-looking default.
        import inspect

        source = inspect.getsource(DelevaConfig)
        assert 'keeperhub_api_key: str | None = None' in source
