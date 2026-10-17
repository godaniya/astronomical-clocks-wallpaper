# Research evidence: 1 Hz vs 1-minute visible redraw cadence and B5 budget (#136)

## Overview

Physical-device research investigation for [#136: research(perf): gather evidence on whether the 1 Hz visible redraw keeps CPU above the B5 budget](https://github.com/godaniya/astronomical-clocks-wallpaper/issues/136).

The budget defined in [`docs/battery-budget.md`](../../battery-budget.md) specifies:
> **B5: Visible CPU Utilization**: **≤ 3% of one core** at 1 Hz over ≥ 15 min.

Prior empirical qualification runs ([PR #126 / report `2026-10-12-test-126-drain-comparison.md`](2026-10-12-test-126-drain-comparison.md) and [`2026-10-13-test-126-drain-comparison-on-battery.md`](2026-10-13-test-126-drain-comparison-on-battery.md)) repeatedly found the live wallpaper engine consuming 3.28%–3.65% of one core while visible on the home screen, consistently breaching the 3.0% B5 limit.

Issue #136 framed the core empirical question:
1. Does the 1 Hz redraw cadence account for the budget breach?
2. Does reducing the redraw cadence to once per minute bring CPU consumption within the ≤ 3.0% B5 budget?
3. Is a once-per-minute cadence visually distinguishable or aesthetically jarring?
4. What mechanisms account for the frame execution cost?

This report records controlled physical-device measurements comparing the baseline 1 Hz visible tick cadence against a 1-minute tick cadence under identical environmental controls.

---

## Hardware & Environment Attribution

- **Target Platform**: Physical device running Android 16 (API 36), display 1080x2408 (480 dpi).
- **Privacy Policy Compliance**: Hardware serial number, OEM name, marketing model, and firmware build identifier are withheld in accordance with the project's [physical-device privacy policy](../../../CONTRIBUTING.md#physical-device-testing-and-privacy).
- **Saved Observing Site**: `Europe/Prague` (source `MANUAL`, latitude `50.08`, longitude `14.42`).
- **Clock-Tick Rate**: `getconf CLK_TCK` returns `100` on this device.
- **Power Source**: `simulated` discharge (`cmd battery unplug` on USB connection) with brightness pinned at 128, auto-brightness disabled, display held awake, and airplane mode enabled.
- **Baseline Test Build**: Local debug `app-debug.apk`, SHA-256 `3ef8bf795587aff1488e2e073b3cc3bf70eb7620df821cb4bfa3d953fda3dc4d` (1 Hz tick cadence, commit `9ae118b`).
- **Modified Test Build**: Local debug `app-debug.apk`, SHA-256 `d5532f311d1bb8eefc9c7ecfbb5c1910109ff9487eb6fb87b8a4a274bb7cd812` (1-minute tick cadence aligned to minute boundaries).

---

## Controlled Measurement Method

Both arms were measured using `python3 scripts/battery_protocol.py visible --arm A --minutes 15` targeting the physical device:

1. **Environmental controls**:
   - Pinned screen brightness to 128 (manual brightness mode).
   - Raised screen timeout to prevent premature sleep.
   - Pinned `stay_on_while_plugged_in` to keep the display active.
   - Enabled airplane mode.
   - Simulated discharge via `cmd battery unplug`.
   - All settings restored in `finally` and validated by readback (`restore_problems: []`).
2. **Measurement window**:
   - Continuous 15-minute home-screen visible sampling (30 samples at 30-second intervals checking `screen_on=True`, `on_battery=True`, `home_in_front=True`, `keyguard_locked=False`).
   - Process CPU ticks measured across `/proc/<pid>/stat` deltas over the window.

---

## Empirical Results: Visible CPU (B5) Comparison

| Date | Build / Cadence | Window Duration | Discharge Delta | Mean Discharge Rate | Process CPU % (of 1 core) | B5 Budget (≤ 3.0%) |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-10-17 | Baseline (1 Hz) | 914.7 s | 0 µAh | 0 µA (simulated) | **3.2810%** | **FAIL** (> 3.0%) |
| 2026-10-17 | Modified (1 min) | 915.8 s | 0 µAh | 0 µA (simulated) | **0.0863%** | **PASS** (≤ 3.0%) |

### Key Metrics Summary
- **Baseline CPU**: 3.2810% of one core (~300 ticks over 914.7s at 100 ticks/s).
- **Modified CPU**: 0.0863% of one core (~79 ticks over 915.8s at 100 ticks/s).
- **Absolute CPU Reduction**: **-3.1947%** of one core.
- **Relative CPU Reduction**: **97.37%** drop in visible CPU utilization.

Both runs passed all 30 environmental integrity checks with zero restore problems.

---

## Verification & Smoke Checks (`device_smoke.py`)

Prior to the 15-minute measurement, the modified 1-minute cadence build was verified on the device using `scripts/device_smoke.py`:

```
Targeting ADB device: <withheld> (API 36)
Logcat start marker: 10-17 14:58:50.000
Waking the screen and showing the home screen...
Resetting virtual clock...
Capturing baseline frame t0...
Baseline hand angle at t0: 44.558°
Advancing virtual time +30 minutes via debug broadcast...
Capturing frame t1 at +30m...
Hand angle at t1 (+30m): 52.132°
Observed angular advance: 7.574° (expected: 7.500°, residual: +0.074°)
Testing surface recreation...
Restoring virtual clock, display size, and screen state...
Renderer log scan inconclusive: no matching warning records.
```

| Date | Check | Observed |
| --- | --- | --- |
| 2026-10-17 | virtual time travel (+30m) | Hand advanced 7.574° against 7.500° expected, residual +0.074°; broadcast confirmed by service log |
| 2026-10-17 | surface recreation | effective 1080x2408, `wm size 1080x2000` (active as requested) then `wm size reset` (verified); hand redrawn |
| 2026-10-17 | renderer log | Inconclusive: no matching warning records; rendering was not verified |

---

## Visual Distinction and Aesthetics Analysis

Issue #136 requires checking whether the slower cadence is visually distinguishable from 1 Hz at the measured dial size:

1. **Angular velocity**:
   - The Prague Orloj hour hand completes one full revolution ($360^\circ$) every 24 hours ($1440\text{ minutes} = 86,400\text{ seconds}$).
   - Angular rate: $0.25^\circ\text{ per minute} = 15\text{ arcminutes per minute} \approx 0.004167^\circ\text{ per second}$.
2. **Display geometry & pixel displacement**:
   - On this 1080x2408 (480 dpi) display, dial width fills 1080 px, yielding an outer ring radius $R \approx 500\text{ px}$.
   - At 1 Hz: Arc displacement per frame is $2\pi \times 500 \times \frac{0.004167^\circ}{360^\circ} \approx 0.036\text{ px}$ (sub-pixel, completely imperceptible frame-to-frame).
   - At 1-minute cadence: Arc displacement per tick is $2\pi \times 500 \times \frac{0.25^\circ}{360^\circ} \approx 2.18\text{ px}$.
   - At 480 dpi (density factor ~3.0), 2.18 physical pixels corresponds to $\approx 0.73\text{ dp}$ or $\approx 0.115\text{ mm}$ physical arc length.
3. **Observational impact**:
   - For an astronomical 24-hour clock dial, a 0.11 mm step every 60 seconds is imperceptible during passive viewing.
   - Stepping at minute boundaries aligns intuitively with civil minute rollovers (matching standard mechanical or digital clock expectations).
   - Static elements (astrolabe stereographic projection curves, Roman numeral ring, zodiac ecliptic ring) render identically with zero visual degradation or jitter.

---

## Mechanism Breakdown: What Accounts for the Frame CPU Cost

The measured 97.4% reduction in CPU utilization when reducing frame rate from 1 Hz (900 frames / 15 min) to 1/60 Hz (15 frames / 15 min) reveals the CPU consumption mechanism:

1. **Per-frame CPU consumption**:
   - At 1 Hz, 914.7s used ~30.01 seconds of single-core CPU time across ~915 frames, or **~32.8 ms of CPU time per frame**.
   - At 1-minute cadence, 915.8s used ~0.79 seconds of CPU time across ~15 frames, or **~52.6 ms of CPU time per active minute** (including Looper scheduling overhead and wakefulness sampling).
2. **Components of the frame pipeline**:
   - **Coordinate calculations**: Astronomy Engine solar/lunar position, ecliptic coordinate transformations, local sidereal time calculation, unequal temporal hour curve intersections.
   - **Canvas draw calls**: Canvas save/restore, transformation matrices for the zodiac dial, drawing dynamic sun/moon glyphs, anti-aliased hand lines, and counterweight geometries.
   - **Surface locking and synchronization**: `SurfaceHolder.lockHardwareCanvas()` and `unlockCanvasAndPost()` synchronization between application Looper and SurfaceFlinger.
3. **Conclusion on mechanism**:
   - The CPU cost was predominantly driving the 1 Hz Canvas/ephemeris rendering loop rather than background idle overhead.
   - By eliminating 59 out of 60 unnecessary redraws, the engine drops well below 0.1% CPU of one core, cleanly satisfying the B5 budget of ≤ 3.0%.
