"""Asserts the adapter boundary: real Almanak ActionBundle -> valid KeeperHub request.

Runs against a REAL (non-mocked) IntentCompiler.compile() call -- offline, no
RPC, no funds, no signer/gateway. Run with:

    pytest test_adapter.py -v
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from eth_utils import keccak, to_checksum_address

from almanak.framework.intents import (
    BorrowIntent,
    DeleverageIntent,
    IntentCompiler,
    IntentCompilerConfig,
    SupplyIntent,
    WrapNativeIntent,
)
from almanak.framework.intents.compiler_models import CompilationStatus

from keeperhub_adapter import CHAIN_ID_BY_ALMANAK_CHAIN, almanak_tx_to_keeperhub_request, decode_calldata

DUMMY_WALLET = "0x000000000000000000000000000000000000dEaD"

REQUIRED_KEEPERHUB_FIELDS = {"contractAddress", "chainId", "functionName", "functionArgs", "abi", "value"}


def _compile(intent) -> list[dict]:
    compiler = IntentCompiler(
        chain="base",
        wallet_address=DUMMY_WALLET,
        config=IntentCompilerConfig(allow_placeholder_prices=True),
        rpc_url=None,
    )
    result = compiler.compile(intent)
    assert result.status == CompilationStatus.SUCCESS, f"compile failed: {result.error}"
    assert result.action_bundle is not None
    return result.action_bundle.transactions, result.action_bundle.metadata


@pytest.fixture(scope="module")
def aave_supply_bundle():
    intent = SupplyIntent(token="USDC", amount=Decimal("100"), protocol="aave_v3", chain="base")
    return _compile(intent)


@pytest.fixture(scope="module")
def wrap_native_bundle():
    intent = WrapNativeIntent(token="WETH", amount=Decimal("0.001"), chain="base")
    return _compile(intent)


@pytest.fixture(scope="module")
def borrow_bundle():
    """Real BorrowIntent bundle: the position-opening leg DELEVA's own real
    Base-mainnet position was created with (see DELEVA_TRANSACTION_PROOF.md).
    collateral_amount=0 because collateral is supplied via a separate
    SupplyIntent first -- Almanak's own compiler rejects a bundled
    supply+borrow for accounting-correctness reasons (see its own
    ValidationError message)."""
    intent = BorrowIntent(
        protocol="aave_v3",
        collateral_token="WETH",
        collateral_amount=Decimal("0"),
        borrow_token="USDC",
        borrow_amount=Decimal("12"),
        interest_rate_mode="variable",
        chain="base",
    )
    return _compile(intent)


@pytest.fixture(scope="module")
def deleverage_bundle():
    """DELEVA's actual product intent: risk-guard forced repay on Aave V3 (Base)."""
    intent = DeleverageIntent(
        protocol="aave_v3",
        token="USDC",
        amount=Decimal("10"),
        repay_full=False,
        chain="base",
        trigger_reason="health_factor_below_threshold",
        observed_hf=Decimal("1.08"),
        target_hf=Decimal("1.50"),
    )
    return _compile(intent)


class TestActionBundleHasNoAbiInfo:
    """Item 3/4: functionName/functionArgs/abi are NOT present on the real bundle."""

    def test_no_function_metadata_on_transactions_or_bundle(self, aave_supply_bundle):
        transactions, metadata = aave_supply_bundle
        forbidden = {"functionName", "functionArgs", "abi", "function_name", "function_args"}
        for tx in transactions:
            assert forbidden.isdisjoint(tx.keys())
        assert forbidden.isdisjoint(metadata.keys())


class TestDecodeRoundTrip:
    """Item 5/8: decode calldata back to (functionName, args, abi), and prove the
    decode is lossless by re-encoding and comparing to the original bytes."""

    @pytest.mark.parametrize("tx_index", [0, 1, 2])
    def test_selector_independently_matches_signature(self, aave_supply_bundle, tx_index):
        transactions, _ = aave_supply_bundle
        tx = transactions[tx_index]
        decoded = decode_calldata(tx["data"])

        # Independently recompute the selector from the canonical Solidity
        # signature (not by trusting the adapter's own registry lookup).
        signature = f"{decoded.function_name}({','.join(decoded.arg_types)})"
        expected_selector = "0x" + keccak(text=signature).hex()[:8]
        assert expected_selector == tx["data"][:10]
        assert expected_selector == decoded.selector

    @pytest.mark.parametrize("tx_index", [0, 1, 2])
    def test_reencoded_calldata_matches_original_exactly(self, aave_supply_bundle, tx_index):
        transactions, _ = aave_supply_bundle
        tx = transactions[tx_index]
        decoded = decode_calldata(tx["data"])
        assert decoded.reencode() == tx["data"]

    def test_wrap_native_zero_arg_call_round_trips(self, wrap_native_bundle):
        transactions, _ = wrap_native_bundle
        assert len(transactions) == 1
        tx = transactions[0]
        decoded = decode_calldata(tx["data"])
        assert decoded.function_name == "deposit"
        assert decoded.arg_values == ()
        assert decoded.reencode() == tx["data"] == "0xd0e30db0"


class TestKeeperHubRequestShape:
    """Item 6/8: the adapter produces a structurally valid KeeperHub contract-call body."""

    @pytest.mark.parametrize("tx_index", [0, 1, 2])
    def test_required_fields_present(self, aave_supply_bundle, tx_index):
        transactions, metadata = aave_supply_bundle
        tx = transactions[tx_index]
        body = almanak_tx_to_keeperhub_request(tx, chain=metadata["chain"], simulate=True)
        assert REQUIRED_KEEPERHUB_FIELDS.issubset(body.keys())
        assert body["simulate"] is True

    @pytest.mark.parametrize("tx_index", [0, 1, 2])
    def test_contract_address_matches_action_bundle_to(self, aave_supply_bundle, tx_index):
        transactions, metadata = aave_supply_bundle
        tx = transactions[tx_index]
        body = almanak_tx_to_keeperhub_request(tx, chain=metadata["chain"], simulate=True)
        assert body["contractAddress"].lower() == tx["to"].lower()
        assert body["contractAddress"] == to_checksum_address(tx["to"])

    @pytest.mark.parametrize("tx_index", [0, 1, 2])
    def test_chain_id_matches_action_bundle_chain(self, aave_supply_bundle, tx_index):
        transactions, metadata = aave_supply_bundle
        tx = transactions[tx_index]
        body = almanak_tx_to_keeperhub_request(tx, chain=metadata["chain"], simulate=True)
        assert metadata["chain"] == "base"
        assert body["chainId"] == 8453 == CHAIN_ID_BY_ALMANAK_CHAIN["base"]

    @pytest.mark.parametrize("tx_index", [0, 1, 2])
    def test_value_preserved_exactly(self, aave_supply_bundle, tx_index):
        transactions, metadata = aave_supply_bundle
        tx = transactions[tx_index]
        body = almanak_tx_to_keeperhub_request(tx, chain=metadata["chain"], simulate=True)
        original_wei = int(tx["value"])
        reconstructed_wei = int(Decimal(body["value"]) * Decimal(10**18))
        assert reconstructed_wei == original_wei

    @pytest.mark.parametrize("tx_index", [0, 1, 2])
    def test_decoded_function_name_matches_bundle_selector(self, aave_supply_bundle, tx_index):
        transactions, metadata = aave_supply_bundle
        tx = transactions[tx_index]
        body = almanak_tx_to_keeperhub_request(tx, chain=metadata["chain"], simulate=True)
        decoded = decode_calldata(tx["data"])
        assert body["functionName"] == decoded.function_name
        assert body["functionArgs"] == decoded.function_args_json()

    def test_wrap_native_full_request_shape(self, wrap_native_bundle):
        transactions, metadata = wrap_native_bundle
        tx = transactions[0]
        body = almanak_tx_to_keeperhub_request(tx, chain=metadata["chain"], simulate=True)
        assert body == {
            "contractAddress": "0x4200000000000000000000000000000000000006",
            "chainId": 8453,
            "functionName": "deposit",
            "functionArgs": "[]",
            "abi": body["abi"],  # exact JSON string checked separately below
            "value": "0.001",
            "simulate": True,
        }
        assert '"name": "deposit"' in body["abi"]
        assert '"stateMutability": "payable"' in body["abi"]


class TestDeleverageBundle:
    """DELEVA's actual product flow: DeleverageIntent -> [approve, repay] on Aave V3 (Base).

    IntentType.DELEVERAGE routes through the identical compiler path as REPAY
    (almanak/framework/intents/compiler.py), so this is not a synthetic bundle --
    it is what a real risk-management strategy emits when health factor crosses
    its danger threshold.
    """

    def test_bundle_has_exactly_two_transactions(self, deleverage_bundle):
        transactions, metadata = deleverage_bundle
        assert len(transactions) == 2
        assert [tx["tx_type"] for tx in transactions] == ["approve", "lending_repay"]
        assert metadata["chain"] == "base"

    def test_approve_leg_targets_usdc_and_pool(self, deleverage_bundle):
        transactions, _ = deleverage_bundle
        approve_tx = transactions[0]
        decoded = decode_calldata(approve_tx["data"])
        assert approve_tx["to"].lower() == "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
        assert decoded.function_name == "approve"
        spender, _amount = decoded.arg_values
        assert to_checksum_address(spender) == "0xA238Dd80C259a72e81d7e4664a9801593F98d1c5"

    def test_repay_leg_uses_selector_0x573ade81(self, deleverage_bundle):
        transactions, _ = deleverage_bundle
        repay_tx = transactions[1]
        assert repay_tx["data"][:10] == "0x573ade81"
        decoded = decode_calldata(repay_tx["data"])
        assert decoded.selector == "0x573ade81"
        assert decoded.function_name == "repay"

    def test_repay_leg_targets_real_aave_v3_pool_on_base(self, deleverage_bundle):
        transactions, _ = deleverage_bundle
        repay_tx = transactions[1]
        assert repay_tx["to"] == "0xA238Dd80C259a72e81d7e4664a9801593F98d1c5"

    def test_repay_leg_args_match_intent(self, deleverage_bundle):
        transactions, _ = deleverage_bundle
        repay_tx = transactions[1]
        decoded = decode_calldata(repay_tx["data"])
        asset, amount, interest_rate_mode, _on_behalf_of = decoded.arg_values
        assert to_checksum_address(asset) == "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
        assert amount == 10_000_000  # 10 USDC, 6 decimals
        assert interest_rate_mode == 2  # variable rate

    @pytest.mark.parametrize("tx_index", [0, 1])
    def test_both_legs_round_trip_exactly(self, deleverage_bundle, tx_index):
        transactions, _ = deleverage_bundle
        tx = transactions[tx_index]
        decoded = decode_calldata(tx["data"])
        assert decoded.reencode() == tx["data"]

    @pytest.mark.parametrize("tx_index", [0, 1])
    def test_both_legs_produce_valid_keeperhub_request(self, deleverage_bundle, tx_index):
        transactions, metadata = deleverage_bundle
        tx = transactions[tx_index]
        body = almanak_tx_to_keeperhub_request(tx, chain=metadata["chain"], simulate=True)
        assert REQUIRED_KEEPERHUB_FIELDS.issubset(body.keys())
        assert body["chainId"] == 8453
        assert body["contractAddress"] == to_checksum_address(tx["to"])
        assert body["simulate"] is True

    def test_deleverage_intent_type_reported_as_repay(self, deleverage_bundle):
        """DELEVERAGE shares REPAY's on-chain path; the bundle's intent_type reflects that."""
        _transactions, metadata = deleverage_bundle
        # intent_type lives on the ActionBundle itself, not metadata; re-verify via a
        # fresh compile since the fixture only returns (transactions, metadata).
        intent = DeleverageIntent(
            protocol="aave_v3",
            token="USDC",
            amount=Decimal("10"),
            repay_full=False,
            chain="base",
        )
        compiler = IntentCompiler(
            chain="base",
            wallet_address=DUMMY_WALLET,
            config=IntentCompilerConfig(allow_placeholder_prices=True),
            rpc_url=None,
        )
        result = compiler.compile(intent)
        assert result.status == CompilationStatus.SUCCESS
        assert result.action_bundle.intent_type == "REPAY"


class TestBorrowBundle:
    """Aave V3 borrow -- the position-opening leg, previously untested (adapter
    gap identified during Phase 1 repo inspection)."""

    def test_bundle_has_exactly_one_transaction(self, borrow_bundle):
        transactions, metadata = borrow_bundle
        assert len(transactions) == 1
        assert transactions[0]["tx_type"] == "lending_borrow"
        assert metadata["chain"] == "base"

    def test_borrow_uses_selector_0xa415bcad(self, borrow_bundle):
        transactions, _ = borrow_bundle
        tx = transactions[0]
        assert tx["data"][:10] == "0xa415bcad"
        decoded = decode_calldata(tx["data"])
        assert decoded.selector == "0xa415bcad"
        assert decoded.function_name == "borrow"

    def test_borrow_targets_real_aave_v3_pool_on_base(self, borrow_bundle):
        transactions, _ = borrow_bundle
        assert transactions[0]["to"] == "0xA238Dd80C259a72e81d7e4664a9801593F98d1c5"

    def test_borrow_args_match_intent(self, borrow_bundle):
        transactions, _ = borrow_bundle
        decoded = decode_calldata(transactions[0]["data"])
        asset, amount, interest_rate_mode, referral_code, _on_behalf_of = decoded.arg_values
        assert to_checksum_address(asset) == "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
        assert amount == 12_000_000  # 12 USDC, 6 decimals
        assert interest_rate_mode == 2  # variable rate
        assert referral_code == 0

    def test_borrow_round_trips_exactly(self, borrow_bundle):
        transactions, _ = borrow_bundle
        tx = transactions[0]
        decoded = decode_calldata(tx["data"])
        assert decoded.reencode() == tx["data"]

    def test_borrow_produces_valid_keeperhub_request(self, borrow_bundle):
        transactions, metadata = borrow_bundle
        tx = transactions[0]
        body = almanak_tx_to_keeperhub_request(tx, chain=metadata["chain"], simulate=True)
        assert REQUIRED_KEEPERHUB_FIELDS.issubset(body.keys())
        assert body["chainId"] == 8453
        assert body["contractAddress"] == to_checksum_address(tx["to"])
        assert body["functionName"] == "borrow"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
