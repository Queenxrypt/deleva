import { api } from "../api/client";
import { useApi } from "../api/useApi";
import { AsyncBoundary } from "../components/AsyncBoundary";
import { ActivityTimeline } from "../components/ActivityTimeline";
import { ModeIndicator } from "../components/ModeIndicator";
import { truncateHex } from "../lib/format";

const AUTONOMOUS_TX = "0xd16bd7157d4415d7899345c8787858e0affdc01800739225635f0421999cd831";
const AUTONOMOUS_TX_LINK = `https://basescan.org/tx/${AUTONOMOUS_TX}`;

export function Activity() {
  const activity = useApi(api.activity, []);

  return (
    <div>
      <div className="page-head">
        <h1 className="page-title">Activity</h1>
      </div>

      <div className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <p className="section-title" style={{ margin: 0 }}>
            Autonomous execution
          </p>
          <ModeIndicator mode="live" />
        </div>
        <p className="body-copy" style={{ marginTop: 12 }}>
          DELEVA detected a real health-factor breach and autonomously executed a deleverage
          through KeeperHub, unattended.
        </p>

        <hr className="card-divider" />

        <div className="stat-row">
          <div className="stat">
            <div className="label">Deleverage amount</div>
            <div className="mono metric-value small">2.93256692</div>
          </div>
          <div className="stat">
            <div className="label">Pre-trigger HF</div>
            <div className="mono metric-value small">1.28</div>
          </div>
          <div className="stat">
            <div className="label">Post-execution HF</div>
            <div className="mono metric-value small">1.4999</div>
          </div>
        </div>

        <a
          href={AUTONOMOUS_TX_LINK}
          target="_blank"
          rel="noopener noreferrer"
          className="btn primary"
          style={{ marginTop: 18, display: "inline-block" }}
        >
          View transaction: {truncateHex(AUTONOMOUS_TX, 10, 6)}
        </a>
      </div>

      <div className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <p className="section-title" style={{ margin: 0 }}>
            Manual execution
          </p>
          <ModeIndicator mode="historical_proof" />
        </div>
        <AsyncBoundary
          state={activity}
          render={(a) => (
            <>
              <p className="body-copy" style={{ marginTop: 12 }}>
                An earlier deleverage, manually invoked to validate the Almanak → KeeperHub → Aave
                execution path before autonomous monitoring was running.
              </p>
              <a
                href={a.real_proof_transaction_link}
                target="_blank"
                rel="noopener noreferrer"
                className="btn"
                style={{ marginTop: 12, display: "inline-block" }}
              >
                View transaction: {truncateHex(a.real_proof_transaction_hash, 10, 6)}
              </a>
            </>
          )}
        />
      </div>

      <div className="card">
        <p className="section-title">Execution history</p>
        <p className="metadata" style={{ marginBottom: 16 }}>
          Every event below is tagged with its source: live or manual.
        </p>
        <AsyncBoundary state={activity} render={(a) => <ActivityTimeline events={[...a.events].reverse()} />} />
      </div>
    </div>
  );
}
