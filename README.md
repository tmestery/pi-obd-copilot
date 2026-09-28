# gti-copilot

[![CI](https://github.com/tmestery/pi-obd-copilot/actions/workflows/ci.yml/badge.svg)](https://github.com/tmestery/pi-obd-copilot/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)

A Raspberry Pi 5 in-car computer for a 2016 VW Golf GTI (MK7, EA888 Gen3). It starts as a
**read-only OBD-II performance dashboard and trip logger** and grows into a full "car brain":
radar-detector + GPS fusion, a perception dashcam, and a fully offline small-language-model
co-pilot that only narrates facts computed by deterministic code.

> **Status:** under construction. Follow [`docs/PROGRESS.md`](docs/PROGRESS.md) for the current
> step and [`docs/PLAN.md`](docs/PLAN.md) for the roadmap.

## Principles

- **Read-only on the car.** Only OBD-II services 01/02/03/07/09/0A are ever sent. Clearing codes
  and every write path is blocked in code and proven by tests.
- **Driver safety first.** Glanceable UI, no flashing, interaction lockout while moving, night theme.
- **Hardware-abstracted.** Every device (OBD adapter, GPS, radar, camera, LLM) sits behind an
  interface with a simulator. The whole stack runs on a laptop with `make demo`.
- **Offline-first and private.** No cloud, no telemetry.

## Quickstart (laptop, no hardware)

```bash
git clone https://github.com/tmestery/pi-obd-copilot.git && cd pi-obd-copilot
make install
make demo
```

## Legal and safety

Radar detector legality varies by jurisdiction and vehicle type. This project logs and displays
alerts for awareness; it does not jam or defeat enforcement and does not encourage speeding.
Use at your own risk; do not operate controls while driving; install wiring correctly and fuse
every tap. See [`SECURITY.md`](SECURITY.md).

## License

[MIT](LICENSE)
