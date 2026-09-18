"""Builds the API's shared application state from real DelevaConfig/deleva
components exactly once at startup. No business logic lives here -- this
module only wires Phase 1/2 objects together and records whether real
execution credentials are configured.

If KEEPERHUB_API_KEY or DELEVA_MONITORED_WALLET are missing, the app still
starts (so /api/health always works), but every data endpoint that needs
real chain access reports itself explicitly unavailable rather than
crashing or fabricating data.
"""

from __future__ import annotations

from dataclasses import dataclass

from deleva.activity import ActivityEvent, ActivityLog, real_deleva_proof_events
from deleva.almanak_interface import AlmanakStrategyInterface
from deleva.config import ConfigError, DelevaConfig
from deleva.engine import AutonomousEngine, CycleResult
from deleva.keeperhub_client import KeeperHubClient
from deleva.position_service import AavePositionService
from deleva.risk import RiskEvaluator
from deleva.runner import MonitoringRunner
from deleva.strategy import DelevaStrategy


@dataclass
class AppState:
    config: DelevaConfig
    strategy: DelevaStrategy
    configuration_error: str | None
    engine: AutonomousEngine | None
    runner: MonitoringRunner | None
    position_service: AavePositionService | None
    historical_activity: list[ActivityEvent]
    last_cycle: CycleResult | None = None

    @property
    def is_configured(self) -> bool:
        return self.engine is not None


def build_app_state() -> AppState:
    config = DelevaConfig.from_env()
    strategy = DelevaStrategy.default(config)
    historical_activity = real_deleva_proof_events()

    try:
        config.require_monitored_wallet()
        api_key = config.require_keeperhub_api_key()
    except ConfigError as exc:
        return AppState(
            config=config,
            strategy=strategy,
            configuration_error=str(exc),
            engine=None,
            runner=None,
            position_service=None,
            historical_activity=historical_activity,
        )

    keeperhub_client = KeeperHubClient(api_key, base_url=config.keeperhub_api_base)
    position_service = AavePositionService(keeperhub_client, config)
    risk_evaluator = RiskEvaluator(trigger_threshold=strategy.trigger_health_factor)
    almanak_interface = AlmanakStrategyInterface(chain=strategy.chain, wallet_address=config.monitored_wallet)

    engine = AutonomousEngine(
        config=config,
        strategy=strategy,
        position_service=position_service,
        risk_evaluator=risk_evaluator,
        almanak_interface=almanak_interface,
        keeperhub_client=keeperhub_client,
        activity_log=ActivityLog(),
        # execution_mode intentionally omitted -- derived from
        # DELEVA_EXECUTION_DRY_RUN, which defaults true. The API never
        # overrides this.
    )
    runner = MonitoringRunner(engine, interval_seconds=config.monitoring_interval_seconds)

    return AppState(
        config=config,
        strategy=strategy,
        configuration_error=None,
        engine=engine,
        runner=runner,
        position_service=position_service,
        historical_activity=historical_activity,
    )
