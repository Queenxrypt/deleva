"""Reusable entry point to DELEVA's existing ActionBundle -> KeeperHub adapter.

The actual translation logic lives in ``keeperhub_adapter.py`` (project
root: ``proof/keeperhub_adapter.py``), unchanged -- it is already a plain,
reusable module (not proof-script-specific), already imported by
``run_proof.py``, ``run_deleverage_proof.py``, and the full test suite in
``test_adapter.py``. This module does not duplicate that logic; it re-exports
it under the ``deleva`` namespace so Phase 2 code has one consistent import
path (``from deleva.adapter import ...``) instead of reaching past the
package boundary, and adds one small, genuine convenience: translating an
entire ActionBundle's transaction list in one call instead of every caller
looping by hand.
"""

from __future__ import annotations

from typing import Any

from keeperhub_adapter import (
    CHAIN_ID_BY_ALMANAK_CHAIN,
    AbiEntry,
    DecodedCall,
    UnsupportedCalldata,
    almanak_tx_to_keeperhub_request,
    decode_calldata,
)

__all__ = [
    "CHAIN_ID_BY_ALMANAK_CHAIN",
    "AbiEntry",
    "DecodedCall",
    "UnsupportedCalldata",
    "almanak_tx_to_keeperhub_request",
    "decode_calldata",
    "translate_action_bundle",
]


def translate_action_bundle(
    transactions: list[dict[str, Any]], *, chain: str, simulate: bool = True
) -> list[dict[str, Any]]:
    """Translate every transaction in an ActionBundle into a KeeperHub contract-call request.

    Preserves transaction order (execution order matters -- e.g. approve
    must precede repay). Raises ``UnsupportedCalldata`` immediately if any
    transaction's selector isn't registered, rather than silently skipping
    it.
    """
    return [almanak_tx_to_keeperhub_request(tx, chain=chain, simulate=simulate) for tx in transactions]
