"""Read-only Aave V3 position retrieval.

This service has exactly one job: given a wallet, read its real Aave V3
account data through KeeperHub and return a normalized ``Position``. It
never writes, never simulates a write, and never calls execute. It uses the
same ``getUserAccountData`` read call already used and verified repeatedly
against the real Base mainnet Aave V3 Pool during this project's proof work
(see DELEVA_TRANSACTION_PROOF.md).
"""

from __future__ import annotations

import json
from decimal import Decimal

from deleva.config import DelevaConfig
from deleva.keeperhub_client import KeeperHubClient
from deleva.models import Position

# Standard Aave V3 Pool.getUserAccountData(address) ABI fragment. Verified
# against the real Base mainnet deployment during this project's live
# investigation -- not assumed from memory.
GET_USER_ACCOUNT_DATA_ABI = json.dumps(
    [
        {
            "inputs": [{"name": "user", "type": "address"}],
            "name": "getUserAccountData",
            "outputs": [
                {"name": "totalCollateralBase", "type": "uint256"},
                {"name": "totalDebtBase", "type": "uint256"},
                {"name": "availableBorrowsBase", "type": "uint256"},
                {"name": "currentLiquidationThreshold", "type": "uint256"},
                {"name": "ltv", "type": "uint256"},
                {"name": "healthFactor", "type": "uint256"},
            ],
            "stateMutability": "view",
            "type": "function",
        }
    ]
)

# Standard ERC20 balanceOf(address) ABI fragment.
BALANCE_OF_ABI = json.dumps(
    [
        {
            "inputs": [{"name": "account", "type": "address"}],
            "name": "balanceOf",
            "outputs": [{"name": "", "type": "uint256"}],
            "stateMutability": "view",
            "type": "function",
        }
    ]
)

USDC_DECIMALS = 6


class PositionRetrievalError(Exception):
    """Raised when the Aave position read fails or returns an unexpected shape."""


class AavePositionService:
    """Read-only Aave V3 position retrieval, via KeeperHub's contract-call read path."""

    def __init__(self, keeperhub_client: KeeperHubClient, config: DelevaConfig) -> None:
        self._client = keeperhub_client
        self._config = config

    def get_position(self, wallet: str | None = None) -> Position:
        """Read and normalize the given wallet's (or the configured monitored wallet's) Aave V3 position."""
        target_wallet = wallet or self._config.require_monitored_wallet()

        result = self._client.read_contract(
            contract_address=self._config.aave_pool_address,
            chain_id=self._config.chain_id,
            function_name="getUserAccountData",
            function_args=json.dumps([target_wallet]),
            abi=GET_USER_ACCOUNT_DATA_ABI,
        )
        if not isinstance(result, dict):
            raise PositionRetrievalError(
                f"Unexpected getUserAccountData response shape for {target_wallet}: {result!r}"
            )

        return Position.from_aave_account_data(
            wallet=target_wallet,
            chain=self._config.chain,
            raw=result,
            protocol="aave_v3",
        )

    def get_usdc_balance(self, wallet: str | None = None) -> Decimal:
        """Read the wallet's real USDC balance (the token DELEVA's deleverage
        strategy repays with) -- relevant context alongside the position
        itself, not part of Aave's own account data."""
        target_wallet = wallet or self._config.require_monitored_wallet()

        raw_balance = self._client.read_contract(
            contract_address=self._config.usdc_address,
            chain_id=self._config.chain_id,
            function_name="balanceOf",
            function_args=json.dumps([target_wallet]),
            abi=BALANCE_OF_ABI,
        )
        if raw_balance is None:
            raise PositionRetrievalError(f"Unexpected balanceOf response for {target_wallet}: {raw_balance!r}")
        return Decimal(int(raw_balance)) / (Decimal(10) ** USDC_DECIMALS)
