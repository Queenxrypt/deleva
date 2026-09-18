# DELEVA

**Autonomous DeFi position management. Almanak decides. KeeperHub executes.**

DELEVA is an autonomous DeFi position manager for Aave V3 on Base. It
continuously monitors a position's health factor and, when it falls below a
configured risk threshold, uses Almanak to determine and compile the
required deleverage action. DELEVA then routes that action to KeeperHub,
which simulates the transactions before executing them on Base and tracks
the execution status. The goal is simple: automatically reduce position
risk without requiring the user to manually react to a health-factor
breach.

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
autonomously executed a 2.93256692 USDC deleverage through KeeperHub,
bringing the health factor back to approximately 1.50. No human triggered
this cycle. Full evidence, including every activity-log
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
**This transaction hash must never be replaced**, not by the earlier WETH
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
`DeleverageIntent`: the exact call shape that produced the real proof
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
`0xA238Dd80C259a72e81d7e4664a9801593F98d1c5`), the same read verified
repeatedly against the real deployment throughout this project. Position
data is protocol-level (Aave's own aggregate account read), not per-asset:
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
KeeperHub, but never calls execute. `LIVE` is the only mode that ever
calls `KeeperHubClient.execute_contract_call`/`execute_and_wait`, and it is
never flipped on by any code path; only an operator explicitly setting the
environment variable before the process starts turns it on. The backend
API never overrides this, and the frontend has no control that can flip
it.

### Known limitations (documented, not hidden)

1. **Multi-transaction execution recovery is simplified.** If a KeeperHub
   execution times out mid-bundle, the engine records the pending
   `executionId` and resolves it with a single status check on the *next*
   cycle, rather than automatically resuming and completing the remaining
   legs of that same bundle. The next cycle re-reads the position and
   decides fresh. This is safe (an ERC-20 approve is idempotent; a repay
   amount is bounded by real outstanding debt), but it is not a full
   saga/resumption engine.
2. **Minimum deleverage size is configurable, not adaptive.**
   `DELEVA_MIN_DELEVERAGE_AMOUNT` (default 10 USDC) is a fixed floor used
   to avoid dust transactions. It does not account for slippage, price
   movement between compile and execution, or gas cost optimization.
3. **Background monitoring runs inside the API process.**
   `POST /api/engine/start` runs `MonitoringRunner` on a background thread
   inside the API process itself, not as a separate, dedicated worker or
   service. This is what produced the autonomous proof transaction above.
   A CLI-only foreground loop (`python -m deleva start`) is also
   available, but the CLI and the API never share one running process.
4. **Strategy scope is limited to Aave V3 deleveraging on Base.** DELEVA
   does not currently support other protocols, other chains, or other
   strategy types.

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
starts. `/api/health` and `/api/strategy` work immediately, and
`/api/position`/`/api/engine/status` report themselves explicitly
unavailable (never fake data).

CLI (same engine, no HTTP layer):

```bash
python -m deleva status
python -m deleva once
python -m deleva dry-run
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

**234 tests passing.** Frontend has no dedicated test
runner -- its contract with the backend is covered by the API tests in
`tests/test_api.py`, and the build (`npm run build`, TypeScript strict
mode) is verified to pass cleanly.

## Security

- `KEEPERHUB_API_KEY` is read only from the environment, held only inside
  `KeeperHubClient`, and never returned by any API route (enforced by
  `tests/test_api.py::TestNoSecretsExposed`, including a check of the
  generated OpenAPI schema).
- No private keys, signing credentials, or RPC secrets are used or stored
  by this codebase; KeeperHub's own organization wallet performs signing.
- CORS is restricted to `localhost:5173`/`127.0.0.1:5173` (the Vite dev
  server), not `*`.
- Never commit a real `.env`. `.env.example` contains placeholders only.
