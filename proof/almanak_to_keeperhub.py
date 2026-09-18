"""Local, offline proof: Almanak Intent -> ActionBundle -> KeeperHub contract-call body.

Scope (intentionally minimal, per the hackathon technical-proof requirement):
  - No real funds. No mainnet transaction. No RPC call. No signer/gateway.
  - We call Almanak's own `IntentCompiler.compile()` and stop there -- the
    ActionBundle it returns is a plain dataclass; nothing has been signed or
    submitted. Almanak's ExecutionOrchestrator (the thing that actually signs
    and broadcasts) is never constructed.
  - We do NOT call KeeperHub's live API in this script. We only prove that a
    real Almanak-compiled transaction can be losslessly translated into the
    exact JSON body KeeperHub's documented `POST /api/execute/contract-call`
    endpoint expects (schema taken verbatim from docs.keeperhub.com).

Why WrapNativeIntent: it is the simplest real DeFi action in the SDK -- it
compiles to exactly one transaction, with a fixed, argument-less selector
(`deposit()`), so translating its calldata into KeeperHub's
{functionName, functionArgs, abi} shape requires no generic calldata decoder.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from almanak.framework.intents import IntentCompiler, IntentCompilerConfig, WrapNativeIntent
from almanak.framework.intents.compiler_models import CompilationStatus

BASE_CHAIN_ID = 8453

# A dummy address is fine: we never touch a wallet, sign anything, or read
# on-chain state. IntentCompilerConfig(allow_placeholder_prices=True) plus no
# rpc_url means the compiler never makes a network call for this intent type.
DUMMY_WALLET = "0x000000000000000000000000000000000000dEaD"

WETH_DEPOSIT_ABI_FRAGMENT = json.dumps(
    [
        {
            "inputs": [],
            "name": "deposit",
            "outputs": [],
            "stateMutability": "payable",
            "type": "function",
        }
    ]
)


@dataclass
class UnsupportedCalldata(Exception):
    tx_type: str
    data: str

    def __str__(self) -> str:
        return (
            f"No known ABI mapping for tx_type={self.tx_type!r} data={self.data!r}. "
            "This adapter only knows the WETH deposit() selector; it does not "
            "generically decode arbitrary Almanak calldata."
        )


def almanak_tx_to_keeperhub_contract_call(tx: dict[str, Any], *, chain_id: int, simulate: bool = True) -> dict[str, Any]:
    """Translate one Almanak ``TransactionData`` dict into a KeeperHub
    ``POST /api/execute/contract-call`` request body.

    Almanak's ActionBundle carries already-ABI-encoded calldata (`data`), with
    no function name/args/ABI alongside it. KeeperHub's contract-call endpoint
    takes the inverse shape: {functionName, functionArgs, abi} which it
    encodes itself -- there is no raw-calldata field in KeeperHub's documented
    API. So this adapter has to know, per selector, how to go from calldata
    back to a named call. It currently knows exactly one: WETH `deposit()`.
    """
    data = tx["data"]
    selector = data[:10]  # "0x" + 4 bytes

    if selector == "0xd0e30db0" and tx["tx_type"] == "wrap":
        function_name = "deposit"
        function_args = "[]"
        abi = WETH_DEPOSIT_ABI_FRAGMENT
    else:
        raise UnsupportedCalldata(tx_type=tx["tx_type"], data=data)

    value_wei = int(tx["value"])
    value_ether_str = str(Decimal(value_wei) / Decimal(10**18))

    body: dict[str, Any] = {
        "contractAddress": tx["to"],
        "chainId": chain_id,
        "functionName": function_name,
        "functionArgs": function_args,
        "abi": abi,
        "value": value_ether_str,
    }
    if simulate:
        body["simulate"] = True
    return body


def main() -> None:
    print("=" * 80)
    print("STEP 1: Strategy layer -> Intent")
    print("=" * 80)
    intent = WrapNativeIntent(token="WETH", amount=Decimal("0.001"), chain="base")
    print(f"Intent: {intent!r}")

    print()
    print("=" * 80)
    print("STEP 2: Intent -> ActionBundle (IntentCompiler.compile) -- OFFLINE, no RPC")
    print("=" * 80)
    compiler = IntentCompiler(
        chain="base",
        wallet_address=DUMMY_WALLET,
        config=IntentCompilerConfig(allow_placeholder_prices=True),
        rpc_url=None,
    )
    result = compiler.compile(intent)

    assert result.status == CompilationStatus.SUCCESS, f"Compilation failed: {result.error}"
    assert result.action_bundle is not None

    bundle = result.action_bundle
    print(f"CompilationStatus: {result.status.value}")
    print("ActionBundle.to_dict():")
    print(json.dumps(bundle.to_dict(), indent=2))

    assert len(bundle.transactions) == 1, "expected exactly one transaction from WRAP_NATIVE"
    almanak_tx = bundle.transactions[0]

    print()
    print("=" * 80)
    print("STEP 3 (interception point): stop BEFORE Almanak's signer/gateway")
    print("=" * 80)
    print(
        "No ExecutionOrchestrator was constructed. No Signer/Submitter/Simulator "
        "exist in this process. `almanak_tx` below is the exact unsigned "
        "transaction Almanak produced, exported as plain data:"
    )
    print(json.dumps(almanak_tx, indent=2))

    print()
    print("=" * 80)
    print("STEP 4: our adapter -> KeeperHub contract-call request body")
    print("=" * 80)
    keeperhub_body = almanak_tx_to_keeperhub_contract_call(almanak_tx, chain_id=BASE_CHAIN_ID, simulate=True)
    print(json.dumps(keeperhub_body, indent=2))

    print()
    print("NOTE: this script does not call any KeeperHub API. It only proves the")
    print("structural translation. No network call, no API key, no funds.")


if __name__ == "__main__":
    main()
