# Security policy

## Threat model

gti-copilot runs on a Raspberry Pi inside a car. It is **offline-first**: no cloud services, no
telemetry, and the API binds to `127.0.0.1` by default. The main risks are:

- **Vehicle safety:** the software must never write to the ECU. This is enforced by a strict
  service allowlist (`src/gti_copilot/obd/allowlist.py`) covered by tests. A bug that lets a write
  or clear-codes command through is a security issue.
- **Local network exposure:** if you enable LAN binding (`api.host: 0.0.0.0`) anyone on the same
  network can read your trips, GPS traces and clips. Only do this on a trusted network.
- **Data at rest:** trips, GPS traces, radar alerts and dashcam clips live unencrypted on the
  device's storage. Use full-disk encryption on the SSD if this matters to you.
- **Supply chain:** optional extras pull in third-party packages (`r8link`, `onnxruntime`,
  `llama-cpp-python`, ...). Model weights are never committed and are downloaded only on request.

## Reporting a vulnerability

Please open a private security advisory on GitHub
(`Security` tab -> `Report a vulnerability`) or email the maintainer listed in `pyproject.toml`.
Do not open a public issue for anything that could affect vehicle safety.

You should get an acknowledgement within a week. Fixes are released as patch versions and noted
in `CHANGELOG.md`.

## Supported versions

Only the latest minor release receives fixes.
