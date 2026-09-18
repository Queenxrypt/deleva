---
name: DELEVA infrastructure
colors:
  bg: "#08080a"
  surface: "#111114"
  surfaceRaised: "#17171b"
  surfaceSunken: "#0c0c0e"
  border: "#26262c"
  borderStrong: "#37373f"
  text: "#e9e9ec"
  textMuted: "#9a9aa4"
  textFaint: "#9a9aa4"
  accent: "#5b9dff"
  accentDim: "#2f4a73"
  healthy: "#34c77b"
  healthyDim: "#16371f"
  warning: "#e8a33d"
  warningDim: "#3a2c0f"
  danger: "#ef5350"
  dangerDim: "#3a1616"
typography:
  display: "IBM Plex Mono"
  body: "IBM Plex Mono"
  data: "IBM Plex Mono"
  weights:
    display: 600
    body: 400
    data: 600
spacing:
  radius: 10px
  radiusSm: 6px
  pad: 28px
---

# DELEVA frame system

Brand truth copied from DELEVA's product CSS. Application is scaled for 1920×1080 video (larger type, 2px borders so 1px web hairlines survive encode).

## The Frame

A dark technical operations surface. One product card or one metric cluster per beat. Not a marketing poster. Not a dashboard dump.

Persistent field: `#08080a` with DELEVA's 56px technical grid (`#26262c` at ~0.35 opacity). No radial glows. No glass. No 3D.

## Composition Rules

- Brand wordmark is the word **DELEVA** in IBM Plex Mono, never a mark.
- Eyebrows: 11–14px feel at video scale → 18px, uppercase, 0.14em tracking, `#9a9aa4` (WCAG AA on `#08080a` / `#111114`).
- Metric values: tabular mono, 72–96px for the hero number, `#e9e9ec` or status color.
- Cards: `#111114` fill, `2px solid #26262c`, 10px radius, no shadow.
- Badges: pill, 2px border, 6px status dot. Healthy / warning / danger use the exact token pair.
- One accent hit per scene (`#5b9dff` or a status color). Do not rainbow.
- Motion: 0.18–0.55s, `power3.out` / `power4.out`. Restrained. No bounce. No glow bloom.

## Do

- Show real repository numbers only.
- Label autonomous proof vs execution-path proof in plain language.
- Keep Almanak as decision, KeeperHub as execution.

## Don't

- Gradients, glassmorphism, decorative 3D, glowing blobs.
- Generic blockchain imagery, hex storms, coin spins.
- Present `0xd36217b0…` as the threshold-triggered transaction.
- Invent hashes or metrics.
