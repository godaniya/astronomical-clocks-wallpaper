#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""
Automated physical-device smoke test harness for Astronomical Clock Wallpaper.

Exercises live wallpaper on an attached Android device via ADB:
- Virtual time travel (+30 minutes) via DEBUG_SET_TIME broadcast
- 24-hour hand angular advance verification (7.5 degrees per 30 minutes)
- Surface recreation (wm size), confirmed by reading the override back
- A verified debug-clock reset and a renderer log scan, which reports an empty scan as inconclusive
  rather than as a clean log
"""

import argparse
import subprocess
import sys
import time
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass

import device_layer

# Shared constants re-exported for module parity
ADB_RESTORE_TIMEOUT_SECONDS = device_layer.ADB_RESTORE_TIMEOUT_SECONDS
ADB_TIMEOUT_SECONDS = device_layer.ADB_TIMEOUT_SECONDS
ANGLE_TOLERANCE_DEG = device_layer.ANGLE_TOLERANCE_DEG
COARSE_BIN_COUNT = device_layer.COARSE_BIN_COUNT
COARSE_BIN_WIDTH_DEG = device_layer.COARSE_BIN_WIDTH_DEG
DARK_HAND_MIN_RED_MINUS_BLUE = device_layer.DARK_HAND_MIN_RED_MINUS_BLUE
DARK_HAND_RGB_BOUNDS = device_layer.DARK_HAND_RGB_BOUNDS
DARK_RIM_RGB = device_layer.DARK_RIM_RGB
DEBUG_ACTION = device_layer.DEBUG_ACTION
DEBUG_CLOCK_RESET_EXTRAS = device_layer.DEBUG_CLOCK_RESET_EXTRAS
DEBUG_CLOCK_RESET_MESSAGE = device_layer.DEBUG_CLOCK_RESET_MESSAGE
DISPLAY_STATE_PATTERN = device_layer.DISPLAY_STATE_PATTERN
EXPECTED_ADVANCE_12H_DEG = device_layer.EXPECTED_ADVANCE_12H_DEG
EXPECTED_ADVANCE_30M_DEG = device_layer.EXPECTED_ADVANCE_30M_DEG
FULL_TURN_DEG = device_layer.FULL_TURN_DEG
HALF_TURN_DEG = device_layer.HALF_TURN_DEG
HAND_MIN_SAMPLES = device_layer.HAND_MIN_SAMPLES
HAND_SCAN_INNER_FRACTION = device_layer.HAND_SCAN_INNER_FRACTION
HAND_SCAN_OUTER_FRACTION = device_layer.HAND_SCAN_OUTER_FRACTION
HAND_SCAN_STEP_PX = device_layer.HAND_SCAN_STEP_PX
KEYGUARD_SHOWING_PATTERN = device_layer.KEYGUARD_SHOWING_PATTERN
LIGHT_HAND_RGB_BOUNDS = device_layer.LIGHT_HAND_RGB_BOUNDS
LIGHT_RIM_RGB = device_layer.LIGHT_RIM_RGB
MIN_SPLIT_FIELDS = device_layer.MIN_SPLIT_FIELDS
OVERRIDE_SIZE_PATTERN = device_layer.OVERRIDE_SIZE_PATTERN
PACKAGE_NAME = device_layer.PACKAGE_NAME
PHYSICAL_SIZE_PATTERN = device_layer.PHYSICAL_SIZE_PATTERN
PIXEL_STRIDE = device_layer.PIXEL_STRIDE
REFINE_WEDGE_DEG = device_layer.REFINE_WEDGE_DEG
RIM_PROBE_BEARINGS_DEG = device_layer.RIM_PROBE_BEARINGS_DEG
RIM_PROBE_RADIUS_FRACTION = device_layer.RIM_PROBE_RADIUS_FRACTION
SCREENCAP_HEADER_BYTES = device_layer.SCREENCAP_HEADER_BYTES
SERVICE_LOG_TAG = device_layer.SERVICE_LOG_TAG
SERVICE_NAME = device_layer.SERVICE_NAME
WAKE_READ_PATTERN = device_layer.WAKE_READ_PATTERN
AdbDevice = device_layer.AdbDevice
ScreencapError = device_layer.ScreencapError
error_detail = device_layer.error_detail
captured_text = device_layer.captured_text
list_devices = device_layer.list_devices


# Dynamic wrappers ensuring mock patching on device_layer is immediately observed
def run_adb(args: Sequence[str], serial: str | None = None, timeout: int = ADB_TIMEOUT_SECONDS) -> bytes:
    """Run an adb invocation via device_layer."""
    return device_layer.run_adb(args, serial=serial, timeout=timeout)


def select_target_serial(requested: str | None) -> str:
    """Resolve target serial via device_layer."""
    return device_layer.select_target_serial(requested)


def read_display_size(serial: str) -> tuple[str | None, str | None]:
    """Read display sizes via device_layer."""
    return device_layer.read_display_size(serial)


def choose_recreate_size(physical: str | None, override: str | None) -> str:
    """Choose recreate size via device_layer."""
    return device_layer.choose_recreate_size(physical, override)


def size_restore_command(override: str | None) -> list[str]:
    """Get size restore command via device_layer."""
    return device_layer.size_restore_command(override)


def read_keyguard_locked(serial: str) -> bool | None:
    """Read keyguard state via device_layer."""
    return device_layer.read_keyguard_locked(serial)


def read_screen_on(serial: str) -> bool | None:
    """Read screen state via device_layer."""
    return device_layer.read_screen_on(serial)


def sleep_screen(serial: str) -> bool:
    """Sleep screen via device_layer."""
    return device_layer.sleep_screen(serial)


def run_restore_command(serial: str, command: Sequence[str]) -> bool:
    """Run restore command via device_layer."""
    return device_layer.run_restore_command(serial, command)


def count_service_log_messages(serial: str, message: str) -> int:
    """Count service log messages via device_layer."""
    return device_layer.count_service_log_messages(serial, message)


def send_debug_clock_broadcast(serial: str, extras: Sequence[str], expected_message: str) -> bool:
    """Send debug clock broadcast via device_layer."""
    return device_layer.send_debug_clock_broadcast(serial, extras, expected_message)


def confirm_virtual_clock_reset(serial: str) -> bool:
    """Confirm virtual clock reset via device_layer."""
    return device_layer.confirm_virtual_clock_reset(serial)


def capture_frame(serial: str | None = None) -> tuple[int, int, bytes]:
    """Capture screencap frame via device_layer."""
    return device_layer.capture_frame(serial=serial)


def rim_probe_points(width: int, height: int) -> Iterator[tuple[int, int]]:
    """Sample rim probe points via device_layer."""
    return device_layer.rim_probe_points(width, height)


def modal_pixel_rgb(width: int, pixels: bytes, points: Iterable[tuple[int, int]]) -> tuple[int, int, int] | None:
    """Find modal pixel RGB via device_layer."""
    return device_layer.modal_pixel_rgb(width, pixels, points)


def nearest_rim_rgb(rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    """Find nearest rim RGB literal via device_layer."""
    return device_layer.nearest_rim_rgb(rgb)


def is_dark_palette(width: int, height: int, pixels: bytes) -> bool:
    """Check dark palette via device_layer."""
    return device_layer.is_dark_palette(width, height, pixels)


def within_rgb_bounds(channels: tuple[int, int, int], bounds: tuple[tuple[int, int], ...]) -> bool:
    """Check RGB bounds via device_layer."""
    return device_layer.within_rgb_bounds(channels, bounds)


def is_dark_hand_pixel(red: int, green: int, blue: int) -> bool:
    """Check dark hand pixel via device_layer."""
    return device_layer.is_dark_hand_pixel(red, green, blue)


def is_light_hand_pixel(red: int, green: int, blue: int) -> bool:
    """Check light hand pixel via device_layer."""
    return device_layer.is_light_hand_pixel(red, green, blue)


def collect_hand_points(width: int, height: int, pixels: bytes, *, is_dark: bool) -> list[tuple[float, float]]:
    """Collect hand points via device_layer."""
    return device_layer.collect_hand_points(width, height, pixels, is_dark=is_dark)


def coarse_hand_angle(angles: Sequence[float]) -> float:
    """Calculate coarse hand angle via device_layer."""
    return device_layer.coarse_hand_angle(angles)


def refine_hand_angle(angles: Sequence[float], coarse_deg: float) -> float | None:
    """Refine hand angle via device_layer."""
    return device_layer.refine_hand_angle(angles, coarse_deg)


def detect_hand_angle(width: int, height: int, pixels: bytes) -> float | None:
    """Detect hand angle via device_layer."""
    return device_layer.detect_hand_angle(width, height, pixels)


@dataclass(frozen=True)
class SmokeBaseline:
    """The device state the run found, used to size and later restore every mutation."""

    serial: str
    log_start: str
    physical_size: str | None
    size_override: str | None
    screen_was_on: bool | None


@dataclass(frozen=True)
class SurfaceRecreation:
    """The applied override, phase restore verification, and hand angle after a verified restore."""

    override_was_active: bool
    restore_was_verified: bool
    hand_angle: float | None


@dataclass(frozen=True)
class AdvanceMeasurement:
    """The civil hand's measured advance across one debug-clock broadcast."""

    delta_deg: float
    residual_deg: float
    broadcast_ms: float


@dataclass(frozen=True)
class SmokeOutcome:
    """The measured results of one run, assembled into both the failure list and the report."""

    initial_reset_confirmed: bool
    measurement: AdvanceMeasurement | None
    recreation: SurfaceRecreation
    warnings: Sequence[str]
    log_collection_error: str | None = None


def verify_restored_state(serial: str, size_override: str | None, *, screen_was_on: bool | None) -> bool:
    """Re-read the mutated settings and report whether each returned to what the run found."""
    try:
        restored_physical_size, restored_size_override = read_display_size(serial)
        restored_screen_on = read_screen_on(serial) if screen_was_on is not None else None
        keyguard_locked = read_keyguard_locked(serial)
    except (subprocess.SubprocessError, OSError) as error:
        print(f"WARNING: could not verify restored device state: {error_detail(error)}", file=sys.stderr)
        return False

    restored = True
    if restored_physical_size is None:
        restored = False
        print("WARNING: could not read the display size after restore", file=sys.stderr)
    elif restored_size_override != size_override:
        restored = False
        print("WARNING: display size did not return to its initial state", file=sys.stderr)
    if restored_screen_on != screen_was_on:
        restored = False
        print("WARNING: screen state did not return to its initial state", file=sys.stderr)
    if keyguard_locked is not False:
        restored = False
        print("WARNING: device was not confirmed unlocked after the run", file=sys.stderr)
    return restored


def restore_device(serial: str, size_override: str | None, *, screen_was_on: bool | None) -> bool:
    """Best-effort reset of every setting the run changes, never raising."""
    restored = True
    commands = [size_restore_command(size_override)]
    for command in commands:
        if not run_restore_command(serial, command):
            restored = False
    if not confirm_virtual_clock_reset(serial):
        restored = False
    # Last, after the clock reset and display restore, so a failure among the earlier commands still attempts it.
    if screen_was_on is False and not sleep_screen(serial):
        restored = False
    if screen_was_on is None:
        restored = False
        print(
            "WARNING: initial screen state was unreadable; the screen cannot be reported as restored",
            file=sys.stderr,
        )
    if not verify_restored_state(serial, size_override, screen_was_on=screen_was_on):
        restored = False
    return restored


def step_reset_clock_and_show_home(serial: str) -> bool:
    """Wake the screen, dismiss the keyguard, show home, and confirm the debug clock reset."""
    print("Waking the screen and showing the home screen...")
    run_adb(["shell", "input", "keyevent", "KEYCODE_WAKEUP"], serial=serial)
    run_adb(["shell", "wm", "dismiss-keyguard"], serial=serial)
    run_adb(["shell", "input", "keyevent", "KEYCODE_HOME"], serial=serial)
    time.sleep(1.0)
    print("Resetting virtual clock...")
    confirmed = confirm_virtual_clock_reset(serial)
    time.sleep(0.5)
    return confirmed


def step_time_travel(serial: str) -> AdvanceMeasurement | None:
    """Capture the baseline hand, advance the debug clock by a confirmed 30 minutes, and measure it."""
    # Capture baseline frame t0
    print("Capturing baseline frame t0...")
    w0, h0, px0 = capture_frame(serial=serial)
    angle0 = detect_hand_angle(w0, h0, px0)
    if angle0 is not None:
        print(f"Baseline hand angle at t0: {angle0:.3f}°")
    else:
        print("Warning: Could not isolate hand pixels at t0 (wallpaper might be obstructed)")

    # Advance virtual time by +30 minutes
    print("Advancing virtual time +30 minutes via debug broadcast...")
    offset_message = "Debug clock offset set to 1800000ms"
    offset_before = count_service_log_messages(serial, offset_message)
    start_t = time.time()
    run_adb(["shell", "am", "broadcast", "-a", DEBUG_ACTION, "--el", "offset_minutes", "30"], serial=serial)
    broadcast_ms = (time.time() - start_t) * 1000.0
    print(f"Time travel completed in {broadcast_ms:.1f}ms")
    time.sleep(0.3)
    if count_service_log_messages(serial, offset_message) <= offset_before:
        print("ERROR: +30m time offset was not confirmed by the service log", file=sys.stderr)
        return None

    # Capture frame t1 at +30 minutes
    print("Capturing frame t1 at +30m...")
    w1, h1, px1 = capture_frame(serial=serial)
    angle1 = detect_hand_angle(w1, h1, px1)
    if angle1 is not None:
        print(f"Hand angle at t1 (+30m): {angle1:.3f}°")
    if angle0 is None or angle1 is None:
        return None

    delta = (angle1 - angle0) % FULL_TURN_DEG
    residual = delta - EXPECTED_ADVANCE_30M_DEG
    print(
        f"Observed angular advance: {delta:.3f}° "
        f"(expected: {EXPECTED_ADVANCE_30M_DEG:.3f}°, residual: {residual:+.3f}°)"
    )
    return AdvanceMeasurement(delta_deg=delta, residual_deg=residual, broadcast_ms=broadcast_ms)


def step_recreate_surface(serial: str, size_override: str | None, recreate_size: str) -> SurfaceRecreation:
    """Override the display size, restore it, and report whether it took effect and what was drawn."""
    print("Testing surface recreation...")
    run_adb(["shell", "wm", "size", recreate_size], serial=serial)
    time.sleep(0.5)
    _, active_override = read_display_size(serial)
    run_adb(size_restore_command(size_override), serial=serial)
    time.sleep(0.5)
    physical, restored_override = read_display_size(serial)
    if physical is None or restored_override != size_override:
        return SurfaceRecreation(
            override_was_active=active_override == recreate_size,
            restore_was_verified=False,
            hand_angle=None,
        )
    w2, h2, px2 = capture_frame(serial=serial)
    return SurfaceRecreation(
        override_was_active=active_override == recreate_size,
        restore_was_verified=True,
        hand_angle=detect_hand_angle(w2, h2, px2),
    )


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the harness's command-line interface."""
    parser = argparse.ArgumentParser(description="Automated live wallpaper device smoke test")
    parser.add_argument("-s", "--serial", help="ADB device serial", default=None)
    return parser


def read_baseline(requested_serial: str | None) -> SmokeBaseline:
    """Resolve the target and record the device state the run must put back afterwards."""
    target_serial = select_target_serial(requested_serial)
    print(f"Targeting ADB device: {target_serial}")

    log_start = run_adb(["shell", "date +'%m-%d %H:%M:%S.000'"], serial=target_serial).decode().strip()
    print(f"Logcat start marker: {log_start}")

    physical_size, size_override = read_display_size(target_serial)
    if physical_size is None:
        print(
            "ERROR: could not read the physical display size; refusing to change device state.",
            file=sys.stderr,
        )
        sys.exit(1)
    if size_override is not None:
        print(
            f"WARNING: display-size override {size_override} is already active; "
            "it will be restored as found, not reset",
            file=sys.stderr,
        )

    screen_was_on = read_screen_on(target_serial)
    if screen_was_on is None:
        print(
            "ERROR: could not read the initial screen state; refusing to wake the device.",
            file=sys.stderr,
        )
        sys.exit(1)

    keyguard_locked = read_keyguard_locked(target_serial)
    if keyguard_locked is None:
        print(
            "ERROR: could not read the keyguard state; refusing to run on an unconfirmed lock state.",
            file=sys.stderr,
        )
        sys.exit(1)
    if keyguard_locked:
        print("ERROR: device is locked; unlock it before running this smoke test.", file=sys.stderr)
        sys.exit(1)

    return SmokeBaseline(
        serial=target_serial,
        log_start=log_start,
        physical_size=physical_size,
        size_override=size_override,
        screen_was_on=screen_was_on,
    )


def scan_renderer_log(serial: str, log_start: str) -> list[str]:
    """Return this run's renderer warning records, isolated by the device-time marker."""
    logs = run_adb(
        ["logcat", "-d", "-T", log_start, "-s", f"{SERVICE_LOG_TAG}:W", "DialRenderer:W"],
        serial=serial,
    ).decode("utf-8")
    return [line for line in logs.splitlines() if line.strip() and not line.startswith("---------")]


def collect_failures(outcome: SmokeOutcome, *, restored: bool) -> list[str]:
    """Build the failure list from the measured outcome of the run."""
    failures = []
    if not outcome.initial_reset_confirmed:
        failures.append(
            "initial virtual-clock reset was not confirmed; time travel and surface recreation were skipped"
        )
    else:
        measurement = outcome.measurement
        recreation = outcome.recreation
        if measurement is None:
            failures.append("hand not found; wallpaper must be visible and unobstructed")
        elif abs(measurement.residual_deg) > ANGLE_TOLERANCE_DEG:
            failures.append(f"hand advance residual {measurement.residual_deg:+.3f}° exceeds ±{ANGLE_TOLERANCE_DEG}°")
        if not recreation.override_was_active:
            failures.append("display-size override was not active as requested")
        if not recreation.restore_was_verified:
            failures.append("display size was not verified after surface recreation restore")
        elif recreation.hand_angle is None:
            failures.append("hand not drawn after surface recreation")
    if outcome.log_collection_error is not None:
        failures.append(f"renderer log collection failed: {outcome.log_collection_error}")
    if outcome.warnings:
        failures.append(f"{len(outcome.warnings)} renderer warning(s) in logcat")
    if not restored:
        failures.append("device state was not fully restored; see the restore warnings above")
    return failures


def print_results(baseline: SmokeBaseline, recreate_size: str, outcome: SmokeOutcome) -> None:
    """Print the measured-results table a device report is assembled from."""
    print("\n--- Measured results (record in docs/testing/reports/ with APK/source attribution) ---")
    today = time.strftime("%Y-%m-%d")
    print("| Date | Check | Observed |")
    print("| --- | --- | --- |")
    if not outcome.initial_reset_confirmed:
        skip_note = "SKIPPED: initial virtual-clock reset was not confirmed by the service log"
        print(f"| {today} | virtual time travel (+30m) | {skip_note} |")
        print(f"| {today} | surface recreation | {skip_note} |")
    else:
        measurement = outcome.measurement
        recreation = outcome.recreation
        if measurement is not None:
            print(
                f"| {today} | virtual time travel (+30m) | "
                f"Hand advanced {measurement.delta_deg:.3f}° against {EXPECTED_ADVANCE_30M_DEG:.3f}° expected, "
                f"residual {measurement.residual_deg:+.3f}°; broadcast took {measurement.broadcast_ms:.0f}ms |"
            )
        recreated = "drawn" if recreation.hand_angle is not None else "NOT found"
        applied = "active as requested" if recreation.override_was_active else "NOT active as requested"
        verified = "verified" if recreation.restore_was_verified else "NOT verified"
        restore_desc = f"`wm size {baseline.size_override}`" if baseline.size_override else "`wm size reset`"
        effective_size = baseline.size_override or baseline.physical_size or "unknown"
        print(
            f"| {today} | surface recreation | effective {effective_size}, `wm size {recreate_size}` "
            f"({applied}) then {restore_desc} ({verified}); hand {recreated} afterwards |"
        )
    if outcome.log_collection_error is not None:
        log_row = f"FAILED: renderer log collection failed: {outcome.log_collection_error}"
    elif outcome.warnings:
        log_row = f"{len(outcome.warnings)} warning(s) or error(s) from either renderer tag in logcat"
    else:
        log_row = "Inconclusive: no matching warning records; rendering was not verified"
    print(f"| {today} | renderer log | {log_row} |")
    print("---------------------------------------------------------------------------\n")


def finish_run(failures: Sequence[str], *, log_scan_inconclusive: bool) -> None:
    """Exit non-zero when any check failed, or report the pass and what it did not establish."""
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        sys.exit(1)
    if log_scan_inconclusive:
        print("Smoke test passed; renderer log scan was inconclusive.")
    else:
        print("Smoke test passed.")


def main() -> None:
    """Reset the clock, advance it, recreate the surface, restore the device, and report."""
    args = build_argument_parser().parse_args()
    baseline = read_baseline(args.serial)
    recreate_size = choose_recreate_size(baseline.physical_size, baseline.size_override)

    measurement: AdvanceMeasurement | None = None
    recreation = SurfaceRecreation(override_was_active=False, restore_was_verified=False, hand_angle=None)
    restored = True
    initial_reset_confirmed = False

    try:
        initial_reset_confirmed = step_reset_clock_and_show_home(baseline.serial)
        if initial_reset_confirmed:
            measurement = step_time_travel(baseline.serial)
            recreation = step_recreate_surface(baseline.serial, baseline.size_override, recreate_size)
        else:
            print(
                "ERROR: initial virtual-clock reset was not confirmed; "
                "skipping time travel and surface recreation checks.",
                file=sys.stderr,
            )
    finally:
        print("Restoring virtual clock, display size, and screen state...")
        restored = restore_device(baseline.serial, baseline.size_override, screen_was_on=baseline.screen_was_on)

    log_collection_error = None
    try:
        warnings = scan_renderer_log(baseline.serial, baseline.log_start)
    except (subprocess.SubprocessError, OSError) as error:
        warnings = []
        log_collection_error = error_detail(error)
    if log_collection_error is not None:
        print(f"Renderer log collection failed: {log_collection_error}", file=sys.stderr)
    elif warnings:
        print(f"Renderer warnings check: {len(warnings)} unexpected warning(s)")
    else:
        print("Renderer log scan inconclusive: no matching warning records.")

    outcome = SmokeOutcome(
        initial_reset_confirmed=initial_reset_confirmed,
        measurement=measurement,
        recreation=recreation,
        warnings=warnings,
        log_collection_error=log_collection_error,
    )
    failures = collect_failures(outcome, restored=restored)
    print_results(baseline, recreate_size, outcome)
    finish_run(failures, log_scan_inconclusive=log_collection_error is None and not warnings)


if __name__ == "__main__":
    main()
