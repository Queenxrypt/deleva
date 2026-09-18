"""API tests. No network access, no real KeeperHub/Almanak calls beyond the
real (offline, no-RPC) Almanak compile that FakeAlmanakInterface bypasses
entirely -- every route is exercised against a controlled AppState built
from the same Phase 2 test doubles used in tests/test_engine.py.
"""

from __future__ import annotations

import threading
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

import api.main as api_main
from api.schemas import REAL_PROOF_TX_HASH
from api.state import AppState

from deleva.activity import ActivityLog, real_deleva_proof_events
from deleva.config import DelevaConfig
from deleva.engine import AutonomousEngine
from deleva.risk import RiskEvaluator
from deleva.runner import MonitoringRunner
from deleva.strategy import DelevaStrategy

from fakes import DUMMY_WALLET, FakeAlmanakInterface, FakeKeeperHubClient, FakePositionService, make_position

FAKE_SECRET = "kh_test_secret_should_never_leak_9f3a"


def _unconfigured_state() -> AppState:
    config = DelevaConfig()
    return AppState(
        config=config,
        strategy=DelevaStrategy.default(config),
        configuration_error="DELEVA_MONITORED_WALLET is not set.",
        engine=None,
        runner=None,
        position_service=None,
        historical_activity=real_deleva_proof_events(),
    )


def _configured_state(
    *, health_factor=Decimal("2.0"), keeperhub_client=None, interval_seconds=1, sleep_fn=None
) -> AppState:
    config = DelevaConfig(
        monitored_wallet=DUMMY_WALLET,
        hf_trigger_threshold=Decimal("1.50"),
        keeperhub_api_key=FAKE_SECRET,
    )
    strategy = DelevaStrategy.default(config)
    position_service = FakePositionService([make_position(health_factor=health_factor)])
    engine = AutonomousEngine(
        config=config,
        strategy=strategy,
        position_service=position_service,
        risk_evaluator=RiskEvaluator(trigger_threshold=strategy.trigger_health_factor),
        almanak_interface=FakeAlmanakInterface(),
        keeperhub_client=keeperhub_client or FakeKeeperHubClient(),
        activity_log=ActivityLog(),
    )
    runner_kwargs = {"interval_seconds": interval_seconds}
    if sleep_fn is not None:
        runner_kwargs["sleep_fn"] = sleep_fn
    runner = MonitoringRunner(engine, **runner_kwargs)
    return AppState(
        config=config,
        strategy=strategy,
        configuration_error=None,
        engine=engine,
        runner=runner,
        position_service=position_service,
        historical_activity=real_deleva_proof_events(),
    )


@pytest.fixture
def unconfigured_client(monkeypatch):
    monkeypatch.setattr(api_main, "state", _unconfigured_state())
    return TestClient(api_main.app)


@pytest.fixture
def configured_client(monkeypatch):
    state = _configured_state()
    monkeypatch.setattr(api_main, "state", state)
    client = TestClient(api_main.app)
    client.deleva_state = state  # convenience handle for assertions
    yield client
    # Never leak a running background thread into the next test, even if
    # this test's own assertions failed before it could stop the runner.
    if state.runner is not None:
        state.runner.stop(wait=True, timeout=2.0)


@pytest.fixture
def fast_loop_client(monkeypatch):
    """A configured client whose background loop runs with no real delay --
    for tests that need at least one real background cycle to have happened."""
    ran_event = threading.Event()

    def sleep_and_signal(_seconds):
        ran_event.set()

    state = _configured_state(interval_seconds=0, sleep_fn=sleep_and_signal)
    monkeypatch.setattr(api_main, "state", state)
    client = TestClient(api_main.app)
    client.deleva_state = state
    client.ran_event = ran_event
    yield client
    if state.runner is not None:
        state.runner.stop(wait=True, timeout=2.0)


class _RaisingThenHealthyPositionService:
    """Raises an unexpected exception (simulating a real network/KeeperHub
    failure) on its first call, then behaves normally -- see
    tests/test_runner.py::RaisingThenHealthyPositionService for the same
    double used at the runner-unit level."""

    def __init__(self, position):
        self.calls = 0
        self._position = position

    def get_position(self, wallet=None):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("simulated transient KeeperHub/network failure")
        return self._position

    def get_usdc_balance(self, wallet=None):
        return Decimal("2.00")


@pytest.fixture
def flaky_loop_client(monkeypatch):
    """A configured client whose position service fails its first read, then
    succeeds -- for proving /api/engine/status exposes and then clears
    runner_error through real HTTP requests, end to end.

    Uses a two-way handshake sleep_fn (signal, then block until the test
    says to proceed) so the background thread can be paused deterministically
    right after each cycle attempt, exactly as in test_runner.py."""
    after_cycle = threading.Event()
    proceed = threading.Event()

    def sleep_and_wait(_seconds):
        after_cycle.set()
        proceed.wait(timeout=5.0)
        proceed.clear()

    config = DelevaConfig(
        monitored_wallet=DUMMY_WALLET, hf_trigger_threshold=Decimal("1.50"), keeperhub_api_key=FAKE_SECRET
    )
    strategy = DelevaStrategy.default(config)
    position_service = _RaisingThenHealthyPositionService(make_position(health_factor=Decimal("2.0")))
    engine = AutonomousEngine(
        config=config,
        strategy=strategy,
        position_service=position_service,
        risk_evaluator=RiskEvaluator(trigger_threshold=strategy.trigger_health_factor),
        almanak_interface=FakeAlmanakInterface(),
        keeperhub_client=FakeKeeperHubClient(),
        activity_log=ActivityLog(),
    )
    runner = MonitoringRunner(engine, interval_seconds=0, sleep_fn=sleep_and_wait)
    state = AppState(
        config=config,
        strategy=strategy,
        configuration_error=None,
        engine=engine,
        runner=runner,
        position_service=position_service,
        historical_activity=real_deleva_proof_events(),
    )
    monkeypatch.setattr(api_main, "state", state)
    client = TestClient(api_main.app)
    client.deleva_state = state
    client.after_cycle = after_cycle
    client.proceed = proceed
    yield client
    proceed.set()
    state.runner.stop(wait=True, timeout=2.0)


class TestHealth:
    def test_health_ok_even_when_unconfigured(self, unconfigured_client):
        response = unconfigured_client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestPositionUnavailable:
    def test_unconfigured_reports_unavailable_not_500(self, unconfigured_client):
        response = unconfigured_client.get("/api/position")
        assert response.status_code == 200
        body = response.json()
        assert body["available"] is False
        assert body["data"] is None
        assert "DELEVA_MONITORED_WALLET" in body["reason"]

    def test_unavailable_position_never_reports_source_live(self, unconfigured_client):
        # Regression test: PositionResponse.source used to be hardcoded to
        # "live" even when available=False. An unavailable position must
        # never claim a source at all.
        response = unconfigured_client.get("/api/position")
        body = response.json()
        assert body["available"] is False
        assert body["source"] is None


class TestPositionReal:
    def test_configured_returns_real_shaped_position(self, configured_client):
        response = configured_client.get("/api/position")
        assert response.status_code == 200
        body = response.json()
        assert body["available"] is True
        assert body["source"] == "live"
        data = body["data"]
        assert data["wallet"] == DUMMY_WALLET
        assert data["chain_display"] == "Base"
        assert data["protocol_display"] == "Aave V3"
        assert data["health_factor"] == "2.0"
        assert data["usdc_balance"] == "2.00"

    def test_no_fields_are_fabricated_when_unavailable(self, configured_client):
        # available_borrows_usd is None on make_position's default -- must
        # surface as null, not a fabricated zero.
        response = configured_client.get("/api/position")
        assert response.json()["data"]["available_borrows_usd"] is None


class TestStrategy:
    def test_strategy_matches_configured_thresholds(self, configured_client):
        response = configured_client.get("/api/strategy")
        assert response.status_code == 200
        body = response.json()
        assert body["protocol_display"] == "Aave V3"
        assert body["chain_display"] == "Base"
        assert body["trigger"] == "health_factor < 1.50"
        assert body["trigger_health_factor"] == "1.50"
        assert body["target_health_factor"] == "1.50"
        assert body["action"] == "Deleverage"
        assert body["decision_engine"] == "Almanak"
        assert body["execution_layer"] == "KeeperHub"

    def test_strategy_available_even_when_unconfigured(self, unconfigured_client):
        # Strategy is configuration, not a chain read -- it's always knowable.
        response = unconfigured_client.get("/api/strategy")
        assert response.status_code == 200
        assert response.json()["protocol_display"] == "Aave V3"


class TestEngineStatus:
    def test_unconfigured_is_explicit_not_fake_running(self, unconfigured_client):
        response = unconfigured_client.get("/api/engine/status")
        body = response.json()
        assert body["configured"] is False
        assert body["container_state"] is None
        assert body["engine_state"] is None

    def test_configured_defaults_to_stopped_and_dry_run(self, configured_client):
        response = configured_client.get("/api/engine/status")
        body = response.json()
        assert body["configured"] is True
        assert body["container_state"] == "STOPPED"  # no runner loop has been started
        assert body["engine_state"] == "STOPPED"
        assert body["execution_mode"] == "DRY_RUN"  # never LIVE by default
        assert body["last_cycle"] is None


class TestRunOnce:
    def test_returns_409_when_unconfigured(self, unconfigured_client):
        response = unconfigured_client.post("/api/engine/run-once")
        assert response.status_code == 409

    def test_healthy_cycle_updates_status_and_never_calls_keeperhub_execute(self, configured_client):
        keeperhub = configured_client.deleva_state.engine._keeperhub_client  # noqa: SLF001
        response = configured_client.post("/api/engine/run-once")
        assert response.status_code == 200
        body = response.json()
        assert body["last_cycle"]["risk_state"] == "HEALTHY"
        assert body["last_cycle"]["triggered"] is False
        assert body["last_cycle"]["action_taken"] is False
        assert keeperhub.execute_calls == []  # nothing was ever broadcast

    def test_run_once_never_flips_execution_mode(self, configured_client):
        configured_client.post("/api/engine/run-once")
        response = configured_client.get("/api/engine/status")
        assert response.json()["execution_mode"] == "DRY_RUN"


class TestEngineLifecycle:
    """Phase 3.1: the API can actually start/stop the real MonitoringRunner
    against the same AutonomousEngine instance every other route reads --
    not a fake heartbeat."""

    def test_start_returns_409_when_unconfigured(self, unconfigured_client):
        response = unconfigured_client.post("/api/engine/start")
        assert response.status_code == 409

    def test_stop_returns_409_when_unconfigured(self, unconfigured_client):
        response = unconfigured_client.post("/api/engine/stop")
        assert response.status_code == 409

    def test_start_actually_runs_the_same_engine_instance(self, configured_client):
        engine = configured_client.deleva_state.engine
        runner = configured_client.deleva_state.runner

        response = configured_client.post("/api/engine/start")
        assert response.status_code == 200
        body = response.json()
        assert body["container_state"] == "RUNNING"
        # Not a fake heartbeat: the actual MonitoringRunner is now running,
        # against the exact engine instance /api/position etc. also use.
        assert runner.is_running is True
        assert engine._container_state.value == "RUNNING"  # noqa: SLF001

        stop_response = configured_client.post("/api/engine/stop")
        assert stop_response.status_code == 200
        assert stop_response.json()["container_state"] == "STOPPED"
        assert runner.is_running is False

    def test_start_never_flips_execution_mode_to_live(self, configured_client):
        response = configured_client.post("/api/engine/start")
        assert response.json()["execution_mode"] == "DRY_RUN"

    def test_starting_twice_does_not_create_a_second_loop(self, configured_client):
        runner = configured_client.deleva_state.runner
        configured_client.post("/api/engine/start")
        thread_after_first = runner._thread  # noqa: SLF001

        response = configured_client.post("/api/engine/start")
        assert response.status_code == 200
        assert response.json()["container_state"] == "RUNNING"
        assert runner._thread is thread_after_first  # noqa: SLF001 -- no second thread spawned

    def test_stop_is_safe_when_already_stopped(self, configured_client):
        response = configured_client.post("/api/engine/stop")
        assert response.status_code == 200
        assert response.json()["container_state"] == "STOPPED"

    def test_run_once_returns_409_while_loop_is_running(self, configured_client):
        configured_client.post("/api/engine/start")
        response = configured_client.post("/api/engine/run-once")
        assert response.status_code == 409

    def test_run_once_works_again_after_stopping_the_loop(self, configured_client):
        configured_client.post("/api/engine/start")
        configured_client.post("/api/engine/stop")
        response = configured_client.post("/api/engine/run-once")
        assert response.status_code == 200

    def test_no_secrets_leak_from_start_or_stop(self, configured_client):
        start_response = configured_client.post("/api/engine/start")
        stop_response = configured_client.post("/api/engine/stop")
        assert FAKE_SECRET not in start_response.text
        assert FAKE_SECRET not in stop_response.text

    def test_background_loop_actually_produces_a_real_cycle(self, fast_loop_client):
        """The strongest possible check: the loop genuinely executes
        AutonomousEngine.run_cycle() on its own, unattended, and the result
        is observable through /api/activity -- not a fabricated status."""
        response = fast_loop_client.post("/api/engine/start")
        assert response.status_code == 200

        signaled = fast_loop_client.ran_event.wait(timeout=2.0)
        assert signaled, "background loop did not complete a real cycle within the timeout"

        fast_loop_client.post("/api/engine/stop")

        activity = fast_loop_client.get("/api/activity").json()
        live_events = [e for e in activity["events"] if e["source"] == "live"]
        assert len(live_events) >= 1
        assert live_events[0]["event_type"] == "POSITION_EVALUATED"


class TestEngineDegradedState:
    """Phase 3.1.1 (Option B): an unexpected cycle-level exception must not
    kill the background loop, and the API must expose/clear runner_error so
    the dashboard can tell 'running normally' apart from 'running but
    degraded' -- without a new engine state."""

    def test_runner_error_is_none_before_anything_has_run(self, configured_client):
        body = configured_client.get("/api/engine/status").json()
        assert body["runner_error"] is None

    def test_unconfigured_runner_error_is_none(self, unconfigured_client):
        body = unconfigured_client.get("/api/engine/status").json()
        assert body["runner_error"] is None

    def test_unexpected_exception_does_not_kill_the_loop_and_is_exposed_then_cleared(self, flaky_loop_client):
        start_response = flaky_loop_client.post("/api/engine/start")
        assert start_response.status_code == 200

        # 1st cycle: raises. The loop must survive it, and the failure must
        # be visible through the same API a dashboard would poll.
        assert flaky_loop_client.after_cycle.wait(timeout=2.0)
        flaky_loop_client.after_cycle.clear()
        status = flaky_loop_client.get("/api/engine/status").json()
        assert status["container_state"] == "RUNNING"  # not killed -- still genuinely running
        assert status["execution_mode"] == "DRY_RUN"
        assert status["runner_error"] is not None
        assert "RuntimeError" in status["runner_error"]

        # 2nd cycle: succeeds. runner_error must clear, loop still running.
        flaky_loop_client.proceed.set()
        assert flaky_loop_client.after_cycle.wait(timeout=2.0)
        flaky_loop_client.after_cycle.clear()
        status = flaky_loop_client.get("/api/engine/status").json()
        assert status["container_state"] == "RUNNING"
        assert status["runner_error"] is None

        # Intentional stop still works after recovering from a degraded state.
        flaky_loop_client.proceed.set()
        stop_response = flaky_loop_client.post("/api/engine/stop")
        assert stop_response.status_code == 200
        assert stop_response.json()["container_state"] == "STOPPED"

    def test_no_secrets_leak_while_degraded(self, flaky_loop_client):
        flaky_loop_client.post("/api/engine/start")
        flaky_loop_client.after_cycle.wait(timeout=2.0)
        status_response = flaky_loop_client.get("/api/engine/status")
        flaky_loop_client.proceed.set()
        assert FAKE_SECRET not in status_response.text


class TestActivity:
    def test_includes_historical_proof_with_the_real_hash(self, configured_client):
        response = configured_client.get("/api/activity")
        body = response.json()
        assert body["real_proof_transaction_hash"] == REAL_PROOF_TX_HASH
        historical = [e for e in body["events"] if e["source"] == "historical_proof"]
        assert len(historical) > 0
        confirmed = [e for e in historical if e["transaction_hash"] == REAL_PROOF_TX_HASH]
        # The real hash legitimately appears on more than one event (the
        # execution and the confirmation both reference the same tx) --
        # what matters is that it appears, correctly linked, at least once.
        assert len(confirmed) >= 1
        assert all(e["transaction_link"] == f"https://basescan.org/tx/{REAL_PROOF_TX_HASH}" for e in confirmed)

    def test_available_even_when_unconfigured(self, unconfigured_client):
        # Historical proof is static, real, recorded data -- doesn't need a
        # live KeeperHub connection to be shown.
        response = unconfigured_client.get("/api/activity")
        assert response.status_code == 200
        assert len(response.json()["events"]) > 0

    def test_live_events_appear_after_run_once(self, configured_client):
        before = configured_client.get("/api/activity").json()["events"]
        configured_client.post("/api/engine/run-once")
        after = configured_client.get("/api/activity").json()["events"]
        assert len(after) == len(before) + 1
        assert after[-1]["source"] == "live"
        assert after[-1]["event_type"] == "POSITION_EVALUATED"

    def test_historical_and_live_are_never_mixed_up(self, configured_client):
        configured_client.post("/api/engine/run-once")
        events = configured_client.get("/api/activity").json()["events"]
        for event in events:
            assert event["source"] in ("live", "demo", "historical_proof")
        # The real proof hash only ever appears on a historical_proof event.
        for event in events:
            if event["transaction_hash"] == REAL_PROOF_TX_HASH:
                assert event["source"] == "historical_proof"


class TestDemoMode:
    def test_returns_exactly_three_cycles_labeled_demo(self):
        client = TestClient(api_main.app)  # demo mode needs no configuration at all
        response = client.post("/api/demo/run")
        assert response.status_code == 200
        body = response.json()
        assert body["mode"] == "demo"
        assert len(body["cycles"]) == 3

    def test_demo_never_produces_the_real_proof_hash(self):
        client = TestClient(api_main.app)
        body = client.post("/api/demo/run").json()
        for cycle in body["cycles"]:
            for event in cycle["events"]:
                assert event["transaction_hash"] != REAL_PROOF_TX_HASH
                if event["transaction_hash"]:
                    assert event["transaction_hash"].startswith("0xDEMO")

    def test_demo_events_are_all_tagged_demo(self):
        client = TestClient(api_main.app)
        body = client.post("/api/demo/run").json()
        for cycle in body["cycles"]:
            for event in cycle["events"]:
                assert event["source"] == "demo"

    def test_demo_does_not_touch_the_configured_engines_activity_log(self, configured_client):
        before = len(configured_client.deleva_state.engine.activity_log.all())
        configured_client.post("/api/demo/run")
        after = len(configured_client.deleva_state.engine.activity_log.all())
        assert after == before  # demo activity never leaks into the real engine's log

    def test_demo_cycles_report_demo_execution_mode_not_live(self):
        # Regression test: a demo cycle's own summary used to report
        # execution_mode "LIVE" (control-flow-correct against the fake
        # DemoKeeperHubClient, but a misleading label for anything reading
        # the API response). Must never claim LIVE.
        client = TestClient(api_main.app)
        body = client.post("/api/demo/run").json()
        for cycle in body["cycles"]:
            assert cycle["summary"]["execution_mode"] == "DEMO"
            assert cycle["summary"]["execution_mode"] != "LIVE"

    def test_demo_does_not_touch_the_configured_engines_container_state(self, configured_client):
        # Regression test for the same isolation guarantee, specifically for
        # the new start/stop lifecycle: running the demo must never make the
        # real engine's container_state look like it's monitoring.
        before = configured_client.get("/api/engine/status").json()["container_state"]
        configured_client.post("/api/demo/run")
        after = configured_client.get("/api/engine/status").json()["container_state"]
        assert before == after == "STOPPED"


class TestNoSecretsExposed:
    """The KeeperHub API key must never appear in any API response."""

    @pytest.mark.parametrize(
        "method,path",
        [
            ("get", "/api/health"),
            ("get", "/api/position"),
            ("get", "/api/strategy"),
            ("get", "/api/engine/status"),
            ("get", "/api/activity"),
        ],
    )
    def test_get_routes_never_leak_the_api_key(self, configured_client, method, path):
        response = getattr(configured_client, method)(path)
        assert FAKE_SECRET not in response.text

    def test_run_once_never_leaks_the_api_key(self, configured_client):
        response = configured_client.post("/api/engine/run-once")
        assert FAKE_SECRET not in response.text

    def test_demo_never_leaks_the_api_key(self, configured_client):
        response = configured_client.post("/api/demo/run")
        assert FAKE_SECRET not in response.text

    def test_openapi_schema_never_leaks_the_api_key(self, configured_client):
        response = configured_client.get("/openapi.json")
        assert FAKE_SECRET not in response.text


class TestCors:
    def test_untrusted_origin_is_not_reflected(self, configured_client):
        response = configured_client.get("/api/health", headers={"Origin": "https://evil.example.com"})
        allow_origin = response.headers.get("access-control-allow-origin")
        assert allow_origin != "https://evil.example.com"
        assert allow_origin != "*"

    def test_localhost_dev_origin_is_allowed(self, configured_client):
        response = configured_client.get("/api/health", headers={"Origin": "http://localhost:5173"})
        assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
