---
workflow: general-video
flow: automation
storyboard: no
message: "Almanak decides. KeeperHub executes."
destination: youtube
aspect: 1920x1080
language: en
length: 70s
audience: KeeperHub Agent Economy Hackathon judges
narration: yes
voice: Kokoro am_michael
---

## Intent

A 60–75 second cinematic hackathon demo for DELEVA. Recreate DELEVA's product UI
as HyperFrames motion-graphics scenes — not a screen recording. Serious DeFi
infrastructure tone. The video must communicate the real pipeline: Aave V3
position → DELEVA monitors risk → threshold breach → Almanak DeleverageIntent →
ActionBundle → DELEVA adapter → KeeperHub simulation → KeeperHub execution →
Aave repayment → on-chain proof.

Two real proofs must stay distinct:
- Autonomous proof: unattended runner, HF 1.2800 below 1.50, repay 2.93256692 USDC, tx 0xd16bd715…
- Manual execution-path proof: 0xd36217b09ba81cea624e88e756514f2ebc0dc689a20dad4286d6f852f205ec57 — HF was 2.0795, above trigger. Never present this hash as threshold-triggered.

## Assets

- DELEVA design tokens from the product CSS (copied into frame.md, not from web/ files)
- Bundled HyperFrames SFX in assets/sfx/ (click-soft, ping, whoosh-short, notification)
- Local Kokoro voiceover in assets/voice/

## Customizations

- Voiceover on every story beat
- Subtle UI SFX on risk detect, simulation pass, execution confirm
- No BGM: HeyGen catalog unavailable without sign-in; MusicGen not installed. Silence under VO keeps the infrastructure tone.

## Notes

- Do not modify web/ or proof/. This directory is the only deliverable.
- No gradients, glassmorphism, decorative 3D, glowing blobs, or generic AI graphics.
- System-font philosophy: IBM Plex Mono (bundled, technical) for brand and data — DELEVA's own UI is mono-forward.
- HeyGen auth: not signed in. Autonomous fallback: local Kokoro `am_michael` (measured, male, infrastructure).
- Aegis was studied only for storytelling philosophy (value-first, honest real vs synthetic, simulate-then-execute). No Aegis branding, UI, or visual design was copied.
