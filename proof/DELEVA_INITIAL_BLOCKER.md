# DELEVA Initial Blocker Report (superseded — historical record only)

> **This report is superseded.** It documents the pre-funding investigation
> phase, when the KeeperHub organization wallet had no Aave V3 debt position
> and the DELEVA repayment could not yet be attempted. The real, successful
> DELEVA proof transaction is documented separately in
> **`DELEVA_TRANSACTION_PROOF.md`** — that is the file to cite for the
> hackathon submission. This file is kept only as a historical record of the
> feasibility investigation that led up to it.

Status: **NOT EXECUTED — blocked at the mandatory pre-broadcast prerequisite check (no existing debt to repay).**
No transaction was broadcast. No funds moved. This report documents what was
verified, what was simulated, and exactly what is missing before Phase 1 can
be marked DONE.

## 1. Almanak intent parameters (real, non-mocked)

```
DeleverageIntent(
  protocol      = "aave_v3",
  token         = "USDC",
  amount        = 10,
  repay_full    = False,
  chain         = "base",
  trigger_reason = "health_factor_below_threshold",
  observed_hf   = 1.08,
  target_hf     = 1.50,
)
```

Compiled with the real, installed `IntentCompiler` (offline: `rpc_url=None`,
`allow_placeholder_prices=True`). See `proof/run_deleverage_proof.py`.
`IntentType.DELEVERAGE` routes through the identical compiler path as
`IntentType.REPAY` (`almanak/framework/intents/compiler.py`), confirmed live —
`ActionBundle.intent_type == "REPAY"`.

## 2. Real ActionBundle (2 transactions)

| # | tx_type | to | selector | description |
|---|---|---|---|---|
| 0 | `approve` | `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913` (Base USDC) | `0x095ea7b3` | Approve `0xA238Dd80...` to spend token |
| 1 | `lending_repay` | `0xA238Dd80C259a72e81d7e4664a9801593F98d1c5` (Aave V3 Pool) | `0x573ade81` | Repay 10 USDC (variable rate) |

Decoded arguments (adapter round-trip verified byte-for-byte against the
original calldata — see `proof/test_adapter.py::TestDeleverageBundle`):

- `approve(spender=0xA238Dd80C259a72e81d7e4664a9801593F98d1c5, amount=11000000)` (11 USDC — 10% buffer over the 10 USDC repay amount, baked in by the SDK)
- `repay(asset=0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913, amount=10000000, interestRateMode=2, onBehalfOf=<wallet>)`

## 3. Adapter change

Added one registry entry to `proof/keeperhub_adapter.py`:
`repay(address,uint256,uint256,address)`, selector `0x573ade81`
(independently keccak-derived, not hand-copied — matches the real compiled
calldata exactly). No other adapter code changed.

## 4. Tests

`proof/test_adapter.py` — added `TestDeleverageBundle` (9 new tests: tx
count/order, approve target, repay selector, repay target/args, round-trip
re-encode for both legs, valid KeeperHub request shape for both legs,
intent_type routing). Full suite: **34/34 passed, 0 regressions.**

## 5. KeeperHub payloads sent (both `simulate: true` — no signing, no broadcast, no audit row, no spending-cap consumption per KeeperHub docs)

**Approve leg** — `POST /api/execute/contract-call`:
```json
{
  "contractAddress": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
  "chainId": 8453,
  "functionName": "approve",
  "functionArgs": "[\"0xA238Dd80C259a72e81d7e4664a9801593F98d1c5\", \"11000000\"]",
  "value": "0",
  "simulate": true
}
```
Result: `success: true`, `wouldRevert: false`, `gasEstimate: 56240`. Would succeed.

**Repay leg** — same endpoint, `onBehalfOf` set to the real organization
wallet (not a placeholder):
```json
{
  "contractAddress": "0xA238Dd80C259a72e81d7e4664a9801593F98d1c5",
  "chainId": 8453,
  "functionName": "repay",
  "functionArgs": "[\"0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913\", \"10000000\", \"2\", \"<org_wallet>\"]",
  "value": "0",
  "simulate": true
}
```
Result: `success: false`, `status: "simulated"`, `failureKind: "revert"`,
`wouldRevert: true`, `undecodedRevertData: "0xf0788fb2"` (an Aave V3 custom
error selector, consistent with "no outstanding variable debt for this
reserve/rate mode").

No `executionId` was returned for either call — expected, since
`simulate: true` never creates an execution record per KeeperHub's own docs.

## 6. Prerequisite check (Direct Execution, read-only `getUserAccountData` call against the real Aave V3 Pool on Base)

Organization wallet: `0x02168b0be574a884bAe550F3D6b9F080670f8f7F`
(discovered from the `from` field of the simulate response — not stored anywhere before this).

```json
{
  "totalCollateralBase": "0",
  "totalDebtBase": "0",
  "availableBorrowsBase": "0",
  "currentLiquidationThreshold": "0",
  "ltv": "0",
  "healthFactor": "115792089237316195423570985008687907853269984665640564039457584007913129639935"
}
```

`healthFactor` is Aave's `type(uint256).max` sentinel for "no debt" — this
wallet has **zero collateral and zero debt** on Aave V3 Base. The repay
simulation's revert is a direct, correct consequence of this, not an
adapter/encoding bug: there is nothing to repay.

## 7. What was verified (real, live)

- API key is valid and authorized for `contract-call` (both simulate and read).
- Organization wallet address, confirmed live.
- Real Almanak `DeleverageIntent` → real `ActionBundle`, both transactions,
  round-tripped exactly through the adapter.
- Approve leg would succeed on real Base mainnet (simulated).
- Repay leg correctly reverts on real Base mainnet given the real, current
  on-chain state of the org wallet (simulated, not guessed).
- Aave V3 Pool address (`0xA238Dd80...`) and Base USDC address independently
  agree between Almanak's own registry and KeeperHub's registry.

## 8. What was simulated (never broadcast)

Both legs of the deleverage bundle, via `simulate: true`. No signature, no
broadcast, no gas spent, no funds moved.

## 9. Was a real Aave transaction executed?

**No.** Execution was correctly halted before broadcast per the explicit
prerequisite gate: the organization has no Aave V3 debt position on Base to
repay. Broadcasting the repay would revert on-chain; broadcasting only the
approve leg would move no funds and prove nothing about the deleverage
product flow, so neither was sent.

## 10. Did the Aave debt/position change?

No — no debt existed before this investigation, and none exists after it.
Nothing was changed on-chain.

## 11. Exactly what is missing before Phase 1 can be marked DONE

The KeeperHub organization wallet (`0x02168b0be574a884bAe550F3D6b9F080670f8f7F`)
needs a **real Aave V3 USDC borrow position on Base** before the actual repay
broadcast can be attempted:

1. Supply some collateral (e.g. a small amount of WETH or USDC) to the Aave V3
   Pool on Base from that wallet.
2. Borrow a small amount of USDC against it (enough that a 10 USDC partial
   repay is meaningful and leaves the position solvent).
3. Re-run the read in §6 to confirm `totalDebtBase > 0` and a finite
   `healthFactor`.
4. Only then re-simulate the repay leg (§5) — it should return
   `wouldRevert: false` — and only then is broadcasting in scope.

This was **not** done in this session: per instruction, no position was
opened, faked, or substituted with another protocol. This is a decision for
the user — it requires committing real (if small) capital and taking on a
real borrow position, which is outside what this phase was authorized to do
autonomously.

## 12. Limitations / notes

- The approve leg's amount (11 USDC) includes a 10% buffer over the 10 USDC
  repay amount — this is the SDK's own behavior, not an adapter choice.
- `repay_full=True` would use the wallet's live on-chain balance instead of a
  fixed amount (via RPC) — not exercised here since `repay_full=False` was
  specified.
- The Multicall3 batching hazard identified in the prior investigation
  (msg.sender mismatch) means these two legs must always be sent as two
  separate Direct Execution / Write Contract calls, never batched — this
  report's payloads follow that.
- No API key value appears anywhere in this repo or this report.
