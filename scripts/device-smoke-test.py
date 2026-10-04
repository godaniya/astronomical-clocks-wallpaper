#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""
Automated physical-device smoke test harness for Astronomical Clock Wallpaper.

Exercises live wallpaper on an attached Android device via ADB:
- Virtual time travel (+30 minutes) via DEBUG_SET_TIME broadcast
- 24-hour hand angular advance verification (7.5 degrees per 30 minutes)
- Surface recreation (wm size)
- Clock reset and renderer log verification
"""

import argparse
import math
import re
import subprocess
import struct
import sys
import time

# Allowed deviation of the measured hand advance from the expected value. The probe localises the
# hand to a fraction of a degree; a larger residual means the clock did not advance as commanded.
ANGLE_TOLERANCE_DEG = 0.5

# Action the debug build listens on to move or reset the wallpaper's virtual clock.
DEBUG_ACTION = "io.github.godaniya.astronomicalclockswallpaper.DEBUG_SET_TIME"

# Bound every ADB call: a stalled transport would otherwise block the run forever, after a mutating
# command, and prevent control from reaching the `finally` that restores the device.
ADB_TIMEOUT_SECONDS = 30

# The restore path gets a longer budget than the calls it recovers from: it runs precisely when the
# transport is already slow or wedged, so it must not share the tight limit that triggered it.
ADB_RESTORE_TIMEOUT_SECONDS = 60

# `wm size` prints the physical size first and the active override, if any, after it. Anchoring and
# taking the last match avoids matching a line whose text merely contains the words.
OVERRIDE_SIZE_PATTERN = re.compile(r"^Override size:\s*(\d+x\d+)$")


def run_adb(args, serial=None, timeout=ADB_TIMEOUT_SECONDS):
    cmd = ["adb"]
    if serial:
        cmd.extend(["-s", serial])
    cmd.extend(args)
    res = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=timeout
    )
    return res.stdout


def list_devices():
    """
    Returns {serial: state} for every entry `adb devices` reports, with the header dropped.

    Each line is split on whitespace and the state token compared exactly. A substring test for
    "device" would also match a serial, a model, or an "unauthorized"/"offline" state.
    """
    output = run_adb(["devices"]).decode("utf-8")
    devices = {}
    for line in output.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2:
            devices[parts[0]] = parts[1]
    return devices


def select_target_serial(requested):
    """
    Resolves the one device to operate on, refusing to guess.

    Every later step mutates the device (wake, resize, virtual clock) and the device is shared, so
    an ambiguous list must not silently resolve to its first entry. Exits non-zero on any ambiguity.
    """
    devices = list_devices()
    active = [serial for serial, state in devices.items() if state == "device"]
    if requested is not None:
        if requested in active:
            return requested
        state = devices.get(requested, "not attached")
        active_text = ", ".join(active) if active else "none"
        print(
            f"ERROR: --serial {requested} is not an active device (state: {state}).",
            file=sys.stderr,
        )
        print(f"Active devices: {active_text}", file=sys.stderr)
        sys.exit(1)
    if len(active) == 1:
        return active[0]
    print(
        f"ERROR: expected exactly one active ADB device but found {len(active)}.",
        file=sys.stderr,
    )
    if active:
        print(f"Active devices: {', '.join(active)}", file=sys.stderr)
    inactive = [f"{serial} ({state})" for serial, state in devices.items() if state != "device"]
    if inactive:
        print(f"Attached but not ready: {', '.join(inactive)}", file=sys.stderr)
    print("Pass --serial to choose one.", file=sys.stderr)
    sys.exit(1)


def read_display_size(serial):
    """
    Returns the active `wm size` override as "WxH", or None when the physical size is in effect.

    Only an override needs restoring verbatim; with none, `wm size reset` is the correct restore,
    and a bare `Physical size:` line is not an override to put back.
    """
    output = run_adb(["shell", "wm", "size"], serial=serial).decode("utf-8")
    override = None
    for line in output.splitlines():
        match = OVERRIDE_SIZE_PATTERN.match(line.strip())
        if match:
            override = match.group(1)
    return override


def size_restore_command(override):
    """The `wm size` invocation that puts the display back to the size the run found."""
    if override:
        return ["shell", "wm", "size", override]
    return ["shell", "wm", "size", "reset"]


def restore_device(serial, size_override):
    """
    Best-effort reset of every setting the run changes, never raising.

    Called from a `finally`, so a failed step cannot leave the shared device resized or on virtual
    time. The display is restored to the override the run found, not unconditionally reset, so a
    pre-existing override is not discarded. A failing restore is reported without masking the
    original exception, which still propagates and keeps the run's non-zero exit code. Returns False
    if any restore command failed, so a pass that leaked device state is not reported as clean.
    """
    restored = True
    for command in (
        size_restore_command(size_override),
        ["shell", "am", "broadcast", "-a", DEBUG_ACTION, "--ez", "reset", "true"],
    ):
        try:
            run_adb(command, serial=serial, timeout=ADB_RESTORE_TIMEOUT_SECONDS)
        except (subprocess.SubprocessError, OSError) as error:
            restored = False
            print(f"WARNING: restore command failed: {error}", file=sys.stderr)
    return restored


def capture_frame(serial=None):
    raw = run_adb(["exec-out", "screencap"], serial=serial)
    if len(raw) < 16:
        raise RuntimeError("Failed to capture screencap; payload too small")
    width, height, fmt, _ = struct.unpack("<IIII", raw[:16])
    pixels = raw[16:]
    return width, height, pixels


def detect_hand_angle(width, height, pixels):
    """
    Locates hand pixels (DialStyle.HAND: #F4E5B8 -> ~235-255, 220-245, 175-205)
    and computes the principal angle from the dial center.
    """
    cx, cy = width / 2.0, height / 2.0
    # Search for hand pixels inside the dial region (radius 0.1 to 0.8 * min(w, h))
    max_radius = min(width, height) * 0.43
    min_radius = min(width, height) * 0.08
    min_r_sq = min_radius * min_radius
    max_r_sq = max_radius * max_radius

    hand_points = []
    # Sample every 2 pixels for speed
    row_stride = width * 4
    for y in range(int(cy - max_radius), int(cy + max_radius), 2):
        if y < 0 or y >= height:
            continue
        dy = y - cy
        row_offset = y * row_stride
        for x in range(int(cx - max_radius), int(cx + max_radius), 2):
            if x < 0 or x >= width:
                continue
            dx = x - cx
            dist_sq = dx * dx + dy * dy
            if min_r_sq <= dist_sq <= max_r_sq:
                px = row_offset + x * 4
                r = pixels[px]
                g = pixels[px + 1]
                b = pixels[px + 2]
                # DialStyle.HAND color matching
                if r >= 225 and g >= 210 and 165 <= b <= 215 and (r - b) >= 20:
                    hand_points.append((dx, dy))

    if len(hand_points) < 20:
        return None

    angles = [math.degrees(math.atan2(dx, -dy)) % 360.0 for dx, dy in hand_points]  # 0 at noon, clockwise

    # Coarse estimate: the densest 4-degree bin. The hand is a long straight stroke, so it dominates
    # any isolated cream-coloured glyph.
    bins = [0] * 90
    for a in angles:
        bins[int(a // 4.0) % 90] += 1
    coarse = (bins.index(max(bins)) + 0.5) * 4.0

    # Refine with only the pixels inside a narrow wedge around the coarse estimate, using a circular
    # mean, so stray pixels elsewhere cannot bias the result.
    sum_sin = 0.0
    sum_cos = 0.0
    kept = 0
    for a in angles:
        if abs((a - coarse + 180.0) % 360.0 - 180.0) <= 6.0:
            sum_sin += math.sin(math.radians(a))
            sum_cos += math.cos(math.radians(a))
            kept += 1
    if kept < 20:
        return None
    return math.degrees(math.atan2(sum_sin, sum_cos)) % 360.0


def main():
    parser = argparse.ArgumentParser(description="Automated live wallpaper device smoke test")
    parser.add_argument("-s", "--serial", help="ADB device serial", default=None)
    args = parser.parse_args()

    target_serial = select_target_serial(args.serial)
    print(f"Targeting ADB device: {target_serial}")

    # Device-time marker for the logcat filter below. Reading only entries newer than the run start
    # isolates this run's warnings without wiping the shared buffer, which `logcat -c` would do to
    # another session's evidence. The whole format string is one argv element because the device's
    # toybox `date` rejects splitting `+%m-%d` and `%H:%M:%S.000` into two arguments.
    log_start = run_adb(["shell", "date +'%m-%d %H:%M:%S.000'"], serial=target_serial).decode().strip()
    print(f"Logcat start marker: {log_start}")

    # A pre-existing override is put back verbatim rather than reset, so the run leaves the display
    # as it found it. Report it: an override leaked by another session would otherwise be silently
    # reproduced and read as this run's own state.
    size_override = read_display_size(target_serial)
    if size_override is not None:
        print(
            f"WARNING: display-size override {size_override} is already active; "
            "it will be restored as found, not reset",
            file=sys.stderr,
        )

    # Recreate the surface with a size that differs from the one in effect, so the resize is never a
    # no-op that passes without a recreation. An active 1080x2000 override is the one case where the
    # default target would coincide, so fall back to 1080x1800 there.
    recreate_size = "1080x1800" if size_override == "1080x2000" else "1080x2000"

    delta = residual = None
    angle2 = None
    restored = True
    # Steps 1 and 2 mutate the device (it is woken, and its debug clock is reset) before step 3, so
    # they run inside the try as well: with a bounded ADB timeout a stall can now raise from either,
    # and a raise here must still reach the finally that restores the device.
    try:
        # 1. Reset debug clock to baseline and show the home screen
        print("Waking the screen and showing the home screen...")
        run_adb(["shell", "input", "keyevent", "KEYCODE_WAKEUP"], serial=target_serial)
        run_adb(["shell", "input", "keyevent", "KEYCODE_HOME"], serial=target_serial)
        time.sleep(1.0)
        print("Resetting virtual clock...")
        run_adb(["shell", "am", "broadcast", "-a", DEBUG_ACTION, "--ez", "reset", "true"], serial=target_serial)
        time.sleep(0.5)

        # 2. Capture baseline frame t0
        print("Capturing baseline frame t0...")
        w0, h0, px0 = capture_frame(serial=target_serial)
        angle0 = detect_hand_angle(w0, h0, px0)
        if angle0 is not None:
            print(f"Baseline hand angle at t0: {angle0:.3f}°")
        else:
            print("Warning: Could not isolate hand pixels at t0 (wallpaper might be obstructed)")

        # 3. Advance virtual time by +30 minutes
        print("Advancing virtual time +30 minutes via debug broadcast...")
        start_t = time.time()
        run_adb(["shell", "am", "broadcast", "-a", DEBUG_ACTION,
                 "--el", "offset_minutes", "30"], serial=target_serial)
        elapsed = time.time() - start_t
        print(f"Time travel completed in {elapsed * 1000.0:.1f}ms")
        time.sleep(0.3)

        # 4. Capture frame t1 at +30 minutes
        print("Capturing frame t1 at +30m...")
        w1, h1, px1 = capture_frame(serial=target_serial)
        angle1 = detect_hand_angle(w1, h1, px1)
        if angle1 is not None:
            print(f"Hand angle at t1 (+30m): {angle1:.3f}°")
        if angle0 is not None and angle1 is not None:
            delta = (angle1 - angle0) % 360.0
            expected = 7.500  # 30 min on a 24h dial = 0.5 * 15 deg = 7.5 deg
            residual = delta - expected
            print(f"Observed angular advance: {delta:.3f}° (expected: {expected:.3f}°, residual: {residual:+.3f}°)")

        # 5. Test surface recreation
        print("Testing surface recreation...")
        run_adb(["shell", "wm", "size", recreate_size], serial=target_serial)
        time.sleep(0.5)
        run_adb(size_restore_command(size_override), serial=target_serial)
        time.sleep(0.5)
        w2, h2, px2 = capture_frame(serial=target_serial)
        angle2 = detect_hand_angle(w2, h2, px2)
    finally:
        # Restore on both the pass and the failure path, before any exception propagates, so a
        # failed run cannot strand the shared device resized or on virtual time. This also covers
        # the collect-results path, so a pass leaves the device as it was found.
        print("Restoring virtual clock and display size...")
        restored = restore_device(target_serial, size_override)

    # 6. Check renderer logs, isolated to the entries this run produced. Both renderer tags are
    # watched: the dial draw logs render failures under DialRenderer, so a filter on the service tag
    # alone can miss them and pass a run whose dial threw.
    logs = run_adb(["logcat", "-d", "-T", log_start, "-s",
                    "AstronomicalClocksWallpaperService:W", "DialRenderer:W"], serial=target_serial).decode("utf-8")
    warnings = [l for l in logs.splitlines() if l.strip() and not l.startswith("---------")]
    print(f"Renderer warnings check: {len(warnings)} unexpected warning(s)")

    failures = []
    if delta is None:
        failures.append("hand not found; wallpaper must be visible and unobstructed")
    elif abs(residual) > ANGLE_TOLERANCE_DEG:
        failures.append(f"hand advance residual {residual:+.3f}° exceeds ±{ANGLE_TOLERANCE_DEG}°")
    if angle2 is None:
        failures.append("hand not drawn after surface recreation")
    if warnings:
        failures.append(f"{len(warnings)} renderer warning(s) in logcat")
    if not restored:
        failures.append("device state was not fully restored; see the restore warnings above")

    print("\n--- Measured results (paste into docs/device-testing.md only if all pass) ---")
    today = time.strftime("%Y-%m-%d")
    print("| Date | Check | Observed |")
    print("| --- | --- | --- |")
    if delta is not None:
        print(f"| {today} | virtual time travel (+30m) | Hand advanced {delta:.3f}° against 7.500° expected, "
              f"residual {residual:+.3f}°; broadcast took {elapsed * 1000.0:.0f}ms |")
    recreated = "drawn" if angle2 is not None else "NOT found"
    restore_desc = f"`wm size {size_override}`" if size_override else "`wm size reset`"
    print(f"| {today} | surface recreation | `wm size {recreate_size}` then {restore_desc}; hand {recreated} afterwards |")
    print(f"| {today} | renderer log | {len(warnings)} warning(s) or error(s) from either renderer tag in logcat |")
    print("---------------------------------------------------------------------------\n")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        sys.exit(1)
    print("Smoke test passed.")


if __name__ == "__main__":
    main()
