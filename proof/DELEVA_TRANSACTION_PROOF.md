# DELEVA REAL TRANSACTION PROOF

Status: **EXECUTED — real Base mainnet transaction, real Aave V3 debt reduction.**

## Product flow

```
DELEVA
  -> Almanak DeleverageIntent(protocol=aave_v3, token=USDC, amount=10, repay_full=False, chain=base)
  -> IntentCompiler.compile() -> real ActionBundle (intent_type=REPAY, 2 transactions)
  -> DELEVA adapter (keeperhub_adapter.py: decode_calldata + almanak_tx_to_keeperhub_request)
  -> KeeperHub REST Direct Execution (POST /api/execute/contract-call)
  -> Aave V3 Pool.repay() on Base mainnet
```

No manual/hand-built calldata was used at any step. Both transactions below are exactly what the real, installed Almanak SDK compiled; the adapter only decoded and reshaped them into KeeperHub's request format.

## Before

- Debt: **$11.9985** (totalDebtBase 1,199,848,584 / 1e8)
- Health Factor: **2.0795** (2,079,485,770,506,189,137 / 1e18)
- Collateral: **$30.061** (totalCollateralBase 3,006,106,093 / 1e8), 0.0126 WETH
- USDC wallet balance: **12.000000 USDC**

(Position itself was opened in Stage 2, immediately prior: supply tx `0x47142ea9...`, borrow tx `0x7f78830d...`.)

## Almanak

**Intent parameters** (real, compiled by the installed SDK, not mocked):
```python
DeleverageIntent(
    protocol="aave_v3",
    token="USDC",
    amount=Decimal("10"),
    repay_full=False,
    chain="base",
    trigger_reason="health_factor_below_threshold",
    observed_hf=Decimal("2.0795"),   # actual live HF at compile time
    target_hf=Decimal("1.50"),
)
```
`IntentType.DELEVERAGE` routed through the same compiler path as `REPAY` (confirmed: `bundle.intent_type == "REPAY"`), consistent with every prior verification in this project.

**ActionBundle transactions** (both real, both round-tripped byte-for-byte through the adapter):

| # | tx_type | to | selector | decoded call |
|---|---|---|---|---|
| 0 | `approve` | `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913` (Base USDC) | `0x095ea7b3` | `approve(spender=0xA238Dd80C259a72e81d7e4664a9801593F98d1c5, amount=11000000)` |
| 1 | `lending_repay` | `0xA238Dd80C259a72e81d7e4664a9801593F98d1c5` (Aave V3 Pool) | `0x573ade81` | `repay(asset=0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913, amount=10000000, interestRateMode=2, onBehalfOf=0x02168b0be574a884bAe550F3D6b9F080670f8f7F)` |

Verified programmatically: `asset` == real Base USDC, `amount` == 10,000,000 (10 USDC), `interestRateMode` == 2 (variable), `onBehalfOf` == the real KeeperHub organization wallet, target == the real Base Aave V3 Pool.

## KeeperHub

**Simulation (required before broadcast, per protocol):**
- Approve leg: `simulate: true` → `success: true`, `wouldRevert: false`, gasEstimate 56,240 (valid immediately, funding-independent).
- Repay leg, simulated *before* the approve was broadcast: correctly reverted with `"ERC20: transfer amount exceeds allowance"` — expected sequential-dependency behavior (identical pattern already characterized during position-opening), not a defect. All of the repay leg's fields (contract, calldata, amount, onBehalfOf) were independently verified correct via the Python assertions above regardless of this expected revert.
- Repay leg, re-simulated *after* the approve was actually broadcast and confirmed: `success: true`, `wouldRevert: false`, gasEstimate 160,745. Broadcast only proceeded after this clean result.

**Execution IDs:**
- Approve: `q5t9cuj4qhsjcaex69eeh`
- Repay (proof transaction): `za25idtoxl42mtyfjmbks`

**Execution status:** both `completed`. Idempotency-Key used for each broadcast was freshly generated (UUID4), never reused.

## Blockchain

- **Transaction hash (proof transaction):** `0xd36217b09ba81cea624e88e756514f2ebc0dc689a20dad4286d6f852f205ec57`
- **Block:** `51,395,399`
- **Receipt status:** `success` (verified: true)
- **Gas used:** 184,531 units, effective gas price 6,318,549 wei — **sponsored by KeeperHub** (`"sponsored": true` in the execution status; the org wallet's own ETH was not spent for this transaction)
- **Aave Pool:** `0xA238Dd80C259a72e81d7e4664a9801593F98d1c5` (Base mainnet)
- **Repayment amount:** 10.000000 USDC (10,000,000 base units)
- **BaseScan URL:** https://basescan.org/tx/0xd36217b09ba81cea624e88e756514f2ebc0dc689a20dad4286d6f852f205ec57

(Approve transaction, leg 1 of the same bundle: `0x12db82010410feb4339c41523ede3801968b5d51c50d4cf7047d880203ea011f`)

## After

- Debt: **$1.9998** (totalDebtBase 199,975,914 / 1e8)
- Health Factor: **12.454** (12,453,999,782,743,835,840 / 1e18)
- Collateral: **$30.006** (totalCollateralBase 3,000,602,397 / 1e8) — unchanged aside from trivial WETH oracle-price drift; no collateral was touched by this transaction
- USDC wallet balance: **2.000000 USDC**

## Proof

This transaction was not a substitute, a mock, or a hand-built call to Aave. It is the direct, unmodified output of DELEVA's real product pipeline: a real `DeleverageIntent` was constructed with the actual current on-chain health factor, compiled by the real, installed Almanak `IntentCompiler` into a real two-transaction `ActionBundle`, decoded by the existing `keeperhub_adapter.py` (the same adapter used and tested throughout this project, extended only with the standard, independently keccak-verified Aave `repay` selector), and submitted to KeeperHub's live REST Direct Execution API, which signed and broadcast it from the real KeeperHub organization wallet.

The on-chain result is unambiguous and independently re-read after the fact, not inferred: Aave V3 debt for wallet `0x02168b0be574a884bAe550F3D6b9F080670f8f7F` dropped from $11.9985 to $1.9998 (a ~$10.00 reduction matching the intended 10 USDC repayment exactly), health factor rose from 2.0795 to 12.454, USDC wallet balance dropped by exactly 10.000000, and collateral was untouched. Transaction `0xd36217b0...` is confirmed in block 51,395,399 on Base mainnet with `receiptStatus: success`.

## Remaining state (per instruction, untouched)

Remaining debt (~$2, plus negligible accrued interest) has **not** been repaid. WETH collateral has **not** been withdrawn. No transaction beyond the two DELEVA legs above was sent. The unwind is a separately authorized next stage.
