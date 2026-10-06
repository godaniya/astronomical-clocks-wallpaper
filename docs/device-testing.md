# Physical-device testing

Procedures and acceptance guidelines for verifying the live wallpaper on a physical Android device.
This page is deliberately device-agnostic about identity: the device is referred to only as
"the physical device", and its model, OEM, and serial number are omitted from public surfaces per
the project's device-privacy policy. Android version is non-identifying and is recorded in reports; the
firmware build string embeds the model identifier, so it is withheld.

## Connecting

Prefer wireless debugging (Android 11+, API 30+) so no USB cable or vendor ID is needed:

```sh
adb pair <host>:<port> <pairing-code>   # one-time pairing from Developer options
adb connect <host>:<port>
adb devices                             # confirm the device is listed as "device"
```

A USB connection works too; the steps below are transport-independent.

## Install and launch

The application ID changed from `io.github.cmp0xff.astronomicalclockswallpaper` to
`io.github.godaniya.astronomicalclockswallpaper` in #47, so Android installs the new build as a
separate app. Remove any pre-migration debug build first; otherwise both stay installed and the
old wallpaper binding and saved data remain on the device. Saved site and dial settings do not
carry over to the new package.

```sh
adb uninstall io.github.cmp0xff.astronomicalclockswallpaper.debug   # only if a pre-migration build is installed
adb install -r app-debug.apk   # replaces a previous build of the same application ID in place
adb shell am start -n \
  io.github.godaniya.astronomicalclockswallpaper.debug/io.github.godaniya.astronomicalclockswallpaper.SettingsActivity
```

In **Astro Clocks**, tap **Open wallpaper preview**, then apply it to the home and lock screens.

## Inspecting state

```sh
adb shell dumpsys wallpaper                            # active component and visibility
adb shell pidof io.github.godaniya.astronomicalclockswallpaper.debug
adb logcat --pid=<pid> -v time                         # follow the running wallpaper process
adb shell screenrecord /sdcard/clock.mp4               # record; press Ctrl-C to stop
adb pull /sdcard/clock.mp4
```

## Lifecycle transitions

Each #2 transition is mapped to the `ClockEngine` callback it should trigger, so an observation can
be checked against the expected handler.

| Transition | Expected `ClockEngine` behavior |
| --- | --- |
| Preview open | `onCreateEngine`, then `onVisibilityChanged(true)` draws and schedules the next tick |
| Preview close | `onVisibilityChanged(false)` cancels the pending tick |
| Lock / unlock (lit lock screen) | `onVisibilityChanged(false)` / `(true)` across the surface switch |
| Screen off | `onVisibilityChanged(false)` cancels the pending tick |
| Screen on | `onVisibilityChanged(true)` redraws and reschedules from wall time |
| Surface recreation (no visibility change) | `onSurfaceDestroyed` cancels the pending tick; `onSurfaceChanged` redraws and reschedules while visible |
| Reboot | Process and engine recreated; clock resumes from the device wall time |

## Virtual time

Debug builds (the `debuggable` flag, so never release builds) accept a broadcast that moves the
wallpaper's clock without touching the phone's real time, so a drift check no longer needs a
30-minute wait. Every engine that is visible with a live surface redraws immediately; a destroyed
engine, a hidden engine, or one whose surface has been destroyed is skipped and catches up on its
next visibility or surface change (the debug trigger logs which guard failed at debug level).

```sh
ACTION=io.github.godaniya.astronomicalclockswallpaper.DEBUG_SET_TIME
adb shell am broadcast -a $ACTION --el offset_minutes 30        # also offset_millis/seconds/hours
adb shell am broadcast -a $ACTION --es instant 2026-06-21T00:00:00Z   # fix an exact instant
adb shell am broadcast -a $ACTION --ez reset true               # back to system time
```

Offsets are added to the real clock, so they keep running; an `instant` freezes it. Always reset
afterwards. `scripts/device-smoke-test.py` reads the screen's power state, wakes the screen, advances
30 minutes, measures the civil hand's advance (7.5° expected on the 24-hour dial), recreates the
surface, checks logcat, resets the clock, sleeps the screen again when it did not start awake, and
exits non-zero on failure. It needs the wallpaper applied and visible on the home screen.

This clock moves the civil hand and the astronomy together from one instant, so it shows that the
marker follows the ephemeris but does not replace the independent ERFA comparison in the Sun and Moon
passes. A smoke run only measures the hand; it does not exercise lifecycle, reboot, or the lock screen.

## Standard acceptance test matrix

The matrix below maps standard verification areas to their expected behavior, failure traps, and historical physical-device qualification reports.

| Category | Key Acceptance Criteria | Diagnostic Checks | Baseline Verification Report |
| :--- | :--- | :--- | :--- |
| **Lifecycle & Surfaces** | Wallpaper resumes on surface recreation (`wm size`) and visibility toggles; halts when hidden; recovers after non-stopping `SIGKILL`. Force-stop is an accepted platform limitation requiring manual re-application. | `dumpsys wallpaper`, `pidof`, `onVisibilityChanged`, `onSurfaceChanged` | [2026-10-06 Force-Stop vs Lifecycle](testing/reports/2026-10-06-docs-36-force-stop-lifecycle.md), [2026-09-28 Feasibility](testing/reports/2026-09-28-feat-2-device-feasibility.md) |
| **Cadence & Ticking** | Steady 1.000 Hz frame cadence; no dropped frames or thread churn; zero allocation in draw loop. | `atrace -a <pid> gfx view`, `logcat` skipping-frame probe | [2026-10-01 Orloj Foundation](testing/reports/2026-10-01-feat-4-orloj-foundation.md), [2026-10-02 Dial Caching](testing/reports/2026-10-02-perf-39-dial-caching.md) |
| **Virtual Time Travel** | Advance by offsets and fixed instants via debug broadcast; civil hand moves proportionally (7.5° per 30m); automated smoke test passes. | `scripts/device-smoke-test.py`, `DEBUG_SET_TIME` broadcast | [2026-10-04 Virtual Time Smoke](testing/reports/2026-10-04-feat-6-virtual-time-smoke.md) |
| **Location & Permissions** | Non-promptable denial shows recovery dialog; promptable denial shows rationale; neutral manual coordinates persist across restarts; pure-read storage never writes on read. | `dumpsys package`, `LocationStore`, `observing_location.xml` | [2026-10-05 Permission Recovery](testing/reports/2026-10-05-fix-3-permission-recovery.md), [2026-10-05 Pure-Read Storage](testing/reports/2026-10-05-refactor-35-pure-location-store.md), [2026-09-29 Location Slice](testing/reports/2026-09-29-feat-3-location-slice.md) |
| **Site Timezone & Selection** | Preserves site geographic timezone across device timezone changes; unchanged Save preserves `CURRENT_COARSE`; searchable picker pre-selects active zone and filters accurately. | `persist.sys.timezone`, `SettingsActivity`, timezone picker dialog | [2026-09-30 Site Timezone](testing/reports/2026-09-30-feat-24-site-timezone.md), [2026-10-02 Unchanged Save](testing/reports/2026-10-02-fix-42-unchanged-save.md), [2026-10-04 Timezone Picker](testing/reports/2026-10-04-feat-21-geographic-timezone.md) |
| **Dial Astronomy & Geometry** | 24-hour civil hand tracks local solar/civil time; Sun/Moon markers match ERFA coordinates within 1 px; southern plate inverts altitude correctly; lunar terminator reflects phase and hemisphere mirror. | Screencap least-squares rim fit, principal-axis angle probe, ERFA fixtures | [2026-10-03 Sun Marker](testing/reports/2026-10-03-feat-27-sun-marker.md), [2026-10-04 Moon Marker](testing/reports/2026-10-04-feat-28-moon-marker.md), [2026-10-02 Southern Plate](testing/reports/2026-10-02-feat-4-southern-plate.md), [2026-10-03 Zodiac Compartments](testing/reports/2026-10-03-feat-43-zodiac-compartments.md) |
| **Themes & Contrast** | Light, Dark, and System appearance modes render correctly; visible repaints immediately on `cmd uimode night`; markers remain legible with casing across day/twilight/night plates. | `cmd uimode night yes/no`, screencap palette match | [2026-10-04 Appearance Themes](testing/reports/2026-10-04-feat-31-appearance.md) |

## Historical verification reports

Detailed, immutable physical-device verification reports are maintained in [`docs/testing/reports/`](testing/reports/):

| Date | Topic / Feature | Primary Evidence | Report Link |
| :--- | :--- | :--- | :--- |
| 2026-09-07 | Repository bootstrap | Toolchain, quality gate, negative compiler/linter probes | [2026-09-07-bootstrap.md](testing/reports/2026-09-07-bootstrap.md) |
| 2026-09-28 | Device feasibility & initial render (#2, #19) | Hand angles, tick geometry, 1 Hz ticking, surface recreation | [2026-09-28-feat-2-device-feasibility.md](testing/reports/2026-09-28-feat-2-device-feasibility.md) |
| 2026-09-29 | Location slice & coordinate locale (#3) | Manual coordinates, coarse location prompt, German locale separator | [2026-09-29-feat-3-location-slice.md](testing/reports/2026-09-29-feat-3-location-slice.md) |
| 2026-09-30 | Saved-site timezone & coordinate precision (#24) | Zone retention across phone-zone changes, 4-decimal precision | [2026-09-30-feat-24-site-timezone.md](testing/reports/2026-09-30-feat-24-site-timezone.md) |
| 2026-10-01 | Orloj 24-hour foundation (#4, #5) | 24-hour scale, 1.000 Hz cadence, representative sites | [2026-10-01-feat-4-orloj-foundation.md](testing/reports/2026-10-01-feat-4-orloj-foundation.md) |
| 2026-10-02 | Southern plate & Sun layer (#4, #5) | Southern stereographic projection, horizon nesting, Sun toggle | [2026-10-02-feat-4-southern-plate.md](testing/reports/2026-10-02-feat-4-southern-plate.md) |
| 2026-10-02 | Dial caching & error containment (#39) | Path caching, 1 Hz steady cadence, first-frame error containment | [2026-10-02-perf-39-dial-caching.md](testing/reports/2026-10-02-perf-39-dial-caching.md) |
| 2026-10-02 | Unchanged Save provenance & zone retention (#42) | Untouched Save preserves CURRENT_COARSE and geographic zone | [2026-10-02-fix-42-unchanged-save.md](testing/reports/2026-10-02-fix-42-unchanged-save.md) |
| 2026-10-03 | Zodiac compartments & vernal equinox star (#43) | 12 sign compartments, 0° Aries star, reoriented dial-centre dividers | [2026-10-03-feat-43-zodiac-compartments.md](testing/reports/2026-10-03-feat-43-zodiac-compartments.md) |
| 2026-10-03 | Sun marker & ERFA ephemeris verification (#27) | Sun marker bearing/radius vs ERFA ephemeris, lock screen | [2026-10-03-feat-27-sun-marker.md](testing/reports/2026-10-03-feat-27-sun-marker.md) |
| 2026-10-03 | Zodiac hardening (#74) | Discriminant clamp, try-finally canvas restore spot-check | [2026-10-03-refactor-74-zodiac-hardening.md](testing/reports/2026-10-03-refactor-74-zodiac-hardening.md) |
| 2026-10-04 | Moon marker & phase terminator (#28) | Moon bearing, radius, phase fidelity, southern limb mirror | [2026-10-04-feat-28-moon-marker.md](testing/reports/2026-10-04-feat-28-moon-marker.md) |
| 2026-10-04 | Geographic timezone & searchable picker (#21, #24) | Offline timezone estimation dialog, searchable picker list | [2026-10-04-feat-21-geographic-timezone.md](testing/reports/2026-10-04-feat-21-geographic-timezone.md) |
| 2026-10-04 | Virtual time travel & smoke harness (#6) | Broadcast-driven time travel (+30m), automated script validation | [2026-10-04-feat-6-virtual-time-smoke.md](testing/reports/2026-10-04-feat-6-virtual-time-smoke.md) |
| 2026-10-04 | Appearance themes & night mode (#31) | Light/Dark/System themes, live night mode repainting, marker contrast | [2026-10-04-feat-31-appearance.md](testing/reports/2026-10-04-feat-31-appearance.md) |
| 2026-10-05 | Pure-read location storage & startup migration (#35) | Zero-write load(), startup migration and repair once in Application.onCreate | [2026-10-05-refactor-35-pure-location-store.md](testing/reports/2026-10-05-refactor-35-pure-location-store.md) |
| 2026-10-05 | Location permission recovery (#3) | Non-promptable denial recovery dialog, promptable denial toast | [2026-10-05-fix-3-permission-recovery.md](testing/reports/2026-10-05-fix-3-permission-recovery.md) |
| 2026-10-06 | Force-stop vs process-recreation lifecycle (#36) | Non-stopping SIGKILL auto-rebind vs force-stop platform limitations | [2026-10-06-docs-36-force-stop-lifecycle.md](testing/reports/2026-10-06-docs-36-force-stop-lifecycle.md) |
