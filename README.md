# DELEVA

**Autonomous DeFi position management.**
**Almanak decides. KeeperHub executes.**

DELEVA monitors an Aave V3 position on Base, and when its health factor
crosses a configured risk threshold, has Almanak compile the exact
deleverage action needed, translates it for KeeperHub, simulates it, and —
only on a clean simulation — executes it. Built for the KeeperHub Agent
Economy Hackathon.

## Proof transactions

DELEVA has two real, distinct proof transactions on Base mainnet. Neither
replaces or relabels the other.

### Autonomous execution (primary)

```
0xd16bd7157d4415d7899345c8787858e0affdc01800739225635f0421999cd831
```
https://basescan.org/tx/0xd16bd7157d4415d7899345c8787858e0affdc01800739225635f0421999cd831

DELEVA's own `MonitoringRunner`, running unattended in `LIVE` mode, detected
a real Aave V3 health-factor breach (1.28, below the 1.50 trigger) and
autonomously executed a 2.93256692 USDC deleverage through KeeperHub. No
human triggered this cycle. Full evidence, including every activity-log
timestamp and an independent cross-check against KeeperHub's own status API,
is in [`proof/DELEVA_AUTONOMOUS_PROOF.md`](proof/DELEVA_AUTONOMOUS_PROOF.md).
**This transaction hash must never be replaced or relabeled.**

### Manual execution (secondary)

```
0xd36217b09ba81cea624e88e756514f2ebc0dc689a20dad4286d6f852f205ec57
```
https://basescan.org/tx/0xd36217b09ba81cea624e88e756514f2ebc0dc689a20dad4286d6f852f205ec57

An earlier real Base mainnet transaction, manually invoked while the
position's health factor (2.0795) was above the 1.50 trigger, to validate
that the Almanak `DeleverageIntent` → `ActionBundle` → KeeperHub → Aave V3
path executes correctly end to end before autonomous monitoring was running.
It reduced real debt from $11.9985 to $1.9998. Full evidence is in
[`proof/DELEVA_TRANSACTION_PROOF.md`](proof/DELEVA_TRANSACTION_PROOF.md).
**This transaction hash must never be replaced** — not by the earlier WETH
feasibility test (superseded, see
[`proof/DELEVA_INITIAL_BLOCKER.md`](proof/DELEVA_INITIAL_BLOCKER.md)), and
not by a demo/mock hash.

## Architecture

```
Aave V3 Position (Base)
        |
        v
DELEVA  ---------------------------  product orchestration / position management
   - AavePositionService (read)
   - RiskEvaluator (HEALTHY / THRESHOLD_BREACHED)
   - AutonomousEngine (the monitor -> decide -> execute -> verify cycle)
        |
        v
Almanak  ---------------------------  decision / strategy layer
   - Real, installed IntentCompiler
   - DeleverageIntent -> ActionBundle (real ABI-encoded calldata)
        |
        v
DELEVA adapter (keeperhub_adapter.py)  --  translates ActionBundle -> KeeperHub requests
        |
        v
KeeperHub  --------------------------  execution / reliability layer
   - REST Direct Execution API: simulate -> (if safe) execute -> poll status
        |
        v
Base  -------------------------------  settlement
   - Confirmed transaction, verified against the resulting position
```

### Almanak integration

DELEVA never hand-builds a repay/approve transaction. `deleva/almanak_interface.py`
calls the real, vendored Almanak SDK's `IntentCompiler.compile()` on a real
`DeleverageIntent` — the exact call shape that produced the real proof
transaction. The repay amount is derived from the strategy's target health
factor (`deleva/engine.py::_deleverage_amount`), not hardcoded, using Aave's
own health-factor formula: `debt_needed_for_target = collateral_usd *
liquidation_threshold / target_hf`.

### KeeperHub integration

`deleva/keeperhub_client.py` is a small, reusable REST client for KeeperHub's
**Direct Execution API** (`POST /api/execute/contract-call`, with
`simulate: true` for dry-runs, and `GET /api/execute/{id}/status` for
polling). This is the execution surface this integration actually uses.

**KeeperHub Workflow / scheduled monitoring is not used or claimed by this
code.** DELEVA's own `AutonomousEngine`/`MonitoringRunner` is what performs
health-factor monitoring, not a KeeperHub Workflow. **MCP is not implemented
anywhere in this repository** and is not claimed as part of this
integration.

### Aave V3 integration

Reads go through `Pool.getUserAccountData(address)` (Base:
`0xA238Dd80C259a72e81d7e4664a9801593F98d1c5`) — the same read verified
repeatedly against the real deployment throughout this project. Position
data is protocol-level (Aave's own aggregate account read), not per-asset —
per-asset token amounts (e.g. exact WETH supplied) are not exposed by this
model.

### The autonomous engine

```
MonitoringRunner (interval loop, no cycle logic of its own)
        v
AutonomousEngine.run_cycle()
        v
Position -> RiskEvaluator -> Strategy -> Almanak -> ActionBundle -> Adapter
        -> KeeperHub simulate -> KeeperHub execute -> verify -> ActivityLog
```

`AutonomousEngine` is a pure, single-cycle unit with no `time.sleep` of its
own; `MonitoringRunner` is the thin loop around it. This separation exists
specifically so a cycle can be unit tested, run once, or run repeatedly
without changing the engine itself.

### DRY_RUN vs LIVE

`DELEVA_EXECUTION_DRY_RUN` defaults to `true` everywhere in this codebase.
In `DRY_RUN`, the engine reads the real position, calls the real Almanak
compiler, and simulates the first transaction leg for real against
KeeperHub — but never calls execute. `LIVE` is the only mode that ever
calls `KeeperHubClient.execute_contract_call`/`execute_and_wait`, and it is
never flipped on by any code path — only by an operator explicitly setting
the environment variable before the process starts. The backend API never
overrides this, and the frontend has no control that can flip it.

### Demo mode

`deleva/demo.py::run_local_demo()` runs a fully deterministic, three-cycle
simulation (HEALTHY -> THRESHOLD_BREACHED -> HEALTHY) using a scripted
position sequence and a fully mocked KeeperHub client — no network call is
ever made. The one real component it exercises is Almanak: the
`ActionBundle` in cycle 2 is genuinely compiled by the real IntentCompiler.
Every demo transaction hash is prefixed `0xDEMO...` and is asserted (in
tests) to never match the real proof hash. The frontend labels this mode
explicitly wherever it appears.

### Known limitations (documented, not hidden)

1. **Multi-leg timeout/resume is simplified.** If a KeeperHub execution
   times out mid-bundle, the engine records the pending `executionId` and
   resolves it (a single status check, not a blind retry) on the *next*
   cycle — but does not automatically resume and execute the remaining
   legs of that same bundle. The next cycle re-reads the position and
   decides fresh. This is safe (an ERC-20 approve is idempotent; a repay
   amount is bounded by real outstanding debt) but is not a full
   saga/resumption engine.
2. **The repay amount sizing** targets the strategy's `target_health_factor`
   but uses a fixed floor (`DELEVA_MIN_DELEVERAGE_AMOUNT`, default 10 USDC)
   to avoid dust transactions — it does not account for slippage, price
   movement between compile and execution, or gas cost optimization.
3. **Background monitoring is real.** `POST /api/engine/start` runs
   `MonitoringRunner` on a background thread inside the API process itself
   (`deleva/runner.py::start_in_background`) against the same
   `AutonomousEngine` instance every other route reads — this is what
   produced the autonomous proof transaction above, not the CLI. A
   dedicated `_cycle_lock` (added after the initial background-loop work)
   prevents a manual `run-once` call from ever racing an in-flight
   autonomous cycle, including one still finishing after `POST
   /api/engine/stop`. An unexpected cycle-level exception (e.g. a
   transient KeeperHub/network failure) degrades the loop — surfaced via
   `runner_error` in `/api/engine/status` — rather than silently killing
   it; it clears on the next successful cycle. The CLI's own
   `python -m deleva start` remains available as a separate, foreground
   loop against its own engine instance; the CLI and the API never share
   one running process.
4. Per-asset token amounts (e.g. exact WETH collateral quantity) are not
   exposed — only Aave's own protocol-level USD-denominated aggregates.

## Project structure

```
proof/           DELEVA backend: engine, API, tests, proof artifacts
  deleva/        the reusable backend package (config, models, risk,
                 strategy, almanak_interface, keeperhub_client, adapter,
                 activity, engine, runner, persistence, demo, cli)
  api/           FastAPI backend (thin layer over deleva/)
  tests/         pytest suite
  keeperhub_adapter.py, test_adapter.py   original, preserved adapter + tests
  DELEVA_TRANSACTION_PROOF.md             the real proof (see above)
  DELEVA_INITIAL_BLOCKER.md               superseded pre-funding investigation
web/             frontend (landing page + product app)
scratch/         investigation material only, not part of the product
```

**`almanak-sdk/` is not included in this repository.** Almanak
(`almanak==2.28.0`, Apache-2.0, published on PyPI) is installed as a normal
dependency -- see "Running the backend" below -- not vendored in-tree.

## Running the backend

Requires Python >=3.12 (the version Almanak's own package requires).

```bash
cd proof
# almanak-sdk/ is not part of this repository -- Almanak is installed as a
# normal PyPI dependency, pinned to the exact version this project was built
# and tested against.
pip install "almanak==2.28.0" fastapi uvicorn

cp .env.example .env          # fill in real values -- see below
# minimum for real position data:
export KEEPERHUB_API_KEY=kh_...
export DELEVA_MONITORED_WALLET=0x...

uvicorn api.main:app --reload --port 8000
```

Without `KEEPERHUB_API_KEY`/`DELEVA_MONITORED_WALLET` set, the API still
starts — `/api/health` and `/api/strategy` work immediately, and
`/api/position`/`/api/engine/status` report themselves explicitly
unavailable (never fake data). `/api/demo/run` never requires configuration.

CLI (same engine, no HTTP layer):

```bash
python -m deleva status
python -m deleva once
python -m deleva dry-run
python -m deleva demo
python -m deleva start   # foreground loop, Ctrl+C to stop
```

## Running the frontend

```bash
cd web
npm install
npm run dev   # http://localhost:5173, proxies /api to http://127.0.0.1:8000
```

Landing page at `/`, documentation at `/docs`, product app at `/app`
(Overview, Positions, Strategies, Activity).

## Running the tests

```bash
cd proof
python -m pytest test_adapter.py tests/ -v
```

**234 tests passing** as of this phase. Frontend has no dedicated test
runner -- its contract with the backend is covered by the API tests in
`tests/test_api.py`, and the build (`npm run build`, TypeScript strict
mode) is verified to pass cleanly.

## Security

- `KEEPERHUB_API_KEY` is read only from the environment, held only inside
  `KeeperHubClient`, and never returned by any API route (enforced by
  `tests/test_api.py::TestNoSecretsExposed`, including a check of the
  generated OpenAPI schema).
- No private keys, signing credentials, or RPC secrets are used or stored
  by this codebase — KeeperHub's own organization wallet performs signing.
- CORS is restricted to `localhost:5173`/`127.0.0.1:5173` (the Vite dev
  server) — not `*`.
- Never commit a real `.env`. `.env.example` contains placeholders only.
