---
format: 1920x1080
duration: 70s
message: Almanak decides. KeeperHub executes.
arc: Problem → Detect → Decide → Translate/Simulate → Execute → Autonomous result → Execution-path proof → Lockup
audience: KeeperHub hackathon judges
mode: autonomous
---

## Frame 1 — Risk while you're away

- status: outline
- src: compositions/01-problem.html
- duration: 7s
- transition_in: cut
- scene: Aave V3 position. Health factor 1.28 against threshold 1.50. Danger state.
- voiceover: Your DeFi position can become risky while you're away.
- blueprint: dataviz-countup
- rules: counting-dynamic-scale, stat-bars-and-fills, waterfall-entry

Hero health factor 1.28 in danger red. Threshold 1.50 in warning. Risk scale fill stops short of the trigger tick. Context: Aave V3 · Base.

## Frame 2 — DELEVA detects

- status: outline
- src: compositions/02-detect.html
- duration: 8s
- transition_in: cut
- scene: DELEVA risk card. RISK DETECTED. Activity events POSITION_EVALUATED then RISK_THRESHOLD_BREACHED.
- voiceover: DELEVA watches the position and acts when your risk threshold is reached.
- blueprint: agent-progress-theater
- rules: waterfall-entry, discrete-text-sequence

Product overview recreation. HF 1.28 vs 1.50. Danger badge. Timeline events from the real autonomous cycle.

## Frame 3 — Almanak decides

- status: outline
- src: compositions/03-almanak.html
- duration: 9.5s
- transition_in: cut
- scene: DeleverageIntent then ActionBundle REPAY — approve + repay.
- voiceover: Almanak determines the strategy and compiles it into executable actions.
- blueprint: grid-card-assemble
- rules: waterfall-entry, center-outward-expansion

Intent fields: protocol Aave V3, token USDC, target HF 1.50, amount 2.93256692. Then ActionBundle intent_type REPAY, two transactions.

## Frame 4 — Adapter and simulation

- status: outline
- src: compositions/04-adapter-sim.html
- duration: 9.5s
- transition_in: cut
- scene: DELEVA adapter translates ActionBundle to KeeperHub calls. Simulation passed.
- voiceover: DELEVA translates the action, and KeeperHub simulates it before execution.
- blueprint: agent-progress-theater
- rules: waterfall-entry, discrete-text-sequence

Adapter arrow ActionBundle → KeeperHub contract-call. Then SIMULATION PASSED, wouldRevert false on both legs.

## Frame 5 — KeeperHub executes

- status: outline
- src: compositions/05-execute.html
- duration: 7s
- transition_in: cut
- scene: EXECUTION CONFIRMED then Aave V3 repayment executed.
- voiceover: Once the simulation passes, KeeperHub executes.
- blueprint: titlecard-reveal
- rules: waterfall-entry, spring-pop-entrance

KeeperHub execution confirmed, then Aave V3 repayment executed. Status healthy.

## Frame 6 — Autonomous result

- status: outline
- src: compositions/06-autonomous.html
- duration: 12s
- transition_in: cut
- scene: Autonomous proof before/after. HF 1.28 → 1.50. Debt $19.9977 → $17.0652. Amount 2.93256692 USDC.
- voiceover: The autonomous runner detected a health factor of 1.28, below 1.50, and repaid 2.93 USDC.
- blueprint: dataviz-countup
- rules: counting-dynamic-scale, comparison-split (flat, no 3D tilt)

Labeled AUTONOMOUS PROOF / Live. Real hash 0xd16bd715… Real metrics from DELEVA_AUTONOMOUS_PROOF.md. Post-repay HF 1.49997 is shown in warning, not healthy — it landed at the 1.50 boundary.

## Frame 7 — Execution-path proof

- status: outline
- src: compositions/07-manual-proof.html
- duration: 10s
- transition_in: cut
- scene: Manual execution-path proof on Base. Hash 0xd36217b0…. Debt $11.9985 → $1.9998. HF 2.0795 → 12.454.
- voiceover: A separate Base transaction proves the execution path. Real repayment. Confirmed on-chain.
- blueprint: titlecard-reveal
- rules: waterfall-entry, counting-dynamic-scale

Labeled EXECUTION PATH PROOF / Manual execution. Explicitly not the threshold-triggered cycle. Hash 0xd36217b09ba81cea624e88e756514f2ebc0dc689a20dad4286d6f852f205ec57. Base confirmed, block 51,395,399.

## Frame 8 — Lockup

- status: outline
- src: compositions/08-lockup.html
- duration: 6.5s
- transition_in: cut
- scene: DELEVA. Autonomous DeFi position management. Almanak decides. KeeperHub executes.
- voiceover: DELEVA. Almanak decides. KeeperHub executes.
- blueprint: titlecard-reveal
- rules: waterfall-entry, logo-assemble-lockup
