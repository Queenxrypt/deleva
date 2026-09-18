import { useState } from "react";
import { api } from "../api/client";
import { useApi } from "../api/useApi";
import { AsyncBoundary } from "../components/AsyncBoundary";
import { monitoringDisplay, monitoringLabel, type MonitoringDisplay } from "../lib/monitoring";

const FLOW_STEPS = ["Monitor", "Detect", "Decide", "Simulate", "Execute", "Verify"];

/** LIVE means the backend's own environment has DELEVA_EXECUTION_DRY_RUN=false
 * -- any action that could trigger a real broadcast gets an extra native
 * confirm() gate first. Never silently proceeds; never a UI control that
 * flips DRY_RUN/LIVE itself (that stays entirely server-side, see README). */
function confirmIfLive(executionMode: string | null | undefined, action: string): boolean {
  if (executionMode !== "LIVE") return true;
  return window.confirm(
    `This backend is configured for live execution. ${action} could result in a real ` +
      "on-chain transaction if the position's health factor is, or becomes, below the " +
      "trigger threshold. Continue?"
  );
}

export function Strategies() {
  const strategy = useApi(api.strategy, []);
  const engineStatus = useApi(api.engineStatus, []);
  const activity = useApi(api.activity, []);
  const [runResult, setRunResult] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [lifecycleBusy, setLifecycleBusy] = useState(false);
  const [lifecycleError, setLifecycleError] = useState<string | null>(null);

  async function handleRunOnce() {
    if (engineStatus.status === "ready" && !confirmIfLive(engineStatus.data.execution_mode, "Running one cycle")) {
      return;
    }
    setRunning(true);
    setRunResult(null);
    try {
      const result = await api.runOnce();
      setRunResult(
        `Cycle complete. Risk ${result.last_cycle?.risk_state ?? "n/a"}, action taken: ${
          result.last_cycle?.action_taken ?? false
        }, mode ${result.execution_mode}.`
      );
      engineStatus.reload();
    } catch (err) {
      setRunResult(err instanceof Error ? err.message : "Run failed.");
    } finally {
      setRunning(false);
    }
  }

  async function handleStartMonitoring() {
    if (engineStatus.status === "ready" && !confirmIfLive(engineStatus.data.execution_mode, "Starting monitoring")) {
      return;
    }
    setLifecycleBusy(true);
    setLifecycleError(null);
    try {
      await api.startEngine();
      engineStatus.reload();
    } catch (err) {
      setLifecycleError(err instanceof Error ? err.message : "Failed to start monitoring.");
    } finally {
      setLifecycleBusy(false);
    }
  }

  async function handleStopMonitoring() {
    setLifecycleBusy(true);
    setLifecycleError(null);
    try {
      await api.stopEngine();
      engineStatus.reload();
    } catch (err) {
      setLifecycleError(err instanceof Error ? err.message : "Failed to stop monitoring.");
    } finally {
      setLifecycleBusy(false);
    }
  }

  return (
    <div>
      <div className="page-head">
        <h1 className="page-title">Strategies</h1>
      </div>

      <AsyncBoundary
        state={strategy}
        render={(s) => (
          <div className="card">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 12 }}>
              <div>
                <p className="section-title" style={{ marginBottom: 4 }}>
                  {s.protocol_display} Deleverage
                </p>
                <div className="metadata">{s.chain_display}</div>
              </div>
              <span className="badge healthy">
                <span className="dot" /> Active
              </span>
            </div>

            <hr className="card-divider" />

            <div className="stat-row">
              <div className="stat">
                <div className="label">Trigger</div>
                <div className="mono">Health Factor &lt; {s.trigger_health_factor}</div>
              </div>
              <div className="stat">
                <div className="label">Target</div>
                <div className="mono">Health Factor ≥ {s.target_health_factor}</div>
              </div>
              <div className="stat">
                <div className="label">Decision</div>
                <div className="mono">{s.decision_engine}</div>
              </div>
              <div className="stat">
                <div className="label">Execution</div>
                <div className="mono">{s.execution_layer}</div>
              </div>
            </div>
          </div>
        )}
      />

      <div className="card">
        <p className="section-title">Flow</p>
        <div className="flow-strip">
          {FLOW_STEPS.map((step, i) => (
            <div key={step} style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span className="flow-step">{step}</span>
              {i < FLOW_STEPS.length - 1 && <span className="flow-sep">→</span>}
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <p className="section-title">Monitoring</p>
        <AsyncBoundary
          state={engineStatus}
          render={(e) => {
            if (!e.configured) {
              return (
                <p className="body-copy">
                  DELEVA is not configured for this environment. Monitoring cannot start.
                </p>
              );
            }

            const display: MonitoringDisplay = monitoringDisplay(e);

            // Real evidence, not an assumption: only claim a completed
            // autonomous execution if the live activity log actually
            // contains a verified one. A freshly configured engine that has
            // never run shows plain "Stopped", never "Paused".
            const hasCompletedAutonomousExecution =
              activity.status === "ready" &&
              activity.data.events.some((ev) => ev.source === "live" && ev.event_type === "POSITION_VERIFIED");

            const isPaused = display === "stopped" && hasCompletedAutonomousExecution;
            const badgeClass = display === "running" ? "healthy" : isPaused ? "accent" : display === "stopped" ? "neutral" : "warning";
            const badgeLabel = isPaused ? "Paused" : monitoringLabel(display);

            const description =
              display === "running"
                ? e.execution_mode === "DRY_RUN"
                  ? "Monitoring is active. Any triggered action is currently simulated, not broadcast."
                  : "Monitoring is active. This backend is configured for live execution."
                : display === "degraded"
                  ? "Monitoring is active and will retry on its next scheduled cycle. The most recent cycle failed unexpectedly."
                  : display === "stopping"
                    ? `Monitoring stopped. The cycle already in progress (${e.engine_state}) is finishing on its own.`
                    : isPaused
                      ? "Monitoring is paused. The last autonomous execution completed successfully."
                      : "Monitoring is not running. Start it to continuously evaluate the position and react to a breach automatically.";

            const canStart = display === "stopped";

            return (
              <>
                <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
                  <div>
                    <div className="label">Monitoring</div>
                    <span className={`badge ${badgeClass}`}>
                      <span className="dot" /> {badgeLabel}
                    </span>
                  </div>
                  <div>
                    <div className="label">Execution mode</div>
                    <span className={`badge ${e.execution_mode === "LIVE" ? "danger" : "accent"}`}>
                      {e.execution_mode === "DRY_RUN" ? "Dry run" : e.execution_mode}
                    </span>
                  </div>
                </div>
                <p className="body-copy" style={{ marginTop: 16 }}>{description}</p>
                {display === "degraded" && e.runner_error && (
                  <p className="mono" style={{ fontSize: 12, color: "var(--danger)", marginTop: 4 }}>
                    {e.runner_error}
                  </p>
                )}
                <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
                  {display === "running" || display === "degraded" ? (
                    <button className="btn" onClick={handleStopMonitoring} disabled={lifecycleBusy}>
                      {lifecycleBusy ? "Stopping…" : "Stop monitoring"}
                    </button>
                  ) : (
                    <button
                      className="btn primary"
                      onClick={handleStartMonitoring}
                      disabled={lifecycleBusy || !canStart}
                      title={canStart ? undefined : "Wait for the in-progress cycle to finish first."}
                    >
                      {lifecycleBusy ? "Starting…" : "Start monitoring"}
                    </button>
                  )}
                </div>
                {lifecycleError && (
                  <p style={{ marginTop: 12, fontSize: 13, color: "var(--danger)" }}>{lifecycleError}</p>
                )}
              </>
            );
          }}
        />
      </div>

      <div className="card">
        <p className="section-title">Manual check</p>
        <AsyncBoundary
          state={engineStatus}
          render={(e) => {
            if (!e.configured) {
              return <p className="body-copy">Not configured. A manual cycle cannot run.</p>;
            }
            const display = monitoringDisplay(e);
            if (display !== "stopped") {
              return (
                <p className="body-copy">
                  {display === "stopping"
                    ? "The previous cycle is still finishing. Wait for monitoring to fully stop before running one manually."
                    : "Monitoring is already active. Stop it above to run a cycle manually."}
                </p>
              );
            }
            return (
              <>
                <p className="body-copy">
                  Runs one cycle against the current position. Mode: <strong className="mono">{e.execution_mode === "DRY_RUN" ? "Dry run" : e.execution_mode}</strong>.
                </p>
                <button className="btn" onClick={handleRunOnce} disabled={running} style={{ marginTop: 8 }}>
                  {running ? "Running…" : "Run one cycle"}
                </button>
                {runResult && <p style={{ marginTop: 12, fontSize: 13, color: "var(--text)" }}>{runResult}</p>}
              </>
            );
          }}
        />
      </div>
    </div>
  );
}
