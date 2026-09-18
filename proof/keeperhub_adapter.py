"""Adapter: Almanak ``ActionBundle`` transactions -> KeeperHub contract-call requests.

Why this file exists (VIB-free, plain English):

Almanak's ``TransactionData`` (see almanak/framework/intents/compiler_models.py in
the Almanak SDK) carries only ``to``, ``value``, and already-ABI-encoded ``data``.
Neither ``TransactionData`` nor the surrounding ``ActionBundle.metadata`` carries a
function name, decoded arguments, or an ABI fragment anywhere -- confirmed by
reading the real dataclass fields and by inspecting a real compiled bundle at
runtime (see run_proof.py). The only place that information lives is in the
*source code* of the connector adapter that built the calldata in the first
place (e.g. ``almanak.framework.intents.compiler_adapters.AaveV3Adapter``),
which hand-encodes each call with a hardcoded 4-byte selector plus manually
padded arguments and then throws the function name away.

KeeperHub's ``POST /api/execute/contract-call`` (docs.keeperhub.com/api/direct-execution)
wants the inverse shape: ``functionName`` + ``functionArgs`` + ``abi``, and encodes
the call itself. There is no raw-calldata field anywhere in KeeperHub's documented
API.

So bridging the two requires a calldata decoder keyed by 4-byte selector. This
module is that decoder, for exactly the selectors that show up in the two
concrete Almanak actions we've verified end-to-end so far:

  - 0xd0e30db0  WETH  deposit()                                          (0 args)
  - 0x095ea7b3  ERC20 approve(address,uint256)
  - 0x617ba037  Aave V3 Pool  supply(address,uint256,address,uint16)
  - 0x5a3b74b9  Aave V3 Pool  setUserUseReserveAsCollateral(address,bool)
  - 0x573ade81  Aave V3 Pool  repay(address,uint256,uint256,address)
  - 0xa415bcad  Aave V3 Pool  borrow(address,uint256,uint256,uint16,address)

Every selector below is INDEPENDENTLY computed here via keccak256 of the
canonical Solidity function signature (not copied from Almanak's internal
constants) and asserted to match what the real compiler produced -- see
test_adapter.py.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from eth_abi import decode as abi_decode
from eth_abi import encode as abi_encode
from eth_utils import keccak, to_checksum_address

# Chain-name -> EIP-155 chain id. Base = 8453 per KeeperHub's own docs
# (docs.keeperhub.com/agent/mcp-server) and per Almanak's chain registry.
CHAIN_ID_BY_ALMANAK_CHAIN = {
    "base": 8453,
    "ethereum": 1,
    "arbitrum": 42161,
}


@dataclass(frozen=True)
class AbiEntry:
    name: str
    arg_types: tuple[str, ...]
    arg_names: tuple[str, ...]
    state_mutability: str  # "payable" | "nonpayable" | "view"

    @property
    def signature(self) -> str:
        return f"{self.name}({','.join(self.arg_types)})"

    @property
    def selector(self) -> str:
        return "0x" + keccak(text=self.signature).hex()[:8]

    def abi_json_fragment(self) -> str:
        return json.dumps(
            [
                {
                    "inputs": [{"name": n, "type": t} for n, t in zip(self.arg_names, self.arg_types, strict=True)],
                    "name": self.name,
                    "outputs": [],
                    "stateMutability": self.state_mutability,
                    "type": "function",
                }
            ]
        )


# Registered ABIs, keyed by their independently-derived 4-byte selector.
_REGISTRY: dict[str, AbiEntry] = {
    entry.selector: entry
    for entry in (
        AbiEntry("deposit", (), (), "payable"),
        AbiEntry("approve", ("address", "uint256"), ("spender", "amount"), "nonpayable"),
        AbiEntry(
            "supply",
            ("address", "uint256", "address", "uint16"),
            ("asset", "amount", "onBehalfOf", "referralCode"),
            "nonpayable",
        ),
        AbiEntry(
            "setUserUseReserveAsCollateral",
            ("address", "bool"),
            ("asset", "useAsCollateral"),
            "nonpayable",
        ),
        AbiEntry(
            "repay",
            ("address", "uint256", "uint256", "address"),
            ("asset", "amount", "interestRateMode", "onBehalfOf"),
            "nonpayable",
        ),
        AbiEntry(
            "borrow",
            ("address", "uint256", "uint256", "uint16", "address"),
            ("asset", "amount", "interestRateMode", "referralCode", "onBehalfOf"),
            "nonpayable",
        ),
    )
}


@dataclass
class UnsupportedCalldata(Exception):
    data: str

    def __str__(self) -> str:
        return (
            f"No registered ABI for selector {self.data[:10]!r}. "
            "This adapter only decodes the selectors it has been explicitly "
            "given an ABI for; it does not guess."
        )


@dataclass
class DecodedCall:
    function_name: str
    arg_types: tuple[str, ...]
    arg_values: tuple[Any, ...]
    abi_json: str
    selector: str

    def function_args_json(self) -> str:
        """Render args as the JSON-array-string KeeperHub's ``functionArgs`` expects.

        KeeperHub's own docs examples always render address/uint256 args as
        quoted strings inside the array (e.g. '["0x...", "1000"]') -- so we
        stringify every scalar. Only the one non-scalar case we have
        (`bool`) is emitted as a native JSON boolean, since KeeperHub's docs
        do not show a bool example either way and `true`/`false` is the
        unambiguous ABI-JSON convention.
        """
        rendered: list[Any] = []
        for typ, val in zip(self.arg_types, self.arg_values, strict=True):
            if typ == "address":
                rendered.append(to_checksum_address(val))
            elif typ == "bool":
                rendered.append(bool(val))
            else:  # uintN / intN
                rendered.append(str(val))
        return json.dumps(rendered)

    def reencode(self) -> str:
        """Re-encode (selector, args) and return calldata -- used to prove the
        decode is lossless (round-trips back to the exact original bytes)."""
        body = abi_encode(list(self.arg_types), list(self.arg_values)) if self.arg_types else b""
        return self.selector + body.hex()


def decode_calldata(data: str) -> DecodedCall:
    """Decode ``0x<selector><args>`` using the local ABI registry.

    Raises UnsupportedCalldata if the selector isn't registered -- this
    adapter never guesses at an unknown function.
    """
    if not data.startswith("0x") or len(data) < 10:
        raise UnsupportedCalldata(data)
    selector = data[:10]
    entry = _REGISTRY.get(selector)
    if entry is None:
        raise UnsupportedCalldata(data)

    args_hex = data[10:]
    if entry.arg_types:
        values = abi_decode(list(entry.arg_types), bytes.fromhex(args_hex))
    else:
        values = ()

    return DecodedCall(
        function_name=entry.name,
        arg_types=entry.arg_types,
        arg_values=tuple(values),
        abi_json=entry.abi_json_fragment(),
        selector=selector,
    )


def almanak_tx_to_keeperhub_request(
    tx: dict[str, Any],
    *,
    chain: str,
    simulate: bool = True,
) -> dict[str, Any]:
    """Translate one Almanak ``TransactionData`` dict into a KeeperHub
    ``POST /api/execute/contract-call`` request body.

    Schema per docs.keeperhub.com/api/direct-execution ("Call Smart Contract"
    + "Dry-Run Simulation" sections), verbatim field names:
      contractAddress, chainId, functionName, functionArgs, abi, value, simulate
    """
    decoded = decode_calldata(tx["data"])

    value_wei = int(tx["value"])
    value_ether_str = str(Decimal(value_wei) / Decimal(10**18))

    chain_id = CHAIN_ID_BY_ALMANAK_CHAIN[chain]

    body: dict[str, Any] = {
        "contractAddress": to_checksum_address(tx["to"]),
        "chainId": chain_id,
        "functionName": decoded.function_name,
        "functionArgs": decoded.function_args_json(),
        "abi": decoded.abi_json,
        "value": value_ether_str,
    }
    if simulate:
        body["simulate"] = True
    return body
