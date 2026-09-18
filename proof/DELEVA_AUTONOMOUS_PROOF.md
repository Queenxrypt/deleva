# DELEVA AUTONOMOUS EXECUTION PROOF

Status: **EXECUTED — real, unattended, threshold-triggered Base mainnet transaction.**

**This is the primary hackathon execution proof.** It is a separate, later, and materially different event from the manual proof documented in [`DELEVA_TRANSACTION_PROOF.md`](DELEVA_TRANSACTION_PROOF.md). Neither document replaces or relabels the other.

## How this differs from the earlier manual proof

| | Manual proof (`DELEVA_TRANSACTION_PROOF.md`) | Autonomous proof (this document) |
|---|---|---|
| Date | 2026-09-16 | 2026-09-17 |
| Trigger | Manually invoked while HF (2.0795) was **above** the 1.50 threshold, to demonstrate the execution path | **`MonitoringRunner` running unattended, in `LIVE` mode, autonomously detected a real breach on its own scheduled read** |
| Repay amount | Fixed `10 USDC` (the `min_deleverage_amount` floor bound, not the calculated target-HF value) | **`2.93256692 USDC` (approximately `2.9326 USDC`) — the actual `_deleverage_amount()`-calculated value** (`min_deleverage_amount=2` did not bind; this is the first time the dynamic sizing formula has produced its own value in a real execution, not the floor) |
| Repay tx | `0xd36217b0...` | `0xd16bd715...` |

The manual transaction proves the Almanak → DELEVA → KeeperHub → Aave pipeline executes correctly end-to-end. **This autonomous transaction proves the pipeline is genuinely triggered and driven by DELEVA's own unattended risk monitoring**, exactly as the product is positioned.

## Timeline

```
Aave borrow (manual, external re-leverage, ~$18 additional USDC debt)
        v
POSITION_EVALUATED  15:12:26.988796 UTC  -- HF = 1.280004472315208427
        v
RISK_THRESHOLD_BREACHED  15:12:27.017833 UTC  -- HF < 1.50, autonomous, unattended
        v
ALMANAK_INTENT_CREATED  15:12:30.955796 UTC  -- real DeleverageIntent, real IntentCompiler
        v
ACTION_BUNDLE_COMPILED  15:12:30.955796 UTC  -- real ActionBundle, 2 transactions, intent_type=REPAY
        v
KEEPERHUB_SIMULATION (approve)  15:12:32.471647 UTC  -- success=true, wouldRevert=false
        v
KEEPERHUB_EXECUTION (approve)  15:12:38.448821 UTC  -- tx confirmed
        v
KEEPERHUB_SIMULATION (repay)  15:12:39.297396 UTC  -- success=true, wouldRevert=false
        (simulated only AFTER the approve had actually broadcast and confirmed --
         the same approve-before-repay dependency observed in the manual proof,
         handled correctly here without any manual intervention)
        v
KEEPERHUB_EXECUTION (repay)  15:12:49.167569 UTC  -- tx confirmed
        v
TRANSACTION_CONFIRMED  15:12:49.167569 UTC
        v
POSITION_VERIFIED  15:12:50.274392 UTC  -- debt decreased, HF restored to ~1.50
        v
runner stopped (explicit operator action, after observing the completed cycle)
```

## 1. Position immediately before the autonomous trigger

Source: `POSITION_EVALUATED` activity event immediately preceding the breach.

- **Timestamp:** `2026-09-17T15:12:26.988796+00:00`
- **Health factor:** `1.280004472315208427`
- **Debt:** `$19.99771837` (taken from the `POSITION_VERIFIED` event's recorded "before" value — the position's debt did not change between this read and the verification read)
- **Collateral:** not persisted by the activity log for this exact instant (only `health_factor` is recorded per `POSITION_EVALUATED` event). Algebraically consistent with `HF = collateral × liquidation_threshold / debt` at `liquidation_threshold = 0.83`: **≈ $30.84**. The closest *directly observed* read is `$30.83996473`, from a position read at `2026-09-17T15:14:48` (about 2 minutes later, before any further change occurred) — reported here as the closest real data point, not fabricated for this exact timestamp.

## 2. Risk event

- **`RISK_THRESHOLD_BREACHED` timestamp:** `2026-09-17T15:12:27.017833+00:00`
- **Observed HF:** `1.280004472315208427`
- **Configured trigger HF:** `1.50` (confirmed live via `GET /api/strategy` during this run)

## 3. Almanak

- **`ALMANAK_INTENT_CREATED` timestamp:** `2026-09-17T15:12:30.955796+00:00`
- **Intent ID:** `d6e6f501-9163-4739-87ff-79fe7e554a1c`
- **Intent type (compiled bundle):** `REPAY` (Almanak routes `DeleverageIntent` through the `REPAY` compiler path, consistent with the manual proof)
- **Protocol:** `aave_v3`
- **Token:** `USDC`
- **Actual repay amount:** `2.93256692 USDC` (approximately `2.9326 USDC`) (derived precisely as `19.99771837 − 17.06515145`, per the `POSITION_VERIFIED` event — this is the real, calculated `_deleverage_amount()` output; the `min_deleverage_amount=2` floor did not bind)
- **Target HF:** `1.50`
- **ActionBundle transaction count:** `2` (`ACTION_BUNDLE_COMPILED`: "Real ActionBundle compiled: 2 transaction(s), intent_type=REPAY")

## 4. KeeperHub

Both execution IDs below were independently cross-checked against KeeperHub's own `GET /api/execute/{id}/status` endpoint (a pure, read-only status query — no resend, no idempotency-key rotation) — not taken solely from DELEVA's local activity log.

| Leg | Execution ID | Transaction hash | Status |
|---|---|---|---|
| Approve | `4ftop75p32howsni3o1io` | `0x5e2e8debba3eebf221ea05db197458e8b31caa8ef27bacba2e8d4bfce9fae19e` | `completed` (confirmed via local log **and** independently via KeeperHub's live status API) |
| Repay | `i0qqkeb5ccbvv7nsm1x7g` | `0xd16bd7157d4415d7899345c8787858e0affdc01800739225635f0421999cd831` | `completed` (confirmed via local log **and** independently via KeeperHub's live status API) |

**On execution status precision**: for both legs, KeeperHub reported the execution as `completed`/`succeeded: true` via its own status endpoint (`GET /api/execute/{id}/status`), independently re-queried and matching the local log exactly. This is KeeperHub's own reported execution status, not an independently-parsed on-chain `receiptStatus` field — the current `KeeperHubClient._parse_execution()` does not extract a separate on-chain receipt field from KeeperHub's response. In short: **KeeperHub reported the execution as completed/succeeded**; this document does not separately claim an independently-verified on-chain receipt status beyond that.

**Simulation results:**
- Approve leg (`15:12:32.471647 UTC`): `success=true`, `wouldRevert=false`
- Repay leg (`15:12:39.297396 UTC`, simulated *after* the approve had already broadcast and confirmed): `success=true`, `wouldRevert=false`

**Confirmation timestamps:**
- Approve executed/confirmed: `15:12:38.448821 UTC`
- Repay executed/confirmed: `15:12:49.167569 UTC`
- `TRANSACTION_CONFIRMED` recorded: `15:12:49.167569 UTC`

## 5. Final verification

Source: `POSITION_VERIFIED` activity event.

- **Timestamp:** `2026-09-17T15:12:50.274392+00:00`
- **Debt before:** `$19.99771837`
- **Debt after:** `$17.06515145`
- **HF before:** `1.280004472315208427`
- **HF after:** `1.499967304632388715`
- **Actual repayment amount:** `$2.93256692` (approximately `$2.9326`) (`19.99771837 − 17.06515145`)
- **Wallet USDC after:** `$17.067061` (closest direct read, `2026-09-17T15:14:48+00:00` — no other action occurred between the repay and this read)
- **Verification result:** `success` — debt decreased, confirmed by `verify_deleverage()` (`deleva/verification.py`), not fabricated

## 6. Repay transaction confirmation

The autonomous repay transaction is confirmed to be:

```
0xd16bd7157d4415d7899345c8787858e0affdc01800739225635f0421999cd831
```

https://basescan.org/tx/0xd16bd7157d4415d7899345c8787858e0affdc01800739225635f0421999cd831

Approve transaction (leg 1 of the same bundle):

```
0x5e2e8debba3eebf221ea05db197458e8b31caa8ef27bacba2e8d4bfce9fae19e
```

https://basescan.org/tx/0x5e2e8debba3eebf221ea05db197458e8b31caa8ef27bacba2e8d4bfce9fae19e

## Honest notes and limitations

- The post-repay health factor (`1.499967...`) lands fractionally **below** 1.50 — within the RiskEvaluator's inclusive-healthy boundary being crossed by a razor-thin margin (~0.000033). Subsequent `POSITION_EVALUATED`/`RISK_THRESHOLD_BREACHED` cycles (through `15:17:41.580392 UTC`, the last recorded before the runner was stopped) continued to classify the position as breached. No second autonomous execution occurred before the runner was stopped — the 300-second cooldown (`retry_backoff_seconds`) had not yet elapsed (it started at the first action's completion, ~`15:12:49 UTC`, and would have permitted a second attempt around `~15:17:49 UTC`).
- Collateral at the exact instant of the pre-trigger read (§1) is derived, not directly recorded — see the note there.
- This document was generated from the live activity log and a direct, read-only cross-check against KeeperHub's status API. No transaction was sent, and no on-chain state was modified, in the course of producing this document.
