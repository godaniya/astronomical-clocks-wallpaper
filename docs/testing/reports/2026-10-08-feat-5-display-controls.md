# Orloj display controls on the wallpaper surface (#5)

Test build: local debug `app-debug.apk` built from this branch's tree with
`./gradlew clean :app:assembleDebug`, APK SHA-256
`5ade1d47a4cbcf8ea14760ad0f28592f6f715f0ef2a31c78cd10a3e2bcff1911`. The `app/src/main` and
`app/src/test` trees it compiles are byte-identical to `44a8f61`, so that revision identifies the
application and test sources under test; the branch head carrying this report adds this file only.
The artifact was installed in place with `adb install -r` and the existing home-screen wallpaper
binding survived, rendering under a new PID.

The hash comes from a clean build. Rebuilding the same sources incrementally after an unrelated
source change and its revert produced a different artifact, so the recorded hash is only meaningful
for a clean tree and a clean build.

Physical device running Android 16 (API 36), 1080x2408 at 450 dpi. Vendor, model, serial, firmware
build, and precise location are withheld per the device-privacy policy; the saved site is the manual
Prague reference `50.08, 14.42`, `Europe/Prague`. Firmware build: withheld (embeds the model
identifier).

This pass found and then re-verified a fix for a placement defect that the first run exposed; both
the defective and the fixed build are recorded here, because the defect is the reason the fix
exists and the pre-fix numbers are what a later reader has to reproduce to see it.

## What was measured and why

The controls under test percent-scale one dial and place it, from `DialDisplaySettings`, within a
usable rectangle that the engine derives per frame from its Canvas, its display resources, the
offsets the launcher reports, and the system insets. The host suite pins that arithmetic on
synthetic rectangles; this pass asks whether the rectangle the framework really hands the engine
produces the composition a user sees, which is not something a host test can establish.

Two independent measurements were taken for every state. The first is the debug-only `DialLayout`
report, requested with the `DEBUG_SET_TIME` diagnostics broadcast and read back from logcat, which
carries the engine's own centre, radius, brightness and palette together with the display metrics it
resolved; `scripts/device_layer.py` rejects a report unless exactly one visible engine answers and
the reported centre and radius fit the captured frame. The second is a pixel measurement straight
off `screencap`: the bounding box of the dark palette's gold rim `#D8B66A`, which is drawn as a
stroked circle at the dial's outer radius. Agreement between a number the engine computes and a
number read off the framebuffer is what separates a diagnostic that lies from one that works, and in
this pass the two disagreed by 664 px before the fix.

That disagreement is the defect. `WallpaperViewport.resolve` treated the launcher's reported
`xPixelOffset` as the window's left edge and then clamped the window's *end* to the surface, so a
surface no larger than the display - which is what this device allocates - collapsed its usable
rectangle to whatever slack remained beyond the reported scroll. The launcher reports
`xPixelOffset = -664` for a surface exactly as large as the display, so the rectangle became 416 px
wide starting at surface x 664, and the default dial moved to the right edge at 38.5% of its
intended radius. The same offset was then added back into the `DialLayout` centre, so the diagnostic
reported a point the renderer never drew to and the device harnesses could not find the dial.

The fix clamps the window's *start* to the slack the surface actually has beyond it, which leaves a
screen-sized surface at 0, and drops the offset from the reported centre. The host cases for a
surface wider than the display still pass, and the clamping behaviour is covered by
`DialDisplayRenderTest.offsetsStayWithinTheSurface`.

## The defect this pass found

Measured on the pre-fix artifact, APK SHA-256
`a12e7a98e65b613562606eaa5aa815e1a83db38ec2c76c0afd153c2f736e1440`, revision `896b9e6`. The
`resolve` inputs below come from a temporary instrumented build that logged them and was then
reverted; it was never installed as the reported artifact.

| Check | Observed |
| --- | --- |
| home engine, defaults | reported `cx=208.0 cy=1217.0 radius=178.88 brightness=100`; measured gold rim centred (872, 1216), half-width 178 |
| `resolve` inputs, home engine | `surface=1080x2408 display=1080x2408 offsets=-664,0 insets=0,68,0,42` -> `(664.0, 68.0, 1080.0, 2366.0)` |
| `resolve` inputs, preview engine | `surface=1080x2408 display=1080x2408 offsets=0,0 insets=0,68,0,42` -> `(0.0, 68.0, 1080.0, 2366.0)` |
| engine start, first two frames | frame 1 `cx=540.0 radius=464.4`, frame 2 `cx=208.0 radius=178.88` 0.3 s later, reproduced on every restart and after a launcher restart |
| horizontal Position 0 / 99 | reported `cx=179.4` / `236.0`; the drawn rim's left edge sat at screen x 722 against a predicted 721, confirming the drawn centre was 664 px right of the reported one |
| Size 50 / 100 / 114 | reported `radius=89.4` / `178.88` / `203.9` |
| `scripts/device_smoke.py` | FAIL `hand not found; wallpaper must be visible and unobstructed`, FAIL `hand not drawn after surface recreation`, while the wallpaper was visible and correctly drawn |
| hand detector, both centres | reported centre (208, 1217) -> no hand found; drawn centre (872, 1217) -> hand at 151.63 deg |
| surface covered | the whole screen reads the wallpaper background `#101923` and dims with it, so the Canvas is the screen and the reported centre cannot be a screen coordinate |

## Observed results, fixed build

| Date | Check | Observed |
| --- | --- | --- |
| 2026-10-08 | build, verify, install | `./gradlew qualityGate :app:assembleDebug` passed at 591 tests per debug/release variant with detekt, ktlint and Android Lint clean; `scripts/verify-apk.sh`, codespell 2.4.3 and `git diff --check` passed; `adb install -r` replaced the previous build in place and the home-screen binding re-rendered without being reapplied |
| 2026-10-08 | home defaults | reported `cx=540.0 cy=1217.0 radius=464.4 brightness=100`; measured gold rim centred (540, 1216), half-width 464 |
| 2026-10-08 | Size 50% | `radius=232.2`; measured rim centred (539, 1216), half-width 231 |
| 2026-10-08 | Size 114% | `radius=529.4`; the slider tap landed one step below 115%, which is the 114% row rather than a shortfall |
| 2026-10-08 | Horizontal 0% | `cx=531.0`, equal to the 530.95 px stroked extent at radius 529.4, so the dial's left edge is flush with the usable rectangle |
| 2026-10-08 | Horizontal 99% | `cx=548.9`, equal to 1080 - 530.95 = 549.05 |
| 2026-10-08 | Vertical 0% | `cy=599.0`, equal to the 68 px top inset plus the 530.95 px extent |
| 2026-10-08 | Vertical 99% | `cy=1822.7`, equal to 1217 + (2298 - 2x530.95) x 0.49 |
| 2026-10-08 | Brightness 80% | reported `brightness=80`; the whole screen dims, background `#101923` -> (12, 20, 28) and rim gold (216, 182, 106) -> (172, 145, 84), both x0.8 |
| 2026-10-08 | system screen brightness | `settings get system screen_brightness` read 13 before and 13 after the wallpaper dimming, with `screen_brightness_mode=1` |
| 2026-10-08 | Reset display | returned `cx=540.0 cy=1217.0 radius=464.4 brightness=100`; `dial_display.xml` then held `size=100 horizontal=50 vertical=50 brightness=100`, and the saved Prague site, all three layer checkboxes and the System-default appearance were unchanged |
| 2026-10-08 | persistence | at Size 114% the engine reported `radius=529.4` before and after `run-as <pkg> kill <pid>`; the service came back under a new PID with the saved setting |
| 2026-10-08 | preview engine | reported `cx=540.0 cy=1217.0 radius=232.2` at Size 50% and rendered the dial centred in the picker's preview |
| 2026-10-08 | `scripts/device_smoke.py` | passed: baseline hand 154.731 deg, at +30 m 162.293 deg, advance 7.562 deg against 7.500 deg expected, residual +0.062 deg; surface recreation `wm size 1080x2000` then reset, hand drawn afterwards |
| 2026-10-08 | renderer log scan | Inconclusive: the `AstronomicalClocksWallpaperService:W` and `DialRenderer:W` filter matched no record over the run, so it neither passed nor reported a warning |
| 2026-10-08 | device state restored | `wm size reset` and `wm density` back to physical with no override, `screen_off_pocket=1`, `proximity_sensor=1`, `accelerometer_rotation=1`, `user_rotation=0`, `screen_brightness=13`, `stay_on_while_plugged_in` back off, the keyguard left not showing, the home binding still this service, and `dial_display.xml` left at the defaults |

## What this does not establish

Rotation was not exercised: the home screen is portrait-locked and the display stayed at
`ROTATION_0` with `user_rotation=1`, so the landscape path and the wider-than-display surface that
the offsets pan over are host-tested only and were not reproduced on hardware. Only the dark
appearance was measured, so the light palette, the Sun, Moon and equinox markers, and the ring
scaling under the controls are not re-measured here. This build's lock slot is bound to the platform
`ImageWallpaper`, so there was no keyguard engine of this application to exercise. `screencap`
composites the launcher over the wallpaper, so the dimming was measured on wallpaper-painted
background rather than on launcher content, and the launcher's own edge panel overlaps the right
margin of some captures. The virtual clock was left at system time and only the diagnostics
broadcast, which does not move time, was used.

Cadence, screen-off behaviour, surface recreation outside the smoke harness, reboot, low-memory
recovery, allocation and battery or CPU qualification were not re-run against this build and remain
owed to #6. The pass re-checked the controls only on one launcher state; unreported launcher
cropping and OEM wallpaper dimming still cannot be inferred and physical acceptance is what
establishes them. A host check establishes no device behavior on its own, and this report records no
milestone completion, release or tag.
