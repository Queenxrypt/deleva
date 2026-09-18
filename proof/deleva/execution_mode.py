"""Explicit execution modes for AutonomousEngine.

DRY_RUN is the only mode allowed by default. LIVE requires the operator to
explicitly set ``DELEVA_EXECUTION_DRY_RUN=false`` -- there is no code path in
this module (or in ``ExecutionMode.from_config``) that ever produces LIVE on
its own. DEMO exists purely so ``deleva/demo.py`` never has to mislabel its
fully-mocked walkthrough as LIVE (see DEMO's docstring below) -- it is never
returned by ``from_config`` and is only ever constructed explicitly by demo
code.
"""

from __future__ import annotations

from enum import Enum

from deleva.config import DelevaConfig


class ExecutionMode(str, Enum):
    #: Runs the full real pipeline (real position read, real Almanak
    #: compile, real KeeperHub *simulate*) but never calls execute. Records
    #: what WOULD happen.
    DRY_RUN = "DRY_RUN"

    #: Real execution against the real, configured KeeperHubClient. The only
    #: mode ``ExecutionMode.from_config`` ever produces when
    #: ``DELEVA_EXECUTION_DRY_RUN=false`` -- i.e. the only mode reachable
    #: from real environment configuration.
    LIVE = "LIVE"

    #: Deterministic local demo mode (see ``deleva/demo.py``). Control-flow
    #: identical to LIVE (both are "not DRY_RUN", so both simulate *and*
    #: execute each leg) -- the actual safety boundary was always which
    #: ``KeeperHubClient`` instance the engine was built with, never this
    #: label. DEMO is constructed exclusively by ``deleva.demo`` against
    #: ``DemoKeeperHubClient`` (an in-memory fake with no network path);
    #: neither ``api/state.py`` nor ``deleva/cli.py`` (the two real
    #: engine-construction paths) ever produce it. Exists so a demo cycle's
    #: own ``execution_mode`` field never reports itself as "LIVE".
    DEMO = "DEMO"

    @classmethod
    def from_config(cls, config: DelevaConfig) -> "ExecutionMode":
        """Derives a mode from real environment configuration. Never returns
        DEMO -- DEMO is only ever set explicitly by deleva/demo.py."""
        return cls.DRY_RUN if config.execution_dry_run else cls.LIVE
