"""Thin monitoring runner: repeatedly invokes AutonomousEngine.run_cycle()
at a configured interval.

Deliberately separate from AutonomousEngine (see Phase 2 task 3): the engine
is a pure, testable, single-cycle unit with no notion of time. This module
is the only place ``time.sleep`` (injectable, for tests) appears.

Phase 3.1 adds ``start_in_background()``: a thin wrapper that runs the exact
same ``start()`` loop on a daemon ``threading.Thread`` instead of the calling
thread, so the FastAPI process (api/state.py) can genuinely run the
autonomous loop against its own real ``AutonomousEngine`` instance without
blocking every HTTP request. No new infrastructure -- one ``threading.Lock``
guards against a double-start creating two loops against the same engine.
``start()`` itself is unchanged; the CLI's foreground ``python -m deleva
start`` still calls it directly, on its own thread, exactly as before.

Phase 3.1.1 (Option B) makes the background loop resilient to an unexpected,
uncaught exception from a single cycle (e.g. a transient KeeperHub/network
failure -- ``AutonomousEngine.run_cycle()`` only catches the failure modes it
can anticipate; a raw network error from ``simulate_contract_call`` or
``get_position`` is not one of them). DELEVA's purpose is continuous
monitoring, so a single bad cycle must never permanently and silently end
it -- see ``start()``'s docstring for exactly what changed.

Phase 3.1.2 closes a race between ``stop()`` and ``run_once()``: ``stop()``
clears ``_is_running`` immediately, by design, without waiting for an
in-flight cycle to finish (graceful -- never interrupts a cycle mid-flight).
But ``run_once()`` used to check only ``_is_running`` -- so a manual call
arriving in the window after ``stop()`` but before that in-flight cycle
actually returns would see "not running" and call
``AutonomousEngine.run_cycle()`` itself, concurrently with the still-running
one, against the same engine instance (exactly the hazard ``RunnerBusyError``
exists to prevent in the first place). ``_cycle_lock`` closes this: it is
held for the entire duration of every ``AutonomousEngine.run_cycle()`` call,
whether made by the background loop or by ``run_once()``, so at most one is
ever in flight. ``run_once()`` takes it non-blocking (immediate
``RunnerBusyError`` if unavailable -- it never blocks an HTTP request for as
long as a cycle takes); the background loop takes it with a normal blocking
acquire, which is always immediately available in practice since the loop is
the lock's only other, single-threaded, sequential user.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from deleva.engine import AutonomousEngine, CycleResult
from deleva.engine_state import EngineState


class RunnerBusyError(Exception):
    """Raised by ``run_once()`` when it cannot safely run a cycle right now:
    either the autonomous loop is running (``is_running`` True), or a cycle
    -- possibly one already in flight when a ``stop()`` request arrived -- is
    still executing against this same engine instance.

    Manual, one-off cycles and any other cycle are mutually exclusive by
    design -- ``AutonomousEngine.run_cycle()`` was written for a single
    caller at a time (it mutates ``self.state``/``self._pending_execution_id``
    with no internal locking of its own). Rather than serializing the two
    behind a blocking lock (which could block an HTTP request for as long as
    a real execution takes), a manual cycle is simply refused immediately
    while another one owns the engine -- wait for it to finish, or (if the
    loop is running) stop it first.
    """


@dataclass(frozen=True)
class RunnerStatus:
    is_running: bool
    engine_state: EngineState
    cycles_completed: int
    last_error: str | None = None


class MonitoringRunner:
    """Repeatedly calls ``engine.run_cycle()`` on a fixed interval until stopped."""

    def __init__(self, engine: AutonomousEngine, *, interval_seconds: float, sleep_fn=time.sleep) -> None:
        self._engine = engine
        self._interval_seconds = interval_seconds
        self._sleep = sleep_fn
        self._is_running = False
        self._cycles_completed = 0
        self._start_lock = threading.Lock()
        # Held for the full duration of every AutonomousEngine.run_cycle()
        # call, from whichever caller (background loop or run_once()) -- see
        # module docstring, Phase 3.1.2. A plain (non-reentrant) Lock is
        # deliberate: neither caller ever needs to re-acquire it from within
        # a call it already holds, so reentrancy would only hide a bug.
        self._cycle_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._last_error: str | None = None

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def cycles_completed(self) -> int:
        return self._cycles_completed

    @property
    def last_error(self) -> str | None:
        """The error from the most recent background-loop cycle that raised
        an unexpected exception, or None if the most recent cycle succeeded
        (or the loop has never run / hasn't completed a cycle yet).

        Only ever set/cleared by the background loop (``start()``/
        ``start_in_background()``) -- a manual ``run_once()`` call still
        raises normally and never touches this, since a manual call is
        observed directly by its caller and doesn't need a separate
        "degraded" signal. Combined with ``is_running``/``engine_state``,
        this is what lets a caller distinguish: intentionally stopped
        (``is_running`` False), running normally (``is_running`` True,
        ``last_error`` None), and running but degraded (``is_running`` True,
        ``last_error`` set) -- without needing a new EngineState.
        """
        return self._last_error

    def status(self) -> RunnerStatus:
        return RunnerStatus(
            is_running=self._is_running,
            engine_state=self._engine.state,
            cycles_completed=self._cycles_completed,
            last_error=self._last_error,
        )

    def _execute_cycle(self) -> CycleResult:
        result = self._engine.run_cycle()
        self._cycles_completed += 1
        return result

    def run_once(self) -> CycleResult:
        """Run exactly one cycle, regardless of running state. Useful for the
        `once` CLI command and for the manual `/api/engine/run-once` route.

        Deliberately does NOT call ``engine.mark_running()`` -- a single,
        manually-triggered cycle is not "ongoing autonomous monitoring," and
        the engine's state should never claim otherwise. Only ``start()``/
        ``start_in_background()`` mark the engine as actively running.

        Raises RunnerBusyError if the background loop is running
        (``is_running`` True -- the pre-existing, immediate check), OR if a
        cycle is currently executing at all -- including one still finishing
        after a ``stop()`` request already cleared ``is_running`` (see module
        docstring, Phase 3.1.2). Never blocks waiting for that cycle to
        finish; fails fast instead.
        """
        if self._is_running:
            raise RunnerBusyError(
                "The autonomous monitoring loop is already running -- stop it first, "
                "or wait for its next scheduled cycle, before running a manual one-off cycle."
            )
        if not self._cycle_lock.acquire(blocking=False):
            raise RunnerBusyError(
                "A cycle is still finishing (the autonomous loop may have just been stopped, but "
                "its in-flight cycle hasn't completed yet) -- wait for it to finish before running "
                "a manual one-off cycle."
            )
        try:
            return self._execute_cycle()
        finally:
            self._cycle_lock.release()

    def start(self, *, max_cycles: int | None = None) -> list[CycleResult]:
        """Run cycles until ``stop()`` is called (or ``max_cycles`` is reached,
        if given -- primarily for tests and the local demo mode, which must
        terminate deterministically rather than loop forever).

        Blocks the calling thread/process for as long as the loop runs. The
        CLI's ``python -m deleva start`` calls this directly, in the
        foreground. ``start_in_background()`` calls this exact same method,
        just on a separate thread.

        An unexpected exception from a single cycle (anything
        ``AutonomousEngine.run_cycle()`` itself didn't anticipate and turn
        into a normal, failed ``CycleResult`` -- e.g. a raw network error)
        is caught here, recorded via ``last_error``, and does NOT stop the
        loop: it waits the normal ``interval_seconds`` (never faster, never
        hammering the service on a tighter retry schedule) and tries again
        on schedule. ``last_error`` clears as soon as a cycle completes
        without raising. This is deliberate -- DELEVA's whole purpose is
        continuous monitoring, so a transient failure must degrade the loop,
        not silently and permanently end it (see module docstring).

        Returns every successfully-completed CycleResult produced during
        this run, in order -- a cycle that raised is not included.
        """
        self._is_running = True
        self._engine.mark_running()
        results: list[CycleResult] = []
        try:
            while self._is_running:
                # Held for the full cycle -- see module docstring, Phase
                # 3.1.2. Always immediately available here in practice: this
                # loop is the lock's only other user, one iteration at a
                # time; run_once() never blocks waiting for it (it fails
                # fast with RunnerBusyError instead), so it can never hold
                # this lock and starve the loop.
                with self._cycle_lock:
                    try:
                        results.append(self._execute_cycle())
                        self._last_error = None
                    except Exception as exc:  # noqa: BLE001 -- deliberately broad: any
                        # cycle-level failure AutonomousEngine itself didn't already
                        # handle must degrade, not kill, the autonomous loop.
                        self._last_error = f"{type(exc).__name__}: {exc}"
                if max_cycles is not None and len(results) >= max_cycles:
                    break
                if self._is_running:
                    self._sleep(self._interval_seconds)
        finally:
            self._is_running = False
            self._engine.mark_stopped()
        return results

    def start_in_background(self) -> bool:
        """Start the monitoring loop on a daemon background thread, so the
        caller (the FastAPI process) is never blocked.

        Idempotent: if a loop is already running, does nothing and returns
        False -- never spawns a second thread against the same engine.
        ``_is_running``/``mark_running()`` are set synchronously here, under
        the lock, before the thread is even started, so a caller that reads
        engine/runner state immediately after this returns True always sees
        RUNNING -- it never has to wait for the background thread to get
        scheduled.

        Returns True if a new loop was actually started.
        """
        with self._start_lock:
            if self._is_running:
                return False
            self._is_running = True
            self._engine.mark_running()
            self._thread = threading.Thread(
                target=self.start, daemon=True, name="deleva-monitoring-runner"
            )
            self._thread.start()
            return True

    def stop(self, *, wait: bool = False, timeout: float | None = None) -> None:
        """Signal the running loop to stop after its current cycle completes.
        Graceful: never interrupts a cycle mid-flight. Safe to call when
        already stopped (a no-op beyond re-affirming STOPPED state).

        With ``wait=True``, also joins the background thread (if one was
        started via ``start_in_background()``) for up to ``timeout`` seconds
        -- best-effort, used by the API's shutdown hook. The thread is a
        daemon, so process exit is never blocked by it regardless of whether
        this join completes.
        """
        self._is_running = False
        self._engine.mark_stopped()
        if wait and self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=timeout)
