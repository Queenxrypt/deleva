import { api } from "../api/client";
import { useApi } from "../api/useApi";
import { AsyncBoundary } from "../components/AsyncBoundary";
import { ContextStrip } from "../components/ContextStrip";
import { riskTier, riskLabel } from "../lib/risk";
import { formatNumber, truncateHex } from "../lib/format";

function RiskScale({ healthFactor, trigger }: { healthFactor: number; trigger: number }) {
  // A simple, honest visual: position on a 0..2x-trigger scale. Not a
  // generic portfolio chart -- specific to this one strategy's threshold.
  const max = trigger * 2.5;
  const pct = Math.min(100, (healthFactor / max) * 100);
  const triggerPct = Math.min(100, (trigger / max) * 100);
  return (
    <div style={{ marginTop: 20 }}>
      <div className="label" style={{ marginBottom: 8 }}>
        Risk scale
      </div>
      <div
        style={{
          position: "relative",
          height: 8,
          background: "var(--surface-raised)",
          borderRadius: 999,
          border: "1px solid var(--border)",
        }}
      >
        <div
          style={{
            position: "absolute",
            left: 0,
            top: 0,
            bottom: 0,
            width: `${pct}%`,
            background: healthFactor >= trigger ? "var(--healthy)" : "var(--danger)",
            borderRadius: 999,
          }}
        />
        <div
          title={`Trigger threshold: ${trigger}`}
          style={{
            position: "absolute",
            left: `${triggerPct}%`,
            top: -4,
            bottom: -4,
            width: 2,
            background: "var(--warning)",
          }}
        />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--text-faint)", marginTop: 6 }}>
        <span>0</span>
        <span style={{ color: "var(--warning)" }}>Trigger {trigger}</span>
        <span>{max.toFixed(1)}+</span>
      </div>
    </div>
  );
}

export function Positions() {
  const position = useApi(api.position, []);
  const strategy = useApi(api.strategy, []);

  return (
    <div>
      <div className="page-head">
        <h1 className="page-title">Positions</h1>
        <AsyncBoundary state={position} render={(p) => <ContextStrip chain="Base" protocol="Aave V3" available={p.available} />} />
      </div>

      <AsyncBoundary
        state={position}
        render={(p) => {
          if (!p.available || !p.data) {
            return (
              <div className="card">
                <p className="metric-value small">Unavailable</p>
                <p style={{ color: "var(--text-muted)", fontSize: 13 }}>{p.reason}</p>
              </div>
            );
          }
          const d = p.data;
          const tier = strategy.status === "ready" ? riskTier(d.health_factor, strategy.data.trigger_health_factor) : "unknown";
          const color = tier === "healthy" ? "var(--healthy)" : tier === "danger" ? "var(--danger)" : "var(--text)";
          return (
            <div className="card">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 12 }}>
                <div>
                  <p className="section-title" style={{ marginBottom: 4 }}>
                    {d.protocol_display} · {d.chain_display}
                  </p>
                  <div className="label" style={{ marginTop: 12, marginBottom: 4 }}>
                    Managed wallet
                  </div>
                  <a
                    href={`https://basescan.org/address/${d.wallet}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="truncated-address"
                    title={d.wallet}
                  >
                    {truncateHex(d.wallet, 8, 6)}
                  </a>
                </div>
                {strategy.status === "ready" && (
                  <span className={`badge ${tier === "healthy" ? "healthy" : tier === "danger" ? "danger" : "neutral"}`}>
                    <span className="dot" /> {riskLabel(tier)}
                  </span>
                )}
              </div>

              <hr className="card-divider" />

              <div style={{ display: "flex", gap: 40, flexWrap: "wrap", alignItems: "flex-end" }}>
                <div>
                  <div className="label">Health factor</div>
                  <div className="metric-value large" style={{ color }}>
                    {formatNumber(d.health_factor, 2)}
                  </div>
                </div>
                <div className="stat-row" style={{ flex: 1, minWidth: 220 }}>
                  <div className="stat">
                    <div className="label">Collateral</div>
                    <div className="mono metric-value small">{d.collateral_usd ? `$${formatNumber(d.collateral_usd, 2)}` : "--"}</div>
                  </div>
                  <div className="stat">
                    <div className="label">Debt</div>
                    <div className="mono metric-value small">{d.debt_usd ? `$${formatNumber(d.debt_usd, 2)}` : "--"}</div>
                  </div>
                </div>
              </div>

              <div className="stat-row" style={{ marginTop: 24 }}>
                <div className="stat">
                  <div className="label">LTV</div>
                  <div className="mono">{d.ltv ?? "--"}</div>
                </div>
                <div className="stat">
                  <div className="label">Liquidation threshold</div>
                  <div className="mono">{d.liquidation_threshold ?? "--"}</div>
                </div>
                <div className="stat">
                  <div className="label">Wallet USDC</div>
                  <div className="mono">{d.usdc_balance ? formatNumber(d.usdc_balance, 2) : "--"}</div>
                </div>
              </div>

              {strategy.status === "ready" && d.health_factor && (
                <RiskScale healthFactor={Number(d.health_factor)} trigger={Number(strategy.data.trigger_health_factor)} />
              )}
            </div>
          );
        }}
      />
    </div>
  );
}
