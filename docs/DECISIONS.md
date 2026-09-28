# Decision log

Format: date, decision, alternatives considered, reason. Newest at the bottom.

## 2026-09-27 - Environment capabilities at start

- **Available:** git 2.51, `gh` 2.66 (authenticated as `tmestery`; note the sandboxed shell cannot
  reach `api.github.com`, so `gh` commands run unsandboxed), Python 3.11/3.12/3.13/3.14 via
  Homebrew, Node 25.9 / npm 11, ffmpeg 8.0.1, Playwright 1.63 with Chromium headless shell
  (installed), shellcheck 0.11 (installed via Homebrew).
- **Gaps:** no `rsvg-convert`, `cairosvg` or `mermaid-cli`. SVG rasterisation and Mermaid-style
  diagrams are therefore done through Playwright/Chromium, which we need anyway for screenshots.
  No real hardware (car, Pi, OBD adapter, Uniden detector, camera, GPS) - everything is simulated.
- **Python version for development:** 3.12 (`.venv`). CI tests 3.11 and 3.12 as required.

## 2026-09-27 - Use the existing repository `tmestery/pi-obd-copilot`

- **Decision:** keep the pre-existing public GitHub repo `pi-obd-copilot` as the remote instead of
  creating a new `gti-copilot` repo. The Python package, CLI and product name remain
  `gti-copilot` / `gti_copilot`.
- **Alternatives:** create `gti-copilot` and re-point the remote.
- **Reason:** the brief says to use the current repo if one exists; renaming a fresh repo gains
  nothing and would orphan the existing remote.

## 2026-09-27 - Ship through real GitHub PRs

- **Decision:** feature branches, Conventional Commits, `gh pr create`, `gh pr checks --watch`,
  `gh pr merge --merge --delete-branch`. No local-merge fallback needed since `gh` is authenticated.

## 2026-09-27 - SQLite via stdlib `sqlite3` in a dedicated writer thread

- **Decision:** use `sqlite3` from the standard library driven from a single worker thread (queue
  fed from asyncio) rather than `aiosqlite`.
- **Alternatives:** `aiosqlite`, SQLAlchemy.
- **Reason:** one fewer dependency on the Pi, WAL + batched inserts are simplest with a single
  owning thread, and it makes the graceful-flush-on-SIGTERM path a single join.

## 2026-09-27 - Own ELM327/STN protocol implementation instead of wrapping `python-obd`

- **Decision:** `ElmTransport` speaks the ELM327 AT/hex protocol directly over `pyserial`.
- **Alternatives:** wrap `python-obd`.
- **Reason:** `python-obd` owns its own connection/decoding loop and makes it hard to (a) enforce the
  read-only allowlist at the byte level, (b) run our own tiered scheduler, and (c) inject faults
  in tests. Our PID table already handles decoding. `python-obd` remains a documented alternative.

## 2026-09-27 - `r8link` exists and is MIT licensed; wrap it as an optional provider

- **Finding:** PyPI `r8link` 0.9.1 (Aegis, MIT, `bleak`-based, Linux/BlueZ only) reads a Uniden R8w
  over BLE; API is `async with R8W(addr) as r8: async for update in r8.updates()` with
  `update.kind == "alerts"` and alert objects carrying band, frequency, strength, direction.
- **Decision:** `radar/r8link_provider.py` imports it lazily, duck-types the update objects, fails
  soft with a status message when the library, `bleak`, or BlueZ are missing. Marked
  hardware-unverified. Only installed via the `[radar]` extra on Linux.

## 2026-09-27 - Diagrams are hand-authored SVG generated from Python

- **Decision:** `scripts/render_diagrams.py` builds each SVG with a tiny helper library (rects,
  text, arrows) and Chromium rasterises them to PNG. The banner is also generated SVG (no image
  model is available in this environment).
- **Reason:** reproducible, dependency-free, diff-able.

## 2026-09-27 - Frontend `dist/` is not committed

- **Decision:** `src/gti_copilot/web/dist` is built in CI, by `make demo`, and attached to GitHub
  Releases as `gti-copilot-web-<tag>.tar.gz`; `install_pi.sh` downloads that tarball so the Pi never
  needs Node.
- **Reason:** keeps the repo small and avoids stale build artefacts in PR diffs.

## 2026-09-27 - License audit (updated as dependencies are added)

| Package                | License      | Used for                          |
| ---------------------- | ------------ | --------------------------------- |
| fastapi, uvicorn       | MIT / BSD-3  | API + WS                          |
| pydantic               | MIT          | config + schemas                  |
| pyyaml                 | MIT          | config                            |
| pyserial               | BSD-3        | ELM transport                     |
| httpx                  | BSD-3        | LLM HTTP backends, tests          |
| pytest, hypothesis     | MIT / MPL-2  | tests                             |
| ruff, mypy             | MIT          | tooling                           |
| playwright             | Apache-2.0   | e2e + screenshots                 |
| matplotlib, numpy      | PSF-like/BSD | boost-curve chart                 |
| r8link (optional)      | MIT          | Uniden R8w provider               |
| bleak (optional)       | MIT          | BLE                               |
| opencv-python-headless | Apache-2.0   | camera (optional)                 |
| onnxruntime            | MIT          | detector (optional)               |
| Vite, Vitest, TypeScript | MIT        | frontend tooling                  |
