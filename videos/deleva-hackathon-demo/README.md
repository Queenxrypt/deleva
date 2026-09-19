# DELEVA cinematic demo

Separate HyperFrames project. Does not modify `web/` or `proof/`.

**Almanak decides. KeeperHub executes.**

- Duration: 69.5s · 1920×1080 · 30fps
- Render: [`out.mp4`](out.mp4)
- Voice: local Kokoro `am_michael` (HeyGen was not signed in)

```bash
cd videos/deleva-hackathon-demo
npm run check
npm run dev
npx hyperframes render --quality looks --output out.mp4
```

Two real proofs stay distinct in the picture:

1. Autonomous cycle — HF 1.2800 below 1.50, repay 2.93256692 USDC, tx `0xd16bd715…`
2. Manual execution-path proof — `0xd36217b0…`, HF was 2.0795, labeled verified execution path (not threshold-triggered)
