# Progress log

Resumable state of the build. If you are picking this up cold: read `PLAN.md`, this file, then
`DECISIONS.md`, and continue from **Current step**.

## PR checklist

| #  | Branch                       | Status      | PR |
| -- | ---------------------------- | ----------- | -- |
| 0  | `chore/bootstrap`            | merged      | [#1](https://github.com/tmestery/pi-obd-copilot/pull/1) |
| 1  | `feat/core-domain`           | in review   | #2 |
| 2  | `feat/obd-transport-sim`     | todo        |    |
| 3  | `feat/obd-elm-transport`     | todo        |    |
| 4  | `feat/acquisition-storage`   | todo        |    |
| 5  | `feat/perf-events`           | todo        |    |
| 6  | `feat/api-ws`                | todo        |    |
| 7  | `feat/web-dashboard`         | todo        |    |
| 8  | `feat/web-trips-perf-diag`   | todo        |    |
| 9  | `feat/pi-deploy-power`       | todo        |    |
| 10 | `docs/phase1-images-release` | todo        |    |
| 11 | `feat/gps-radar-providers`   | todo        |    |
| 12 | `feat/radar-ui-hotspots`     | todo        |    |
| 13 | `feat/camera-pipeline`       | todo        |    |
| 14 | `feat/perception-clips-ui`   | todo        |    |
| 15 | `feat/copilot-core`          | todo        |    |
| 16 | `feat/copilot-qa-voice-kb`   | todo        |    |
| 17 | `chore/hardening-final`      | todo        |    |

## Current step

PR 1: core domain (config, units, logging, errors, PID table, derived metrics) written and tested; PR open.

## Releases

| Tag      | Status |
| -------- | ------ |
| `v0.1.0` | todo   |
| `v0.2.0` | todo   |
| `v0.3.0` | todo   |
| `v1.0.0` | todo   |

## Known issues

- PR #1 was merged by the owner before the `force-include` build fix landed, so `main` CI was red for one commit; PR #2 carries the fix (`fix(build)` commit).

## Next action

Merge PR 2, then start PR 2 of the plan (`feat/obd-transport-sim`): transport protocol, allowlist,
physics model, scenarios, SimTransport, scheduler.

## Definition-of-done verification (filled in at the end)

| # | Item                                                        | Result |
| - | ----------------------------------------------------------- | ------ |
| 1 | clean main, 0 open PRs, >= 16 merged, tags + v1.0.0 release | -      |
| 2 | `make test` / `lint` / `typecheck` pass, CI green            | -      |
| 3 | `make demo` on a clean clone shows every feature             | -      |
| 4 | `make e2e` passes                                            | -      |
| 5 | `make images` regenerates everything                         | -      |
| 6 | `install_pi.sh --dry-run` + shellcheck + systemd verify      | -      |
| 7 | allowlist tests prove no write path                          | -      |
| 8 | docs complete                                                | -      |
| 9 | extras fail soft                                             | -      |
| 10| final self-review / fresh-clone quickstart                   | -      |
