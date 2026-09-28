# gti-copilot build plan

This is the authoritative plan for building `gti-copilot`, a Raspberry Pi 5 in-car computer for a
2016 VW Golf GTI (MK7). The full specification lives in the original build brief; this file is the
condensed, resumable version. Read it together with `PROGRESS.md` (where we are) and
`DECISIONS.md` (why we did what we did).

## Product in one paragraph

A read-only OBD-II performance dashboard and trip logger first, then radar-detector + GPS fusion,
then a dashcam with on-device perception, then a fully offline small-language-model co-pilot that
only narrates facts computed by deterministic code. Everything runs on a laptop against a
physics-based simulator; real-hardware paths exist behind the same interfaces and stay labelled
*hardware-unverified* until the owner runs `docs/hardware/validation-checklist.md`.

## Non-negotiables

- **Read-only on the car**: only OBD services 01, 02, 03, 07, 09, 0A may ever be sent
  (`obd/allowlist.py`, tested). No Mode 04, no UDS writes, no adapter reconfiguration.
- **Driver safety**: glanceable UI, no flashing, interaction lockout above 3 mph, night theme.
- **Hardware-abstracted**: every device has a Protocol + simulator/mock. `make demo` needs no
  hardware.
- **Offline-first, private**: no cloud, no telemetry, data stays on the device.
- **Reproducible**: `make test`, `make demo`, `make images`.

## Tech stack (decided)

Python 3.11+ / asyncio / FastAPI / pydantic v2 / SQLite WAL / pyserial; TypeScript + Vite
(vanilla TS modules, canvas gauges) with Vitest + Playwright; ffmpeg + OpenCV + onnxruntime;
llama.cpp / Ollama / deterministic template backend; GitHub Actions; Raspberry Pi OS Bookworm
with systemd + Chromium kiosk.

## Repository layout

See section 4 of the brief; mirrored in the tree. `src/gti_copilot/` holds the Python package,
`src/gti_copilot/web/` the Vite project (built `dist/` is produced in CI / `make demo`, never
committed), `docs/images/` holds generated, committed images.

## PR plan (branch -> PR -> CI green -> merge commit -> delete branch)

Each PR: 3+ atomic Conventional Commits, tests, docs, `docs/PROGRESS.md` ticked, PR body with
What / Why / How tested / Screenshots / Follow-ups.

| #  | Branch                          | Scope                                                                                                                                                                                                          |
| -- | ------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 0  | `chore/bootstrap`               | Scaffolding, license, community files, pyproject, Makefile, pre-commit, CI, templates, PLAN/PROGRESS/DECISIONS, README skeleton.                                                                             |
| 1  | `feat/core-domain`              | Config models + YAML loader + `GTI_*` env overrides, units, logging, errors, PID table/decoders, derived metrics (boost, fuel, gear, accel), unit + property tests.                                          |
| 2  | `feat/obd-transport-sim`        | `ObdTransport` protocol, read-only allowlist + tests, vehicle physics model, scenarios, `SimTransport`, tiered adaptive scheduler.                                                                            |
| 3  | `feat/obd-elm-transport`        | `ElmTransport` (pyserial, STN/ELM327, USB + RFCOMM), supported-PID discovery, DTC reading, reconnect/backoff, fault-injection tests, hardware-unverified label.                                               |
| 4  | `feat/acquisition-storage`      | Event bus, acquisition service, SQLite schema + migrations, batched writer, trip segmentation (property tests), graceful flush, retention, CSV/JSON export.                                                  |
| 5  | `feat/perf-events`              | 0-60 / 0-100 / 60-130 / quarter-mile timers, hard-brake / hard-accel / over-rev detectors, events persistence, scenario tests.                                                                              |
| 6  | `feat/api-ws`                   | FastAPI app, REST endpoints, WebSocket stream, pydantic schemas, OpenAPI, contract tests, health, CLI (`run`, `doctor`, `export`, `config`).                                                                 |
| 7  | `feat/web-dashboard`            | Vite/TS project, live gauges (RPM arc, speed, boost w/ peak-hold), themes, warnings, shift light, status bar, reconnect states, lockout, Vitest.                                                              |
| 8  | `feat/web-trips-perf-diag`      | Performance, Trips (charts), Events, Diagnostics (read-only), Settings, About/Health screens; Playwright e2e for the Phase 1 demo drive.                                                                    |
| 9  | `feat/pi-deploy-power`          | Power monitor + shutdown flow, systemd units, udev rules, kiosk script, `install_pi.sh` (idempotent, `--dry-run`, shellcheck CI), hardening docs, hardware docs (BOM, wiring, mounting, power).             |
| 10 | `docs/phase1-images-release`    | Image pipeline v1 (banner, architecture, data-flow, wiring, cabin layout, screenshots, boost curve, demo GIF), full Phase 1 README, `docs/images/README.md`, CHANGELOG, tag `v0.1.0` + Release.            |
| 11 | `feat/gps-radar-providers`      | GPS providers (gpsd/mock/NMEA replay), radar provider interface, mock, optional `r8link` wrapper (fail-soft), parser harness, alert lifecycle + persistence, "add your Uniden" guide.                        |
| 12 | `feat/radar-ui-hotspots`        | Radar overlay, alert history, hotspot clustering + offline map canvas, analytics/export (CSV/GeoJSON), e2e, screenshots, tag `v0.2.0`.                                                                       |
| 13 | `feat/camera-pipeline`          | Video sources (file/V4L2/Pi), ring buffer, event-triggered clips with sidecars/thumbnails, locking, disk caps, clip API, ffmpeg-generated test video.                                                       |
| 14 | `feat/perception-clips-ui`      | `Detector` interface, null + ONNX detector (mocked runtime), overlays, clips gallery/playback synced to telemetry, e2e, screenshots, tag `v0.3.0`.                                                           |
| 15 | `feat/copilot-core`             | LLM backend abstraction (template/llama.cpp/Ollama), facts computation, trip summaries, grounding validator + adversarial tests, driving policy + tests, summaries persistence + UI.                         |
| 16 | `feat/copilot-qa-voice-kb`      | Whitelisted query tools + tool-call loop, knowledge base + retrieval, alert narration, STT/TTS interfaces + null/mocks, push-to-talk UI, evals in CI.                                                       |
| 17 | `chore/hardening-final`         | Soak test (30 simulated minutes), perf tuning, security review, docs site config, validation checklist finalised, complete README with all images, final images, CHANGELOG, tag `v1.0.0` + Release.        |

More PRs are fine if one grows too large; fewer than 16 is not.

## Quality bar

- `mypy --strict` clean for `obd`, `storage`, `perf`, `copilot.grounding`, `copilot.policy`,
  `api.schemas`, `units`, `config`.
- >= 85 % line coverage on backend core (enforced by `scripts/coverage_gate.py` in CI).
- Contract tests for REST/WS schemas; hypothesis property tests for PID decoding, trip
  segmentation, grounding; Playwright e2e for the demo drive.
- No secrets, no model weights, no copyrighted media. License audit in `DECISIONS.md`.

## Images (generated by `make images`, committed under `docs/images/`)

banner, architecture, data-flow, wiring-diagram, cabin-layout, dashboard-live, dashboard-day,
performance-0-60, trips, radar-alert, radar-hotspots, clips, copilot-summary, diagnostics,
boost-curve, roadmap, demo.gif. Screenshots come from the real UI via Playwright against the
simulator; diagrams are hand-authored SVG rasterised with Chromium.

## Definition of done

See section 15 of the brief: clean `main`, zero open PRs, >= 16 merged PRs, tags
`v0.1.0`/`v0.2.0`/`v0.3.0`/`v1.0.0` + GitHub Release, `make test`/`lint`/`typecheck`/`e2e`/
`images` pass, `make demo` on a clean clone works, `install_pi.sh --dry-run` shellchecked,
allowlist tests prove no write path, docs complete, extras fail soft, final self-review.
