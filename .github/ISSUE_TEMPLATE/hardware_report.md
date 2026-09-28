---
name: Hardware validation report
about: Report results from docs/hardware/validation-checklist.md on real hardware
title: "hw: <feature> on <vehicle/adapter>"
labels: hardware-report
---

## Setup

- Vehicle (year / model / transmission):
- OBD adapter (model, firmware, USB or Bluetooth):
- Raspberry Pi model / OS image / gti-copilot version:
- GPS / radar detector / camera (if applicable):

## Checklist items exercised

| Step (from validation-checklist.md) | Result (pass / fail / partial) | Notes |
| --- | --- | --- |
| Bench: adapter connects | | |
| Supported-PID discovery | | |
| RPM / speed vs cluster | | |
| Baro / boost sanity at key-on | | |
| Fuse tap ignition-switched | | |
| Shutdown delay | | |
| Bluetooth reconnect | | |
| GPS fix | | |
| Radar provider | | |
| Camera framing | | |
| Thermal (hot day) | | |

## `gti-copilot doctor` output

```text
```

## Anything surprising

<!-- adapter quirks, PIDs that were not supported, wrong units, etc. -->
