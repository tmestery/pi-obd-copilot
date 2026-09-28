# Internal contracts

These are the interfaces that let subsystems be built and tested independently. They are
deliberately small. Change them only with a note in `docs/DECISIONS.md`.

## Event bus (`gti_copilot.acquisition.bus`)

`EventBus.subscribe(topic, handler) -> unsubscribe`, `await EventBus.publish(topic, payload)`,
`EventBus.publish_nowait(...)` from sync code in the loop, `EventBus.last(topic)`.
Handlers may be sync or async; exceptions are logged, never propagated. Topics and payloads:

| Topic       | Payload                                                                  |
| ----------- | ------------------------------------------------------------------------ |
| `telemetry` | `gti_copilot.telemetry.TelemetrySnapshot` (published at the fast tier)    |
| `event`     | `gti_copilot.telemetry.DriveEvent`                                        |
| `adapter`   | `{"state": "connected"\|"disconnected"\|"connecting", "name": str}`        |
| `trip`      | `{"state": "started"\|"ended", "trip_id": int, "summary": {...}?}`         |
| `dtcs`      | `{"codes": [{"code","kind","description"}], "new": [...]}`                |
| `gps`       | `gti_copilot.gps.provider.GpsFix`                                         |
| `radar`     | `gti_copilot.radar.provider.RadarAlert`                                   |
| `power`     | `{"state": "on"\|"ignition_off"\|"low_voltage"\|"shutdown", "seconds_left": float\|None}` |
| `perf`      | `{"state": "armed"\|"running"\|"complete"\|"aborted", "kind": str, "run": PerfRun.to_dict()?}` |
| `clip`      | `{"state": "saved"\|"failed", "clip": {...}}`                             |
| `copilot`   | `{"kind": "alert"\|"summary"\|"answer", "text": str, "speak": bool, ...}`  |
| `status`    | free-form `{key: value}` merged into the UI status bar                    |

## Telemetry snapshot (`gti_copilot.telemetry.TelemetrySnapshot`)

Dataclass; SI units (km/h, kPa, °C, g/s, V, deg, g). `None` = not available. Fields: `t`
(wall clock), `mono`, `rpm`, `speed_kph`, `map_kpa`, `baro_kpa`, `boost_kpa`, `throttle_pct`,
`load_pct`, `coolant_c`, `iat_c`, `ambient_c`, `maf_gps`, `volt_v`, `timing_deg`,
`fuel_rate_lph`, `fuel_level_pct`, `oil_temp_c`, `stft_pct`, `ltft_pct`, `pedal_pct`, `gear`,
`shift` (`none|warn|shift`), `accel_g`, `peak_boost_kpa`, `peak_rpm`, `peak_speed_kph`,
`instant_mpg`, `lat`, `lon`, `gps_speed_kph`, `heading_deg`, `gps_fix`, `adapter_connected`,
`trip_id`, `extra: dict`.

`DriveEvent(type, ts, severity, payload, lat, lon, trip_id, id)`; `PerfRun(kind, started_ts,
duration_s, curve[(t_rel_s, speed_kph)], completed, trip_id, peak_g)`.

## Storage tables (SQLite, WAL) - `storage/migrations/0001_init.sql`

```
schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT)
trips(id INTEGER PK, started_at REAL, ended_at REAL, start_odo_est REAL, distance_m REAL,
      max_speed_kph REAL, max_boost_kpa REAL, avg_speed_kph REAL, max_rpm REAL, fuel_used_l REAL,
      sample_count INTEGER, status TEXT CHECK(status IN ('active','ended','aborted')))
samples(trip_id INTEGER, ts_ms INTEGER, rpm REAL, speed_kph REAL, map_kpa REAL, baro_kpa REAL,
      boost_kpa REAL, throttle_pct REAL, load_pct REAL, coolant_c REAL, iat_c REAL, maf_gps REAL,
      volt_v REAL, timing_deg REAL, accel_g REAL, gear INTEGER, lat REAL, lon REAL,
      gps_speed_kph REAL, extra_json TEXT)   -- index (trip_id, ts_ms)
events(id INTEGER PK, trip_id INTEGER, ts_ms INTEGER, type TEXT, severity TEXT,
      payload_json TEXT, lat REAL, lon REAL)
perf_runs(id INTEGER PK, trip_id INTEGER, kind TEXT, started_ts_ms INTEGER, duration_ms INTEGER,
      completed INTEGER, peak_g REAL, curve_json TEXT)
dtcs(id INTEGER PK, trip_id INTEGER, ts_ms INTEGER, code TEXT, kind TEXT, description TEXT,
      cleared INTEGER DEFAULT 0)
radar_alerts(id INTEGER PK, trip_id INTEGER, alert_id TEXT, started_ts_ms INTEGER,
      ended_ts_ms INTEGER, band TEXT, freq_mhz REAL, max_strength INTEGER, direction TEXT,
      source TEXT, lat REAL, lon REAL, speed_kph REAL, geohash TEXT, payload_json TEXT)
clips(id INTEGER PK, trip_id INTEGER, event_id INTEGER, created_ts_ms INTEGER, path TEXT,
      thumb_path TEXT, sidecar_path TEXT, duration_s REAL, size_bytes INTEGER,
      locked INTEGER DEFAULT 0, trigger TEXT, detections_json TEXT)
summaries(id INTEGER PK, trip_id INTEGER, created_ts_ms INTEGER, backend TEXT, facts_json TEXT,
      text TEXT, grounded INTEGER, attempts INTEGER)
```

Storage exposes a `Repo` with async methods used by the API and co-pilot tools (names are the
contract even if the storage PR lands first): `list_trips(limit, offset)`, `get_trip(id)`,
`trip_samples(id, downsample)`, `list_events(trip_id?, type?, limit)`, `list_perf_runs(...)`,
`list_dtcs(...)`, `radar_alerts(trip_id?, since?)`, `list_clips(...)`, `summaries(trip_id)`,
`trip_stats(trip_id)`, `top_metric(metric, since_ts)`, `count_events(type, since_ts)`,
`radar_summary(since_ts)`.

## REST + WebSocket (`gti_copilot.api`)

Base `http://127.0.0.1:8765`. JSON everywhere; all times are epoch seconds (floats).

| Method | Path                                       | Notes                                              |
| ------ | ------------------------------------------ | -------------------------------------------------- |
| GET    | `/api/health`                              | adapter, per-PID rates, DB, uptime, versions, power |
| GET    | `/api/state`                               | latest `TelemetrySnapshot` + status + active alerts |
| GET    | `/api/config`                              | resolved config (secrets-free)                     |
| PUT    | `/api/config`                              | validated subset: `units`, `ui.theme`, `ui.thresholds` |
| GET    | `/api/trips?limit&offset`                  | list                                               |
| GET    | `/api/trips/{id}`                          | detail + stats                                     |
| GET    | `/api/trips/{id}/samples?downsample=N`     | arrays                                             |
| GET    | `/api/trips/{id}/export.csv`               | CSV download                                       |
| GET    | `/api/trips/{id}/summary`                  | co-pilot summary (Phase 4)                         |
| POST   | `/api/trips/{id}/summary`                  | (re)generate                                       |
| GET    | `/api/perf-runs?limit`                     |                                                    |
| POST   | `/api/perf/reset`                          | re-arm timers                                      |
| GET    | `/api/events?type&limit`                   |                                                    |
| POST   | `/api/events/manual`                       | driver button (clip trigger)                       |
| GET    | `/api/dtcs`                                | read-only                                          |
| POST   | `/api/dtcs/refresh`                        | re-read only, never clears                         |
| GET    | `/api/radar/alerts?limit`                  | Phase 2                                            |
| GET    | `/api/radar/hotspots`                      | clustered                                          |
| GET    | `/api/radar/export.(csv\|geojson)`         |                                                    |
| GET    | `/api/clips`, `/api/clips/{id}`, `/api/clips/{id}/video`, `/thumb`, `/sidecar` | Phase 3 |
| POST   | `/api/clips/{id}/lock`, `DELETE /api/clips/{id}` |                                              |
| POST   | `/api/copilot/ask` `{"question": str}`     | parked only (policy enforced server-side)          |
| GET    | `/api/copilot/status`                      | backend, model, policy state                       |
| WS     | `/ws`                                      | see below                                          |

WebSocket messages (server -> client), 10-20 Hz for telemetry, others on change:

```json
{"t": 1735000000.123, "type": "telemetry", "data": {TelemetrySnapshot fields}}
{"t": ..., "type": "event",   "data": {DriveEvent fields}}
{"t": ..., "type": "radar",   "data": {"id","band","freq_mhz","strength","direction","state"}}
{"t": ..., "type": "perf",    "data": {"state","kind","elapsed_s"?,"run"?}}
{"t": ..., "type": "copilot", "data": {"kind","text","speak"}}
{"t": ..., "type": "power",   "data": {"state","seconds_left"}}
{"t": ..., "type": "status",  "data": {"adapter": bool, "gps": bool, "radar": bool, "camera": bool, "copilot": bool, "trip_id": int|null, "theme": "night"|"day"}}
{"t": ..., "type": "hello",   "data": {"version": str, "units": {...}, "thresholds": {...}, "vehicle": str}}
```

Client -> server: `{"type": "ping"}`; everything else goes through REST.

## Provider protocols

- `gps.provider.GpsProvider`: `async start()`, `async stop()`, `fixes() -> AsyncIterator[GpsFix]`,
  `status() -> ProviderStatus`. `GpsFix(ts, lat, lon, speed_kph, heading_deg, altitude_m, hdop, fix)`.
- `radar.provider.RadarProvider`: `async start()`, `async stop()`, `alerts() -> AsyncIterator[RadarAlert]`,
  `status() -> ProviderStatus`. `RadarAlert(id, ts, band, freq_mhz, strength 0-8, direction, state
  start|update|end, source, raw)`.
- `camera.source.VideoSource`: `async start()`, `async stop()`, `segments() -> AsyncIterator[Segment]`
  where the ring buffer owns segment files; `clips.ClipExporter.export(event, pre_s, post_s)`.
- `perception.detector.Detector`: `detect(frame) -> list[Detection(cls, conf, bbox, ts)]`, `name`, `available`.
- `copilot.backend.LLMBackend`: `generate(messages, max_tokens, stream) -> AsyncIterator[str]`,
  `name`, `available`.
- `power.monitor.PowerMonitor`: `async start()`, `async stop()`, `events() -> AsyncIterator[PowerEvent]`.
- `ProviderStatus(name, connected, detail, model=None, battery=None, rssi=None, hardware_verified=False)`.

## Simulator hooks

`vehicle.scenarios.Scenario.markers()` yields `(t_offset_s, marker)` such as `launch`,
`wot_start`, `radar_k`, `radar_ka`, `radar_end`, `hard_brake`, `trip_end`, `park`. Mock GPS,
mock radar and the demo choreography key off these markers so all mocks stay in sync.
