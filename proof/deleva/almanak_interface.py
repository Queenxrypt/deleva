"""Clean, reusable interface around the real, vendored Almanak SDK.

This module does not reimplement any Almanak logic. It only constructs the
Intent objects Almanak already defines and calls the real, installed
``IntentCompiler.compile()`` -- the exact same call every proof script in
this project (run_proof.py, run_deleverage_proof.py, and the real DELEVA
proof transaction itself) has used. See DELEVA_TRANSACTION_PROOF.md for the
real, executed result of this exact call shape.

Phase 2's autonomous loop is meant to call
``AlmanakStrategyInterface.generate_deleverage_action_bundle(...)`` once a
RiskEvaluator reports THRESHOLD_BREACHED -- that is the "Almanak decides"
half of this project's core thesis ("Almanak decides. KeeperHub executes.").
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from almanak.framework.intents import DeleverageIntent, IntentCompiler, IntentCompilerConfig
from almanak.framework.intents.compiler_models import CompilationStatus


class AlmanakCompilationError(Exception):
    """Raised when the real Almanak IntentCompiler fails to compile an Intent.

    Carries the compiler's own error message verbatim -- this module never
    guesses at why a compile failed.
    """


@dataclass(frozen=True)
class ActionBundleResult:
    """A normalized view of a real, compiled Almanak ActionBundle.

    ``transactions`` and ``metadata`` are exactly what
    ``ActionBundle.to_dict()`` produced -- nothing here is reshaped or
    invented; this is a thin, typed wrapper, not a reimplementation.
    """

    intent_id: str
    intent_type: str
    transactions: list[dict[str, Any]]
    metadata: dict[str, Any]


class AlmanakStrategyInterface:
    """Compiles DELEVA strategy decisions into real Almanak ActionBundles.

    One instance is scoped to one (chain, wallet) pair, matching how
    ``IntentCompiler`` itself is constructed. Compiles offline: no RPC, no
    gateway client, matching every proof script in this project (this is a
    read/compile-only operation -- it never signs or broadcasts anything).
    """

    def __init__(self, *, chain: str, wallet_address: str) -> None:
        self._chain = chain
        self._wallet_address = wallet_address

    def _build_compiler(self) -> IntentCompiler:
        return IntentCompiler(
            chain=self._chain,
            wallet_address=self._wallet_address,
            config=IntentCompilerConfig(allow_placeholder_prices=True),
            rpc_url=None,
        )

    def generate_deleverage_action_bundle(
        self,
        *,
        protocol: str,
        token: str,
        amount: Decimal,
        repay_full: bool = False,
        observed_hf: Decimal | None = None,
        target_hf: Decimal | None = None,
        trigger_reason: str = "health_factor_below_threshold",
    ) -> ActionBundleResult:
        """Given a breached-position decision, compile the real Almanak DeleverageIntent.

        This is the exact call shape used to produce the real, executed
        DELEVA proof transaction (0xd36217b0...) -- see
        DELEVA_TRANSACTION_PROOF.md. Raises AlmanakCompilationError if the
        real compiler reports failure; never falls back to fabricated
        calldata.
        """
        intent = DeleverageIntent(
            protocol=protocol,
            token=token,
            amount=amount,
            repay_full=repay_full,
            chain=self._chain,
            trigger_reason=trigger_reason,
            observed_hf=observed_hf,
            target_hf=target_hf,
        )
        result = self._build_compiler().compile(intent)
        if result.status != CompilationStatus.SUCCESS or result.action_bundle is None:
            raise AlmanakCompilationError(
                f"Almanak failed to compile DeleverageIntent({protocol=}, {token=}, {amount=}): {result.error}"
            )
        bundle = result.action_bundle
        return ActionBundleResult(
            intent_id=intent.intent_id,
            intent_type=bundle.intent_type,
            transactions=list(bundle.transactions),
            metadata=dict(bundle.metadata),
        )
