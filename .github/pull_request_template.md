## What

<!-- One paragraph: what this PR adds or changes. -->

## Why

<!-- Link to docs/PLAN.md step, issue, or decision. -->

## How tested

- [ ] `make lint` / `make typecheck`
- [ ] `make test` (coverage gate)
- [ ] `make e2e` (if UI or API changed)
- [ ] Simulator scenario(s) exercised: <!-- e.g. wot_pull_3rd_gear -->

## Screenshots (UI changes only)

<!-- Attach or reference regenerated docs/images/*.png -->

## Follow-ups

<!-- Anything intentionally deferred; add to docs/PROGRESS.md "Known issues". -->

## Checklist

- [ ] Conventional Commits, atomic
- [ ] Docs updated (`docs/PROGRESS.md` ticked, `docs/DECISIONS.md` if a decision was made)
- [ ] No writes to the ECU: only read-only OBD services are used (see `obd/allowlist.py`)
- [ ] Hardware-touching code is labelled *hardware-unverified* until validated via `docs/hardware/validation-checklist.md`
