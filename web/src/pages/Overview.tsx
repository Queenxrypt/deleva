import { api } from "../api/client";
import { useApi } from "../api/useApi";
import { AsyncBoundary } from "../components/AsyncBoundary";
import { ContextStrip } from "../components/ContextStrip";
import { ActivityTimeline } from "../components/ActivityTimeline";
import { riskTier, riskLabel } from "../lib/risk";
import { formatNumber } from "../lib/format";
import { monitoringDisplay, monitoringLabel } from "../lib/monitoring";

export function Overview() {
  const position = useApi(api.position, []);
  const strategy = useApi(api.strategy, []);
  const engineStatus = useApi(api.engineStatus, []);
  const activity = useApi(api.activity, []);

  return (
    <div>
      <div className="page-head">
        <h1 className="page-title">Overview</h1>
        <AsyncBoundary
          state={position}
          render={(p) => <ContextStrip chain="Base" protocol="Aave V3" available={p.available} />}
        />
      </div>

      <div className="card">
        <p className="section-title">Position</p>
        <AsyncBoundary
          state={position}
          render={(p) => {
            if (!p.available || !p.data) {
              return <div className="metric-value small">Unavailable</div>;
            }
            const tier = riskTier(p.data.health_factor, strategy.status === "ready" ? strategy.data.trigger_health_factor : null);
            const color = tier === "healthy" ? "var(--healthy)" : tier === "danger" ? "var(--danger)" : "var(--text)";
            return (
              <>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", flexWrap: "wrap", gap: 16 }}>
                  <div>
                    <p className="label" style={{ marginBottom: 4 }}>
                      Health factor
                    </p>
                    <div className="metric-value large" style={{ color }}>
                      {formatNumber(p.data.health_factor, 2)}
                    </div>
                  </div>
                  <span className={`badge ${tier === "healthy" ? "healthy" : tier === "danger" ? "danger" : "neutral"}`}>
                    <span className="dot" /> {riskLabel(tier)}
                  </span>
                </div>

                {strategy.status === "ready" && (
                  <div style={{ display: "flex", gap: 28, marginTop: 14 }}>
                    <div>
                      <div className="label" style={{ marginBottom: 2 }}>
                        Risk threshold
                      </div>
                      <span className="mono">{strategy.data.trigger_health_factor}</span>
                    </div>
                    <div>
                      <div className="label" style={{ marginBottom: 2 }}>
                        Target
                      </div>
                      <span className="mono">≥ {strategy.data.target_health_factor}</span>
                    </div>
                  </div>
                )}

                <hr className="card-divider" />

                <div className="stat-row">
                  <div className="stat">
                    <div className="label">Collateral</div>
                    <div className="mono metric-value small">
                      {p.data.collateral_usd ? `$${formatNumber(p.data.collateral_usd, 2)}` : "--"}
                    </div>
                  </div>
                  <div className="stat">
                    <div className="label">Debt</div>
                    <div className="mono metric-value small">
                      {p.data.debt_usd ? `$${formatNumber(p.data.debt_usd, 2)}` : "--"}
                    </div>
                  </div>
                  <div className="stat">
                    <div className="label">LTV</div>
                    <div className="mono metric-value small">{p.data.ltv ?? "--"}</div>
                  </div>
                  <div className="stat">
                    <div className="label">Chain / Protocol</div>
                    <div className="mono" style={{ marginTop: 6 }}>
                      {p.data.chain_display} / {p.data.protocol_display}
                    </div>
                  </div>
                </div>
              </>
            );
          }}
        />
      </div>

      <div className="grid grid-2" style={{ marginTop: 16 }}>
        <div className="card">
          <p className="section-title">Strategy</p>
          <AsyncBoundary
            state={strategy}
            render={(s) => (
              <>
                <div style={{ fontWeight: 600, fontSize: 15 }}>{s.protocol_display} Deleverage</div>
                <div style={{ color: "var(--text-muted)", fontSize: 13, marginTop: 4 }}>
                  {s.trigger}
                </div>
                <div className="metadata" style={{ marginTop: 10 }}>
                  {s.decision_engine} decides · {s.execution_layer} executes
                </div>
              </>
            )}
          />
        </div>

        <div className="card">
          <p className="section-title">Monitoring</p>
          <AsyncBoundary
            state={engineStatus}
            render={(e) =>
              !e.configured ? (
                <span className="badge neutral">
                  <span className="dot" /> Not configured
                </span>
              ) : (
                <>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    {(() => {
                      const display = monitoringDisplay(e);
                      const badgeClass = display === "running" ? "healthy" : display === "stopped" ? "neutral" : "warning";
                      return (
                        <span className={`badge ${badgeClass}`}>
                          <span className="dot" /> {monitoringLabel(display)}
                        </span>
                      );
                    })()}
                    <span className="badge accent">{e.execution_mode === "DRY_RUN" ? "Dry run" : e.execution_mode}</span>
                  </div>
                  {e.runner_error && (
                    <p className="metadata" style={{ marginTop: 10, color: "var(--danger)" }}>
                      {e.runner_error}
                    </p>
                  )}
                </>
              )
            }
          />
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <p className="section-title">Recent activity</p>
        <AsyncBoundary
          state={activity}
          render={(a) => <ActivityTimeline events={a.events.slice(-5).reverse()} />}
        />
      </div>
    </div>
  );
}
