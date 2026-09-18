"""Local proof, part 2: a REAL (non-mocked) Aave V3 SUPPLY ActionBundle on Base,
decoded and translated into KeeperHub contract-call requests.

Still: no RPC, no funds, no signer/gateway, no network call to KeeperHub.

Why Aave V3 SUPPLY on Base and not a hand-picked toy: it is the simplest
existing multi-step DeFi action already exercised by Almanak's own test suite
(tests/unit/intents/test_compiler_lending_supply.py exercises the same
dispatcher, albeit with a mocked compiler+calldata; here we run the REAL
IntentCompiler with real ABI-encoding, so the calldata below is exactly what
the SDK would produce for a live SUPPLY intent).
"""

from __future__ import annotations

import json
from decimal import Decimal

from almanak.framework.intents import IntentCompiler, IntentCompilerConfig, SupplyIntent
from almanak.framework.intents.compiler_models import CompilationStatus

from keeperhub_adapter import almanak_tx_to_keeperhub_request, decode_calldata

DUMMY_WALLET = "0x000000000000000000000000000000000000dEaD"


def main() -> None:
    print("=" * 80)
    print("STEP 1: Intent -- SupplyIntent(USDC, 100, aave_v3, base)")
    print("=" * 80)
    intent = SupplyIntent(
        token="USDC",
        amount=Decimal("100"),
        protocol="aave_v3",
        chain="base",
    )
    print(repr(intent))

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

    print()
    print("=" * 80)
    print("STEP 3: is functionName / functionArgs / ABI available anywhere on the bundle?")
    print("=" * 80)
    tx_keys = set()
    for tx in bundle.transactions:
        tx_keys.update(tx.keys())
    print(f"Keys present on every transaction dict: {sorted(tx_keys)}")
    print(f"Keys present on bundle.metadata: {sorted(bundle.metadata.keys())}")
    for forbidden in ("functionName", "functionArgs", "abi", "function_name", "function_args"):
        assert forbidden not in tx_keys, f"unexpectedly found {forbidden!r} on a transaction"
        assert forbidden not in bundle.metadata, f"unexpectedly found {forbidden!r} on bundle.metadata"
    print(
        "CONFIRMED: none of functionName / functionArgs / abi appear anywhere "
        "on the real ActionBundle. `tx_type` + free-text `description` are the "
        "only hints; the actual encoding logic (and the function name it used) "
        "lives only in almanak/framework/intents/compiler_adapters.py::AaveV3Adapter "
        "and is discarded once calldata is produced."
    )

    print()
    print("=" * 80)
    print("STEP 4: decode each tx's calldata back to (functionName, args, abi)")
    print("=" * 80)
    for i, tx in enumerate(bundle.transactions):
        decoded = decode_calldata(tx["data"])
        print(f"\n--- tx[{i}] tx_type={tx['tx_type']!r} to={tx['to']} ---")
        print(f"  selector:      {decoded.selector}")
        print(f"  functionName:  {decoded.function_name}")
        print(f"  functionArgs:  {decoded.function_args_json()}")
        reencoded = decoded.reencode()
        assert reencoded == tx["data"], (
            f"round-trip mismatch on tx[{i}]: reencoded {reencoded} != original {tx['data']}"
        )
        print("  round-trip re-encode == original calldata: OK")

    print()
    print("=" * 80)
    print("STEP 5: exact KeeperHub contract-call request per transaction")
    print("=" * 80)
    keeperhub_requests = [
        almanak_tx_to_keeperhub_request(tx, chain=bundle.metadata["chain"], simulate=True) for tx in bundle.transactions
    ]
    for i, body in enumerate(keeperhub_requests):
        print(f"\n--- KeeperHub request for tx[{i}] ({bundle.transactions[i]['tx_type']}) ---")
        print(json.dumps(body, indent=2))

    print()
    print("NOTE: no network call was made. Nothing was sent to KeeperHub or to any RPC.")


if __name__ == "__main__":
    main()
