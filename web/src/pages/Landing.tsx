import { Link } from "react-router-dom";
import { Reveal } from "../components/Reveal";
import { handleSpotlight } from "../lib/interaction";

const AUTONOMOUS_PROOF_TX = "0xd16bd7157d4415d7899345c8787858e0affdc01800739225635f0421999cd831";
const AUTONOMOUS_PROOF_LINK = `https://basescan.org/tx/${AUTONOMOUS_PROOF_TX}`;

const HOW_IT_WORKS: Array<{ index: string; title: string; body: string }> = [
  {
    index: "01",
    title: "Monitor",
    body: "DELEVA reads the real Aave V3 position on Base and evaluates health factor against the configured risk threshold.",
  },
  {
    index: "02",
    title: "Decide",
    body: "When the threshold is breached, Almanak compiles the exact deleverage action as a real ActionBundle.",
  },
  {
    index: "03",
    title: "Execute",
    body: "KeeperHub simulates each transaction first and only executes once the simulation is clean.",
  },
];

const ARCH_FLOW: Array<{ name: string; role: string }> = [
  { name: "Aave Position", role: "Health factor, collateral, debt on Base" },
  { name: "DELEVA", role: "Monitors the position, orchestrates the response" },
  { name: "Almanak", role: "Decision layer, compiles the DeleverageIntent" },
  { name: "ActionBundle", role: "Real, ABI-encoded transactions" },
  { name: "KeeperHub", role: "Execution layer, simulates then executes" },
  { name: "Base", role: "Confirmed transaction" },
];

export function Landing() {
  return (
    <div className="landing">
      <div className="landing-nav">
        <span className="brand">DELEVA</span>
        <div style={{ display: "flex", alignItems: "center", gap: 22 }}>
          <Link to="/docs" className="nav-link">
            Docs
          </Link>
          <Link to="/app" className="btn primary">
            Launch app
          </Link>
        </div>
      </div>

      <section className="hero">
        <span className="eyebrow">Almanak × KeeperHub</span>
        <h1>DELEVA</h1>
        <p className="tagline">Autonomous DeFi position management.</p>
        <p className="substatement">Almanak decides. KeeperHub executes.</p>
        <p className="explainer">
          DeFi positions can become risky faster than a user can react. DELEVA continuously
          evaluates the position, lets Almanak determine the required action, and routes execution
          through KeeperHub. Every transaction is simulated before it is ever sent.
        </p>
        <div className="hero-actions">
          <Link to="/app" className="btn primary">
            Launch app
          </Link>
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <span className="eyebrow">How it works</span>
          <h2>Monitor. Decide. Execute.</h2>
        </div>
        <div className="how-grid">
          {HOW_IT_WORKS.map((step, i) => (
            <Reveal key={step.index} delay={i * 80}>
              <div className="how-card" onMouseMove={handleSpotlight}>
                <div className="how-index">{step.index}</div>
                <h3>{step.title}</h3>
                <p>{step.body}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <span className="eyebrow">Architecture</span>
          <h2>One pipeline, three layers</h2>
        </div>
        <div className="arch-flow">
          {ARCH_FLOW.map((node, i) => (
            <Reveal key={node.name} delay={i * 60}>
              <div className="arch-node">
                <div className="name">{node.name}</div>
                <div className="role">{node.role}</div>
              </div>
              {i < ARCH_FLOW.length - 1 && <div className="arch-arrow">↓</div>}
            </Reveal>
          ))}
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <span className="eyebrow">Proof</span>
          <h2>A real autonomous execution</h2>
        </div>
        <Reveal>
          <div className="proof-compact">
            <div className="proof-copy">
              <p>
                DELEVA detected a real Aave V3 health-factor breach and autonomously executed a
                2.93256692 USDC deleverage through KeeperHub.
              </p>
            </div>
            <a href={AUTONOMOUS_PROOF_LINK} target="_blank" rel="noopener noreferrer" className="proof-link btn">
              View transaction
            </a>
          </div>
        </Reveal>
      </section>

      <div className="footer">
        <div className="footer-brand">DELEVA</div>
        <div className="footer-line">Autonomous DeFi position management.</div>
        <div className="footer-pair">ALMANAK × KEEPERHUB</div>
      </div>
    </div>
  );
}
