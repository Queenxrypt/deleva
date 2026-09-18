"""Thin CLI for operating AutonomousEngine locally.

Contains no business logic -- every command builds the real components from
DelevaConfig.from_env() (or, for ``demo``, the fully-mocked demo builder) and
calls into AutonomousEngine / MonitoringRunner. Safety follows directly from
DelevaConfig: DELEVA_EXECUTION_DRY_RUN defaults to true, so every command
below is safe-by-default unless an operator explicitly sets it to false in
their own environment. Nothing in this file flips that itself.

Usage:
    python -m deleva status
    python -m deleva once
    python -m deleva dry-run
    python -m deleva start
    python -m deleva stop
    python -m deleva demo
"""

from __future__ import annotations

import argparse
import sys

from deleva.activity import ActivityLog
from deleva.almanak_interface import AlmanakStrategyInterface
from deleva.config import ConfigError, DelevaConfig
from deleva.engine import AutonomousEngine, CycleResult
from deleva.execution_mode import ExecutionMode
from deleva.keeperhub_client import KeeperHubClient
from deleva.persistence import JsonFilePersistence
from deleva.position_service import AavePositionService
from deleva.risk import RiskEvaluator
from deleva.runner import MonitoringRunner
from deleva.strategy import DelevaStrategy

DEFAULT_STATE_FILE = ".deleva_state.json"


def build_engine_from_env(*, execution_mode: ExecutionMode | None = None) -> AutonomousEngine:
    """Build a real AutonomousEngine from environment configuration.

    Requires KEEPERHUB_API_KEY and DELEVA_MONITORED_WALLET to be set --
    raises ConfigError with a clear message otherwise (never falls back to a
    fake wallet or a fake key).
    """
    config = DelevaConfig.from_env()
    config.require_monitored_wallet()
    api_key = config.require_keeperhub_api_key()

    strategy = DelevaStrategy.default(config)
    keeperhub_client = KeeperHubClient(api_key, base_url=config.keeperhub_api_base)
    position_service = AavePositionService(keeperhub_client, config)
    risk_evaluator = RiskEvaluator(trigger_threshold=strategy.trigger_health_factor)
    almanak_interface = AlmanakStrategyInterface(chain=strategy.chain, wallet_address=config.monitored_wallet)

    return AutonomousEngine(
        config=config,
        strategy=strategy,
        position_service=position_service,
        risk_evaluator=risk_evaluator,
        almanak_interface=almanak_interface,
        keeperhub_client=keeperhub_client,
        activity_log=ActivityLog(),
        execution_mode=execution_mode,  # None -> ExecutionMode.from_config(config)
        persistence=JsonFilePersistence(DEFAULT_STATE_FILE),
    )


def _print_cycle_result(result: CycleResult) -> None:
    print(f"engine_state:   {result.engine_state.value}")
    print(f"risk_state:     {result.risk_state.value}")
    print(f"execution_mode: {result.execution_mode.value}")
    print(f"triggered:      {result.triggered}")
    if result.skipped_reason:
        print(f"skipped:        {result.skipped_reason}")
    if result.action_bundle:
        print(f"action_bundle:  {len(result.action_bundle.transactions)} transaction(s)")
    for leg in result.leg_results:
        sim = leg.simulation
        sim_desc = "not simulated (DRY_RUN preview)" if sim is None else f"success={sim.success} wouldRevert={sim.would_revert}"
        exec_desc = "not executed" if leg.execution is None else f"status={leg.execution.status} tx={leg.execution.transaction_hash}"
        print(f"  leg[{leg.tx_type}]: simulate({sim_desc}) execute({exec_desc})")
    if result.verification:
        print(f"verification:   success={result.verification.success} -- {result.verification.reason}")
    print(f"overall_success: {result.overall_success}")
    if result.error:
        print(f"error:          {result.error}")
    print(f"activity_events_this_cycle: {len(result.activity_events)}")
    for event in result.activity_events:
        print(f"  [{event.event_type.value}] {event.description}")


def cmd_status(_args: argparse.Namespace) -> int:
    try:
        engine = build_engine_from_env()
    except ConfigError as exc:
        print(f"NOT CONFIGURED: {exc}")
        return 1
    print(f"engine_state:      {engine.state.value}")
    print(f"execution_mode:    {engine.execution_mode.value}")
    print(f"strategy:          {engine._strategy.name}")  # noqa: SLF001 -- CLI reads engine's own config for display only
    print(f"trigger_hf:        {engine._strategy.trigger_health_factor}")  # noqa: SLF001
    print(f"target_hf:         {engine._strategy.target_health_factor}")  # noqa: SLF001
    print(f"pending_execution: {engine._pending_execution_id}")  # noqa: SLF001
    return 0


def cmd_once(_args: argparse.Namespace) -> int:
    try:
        engine = build_engine_from_env()
    except ConfigError as exc:
        print(f"NOT CONFIGURED: {exc}")
        return 1
    result = MonitoringRunner(engine, interval_seconds=engine._config.monitoring_interval_seconds).run_once()  # noqa: SLF001
    _print_cycle_result(result)
    return 0 if result.overall_success else 1


def cmd_dry_run(_args: argparse.Namespace) -> int:
    try:
        engine = build_engine_from_env(execution_mode=ExecutionMode.DRY_RUN)
    except ConfigError as exc:
        print(f"NOT CONFIGURED: {exc}")
        return 1
    print("Running one cycle in DRY_RUN mode (never executes) ...")
    result = MonitoringRunner(engine, interval_seconds=0).run_once()
    _print_cycle_result(result)
    return 0


def cmd_start(_args: argparse.Namespace) -> int:
    try:
        engine = build_engine_from_env()
    except ConfigError as exc:
        print(f"NOT CONFIGURED: {exc}")
        return 1
    interval = engine._config.monitoring_interval_seconds  # noqa: SLF001
    runner = MonitoringRunner(engine, interval_seconds=interval)
    print(f"Starting monitoring loop (interval={interval}s, mode={engine.execution_mode.value}). Ctrl+C to stop.")
    try:
        runner.start()
    except KeyboardInterrupt:
        runner.stop()
        print("\nStopped.")
    return 0


def cmd_stop(_args: argparse.Namespace) -> int:
    print(
        "This CLI has no background daemon or IPC channel to a separately-running "
        "`start` process in this phase, so `stop` cannot reach one from here. "
        "A `start` process is a foreground loop -- stop it with Ctrl+C, which "
        "MonitoringRunner.stop() then shuts down gracefully (finishes the current "
        "cycle, then exits). A real background/daemon mode with a separate stop "
        "control channel is Phase 3 scope (API layer)."
    )
    return 0


def cmd_demo(_args: argparse.Namespace) -> int:
    from deleva.demo import run_local_demo

    print("Running deterministic local demo (3 cycles, mocked KeeperHub, no network, no real position). ")
    print("This is NOT the blockchain proof -- see DELEVA_TRANSACTION_PROOF.md for the real transaction.\n")
    results = run_local_demo()
    for i, result in enumerate(results, start=1):
        print(f"=== Cycle {i} ===")
        _print_cycle_result(result)
        print()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m deleva", description="DELEVA autonomous engine CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status", help="Show current engine configuration and state.").set_defaults(func=cmd_status)
    subparsers.add_parser("once", help="Run exactly one monitoring cycle.").set_defaults(func=cmd_once)
    subparsers.add_parser("dry-run", help="Run one cycle in DRY_RUN mode (never executes).").set_defaults(
        func=cmd_dry_run
    )
    subparsers.add_parser("start", help="Run the monitoring loop until Ctrl+C.").set_defaults(func=cmd_start)
    subparsers.add_parser("stop", help="Explain how to stop a running loop.").set_defaults(func=cmd_stop)
    subparsers.add_parser("demo", help="Run the deterministic local demo (mocked, no network).").set_defaults(
        func=cmd_demo
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
