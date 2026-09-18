"""DELEVA backend API.

    API routes
        v
    existing deleva/ services (AavePositionService, RiskEvaluator,
    AutonomousEngine, ActivityLog, DelevaStrategy)
        v
    real Aave V3 / KeeperHub / Almanak data

No route constructs a KeeperHub or Almanak request itself, computes a risk
threshold, or duplicates strategy constants -- every response is built from
an existing Phase 1/2 object. The KeeperHub API key is held only inside
KeeperHubClient (constructed once in api/state.py) and is never read by, or
returned from, any route.

Run locally:
    uvicorn api.main:app --reload --port 8000
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from deleva.demo import run_local_demo
from deleva.engine import CycleResult
from deleva.position_service import PositionRetrievalError
from deleva.runner import RunnerBusyError

from api.schemas import (
    ActivityResponse,
    DemoCycleResponse,
    DemoRunResponse,
    EngineStatusResponse,
    HealthResponse,
    PositionResponse,
    StrategyResponse,
    activity_event_to_response,
    cycle_result_to_summary,
    position_to_response,
    position_unavailable,
    strategy_to_response,
)
from api.state import AppState, build_app_state


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    yield
    # Best-effort graceful shutdown of the background monitoring loop, if one
    # was started. The loop's thread is a daemon, so process exit is never
    # blocked by it regardless -- this just gives it a short, bounded window
    # to finish its current cycle and exit cleanly first.
    if state.runner is not None:
        state.runner.stop(wait=True, timeout=5.0)


app = FastAPI(title="DELEVA API", version="1.0.0", lifespan=_lifespan)

# Local development only, by default -- see README "Security" section
# before deploying anywhere this would matter.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

state: AppState = build_app_state()


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


@app.get("/api/position", response_model=PositionResponse)
def get_position() -> PositionResponse:
    if not state.is_configured or state.position_service is None:
        return position_unavailable(state.configuration_error or "DELEVA is not configured.")
    try:
        position = state.position_service.get_position()
        usdc_balance = state.position_service.get_usdc_balance()
    except PositionRetrievalError as exc:
        return position_unavailable(str(exc))
    except Exception as exc:  # noqa: BLE001 -- a KeeperHub/network failure is a real "unavailable", not a 500
        return position_unavailable(f"Position read failed: {exc}")
    return position_to_response(position, usdc_balance)


@app.get("/api/strategy", response_model=StrategyResponse)
def get_strategy() -> StrategyResponse:
    return strategy_to_response(state.strategy)


@app.get("/api/engine/status", response_model=EngineStatusResponse)
def get_engine_status() -> EngineStatusResponse:
    if not state.is_configured or state.engine is None:
        return EngineStatusResponse(
            configured=False,
            configuration_error=state.configuration_error,
            container_state=None,
            engine_state=None,
            execution_mode=None,
            pending_execution_id=None,
            monitoring_interval_seconds=None,
            runner_error=None,
        )
    engine = state.engine
    return EngineStatusResponse(
        configured=True,
        configuration_error=None,
        container_state=engine._container_state.value,  # noqa: SLF001 -- API surfaces this deliberately
        engine_state=engine.state.value,
        execution_mode=engine.execution_mode.value,
        pending_execution_id=engine._pending_execution_id,  # noqa: SLF001
        monitoring_interval_seconds=state.config.monitoring_interval_seconds,
        last_cycle=cycle_result_to_summary(state.last_cycle) if state.last_cycle else None,
        runner_error=state.runner.last_error if state.runner is not None else None,
    )


@app.get("/api/activity", response_model=ActivityResponse)
def get_activity() -> ActivityResponse:
    events = [
        activity_event_to_response(event, source="historical_proof") for event in state.historical_activity
    ]
    if state.engine is not None:
        events += [activity_event_to_response(event, source="live") for event in state.engine.activity_log.all()]
    events.sort(key=lambda e: e.timestamp)
    return ActivityResponse(events=events)


@app.post("/api/engine/run-once", response_model=EngineStatusResponse)
def run_once() -> EngineStatusResponse:
    """Runs exactly one real monitoring cycle against the real configured
    position, through the real engine. Safe by construction: execution_mode
    defaults to DRY_RUN (see deleva.config.DelevaConfig) and this endpoint
    never overrides it -- a LIVE broadcast requires the operator to have
    already set DELEVA_EXECUTION_DRY_RUN=false in the backend's own
    environment before the process started.

    409 if the autonomous loop (see /api/engine/start) is already running --
    a manual cycle and the loop are never allowed to run concurrently
    against the same engine instance (see deleva.runner.RunnerBusyError).
    """
    if not state.is_configured or state.engine is None or state.runner is None:
        raise HTTPException(status_code=409, detail=state.configuration_error or "DELEVA is not configured.")
    try:
        result: CycleResult = state.runner.run_once()
    except RunnerBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    state.last_cycle = result
    return get_engine_status()


@app.post("/api/engine/start", response_model=EngineStatusResponse)
def start_engine() -> EngineStatusResponse:
    """Starts the real MonitoringRunner on a background thread, against the
    same AutonomousEngine instance every other route reads -- this is the
    genuine autonomous loop (position -> Almanak -> ActionBundle -> KeeperHub
    -> verify), not a fake heartbeat. Idempotent: calling this while already
    running does nothing beyond returning the current (already RUNNING)
    status -- it never spawns a second loop.

    Never touches execution_mode. DRY_RUN vs LIVE is decided once, at
    process startup, from DELEVA_EXECUTION_DRY_RUN (see api/state.py) -- this
    route has no code path that can change it.
    """
    if not state.is_configured or state.runner is None:
        raise HTTPException(status_code=409, detail=state.configuration_error or "DELEVA is not configured.")
    state.runner.start_in_background()
    return get_engine_status()


@app.post("/api/engine/stop", response_model=EngineStatusResponse)
def stop_engine() -> EngineStatusResponse:
    """Stops the real MonitoringRunner. Graceful (finishes any in-flight
    cycle first) and safe to call when already stopped."""
    if not state.is_configured or state.runner is None:
        raise HTTPException(status_code=409, detail=state.configuration_error or "DELEVA is not configured.")
    state.runner.stop()
    return get_engine_status()


@app.post("/api/demo/run", response_model=DemoRunResponse)
def run_demo() -> DemoRunResponse:
    """Runs the deterministic, fully-mocked local demo (see deleva/demo.py).
    Never touches the network, never touches the real position, and never
    appends to the real engine's activity log -- demo output is returned
    directly and kept entirely separate from live/historical data."""
    results = run_local_demo()
    cycles = [
        DemoCycleResponse(
            cycle_number=i,
            summary=cycle_result_to_summary(result),
            events=[activity_event_to_response(event, source="demo") for event in result.activity_events],
        )
        for i, result in enumerate(results, start=1)
    ]
    return DemoRunResponse(cycles=cycles)
