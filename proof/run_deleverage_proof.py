"""Local proof, part 3: a REAL (non-mocked) Aave V3 DELEVERAGE ActionBundle on Base,
decoded and translated into KeeperHub contract-call requests.

Still: no RPC, no funds, no signer/gateway, no network call to KeeperHub.

Why DeleverageIntent(aave_v3, USDC, base): this is DELEVA's actual product
transaction (risk-guard forced repay), not a hand-picked toy. IntentType.DELEVERAGE
routes through the identical compiler path as IntentType.REPAY
(almanak/framework/intents/compiler.py: DELEVERAGE -> _compile_repay ->
_compile_lending_via_registry(intent, "REPAY") -> aave_v3 connector's
_compile_repay_aave_compatible), so the ActionBundle below is exactly what a
real risk-management strategy would emit when health factor crosses its
danger threshold.

NOTE on wallet_address: this script compiles with the same placeholder wallet
used by proof/run_proof.py, for structural inspection only (selectors, ABI
shapes, transaction count). The repay leg's `onBehalfOf` argument is baked in
at compile time from `wallet_address` -- for a REAL broadcast, this must be
recompiled with KeeperHub's actual organization wallet address (the one that
actually holds the Aave debt being repaid), not this placeholder. That
recompilation happens separately, only after the organization wallet address
and an existing real debt position have been confirmed.
"""

from __future__ import annotations

import json
from decimal import Decimal

from almanak.framework.intents import IntentCompiler, IntentCompilerConfig, DeleverageIntent
from almanak.framework.intents.compiler_models import CompilationStatus

from keeperhub_adapter import almanak_tx_to_keeperhub_request, decode_calldata

DUMMY_WALLET = "0x000000000000000000000000000000000000dEaD"


def main() -> None:
    print("=" * 80)
    print("STEP 1: Intent -- DeleverageIntent(USDC, aave_v3, base)")
    print("=" * 80)
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
    print(repr(intent))
    print(f"intent_type: {intent.intent_type}")

    print()
    print("=" * 80)
    print("STEP 2: IntentCompiler.compile() -- OFFLINE, no RPC, no gateway client")
    print("=" * 80)
    compiler = IntentCompiler(
        chain="base",
        wallet_address=DUMMY_WALLET,
        config=IntentCompilerConfig(allow_placeholder_prices=True),
        rpc_url=None,
    )
    result = compiler.compile(intent)
    assert result.status == CompilationStatus.SUCCESS, f"compile failed: {result.error}"
    bundle = result.action_bundle
    assert bundle is not None

    print(f"CompilationStatus: {result.status.value}")
    print("Real ActionBundle.to_dict() (unmodified, straight from the SDK):")
    print(json.dumps(bundle.to_dict(), indent=2))

    assert len(bundle.transactions) == 2, f"expected 2 transactions (approve + repay), got {len(bundle.transactions)}"
    assert bundle.intent_type == "REPAY", "DELEVERAGE must route through the same on-chain path as REPAY"

    print()
    print("=" * 80)
    print("STEP 3: decode each tx's calldata back to (functionName, args, abi)")
    print("=" * 80)
    for i, tx in enumerate(bundle.transactions):
        decoded = decode_calldata(tx["data"])
        print(f"\n--- tx[{i}] tx_type={tx['tx_type']!r} to={tx['to']} ---")
        print(f"  value:         {tx['value']}")
        print(f"  gas_estimate:  {tx['gas_estimate']}")
        print(f"  description:   {tx['description']}")
        print(f"  selector:      {decoded.selector}")
        print(f"  functionName:  {decoded.function_name}")
        print(f"  functionArgs:  {decoded.function_args_json()}")
        reencoded = decoded.reencode()
        assert reencoded == tx["data"], (
            f"round-trip mismatch on tx[{i}]: reencoded {reencoded} != original {tx['data']}"
        )
        print("  round-trip re-encode == original calldata: OK")

    assert bundle.transactions[1]["data"][:10] == "0x573ade81", "repay selector must be 0x573ade81"

    print()
    print("=" * 80)
    print("STEP 4: exact KeeperHub contract-call request per transaction")
    print("=" * 80)
    keeperhub_requests = [
        almanak_tx_to_keeperhub_request(tx, chain=bundle.metadata["chain"], simulate=True) for tx in bundle.transactions
    ]
    for i, body in enumerate(keeperhub_requests):
        print(f"\n--- KeeperHub request for tx[{i}] ({bundle.transactions[i]['tx_type']}) ---")
        print(json.dumps(body, indent=2))

    print()
    print("NOTE: no network call was made. Nothing was sent to KeeperHub or to any RPC.")
    print("NOTE: onBehalfOf in tx[1] is the placeholder wallet above, not an organization wallet.")


if __name__ == "__main__":
    main()
