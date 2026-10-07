# Screen-off sleep and background pause qualification (#6)

## Overview

Physical-device qualification run for [#6](https://github.com/godaniya/astronomical-clocks-wallpaper/issues/6) verifying screen-off sleep and background pause behavior, addressing the first acceptance criterion of #6:
> *"Instrument or otherwise demonstrate zero rendering while hidden and while the screen is off; hidden engine instances do not keep recurring calculation/render work alive."*

Prior qualification reports noted *"rendering while asleep was not measured"* during Phase 1. This run instruments Phase 1 in `scripts/device_qualification.py` via `read_wallpaper_visible()` to query `dumpsys activity service`, confirming that Android's WallpaperManager reports the engine hidden (`mVisible=false`) during sleep and that render/tick passes remain halted, followed by confirmed screen wake and hand detection within 1 second.

Harness revision under test: branch `test/6-background-pause-qualification` based on `91f2348b64e56570c9c7f698a9c2bc52c3dbfecb`.

Test APK: local debug `app-debug.apk` built from this branch (APK SHA-256 `ac69905fe32b91c3c87bc04f892a0025cd86a389b366707aa5be5783b67a50a5`), verified with `scripts/verify-apk.sh` and confirmed on-device via `sha256sum`.

Target platform: physical device running Android 16 (API 36), locale `de-DE`, timezone `Europe/Prague`. Hardware serial number, OEM, model name, and firmware build identifier are withheld in accordance with the project's [physical-device privacy policy](../../../CONTRIBUTING.md#physical-device-testing-and-privacy). Run date: 2026-10-07.

---

## 1. Automated Smoke Verification (`device_smoke.py`)

Run command:
```sh
python3 scripts/device_smoke.py
```

| Date | Check | Observed |
| --- | --- | --- |
| 2026-10-07 | virtual time travel (+30m) | Hand advanced 7.536° against 7.500° expected, residual +0.036°; broadcast confirmed by the service log |
| 2026-10-07 | surface recreation | effective 1080x2408, `wm size 1080x2000` (active as requested) then `wm size reset` (verified); hand drawn afterwards |
| 2026-10-07 | renderer log | Inconclusive: no matching warning records; rendering was not verified |

Result: Smoke test passed with clean exit code 0.

---

## 2. Multi-Phase Device Qualification Verification (`device_qualification.py`)

Run command:
```sh
python3 scripts/device_qualification.py --max-pss-growth-kb 6144
```

| Date | Check | Observed |
| --- | --- | --- |
| 2026-10-07 | visible dial baseline | Dial rendered (Dark palette), hand at 178.127° |
| 2026-10-07 | screen-off / wake navigation | device reported screen off for 4s; wallpaper reported hidden (mVisible=false, rendering halted); hand visible within 1s of wake at 178.156° |
| 2026-10-07 | preview navigation | returned to home and detected the active wallpaper hand at 178.182°; preview-engine cleanup was not inspected |
| 2026-10-07 | surface recreation | Override to 1080x2000 and verified restore to physical size redrew dial; hand at 178.198° |
| 2026-10-07 | process rebind | new PID observed within 10 polls at 0.5s intervals; hand visible at 178.212°; saved preference values were not inspected |
| 2026-10-07 | time travel (+30m, +12h) | +30m moved hand 7.536° (residual +0.036°); +12h moved 179.762° (residual -0.238°) |
| 2026-10-07 | total PSS sample | 29319 -> 31589 kB over 10s (growth +2270 kB; budget 6144 kB); not battery or CPU evidence |
| 2026-10-07 | renderer log scan | Inconclusive: no matching warning records; rendering was not verified |

Result: All 7 configured qualification phases passed with clean exit code 0. Teardown in `finally` confirmed restored display size (1080x2408), night mode, virtual clock, and screen state.

---

## 3. Not covered

Date rollover, battery and CPU consumption benchmarks (the PSS sample is not battery or CPU evidence), the lit lock-screen scenario, and cold reboot persistence remain unverified.
