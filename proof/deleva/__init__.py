"""DELEVA backend foundation.

Reusable components for the Almanak -> DELEVA adapter -> KeeperHub -> Aave V3
pipeline that Phase 1 established and proved with a real Base mainnet
transaction (see ../DELEVA_TRANSACTION_PROOF.md).

This package intentionally does NOT run anything on import: no scheduler, no
background thread, no network call. Phase 2 composes these pieces into the
actual monitor -> evaluate -> decide -> compile -> simulate -> execute ->
verify loop.

Importing this package must work regardless of the current working
directory, so it puts the ``proof/`` directory (its own parent, where the
existing, already-proven ``keeperhub_adapter.py`` lives) on ``sys.path`` if
it isn't there already. This mirrors the defensive sys.path pattern already
used elsewhere in this project (e.g. scratch/live_simulate_once.py) rather
than introducing a new import mechanism.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROOF_DIR = str(Path(__file__).resolve().parent.parent)
if _PROOF_DIR not in sys.path:
    sys.path.insert(0, _PROOF_DIR)
