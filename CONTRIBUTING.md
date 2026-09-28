# Contributing to gti-copilot

Thanks for your interest. This project is built and tested primarily against a physics-based
simulator, so you can contribute meaningfully without a car, a Raspberry Pi or any hardware.

## Ground rules

1. **Read-only on the car.** Nothing in this repository may send an OBD-II service outside the
   allowlist in `src/gti_copilot/obd/allowlist.py` (Modes 01, 02, 03, 07, 09, 0A). PRs that
   add write paths (Mode 04 clear-codes, UDS writes, adapter reconfiguration) will be closed.
2. **Driver safety first.** UI changes must stay glanceable: no flashing, no text entry while
   moving, night theme by default. See `docs/software/configuration.md` for the lockout rules.
3. **Hardware-abstracted.** Every physical device sits behind an interface with a simulator or
   mock. New hardware support must ship with a mock and tests that run in CI.
4. **Honest about hardware.** If you did not run it on the real thing, label it
   *hardware-unverified* in code comments and docs. If you did, file a
   [hardware report](.github/ISSUE_TEMPLATE/hardware_report.md).

## Development setup

```bash
git clone https://github.com/tmestery/pi-obd-copilot.git
cd pi-obd-copilot
make install          # venv + editable install with dev extras
make install-web      # frontend deps (needs Node 20+)
make lint typecheck test
make demo             # simulator + backend + UI on http://127.0.0.1:8765
```

## Workflow

- Branch names: `feat/...`, `fix/...`, `docs/...`, `chore/...`.
- Commits follow [Conventional Commits](https://www.conventionalcommits.org):
  `feat(obd): add tiered scheduler`, `fix(storage): flush on SIGTERM`.
- Open a PR using the template. CI (lint, mypy, tests, coverage gate, frontend, e2e) must be
  green. PRs are merged with a merge commit to preserve atomic history.
- Update `docs/PROGRESS.md` in every PR, and `docs/DECISIONS.md` when you made a non-obvious
  choice.

## Tests

| Command          | What it runs                                                    |
| ---------------- | --------------------------------------------------------------- |
| `make test-fast` | unit tests, no coverage                                         |
| `make test`      | unit + integration + contract tests, coverage gate (core >= 85%)|
| `make web-test`  | Vitest frontend tests                                           |
| `make e2e`       | Playwright against the simulator                                |
| `make soak`      | 30 simulated minutes, memory/CPU assertions                     |

Property-based tests (`hypothesis`) are used for PID decoding, trip segmentation and the co-pilot
grounding validator; please keep them when touching those areas.

## Adding hardware support

- **OBD adapter quirks:** `obd/elm_transport.py`, add a fixture in `tests/fixtures/elm/`.
- **Radar detector model:** follow `docs/software/radar-providers.md` ("How to add your Uniden").
- **Camera source / detector backend:** implement `camera/source.py` or `perception/detector.py`
  protocols and add a mocked-runtime test.

## Code style

`ruff` (lint + format, line length 100) and `mypy --strict` on the core packages. Run
`make format` before pushing; `pre-commit install` does it for you.
