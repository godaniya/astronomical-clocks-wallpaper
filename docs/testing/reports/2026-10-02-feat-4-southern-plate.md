# Southern plate and Sun layer verification (#4, #5)

Test build: local debug `app-debug.apk` from `feat/4-orloj-foundation` at 96f972a (APK SHA-256
a13cd926bab76cc72347dc5b09bfb6c489b5b4395ccdf02fbf8ffdac0a388eec), the artifact installed on the
device below.

Same physical device. Android version: 16 (API 36). Device locale `de-DE`, with no app-locale
override. Firmware build: withheld (embeds the model identifier).

The sites were entered by hand through Settings. Sydney, the south pole, and the equator were read
from the home screen; the Sun-layer checks used the system live-wallpaper preview, which shows the
dial unobstructed. The screenshot pipeline applies a colour transform (the hand reads back about
`#F1E5BD`, not `#F4E5B8`), so these checks are structural rather than exact-colour, except the hand
angle, which is a principal-axis measurement of the hand pixels.

| Date | Check | Observed |
| --- | --- | --- |
| 2026-10-03 | southern nesting | Sydney (-33.87, 151.21) put night at the dial centre, a twilight annulus around it, and day outside; the zodiac ring stayed tangent to both tropics |
| 2026-10-03 | south pole | (0, -90) gave concentric night, twilight, and day annuli, night innermost |
| 2026-10-03 | equator | (0, 0) put the horizon on a straight line through the hub, day above and twilight then night below |
| 2026-10-03 | Sun layer off | With the zodiac ring off, turning **Sun** off removed the sky and twilight fills and the horizon and night contour strokes, leaving only the tropics, the equator, and the outer rim |
| 2026-10-03 | Sun layer on | Restoring it redrew the fills and both contour strokes on the next visible frame |
| 2026-10-03 | repaint cadence, preview | 8 producer frames in 7.0 s, deltas 0.983-1.016 s, so 1.001 Hz |
| 2026-10-03 | hand angle, preview | Measured hand angle 32.022 degrees against 32.029 degrees implied by the device clock, 0.007 degrees apart |

The equator plate was observed both on the home screen and in the preview; the southern plates on the
home screen. After the pass the saved site was restored to the device's current location
(50.1081, 14.4695) and the wallpaper was left applied. No failure was observed. The cadence check
shows only that a frame is produced once per second; battery and frame-cost qualification remain #6.
