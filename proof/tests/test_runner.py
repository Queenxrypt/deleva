from __future__ import annotations

import threading
from decimal import Decimal

import pytest

from deleva.config import DelevaConfig
from deleva.engine import AutonomousEngine
from deleva.engine_state import EngineState
from deleva.execution_mode import ExecutionMode
from deleva.risk import RiskEvaluator
from deleva.runner import MonitoringRunner, RunnerBusyError
from deleva.strategy import DelevaStrategy

from fakes import DUMMY_WALLET, FakeAlmanakInterface, FakeKeeperHubClient, FakePositionService, make_position


def make_runner(*, positions, interval_seconds=0):
    config = DelevaConfig(monitored_wallet=DUMMY_WALLET, hf_trigger_threshold=Decimal("1.50"))
    strategy = DelevaStrategy.default(config)
    engine = AutonomousEngine(
        config=config,
        strategy=strategy,
        position_service=FakePositionService(positions),
        risk_evaluator=RiskEvaluator(trigger_threshold=strategy.trigger_health_factor),
        almanak_interface=FakeAlmanakInterface(),
        keeperhub_client=FakeKeeperHubClient(),
        execution_mode=ExecutionMode.DRY_RUN,
    )
    sleeps: list[float] = []
    runner = MonitoringRunner(engine, interval_seconds=interval_seconds, sleep_fn=sleeps.append)
    return runner, engine, sleeps


class RaisingThenHealthyPositionService:
    """Stands in for a position service that raises an unexpected exception
    (e.g. a real network/KeeperHub failure) on its first call, then behaves
    normally on every call after -- for testing that the background loop
    survives exactly this class of failure (see MonitoringRunner.start())."""

    def __init__(self, healthy_position):
        self.calls = 0
        self._position = healthy_position

    def get_position(self, wallet=None):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("simulated transient KeeperHub/network failure")
        return self._position

    def get_usdc_balance(self, wallet=None):
        return Decimal("2.00")


def make_flaky_runner(*, interval_seconds=0, sleep_fn):
    """A runner whose engine fails its very first cycle with an unexpected
    (uncaught-by-AutonomousEngine) exception, then succeeds on every cycle
    after."""
    config = DelevaConfig(monitored_wallet=DUMMY_WALLET, hf_trigger_threshold=Decimal("1.50"))
    strategy = DelevaStrategy.default(config)
    position_service = RaisingThenHealthyPositionService(make_position(health_factor=Decimal("2.0")))
    engine = AutonomousEngine(
        config=config,
        strategy=strategy,
        position_service=position_service,
        risk_evaluator=RiskEvaluator(trigger_threshold=strategy.trigger_health_factor),
        almanak_interface=FakeAlmanakInterface(),
        keeperhub_client=FakeKeeperHubClient(),
        execution_mode=ExecutionMode.DRY_RUN,
    )
    runner = MonitoringRunner(engine, interval_seconds=interval_seconds, sleep_fn=sleep_fn)
    return runner, engine, position_service


class TestRunOnce:
    def test_run_once_executes_exactly_one_cycle(self):
        runner, _engine, _sleeps = make_runner(positions=[make_position(health_factor=Decimal("2.0"))])
        result = runner.run_once()
        assert runner.cycles_completed == 1
        assert result.risk_state.value == "HEALTHY"


class TestStartStop:
    """Scenario J: runner stops cleanly, no new cycles after stop, can start again."""

    def test_start_with_max_cycles_runs_exactly_that_many(self):
        runner, _engine, sleeps = make_runner(
            positions=[make_position(health_factor=Decimal("2.0"))], interval_seconds=5
        )
        results = runner.start(max_cycles=3)
        assert len(results) == 3
        assert runner.cycles_completed == 3
        assert runner.is_running is False  # stopped itself after max_cycles
        # Slept between cycles (2 sleeps for 3 cycles), not after the last one.
        assert sleeps == [5, 5]

    def test_stop_prevents_further_cycles(self):
        runner, engine, _sleeps = make_runner(positions=[make_position(health_factor=Decimal("2.0"))])

        # Simulate an external stop() call arriving after the first cycle by
        # having the sleep function itself call stop() -- deterministic,
        # no real threading needed to prove the guard works.
        def sleep_then_stop(_seconds):
            runner.stop()

        runner._sleep = sleep_then_stop  # noqa: SLF001

        results = runner.start()

        assert len(results) == 1  # stopped before a second cycle could run
        assert runner.is_running is False
        assert engine.state == EngineState.STOPPED

    def test_can_start_again_after_stopping(self):
        runner, _engine, _sleeps = make_runner(positions=[make_position(health_factor=Decimal("2.0"))])

        first_run = runner.start(max_cycles=1)
        assert len(first_run) == 1
        assert runner.is_running is False

        second_run = runner.start(max_cycles=1)
        assert len(second_run) == 1
        assert runner.cycles_completed == 2

    def test_status_reports_running_state(self):
        runner, engine, _sleeps = make_runner(positions=[make_position(health_factor=Decimal("2.0"))])
        status_before = runner.status()
        assert status_before.is_running is False
        assert status_before.cycles_completed == 0

        runner.start(max_cycles=1)
        status_after = runner.status()
        assert status_after.cycles_completed == 1
        assert status_after.is_running is False


class TestRunOnceVsBackgroundLoopMutualExclusion:
    """Phase 3.1: a manual run_once() and the background loop must never run
    concurrently against the same engine instance (see RunnerBusyError)."""

    def test_run_once_raises_when_background_loop_is_running(self):
        runner, _engine, _sleeps = make_runner(
            positions=[make_position(health_factor=Decimal("2.0"))], interval_seconds=10
        )
        pause = threading.Event()
        runner._sleep = lambda _seconds: pause.wait(timeout=2.0)  # noqa: SLF001

        started = runner.start_in_background()
        try:
            assert started is True
            assert runner.is_running is True
            with pytest.raises(RunnerBusyError):
                runner.run_once()
        finally:
            pause.set()
            runner.stop(wait=True, timeout=2.0)

    def test_run_once_works_normally_once_the_loop_is_stopped(self):
        runner, _engine, _sleeps = make_runner(
            positions=[make_position(health_factor=Decimal("2.0"))], interval_seconds=10
        )
        runner._sleep = lambda _seconds: None  # noqa: SLF001 -- no-op; only stop()'s promptness matters here

        runner.start_in_background()
        runner.stop(wait=True, timeout=2.0)

        assert runner.is_running is False
        result = runner.run_once()  # must not raise now that the loop is stopped
        assert result.risk_state.value == "HEALTHY"


class TestStartInBackground:
    """Phase 3.1: the same MonitoringRunner the API reads can actually run
    its loop on a background thread, without blocking the caller."""

    def test_runs_real_cycles_on_a_separate_thread(self):
        ran_event = threading.Event()
        runner, engine, _sleeps = make_runner(
            positions=[make_position(health_factor=Decimal("2.0"))], interval_seconds=0
        )

        def sleep_and_signal(_seconds):
            ran_event.set()

        runner._sleep = sleep_and_signal  # noqa: SLF001

        started = runner.start_in_background()
        try:
            assert started is True
            # Synchronous: mark_running() happens under the lock before the
            # thread is even spawned, so this is never a race.
            assert runner.is_running is True
            assert engine._container_state == EngineState.RUNNING  # noqa: SLF001

            signaled = ran_event.wait(timeout=2.0)
            assert signaled, "background loop did not complete a cycle within the timeout"
            assert runner.cycles_completed >= 1
        finally:
            runner.stop(wait=True, timeout=2.0)

        assert runner.is_running is False
        assert engine.state == EngineState.STOPPED

    def test_calling_it_twice_does_not_create_a_second_thread(self):
        runner, _engine, _sleeps = make_runner(
            positions=[make_position(health_factor=Decimal("2.0"))], interval_seconds=10
        )
        pause = threading.Event()
        runner._sleep = lambda _seconds: pause.wait(timeout=2.0)  # noqa: SLF001

        try:
            first = runner.start_in_background()
            thread_after_first = runner._thread  # noqa: SLF001
            second = runner.start_in_background()

            assert first is True
            assert second is False  # no second loop was started
            assert runner._thread is thread_after_first  # noqa: SLF001
        finally:
            pause.set()
            runner.stop(wait=True, timeout=2.0)

    def test_stop_is_safe_when_already_stopped(self):
        runner, engine, _sleeps = make_runner(positions=[make_position(health_factor=Decimal("2.0"))])
        runner.stop()  # never started -- must not raise
        assert runner.is_running is False
        assert engine.state == EngineState.STOPPED

    def test_stop_after_background_start_is_safe_to_call_twice(self):
        runner, _engine, _sleeps = make_runner(
            positions=[make_position(health_factor=Decimal("2.0"))], interval_seconds=0
        )
        ran_event = threading.Event()
        runner._sleep = lambda _s: ran_event.set()

        runner.start_in_background()
        ran_event.wait(timeout=2.0)
        runner.stop(wait=True, timeout=2.0)
        runner.stop()  # calling stop again once already stopped must not raise
        assert runner.is_running is False


class TestUnexpectedExceptionDoesNotKillTheLoop:
    """Phase 3.1.1 (Option B): a single unexpected cycle-level exception (e.g.
    a transient KeeperHub/network failure) must degrade, not kill, the
    background loop -- see MonitoringRunner.start()/last_error."""

    def test_survives_the_failure_records_it_then_clears_it_on_success(self):
        # Two-way handshake: sleep_fn signals "a cycle attempt just finished"
        # and then blocks until the main thread says to proceed -- without
        # this, with interval_seconds=0 the background thread can race ahead
        # through several more cycles before the main thread's assertions
        # even run.
        after_cycle = threading.Event()
        proceed = threading.Event()

        def sleep_and_wait(_seconds):
            after_cycle.set()
            proceed.wait(timeout=5.0)
            proceed.clear()

        runner, engine, position_service = make_flaky_runner(interval_seconds=0, sleep_fn=sleep_and_wait)

        runner.start_in_background()
        try:
            # 1st cycle: raises. The loop must survive it and is now parked
            # (blocked in sleep_and_wait) right after recording the failure.
            assert after_cycle.wait(timeout=2.0), "loop did not reach its first sleep point"
            after_cycle.clear()
            assert runner.is_running is True  # not killed
            assert engine._container_state == EngineState.RUNNING  # noqa: SLF001 -- still genuinely running
            assert runner.last_error is not None
            assert "RuntimeError" in runner.last_error
            assert "simulated transient KeeperHub/network failure" in runner.last_error
            assert runner.cycles_completed == 0  # the failed attempt is not counted as completed

            # 2nd cycle: succeeds. last_error must clear, and the loop keeps going.
            proceed.set()
            assert after_cycle.wait(timeout=2.0), "loop did not reach a second cycle"
            after_cycle.clear()
            assert runner.is_running is True
            assert runner.last_error is None
            assert runner.cycles_completed == 1

            # 3rd cycle: proves the loop keeps processing subsequent cycles,
            # not just a single recovery.
            proceed.set()
            assert after_cycle.wait(timeout=2.0), "loop did not reach a third cycle"
            after_cycle.clear()
            assert runner.cycles_completed == 2
            assert runner.last_error is None
            assert position_service.calls == 3
        finally:
            proceed.set()  # unblock the thread if it's still parked, so stop() can join it
            runner.stop(wait=True, timeout=2.0)

        # Intentional stop still works after a prior degraded/recovered cycle.
        assert runner.is_running is False
        assert engine.state == EngineState.STOPPED

    def test_never_retries_faster_than_the_configured_interval(self):
        # The failing cycle must still go through the normal sleep_fn call
        # before the next attempt -- no tight hammering loop on failure.
        sleep_calls: list[float] = []
        stop_after = threading.Event()

        def sleep_and_maybe_stop(seconds):
            sleep_calls.append(seconds)
            if len(sleep_calls) >= 2:
                stop_after.set()

        runner, _engine, _position_service = make_flaky_runner(interval_seconds=30, sleep_fn=sleep_and_maybe_stop)
        runner.start_in_background()
        try:
            assert stop_after.wait(timeout=2.0)
            # Both the failed 1st cycle and the successful 2nd cycle slept the
            # same, unmodified, configured interval -- never a tighter retry.
            assert sleep_calls[:2] == [30, 30]
        finally:
            runner.stop(wait=True, timeout=2.0)

    def test_run_once_is_unaffected_by_the_background_loop_error_model(self):
        # A manual run_once() (not started via the background loop) still
        # raises normally on an unexpected exception -- last_error is a
        # background-loop-only concept, and a manual caller sees the error
        # directly, as before.
        position_service = RaisingThenHealthyPositionService(make_position(health_factor=Decimal("2.0")))
        config = DelevaConfig(monitored_wallet=DUMMY_WALLET, hf_trigger_threshold=Decimal("1.50"))
        strategy = DelevaStrategy.default(config)
        engine = AutonomousEngine(
            config=config,
            strategy=strategy,
            position_service=position_service,
            risk_evaluator=RiskEvaluator(trigger_threshold=strategy.trigger_health_factor),
            almanak_interface=FakeAlmanakInterface(),
            keeperhub_client=FakeKeeperHubClient(),
            execution_mode=ExecutionMode.DRY_RUN,
        )
        runner = MonitoringRunner(engine, interval_seconds=0)

        with pytest.raises(RuntimeError, match="simulated transient"):
            runner.run_once()
        assert runner.last_error is None  # run_once() never touches last_error

        # And it works normally on the next (successful) call.
        result = runner.run_once()
        assert result.risk_state.value == "HEALTHY"


class BlockingPositionService:
    """A position read that blocks until explicitly released -- lets a test
    hold a cycle deliberately "in flight" for as long as it needs,
    deterministically (no real time.sleep guessing about timing)."""

    def __init__(self, position):
        self.calls = 0
        self.started = threading.Event()
        self.release = threading.Event()
        self._position = position

    def get_position(self, wallet=None):
        self.calls += 1
        self.started.set()
        self.release.wait(timeout=5.0)
        return self._position

    def get_usdc_balance(self, wallet=None):
        return Decimal("2.00")


class TestRunOnceVsInFlightCycleAfterStop:
    """Phase 3.1.2: stop() must not interrupt an in-flight cycle, but
    run_once() must still be refused for as long as that cycle is genuinely
    executing -- even after stop() has already cleared is_running. See
    MonitoringRunner._cycle_lock / module docstring."""

    def test_full_sequence_running_stop_in_flight_reject_finish_settle_available(self):
        position_service = BlockingPositionService(make_position(health_factor=Decimal("2.0")))
        config = DelevaConfig(monitored_wallet=DUMMY_WALLET, hf_trigger_threshold=Decimal("1.50"))
        strategy = DelevaStrategy.default(config)
        engine = AutonomousEngine(
            config=config,
            strategy=strategy,
            position_service=position_service,
            risk_evaluator=RiskEvaluator(trigger_threshold=strategy.trigger_health_factor),
            almanak_interface=FakeAlmanakInterface(),
            keeperhub_client=FakeKeeperHubClient(),
            execution_mode=ExecutionMode.DRY_RUN,
        )
        # A long interval: irrelevant here since we stop before it's ever
        # reached, but confirms nothing about this depends on fast timing.
        runner = MonitoringRunner(engine, interval_seconds=30)

        # 1. Start the background loop.
        started = runner.start_in_background()
        assert started is True
        assert engine._container_state == EngineState.RUNNING  # noqa: SLF001

        # 2. Begin a deliberately slow cycle -- wait for it to actually enter
        # the position read (now blocked inside it).
        assert position_service.started.wait(timeout=2.0), "cycle never started"
        assert position_service.calls == 1

        # 3. Request stop while that cycle is in-flight.
        runner.stop()
        assert runner.is_running is False  # takes effect immediately...
        assert engine._container_state == EngineState.STOPPED  # noqa: SLF001

        # 4. Confirm the cycle continues rather than being interrupted: it's
        # still the same single call, still blocked, not abandoned/restarted.
        assert position_service.calls == 1
        assert not position_service.release.is_set()

        # 5. Attempt run_once() during this in-flight "stopping" window.
        with pytest.raises(RunnerBusyError, match="still finishing"):
            runner.run_once()
        # The rejected attempt must not itself have touched the position
        # service or the engine -- it never got past the lock check.
        assert position_service.calls == 1

        # 6. Allow the in-flight cycle to finish.
        position_service.release.set()
        runner._thread.join(timeout=2.0)  # noqa: SLF001 -- deterministic wait for the loop to actually exit

        # 7. Confirm the runner settles to fully STOPPED.
        assert runner.is_running is False
        assert runner.status().engine_state == EngineState.STOPPED
        assert engine.state == EngineState.STOPPED

        # 8. Confirm run_once() works again now that it's fully stopped.
        result = runner.run_once()
        assert result.risk_state.value == "HEALTHY"
        assert position_service.calls == 2  # the in-flight one, then this manual one

    def test_run_once_rejection_message_distinguishes_in_flight_from_running(self):
        # Different, more specific message than the plain "loop is running"
        # rejection -- an operator/log reader should be able to tell "the
        # loop itself is running" apart from "a lingering cycle is finishing".
        position_service = BlockingPositionService(make_position(health_factor=Decimal("2.0")))
        config = DelevaConfig(monitored_wallet=DUMMY_WALLET, hf_trigger_threshold=Decimal("1.50"))
        strategy = DelevaStrategy.default(config)
        engine = AutonomousEngine(
            config=config,
            strategy=strategy,
            position_service=position_service,
            risk_evaluator=RiskEvaluator(trigger_threshold=strategy.trigger_health_factor),
            almanak_interface=FakeAlmanakInterface(),
            keeperhub_client=FakeKeeperHubClient(),
            execution_mode=ExecutionMode.DRY_RUN,
        )
        runner = MonitoringRunner(engine, interval_seconds=30)

        runner.start_in_background()
        assert position_service.started.wait(timeout=2.0)
        runner.stop()

        try:
            with pytest.raises(RunnerBusyError) as exc_info:
                runner.run_once()
            assert "still finishing" in str(exc_info.value)
            assert "already running" not in str(exc_info.value)
        finally:
            position_service.release.set()
            runner._thread.join(timeout=2.0)  # noqa: SLF001
