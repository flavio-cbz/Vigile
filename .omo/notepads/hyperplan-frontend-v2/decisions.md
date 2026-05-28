# VigileEye — Architectural Decisions

## Decision: Inline SVG `<style>` vs CSS module
**Chosen**: Inline `<style>` tag inside the SVG
**Rationale**: The SVG is self-contained — can be dropped into any context without importing separate CSS. The browser deduplicates duplicate keyframes when multiple VigileEye instances exist on the same page.

## Decision: CSS animations vs SVG `<animate>`
**Chosen**: CSS animations via `@keyframes`
**Rationale**: GPU-composited (no JS main thread involvement), works on Raspberry Pi 4 Chromium, respects `prefers-reduced-motion` naturally.

## Decision: Pupil position via config + CSS transform vs SVG attribute
**Chosen**: Base position via JSX `cx` + CSS `translateX` for animation
**Rationale**: JSX handles the static offset (e.g., attentive pupilX=4 moves cx to 20). CSS handles the scanning animation via `transform: translateX()`. This keeps the two concerns separate.

## Decision: `context` prop inclusion
**Chosen**: Keep as optional prop in the API, use in aria-label
**Rationale**: Task spec explicitly requires `context` in the composable API. Using it in the aria-label gives screen readers meaningful context about whether the eye represents fleet or server status.

## Decision: No `React.memo`
**Chosen**: Skip memoization
**Rationale**: Component is small (pure SVG + inline style), re-render cost is negligible. memo adds complexity for no measurable gain.
