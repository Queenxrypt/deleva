from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from almanak.framework.intents.compiler_models import CompilationStatus
from deleva.almanak_interface import AlmanakCompilationError, AlmanakStrategyInterface

DUMMY_WALLET = "0x000000000000000000000000000000000000dEaD"
REAL_ORG_WALLET = "0x02168b0be574a884bAe550F3D6b9F080670f8f7F"


class _FakeActionBundle:
    def __init__(self, intent_type, transactions, metadata):
        self.intent_type = intent_type
        self.transactions = transactions
        self.metadata = metadata


class _FakeCompiler:
    """Stands in for the real IntentCompiler so these tests exercise only
    AlmanakStrategyInterface's own shaping/error-handling logic, isolated
    from the real SDK (which is covered by the real-compile smoke test
    below and exhaustively by test_adapter.py)."""

    def __init__(self, result):
        self._result = result

    def compile(self, intent):
        return self._result


class TestGenerateDeleverageActionBundleWithMockedCompiler:
    def test_success_shapes_action_bundle_result(self, monkeypatch):
        fake_bundle = _FakeActionBundle(
            intent_type="REPAY",
            transactions=[{"to": "0xPool", "data": "0x573ade81", "value": "0"}],
            metadata={"chain": "base"},
        )
        fake_result = SimpleNamespace(status=CompilationStatus.SUCCESS, action_bundle=fake_bundle, error=None)

        interface = AlmanakStrategyInterface(chain="base", wallet_address=REAL_ORG_WALLET)
        monkeypatch.setattr(interface, "_build_compiler", lambda: _FakeCompiler(fake_result))

        result = interface.generate_deleverage_action_bundle(
            protocol="aave_v3", token="USDC", amount=Decimal("10")
        )

        assert result.intent_type == "REPAY"
        assert result.transactions == fake_bundle.transactions
        assert result.metadata == {"chain": "base"}
        assert result.intent_id  # a real UUID was assigned by the real DeleverageIntent constructor

    def test_compiler_failure_raises_with_real_error_message(self, monkeypatch):
        fake_result = SimpleNamespace(
            status=CompilationStatus.FAILED, action_bundle=None, error="Unsupported lending protocol"
        )
        interface = AlmanakStrategyInterface(chain="base", wallet_address=REAL_ORG_WALLET)
        monkeypatch.setattr(interface, "_build_compiler", lambda: _FakeCompiler(fake_result))

        with pytest.raises(AlmanakCompilationError, match="Unsupported lending protocol"):
            interface.generate_deleverage_action_bundle(protocol="aave_v3", token="USDC", amount=Decimal("10"))

    def test_missing_action_bundle_on_success_status_also_raises(self, monkeypatch):
        # Defensive: even if status says SUCCESS, a None action_bundle must
        # not be silently treated as a valid result.
        fake_result = SimpleNamespace(status=CompilationStatus.SUCCESS, action_bundle=None, error=None)
        interface = AlmanakStrategyInterface(chain="base", wallet_address=REAL_ORG_WALLET)
        monkeypatch.setattr(interface, "_build_compiler", lambda: _FakeCompiler(fake_result))

        with pytest.raises(AlmanakCompilationError):
            interface.generate_deleverage_action_bundle(protocol="aave_v3", token="USDC", amount=Decimal("10"))


class TestGenerateDeleverageActionBundleRealSdk:
    """One real-SDK smoke test: the mocked tests above prove the wrapper's own
    logic, this proves the wrapper truly integrates with the real, installed
    Almanak IntentCompiler -- the same real call that produced the actual
    proof transaction 0xd36217b0... (see DELEVA_TRANSACTION_PROOF.md)."""

    def test_real_compile_produces_the_same_two_transaction_shape(self):
        interface = AlmanakStrategyInterface(chain="base", wallet_address=DUMMY_WALLET)

        result = interface.generate_deleverage_action_bundle(
            protocol="aave_v3",
            token="USDC",
            amount=Decimal("10"),
            repay_full=False,
            observed_hf=Decimal("2.0795"),
            target_hf=Decimal("1.50"),
        )

        assert result.intent_type == "REPAY"
        assert len(result.transactions) == 2
        assert result.transactions[0]["tx_type"] == "approve"
        assert result.transactions[1]["tx_type"] == "lending_repay"
        assert result.transactions[1]["data"][:10] == "0x573ade81"
