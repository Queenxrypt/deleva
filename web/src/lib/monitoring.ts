import type { EngineStatusResponse } from "../api/client";

// engine_state values AutonomousEngine.run_cycle() can be sitting in mid-cycle
// -- see deleva/engine_state.py. Distinct from RiskState/RUNNING/STOPPED.
const ACTIVE_CYCLE_STATES = ["EVALUATING", "TRIGGERED", "SIMULATING", "EXECUTING", "VERIFYING"];

export type MonitoringDisplay = "running" | "degraded" | "stopping" | "stopped";

/** Classifies the engine's current display state from container_state +
 * engine_state + runner_error -- the single source of truth used by every
 * page that shows monitoring state, so Overview and Strategies can never
 * disagree about what "the engine" is doing. No new backend state is
 * invented here -- this is presentation logic only. */
export function monitoringDisplay(e: EngineStatusResponse): MonitoringDisplay {
  if (e.container_state === "RUNNING") {
    return e.runner_error ? "degraded" : "running";
  }
  // container_state is STOPPED: a stop() was requested (or none has ever been
  // started). If engine_state still shows an active cycle phase, that cycle
  // was in flight when stop() was called and is still finishing.
  if (e.engine_state !== null && ACTIVE_CYCLE_STATES.includes(e.engine_state)) {
    return "stopping";
  }
  return "stopped";
}

/** User-facing label for a monitoring display state. Backend implementation
 * terms (ENGINE, RUNNING/STOPPED as raw strings) never reach the product UI. */
export function monitoringLabel(display: MonitoringDisplay): string {
  switch (display) {
    case "running":
      return "Active";
    case "degraded":
      return "Degraded";
    case "stopping":
      return "Stopping";
    case "stopped":
      return "Stopped";
  }
}
