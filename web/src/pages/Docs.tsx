import { Link } from "react-router-dom";
import { Reveal } from "../components/Reveal";
import { truncateHex } from "../lib/format";

const AUTONOMOUS_TX = "0xd16bd7157d4415d7899345c8787858e0affdc01800739225635f0421999cd831";
const AUTONOMOUS_TX_LINK = `https://basescan.org/tx/${AUTONOMOUS_TX}`;

const HOW_IT_WORKS = [
  { title: "Monitor", body: "DELEVA evaluates the Aave V3 position and its health factor." },
  { title: "Detect", body: "A risk threshold is identified." },
  { title: "Decide", body: "Almanak determines the appropriate strategy action." },
  { title: "Simulate", body: "The proposed transaction is simulated before broadcast." },
  { title: "Execute", body: "KeeperHub handles the actual transaction execution." },
  { title: "Verify", body: "The resulting position and execution status are verified." },
];

const ARCH_FLOW = [
  "Aave V3 Position",
  "DELEVA Monitoring",
  "Almanak Strategy",
  "Intent",
  "ActionBundle",
  "KeeperHub Simulation",
  "KeeperHub Execution",
  "Base",
  "Position Verification",
];

export function Docs() {
  return (
    <div className="landing">
      <div className="landing-nav">
        <Link to="/" className="brand">
          DELEVA
        </Link>
        <Link to="/app" className="btn primary">
          Launch app
        </Link>
      </div>

      <section className="hero" style={{ padding: "48px 24px 16px", textAlign: "left", maxWidth: 780 }}>
        <h1 style={{ fontSize: "clamp(32px, 6vw, 44px)" }}>DELEVA</h1>
        <p className="tagline" style={{ textAlign: "left" }}>
          Autonomous DeFi position management.
        </p>
        <p className="docs-lede" style={{ marginTop: 18 }}>
          DELEVA continuously evaluates a DeFi position. When risk conditions are met, Almanak
          determines the required action, and execution is routed through KeeperHub.
        </p>
      </section>

      <section className="section" style={{ maxWidth: 780, margin: "0 auto", textAlign: "left" }}>
        <div className="section-head">
          <span className="eyebrow">How it works</span>
          <h2>Monitor → Detect → Decide → Simulate → Execute → Verify</h2>
        </div>
        <div className="docs-steps">
          {HOW_IT_WORKS.map((step, i) => (
            <div className="docs-step" key={step.title}>
              <div className="docs-step-index">{String(i + 1).padStart(2, "0")}</div>
              <div>
                <h4>{step.title}</h4>
                <p>{step.body}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="section" style={{ maxWidth: 780, margin: "0 auto", textAlign: "left" }}>
        <div className="section-head">
          <span className="eyebrow">Almanak × KeeperHub</span>
          <h2>Almanak decides. KeeperHub executes.</h2>
        </div>
        <div className="grid grid-2">
          <div className="card">
            <p className="section-title">Almanak</p>
            <ul className="docs-list">
              <li>Strategy and decision layer</li>
              <li>Produces the deleverage intent</li>
              <li>Compiles the intent into an ActionBundle</li>
            </ul>
          </div>
          <div className="card">
            <p className="section-title">KeeperHub</p>
            <ul className="docs-list">
              <li>Execution layer</li>
              <li>Simulates transactions before broadcast</li>
              <li>Executes the resulting transactions</li>
              <li>Provides execution status and auditability</li>
            </ul>
          </div>
        </div>
        <p className="body-copy" style={{ marginTop: 16 }}>
          DELEVA connects these two layers: it reads the position, hands the decision to Almanak,
          and routes the resulting transactions through KeeperHub. Execution today is through
          KeeperHub's REST Direct Execution API. KeeperHub Workflows, MCP, x402, and MPP are not
          part of this integration.
        </p>
      </section>

      <section className="section" style={{ maxWidth: 780, margin: "0 auto", textAlign: "left" }}>
        <div className="section-head">
          <span className="eyebrow">Strategy</span>
          <h2>The deleverage strategy</h2>
        </div>
        <div className="stat-row">
          <div className="stat">
            <div className="label">Risk threshold</div>
            <div className="mono metric-value small">HF &lt; 1.50</div>
          </div>
          <div className="stat">
            <div className="label">Target</div>
            <div className="mono metric-value small">HF ≥ 1.50</div>
          </div>
        </div>
        <p className="body-copy" style={{ marginTop: 20 }}>
          When the position's health factor crosses below the risk threshold, Almanak generates a
          deleverage intent. The amount is determined by the strategy for the current position, not
          a fixed value. The real autonomous execution below repaid 2.93256692 USDC for that
          specific position; a different position would produce a different amount.
        </p>
      </section>

      <section className="section" style={{ maxWidth: 780, margin: "0 auto", textAlign: "left" }}>
        <div className="section-head">
          <span className="eyebrow">Execution</span>
          <h2>From intent to transaction</h2>
        </div>
        <p className="body-copy">
          Strategy decision → Intent → ActionBundle → KeeperHub execution. For the current Aave V3
          deleverage strategy, the ActionBundle contains two transactions, executed in sequence:
        </p>
        <div className="docs-tx-steps">
          <div className="docs-tx-step">
            <span className="n">1</span>
            <span>USDC approval to the Aave V3 Pool</span>
          </div>
          <div className="docs-tx-step">
            <span className="n">2</span>
            <span>Aave V3 repay transaction</span>
          </div>
        </div>
        <p className="body-copy">
          These are two separate on-chain transactions, not a single Multicall. The repay's
          allowance check depends on the approval having already been mined, so each transaction is
          simulated and executed in order, not bundled together.
        </p>
      </section>

      <section className="section" style={{ maxWidth: 780, margin: "0 auto", textAlign: "left" }}>
        <div className="section-head">
          <span className="eyebrow">Safety</span>
          <h2>Simulation first</h2>
        </div>
        <p className="body-copy">
          DELEVA does not broadcast a generated transaction directly. Each transaction is simulated
          first, and execution only proceeds after a successful simulation. Simulation catches
          expected execution failures before broadcast; it does not guarantee the transaction will
          succeed once broadcast.
        </p>
      </section>

      <section className="section" style={{ maxWidth: 780, margin: "0 auto", textAlign: "left" }}>
        <div className="section-head">
          <span className="eyebrow">Proof</span>
          <h2>Real autonomous execution</h2>
        </div>
        <Reveal>
          <div className="card">
            <p className="body-copy">
              DELEVA detected a real Aave V3 health-factor breach and autonomously executed a
              2.93256692 USDC deleverage through KeeperHub.
            </p>
            <hr className="card-divider" />
            <div className="stat-row">
              <div className="stat">
                <div className="label">Before</div>
                <div className="mono metric-value small">HF 1.280004…</div>
              </div>
              <div className="stat">
                <div className="label">After</div>
                <div className="mono metric-value small">HF 1.499967…</div>
              </div>
              <div className="stat">
                <div className="label">Debt</div>
                <div className="mono metric-value small">$19.9977 → $17.0652</div>
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
        </Reveal>
      </section>

      <section className="section" style={{ maxWidth: 780, margin: "0 auto", textAlign: "left" }}>
        <div className="section-head">
          <span className="eyebrow">Architecture</span>
          <h2>The pipeline</h2>
        </div>
        <div className="arch-flow">
          {ARCH_FLOW.map((name, i) => (
            <Reveal key={name} delay={i * 40}>
              <div className="arch-node">
                <div className="name">{name}</div>
              </div>
              {i < ARCH_FLOW.length - 1 && <div className="arch-arrow">↓</div>}
            </Reveal>
          ))}
        </div>
        <p className="body-copy" style={{ marginTop: 24, textAlign: "center" }}>
          DELEVA is not a general-purpose autonomous agent framework. It demonstrates autonomous
          DeFi position management for one strategy: Aave V3 deleverage, decided by Almanak and
          executed by KeeperHub.
        </p>
      </section>

      <div className="footer">
        <div className="footer-brand">DELEVA</div>
        <div className="footer-line">Autonomous DeFi position management.</div>
        <div className="footer-pair">ALMANAK × KEEPERHUB</div>
      </div>
    </div>
  );
}
