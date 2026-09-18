from __future__ import annotations

from decimal import Decimal

import pytest

from deleva.config import ConfigError, DelevaConfig
from deleva.position_service import AavePositionService, PositionRetrievalError


class FakeKeeperHubClient:
    """Stands in for deleva.keeperhub_client.KeeperHubClient -- no network access."""

    def __init__(self, result):
        self._result = result
        self.calls: list[dict] = []

    def read_contract(self, *, contract_address, chain_id, function_name, function_args, abi):
        self.calls.append(
            {
                "contract_address": contract_address,
                "chain_id": chain_id,
                "function_name": function_name,
                "function_args": function_args,
                "abi": abi,
            }
        )
        return self._result


REAL_ACCOUNT_DATA = {
    "totalCollateralBase": "3006106093",
    "totalDebtBase": "1199848584",
    "availableBorrowsBase": "1205036290",
    "currentLiquidationThreshold": "8300",
    "ltv": "8000",
    "healthFactor": "2079485770506189137",
}


class TestGetPosition:
    def test_reads_real_shaped_response_and_normalizes(self):
        config = DelevaConfig(monitored_wallet="0x02168b0be574a884bAe550F3D6b9F080670f8f7F")
        client = FakeKeeperHubClient(REAL_ACCOUNT_DATA)
        service = AavePositionService(client, config)

        position = service.get_position()

        assert position.wallet == "0x02168b0be574a884bAe550F3D6b9F080670f8f7F"
        assert position.chain == "base"
        assert position.protocol == "aave_v3"
        assert position.health_factor == Decimal("2.079485770506189137")
        assert position.collateral_usd == Decimal("30.06106093")
        assert position.debt_usd == Decimal("11.99848584")

    def test_calls_read_contract_with_correct_pool_and_chain(self):
        config = DelevaConfig(monitored_wallet="0xabc")
        client = FakeKeeperHubClient(REAL_ACCOUNT_DATA)
        service = AavePositionService(client, config)

        service.get_position()

        call = client.calls[0]
        assert call["contract_address"] == config.aave_pool_address
        assert call["chain_id"] == config.chain_id
        assert call["function_name"] == "getUserAccountData"
        assert "0xabc" in call["function_args"]

    def test_explicit_wallet_overrides_configured_one(self):
        config = DelevaConfig(monitored_wallet="0xconfigured")
        client = FakeKeeperHubClient(REAL_ACCOUNT_DATA)
        service = AavePositionService(client, config)

        position = service.get_position(wallet="0xexplicit")

        assert position.wallet == "0xexplicit"
        assert "0xexplicit" in client.calls[0]["function_args"]

    def test_no_wallet_configured_or_passed_raises(self):
        config = DelevaConfig(monitored_wallet=None)
        client = FakeKeeperHubClient(REAL_ACCOUNT_DATA)
        service = AavePositionService(client, config)

        with pytest.raises(ConfigError):
            service.get_position()

    def test_unexpected_response_shape_raises_position_retrieval_error(self):
        config = DelevaConfig(monitored_wallet="0xabc")
        client = FakeKeeperHubClient(result="not-a-dict")
        service = AavePositionService(client, config)

        with pytest.raises(PositionRetrievalError):
            service.get_position()


class TestGetUsdcBalance:
    def test_reads_and_normalizes_real_shaped_balance(self):
        config = DelevaConfig(monitored_wallet="0x02168b0be574a884bAe550F3D6b9F080670f8f7F", usdc_address="0xUSDC")
        client = FakeKeeperHubClient(result="2000000")  # 2.000000 USDC, 6 decimals
        service = AavePositionService(client, config)

        balance = service.get_usdc_balance()

        assert balance == Decimal("2.000000")
        call = client.calls[0]
        assert call["contract_address"] == "0xUSDC"
        assert call["function_name"] == "balanceOf"

    def test_explicit_wallet_overrides_configured_one(self):
        config = DelevaConfig(monitored_wallet="0xconfigured")
        client = FakeKeeperHubClient(result="1000000")
        service = AavePositionService(client, config)

        service.get_usdc_balance(wallet="0xexplicit")

        assert "0xexplicit" in client.calls[0]["function_args"]

    def test_no_wallet_raises_config_error(self):
        config = DelevaConfig(monitored_wallet=None)
        client = FakeKeeperHubClient(result="1000000")
        service = AavePositionService(client, config)

        with pytest.raises(ConfigError):
            service.get_usdc_balance()

    def test_none_response_raises_position_retrieval_error(self):
        config = DelevaConfig(monitored_wallet="0xabc")
        client = FakeKeeperHubClient(result=None)
        service = AavePositionService(client, config)

        with pytest.raises(PositionRetrievalError):
            service.get_usdc_balance()
