#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""
Run observable live-wallpaper checks on one physical Android device via ADB.

This harness does not measure battery or CPU usage, count successful frames while hidden, inspect
engine cleanup, or verify persisted settings after process recreation.
"""

import argparse
import subprocess
import sys
import time
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from typing import Final

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


def read_night_mode(serial: str) -> str | None:
    """Read night mode setting via device_layer."""
    return device_layer.read_night_mode(serial)


def get_wallpaper_pid(serial: str) -> int | None:
    """Get wallpaper pid via device_layer."""
    return device_layer.get_wallpaper_pid(serial)


def sleep_screen(serial: str) -> bool:
    """Sleep screen via device_layer."""
    return device_layer.sleep_screen(serial)


def wake_screen(serial: str) -> bool:
    """Wake screen via device_layer."""
    return device_layer.wake_screen(serial)


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


REBIND_POLL_COUNT: Final = 10
REBIND_POLL_SECONDS: Final = 0.5
PSS_SAMPLE_SECONDS: Final = 10.0


@dataclass(frozen=True)
class DeviceBaseline:
    """The device state the run found, used to size and later restore every mutation."""

    serial: str
    run_start_marker: str
    physical_size: str
    size_override: str | None
    screen_was_on: bool
    night_mode: str
    wallpaper_pid: int


def non_negative_int(value: str) -> int:
    """Parse a command-line integer, rejecting anything below zero."""
    parsed = int(value)
    if parsed < 0:
        message = "must be zero or greater"
        raise argparse.ArgumentTypeError(message)
    return parsed


def extract_total_pss_kb(mem_output: str) -> int | None:
    """Return the TOTAL row's kB figure from `dumpsys meminfo`, or None when it is absent."""
    for line in mem_output.splitlines():
        parts = line.split()
        if len(parts) >= MIN_SPLIT_FIELDS and parts[0] == "TOTAL" and parts[1].isdigit():
            return int(parts[1])
    return None


def evaluate_pss_growth(pss_before: int | None, pss_after: int | None, max_growth_kb: int) -> tuple[int, bool] | None:
    """Return (growth, within budget) for two PSS samples, or None when either is missing."""
    if pss_before is None or pss_after is None:
        return None
    growth_kb = pss_after - pss_before
    return growth_kb, growth_kb <= max_growth_kb


def matching_renderer_warnings(output: str) -> list[str]:
    """Keep the logcat lines that are records, dropping blanks and the `---------` separators."""
    return [line for line in output.splitlines() if line.strip() and not line.startswith("---------")]


def restore_commands(size_override: str | None, initial_night_mode: str | None) -> list[list[str]]:
    """Build the ordered commands that put every mutated setting back."""
    commands = [
        ["shell", "input", "keyevent", "KEYCODE_WAKEUP"],
        size_restore_command(size_override),
    ]
    if initial_night_mode is not None:
        commands.insert(2, ["shell", "cmd", "uimode", "night", initial_night_mode])
    commands.append(["shell", "input", "keyevent", "KEYCODE_HOME"])
    return commands


def verify_restored_state(
    serial: str,
    size_override: str | None,
    *,
    initial_screen_was_on: bool | None,
    initial_night_mode: str | None,
) -> bool:
    """Re-read the mutated settings and report whether each returned to what the run found."""
    try:
        restored_physical_size, restored_size_override = read_display_size(serial)
        restored_night_mode = read_night_mode(serial) if initial_night_mode is not None else None
        restored_screen_on = read_screen_on(serial) if initial_screen_was_on is not None else None
        restored_keyguard_locked = read_keyguard_locked(serial)
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
    if restored_night_mode != initial_night_mode:
        restored = False
        print("WARNING: night mode did not return to its initial state", file=sys.stderr)
    if restored_screen_on != initial_screen_was_on:
        restored = False
        print("WARNING: screen state did not return to its initial state", file=sys.stderr)
    if restored_keyguard_locked is not False:
        restored = False
        print("WARNING: device was not confirmed unlocked after the run", file=sys.stderr)
    return restored


def restore_device(
    serial: str,
    size_override: str | None,
    *,
    initial_screen_was_on: bool | None,
    initial_night_mode: str | None,
) -> bool:
    """Restore every mutated setting and report whether the result could be verified."""
    restored = True
    if initial_night_mode is None:
        restored = False
        print("WARNING: initial night mode was unknown; it cannot be restored", file=sys.stderr)
    if initial_screen_was_on is None:
        restored = False
        print("WARNING: initial screen state was unknown; it cannot be restored", file=sys.stderr)

    for command in restore_commands(size_override, initial_night_mode):
        if not run_restore_command(serial, command):
            restored = False
    if not confirm_virtual_clock_reset(serial):
        restored = False
    if initial_screen_was_on is False and not sleep_screen(serial):
        restored = False
    if not verify_restored_state(
        serial,
        size_override,
        initial_screen_was_on=initial_screen_was_on,
        initial_night_mode=initial_night_mode,
    ):
        restored = False
    return restored


def phase_environment_setup(serial: str, failures: list[str]) -> bool:
    """Wake the device, dismiss the keyguard, show home, and confirm the debug-clock reset."""
    print("\n--- Phase 0: Environment Wake & Unlocking ---")
    run_adb(["shell", "input", "keyevent", "KEYCODE_WAKEUP"], serial=serial)
    run_adb(["shell", "wm", "dismiss-keyguard"], serial=serial)
    run_adb(["shell", "input", "keyevent", "KEYCODE_HOME"], serial=serial)
    time.sleep(1.0)
    confirmed = send_debug_clock_broadcast(serial, DEBUG_CLOCK_RESET_EXTRAS, DEBUG_CLOCK_RESET_MESSAGE)
    if not confirmed:
        failures.append("Environment reset broadcast was not confirmed by the service log")
    time.sleep(0.5)
    return confirmed


def phase_baseline_capture(serial: str, results: list[tuple[str, str]], failures: list[str]) -> None:
    """Capture one frame and locate the civil hand before any mutating phase."""
    w0, h0, px0 = capture_frame(serial=serial)
    palette_mode = "Dark" if is_dark_palette(w0, h0, px0) else "Light"
    angle0 = detect_hand_angle(w0, h0, px0)
    print(f"Detected dial palette: {palette_mode}")
    if angle0 is not None:
        print(f"Baseline hand angle t0: {angle0:.3f}°")
        results.append(("visible dial baseline", f"Dial rendered ({palette_mode} palette), hand at {angle0:.3f}°"))
    else:
        failures.append("Hand not found at baseline t0")


def phase_screen_off_wake(serial: str, results: list[tuple[str, str]], failures: list[str]) -> None:
    """Sleep the screen, wake it, and confirm the hand is rendered again."""
    print("\n--- Phase 1: Screen-Off / Wake Navigation ---")
    run_adb(["shell", "input", "keyevent", "KEYCODE_SLEEP"], serial=serial)
    time.sleep(4.0)
    screen_went_off = read_screen_on(serial) is False

    # Wake device back up
    run_adb(["shell", "input", "keyevent", "KEYCODE_WAKEUP"], serial=serial)
    run_adb(["shell", "wm", "dismiss-keyguard"], serial=serial)
    run_adb(["shell", "input", "keyevent", "KEYCODE_HOME"], serial=serial)
    time.sleep(1.0)

    screen_is_on = read_screen_on(serial) is True
    w_wake, h_wake, px_wake = capture_frame(serial=serial)
    angle_wake = detect_hand_angle(w_wake, h_wake, px_wake)

    if screen_went_off and screen_is_on and angle_wake is not None:
        print(f"Screen-off state observed; hand visible within 1s of wake at {angle_wake:.3f}°.")
        results.append(
            (
                "screen-off / wake navigation",
                (
                    f"device reported screen off for 4s; hand visible within 1s of wake at {angle_wake:.3f}°; "
                    "rendering while asleep was not measured"
                ),
            )
        )
    else:
        failures.append(
            f"Screen-off / wake navigation failed "
            f"(screen_off={screen_went_off}, screen_on_after_wake={screen_is_on}, hand={angle_wake})"
        )


def phase_preview_navigation(serial: str, results: list[tuple[str, str]], failures: list[str]) -> None:
    """Open the live-wallpaper preview, back out, and confirm the home hand renders."""
    print("\n--- Phase 2: Preview Navigation ---")
    preview_start = run_adb(
        [
            "shell",
            "am",
            "start",
            "-a",
            "android.service.wallpaper.CHANGE_LIVE_WALLPAPER",
            "-W",
            "--ecn",
            "android.service.wallpaper.extra.LIVE_WALLPAPER_COMPONENT",
            SERVICE_NAME,
        ],
        serial=serial,
    ).decode("utf-8")
    preview_started = "Status: ok" in preview_start
    if not preview_started:
        failures.append("Wallpaper preview did not report a successful launch")
    time.sleep(2.0)

    # Back out of preview to home
    run_adb(["shell", "input", "keyevent", "KEYCODE_BACK"], serial=serial)
    time.sleep(0.8)
    run_adb(["shell", "input", "keyevent", "KEYCODE_HOME"], serial=serial)
    time.sleep(1.0)

    w_preview_back, h_preview_back, px_preview_back = capture_frame(serial=serial)
    angle_post_preview = detect_hand_angle(w_preview_back, h_preview_back, px_preview_back)

    if preview_started and angle_post_preview is not None:
        print(f"Returned from preview; hand visible on home screen at {angle_post_preview:.3f}°.")
        results.append(
            (
                "preview navigation",
                (
                    f"returned to home and detected the active wallpaper hand at {angle_post_preview:.3f}°; "
                    "preview-engine cleanup was not inspected"
                ),
            )
        )
    elif preview_started:
        failures.append("Hand missing after preview close")


def phase_surface_recreation(
    serial: str,
    size_override: str | None,
    recreate_size: str,
    results: list[tuple[str, str]],
    failures: list[str],
) -> None:
    """Override the display size and restore it, confirming the dial is redrawn."""
    print("\n--- Phase 3: Surface Recreation ---")
    run_adb(["shell", "wm", "size", recreate_size], serial=serial)
    time.sleep(0.5)
    _, active_override = read_display_size(serial)
    run_adb(size_restore_command(size_override), serial=serial)
    time.sleep(0.8)
    physical, restored_override = read_display_size(serial)
    if physical is None or restored_override != size_override:
        failures.append("Display size was not verified after surface recreation restore")
        return

    w_recreate, h_recreate, px_recreate = capture_frame(serial=serial)
    angle_recreate = detect_hand_angle(w_recreate, h_recreate, px_recreate)
    if active_override != recreate_size:
        failures.append(f"Display-size override was not active as requested ({active_override})")
    elif angle_recreate is not None:
        print(f"Surface recreated via {recreate_size}; hand rendered at {angle_recreate:.3f}°")
        results.append(
            (
                "surface recreation",
                (
                    f"Override to {recreate_size} and verified restore to {size_override or 'physical size'} "
                    f"redrew dial; hand at {angle_recreate:.3f}°"
                ),
            )
        )
    else:
        failures.append("Hand not drawn after surface recreation")


def phase_process_rebind(serial: str, results: list[tuple[str, str]], failures: list[str]) -> None:
    """Kill the wallpaper process as its own uid and observe a rebound PID with a drawn hand."""
    print("\n--- Phase 4: Process Recreation (kill -9 simulation) ---")
    pid_before = get_wallpaper_pid(serial)
    pid_after: int | None = None
    angle_post_kill: float | None = None
    if pid_before is None:
        failures.append("Wallpaper process was not running before the process-recreation check")
    else:
        run_adb(["shell", "run-as", PACKAGE_NAME, "kill", "-9", str(pid_before)], serial=serial)
        for _ in range(REBIND_POLL_COUNT):
            time.sleep(REBIND_POLL_SECONDS)
            curr_pid = get_wallpaper_pid(serial)
            if curr_pid is not None and curr_pid != pid_before:
                pid_after = curr_pid
                w_kill, h_kill, px_kill = capture_frame(serial=serial)
                angle_post_kill = detect_hand_angle(w_kill, h_kill, px_kill)
                if angle_post_kill is not None:
                    break
        print(f"PID transition: {pid_before} -> {pid_after}")

        if pid_after is not None and pid_after != pid_before and angle_post_kill is not None:
            results.append(
                (
                    "process rebind",
                    (
                        f"new PID observed within {REBIND_POLL_COUNT} polls at {REBIND_POLL_SECONDS}s intervals; "
                        f"hand visible at {angle_post_kill:.3f}°; saved preference values were not inspected"
                    ),
                )
            )
        else:
            failures.append(f"Process recreation failed (PIDs: {pid_before} -> {pid_after}, angle={angle_post_kill})")


def measure_hand_advance(serial: str, offset_args: Sequence[str], expected_message: str) -> tuple[bool, float | None]:
    """Advance the virtual clock by one debug offset, returning (confirmed, hand angle after)."""
    if not send_debug_clock_broadcast(serial, offset_args, expected_message):
        return False, None
    time.sleep(0.3)
    w_after, h_after, px_after = capture_frame(serial=serial)
    return True, detect_hand_angle(w_after, h_after, px_after)


def phase_time_travel(serial: str, results: list[tuple[str, str]], failures: list[str]) -> None:
    """Advance the virtual clock +30m then +12h and compare the measured hand advance."""
    print("\n--- Phase 5: Virtual Time Travel (+30m, +12h) ---")
    if not send_debug_clock_broadcast(serial, DEBUG_CLOCK_RESET_EXTRAS, DEBUG_CLOCK_RESET_MESSAGE):
        failures.append("Time-travel baseline reset was not confirmed by the service log")
        return
    time.sleep(0.8)

    w_base, h_base, px_base = capture_frame(serial=serial)
    a_base = detect_hand_angle(w_base, h_base, px_base)

    # Advance +30 minutes
    confirmed_30m, a_30m = measure_hand_advance(
        serial, ["--el", "offset_minutes", "30"], "Debug clock offset set to 1800000ms"
    )
    if not confirmed_30m:
        failures.append("+30m time offset was not confirmed by the service log")

    # Advance +12 hours
    confirmed_12h, a_12h = measure_hand_advance(
        serial, ["--el", "offset_hours", "12"], "Debug clock offset set to 43200000ms"
    )
    if not confirmed_12h:
        failures.append("+12h time offset was not confirmed by the service log")

    if a_base is not None and a_30m is not None and a_12h is not None:
        delta_30m = (a_30m - a_base) % FULL_TURN_DEG
        res_30m = delta_30m - EXPECTED_ADVANCE_30M_DEG
        delta_12h = (a_12h - a_base) % FULL_TURN_DEG
        res_12h = delta_12h - EXPECTED_ADVANCE_12H_DEG

        print(f"+30m advance: {delta_30m:.3f}° (expected: {EXPECTED_ADVANCE_30M_DEG:.3f}°, residual: {res_30m:+.3f}°)")
        print(f"+12h advance: {delta_12h:.3f}° (expected: {EXPECTED_ADVANCE_12H_DEG:.3f}°, residual: {res_12h:+.3f}°)")

        if abs(res_30m) <= ANGLE_TOLERANCE_DEG and abs(res_12h) <= ANGLE_TOLERANCE_DEG:
            results.append(
                (
                    "time travel (+30m, +12h)",
                    (
                        f"+30m moved hand {delta_30m:.3f}° (residual {res_30m:+.3f}°); "
                        f"+12h moved {delta_12h:.3f}° (residual {res_12h:+.3f}°)"
                    ),
                )
            )
        else:
            failures.append(f"Angle residuals exceeded tolerance: 30m={res_30m:+.3f}°, 12h={res_12h:+.3f}°")
    else:
        failures.append("Hand angle missing during time travel")


def phase_total_pss_growth(
    serial: str, max_pss_growth_kb: int, results: list[tuple[str, str]], failures: list[str]
) -> None:
    """Sample total PSS ten seconds apart and compare the growth against the supplied budget."""
    print("\n--- Phase 6: Total PSS Growth ---")
    if not send_debug_clock_broadcast(serial, DEBUG_CLOCK_RESET_EXTRAS, DEBUG_CLOCK_RESET_MESSAGE):
        failures.append("PSS baseline reset was not confirmed by the service log")
        return
    time.sleep(0.5)

    mem_before = run_adb(["shell", "dumpsys", "meminfo", PACKAGE_NAME], serial=serial).decode("utf-8")
    time.sleep(PSS_SAMPLE_SECONDS)
    mem_after = run_adb(["shell", "dumpsys", "meminfo", PACKAGE_NAME], serial=serial).decode("utf-8")

    pss_before = extract_total_pss_kb(mem_before)
    pss_after = extract_total_pss_kb(mem_after)
    pss_result = evaluate_pss_growth(pss_before, pss_after, max_pss_growth_kb)
    if pss_result is None:
        failures.append("Could not parse total PSS from both memory samples")
        print(f"PSS sample before:\n{mem_before}", file=sys.stderr)
        print(f"PSS sample after:\n{mem_after}", file=sys.stderr)
    else:
        pss_growth, within_budget = pss_result
        print(
            f"Total PSS: {pss_before} kB -> {pss_after} kB (growth {pss_growth:+d} kB; budget {max_pss_growth_kb} kB)"
        )
        if not within_budget:
            failures.append(f"Total PSS growth {pss_growth} kB exceeded the {max_pss_growth_kb} kB budget")
        else:
            results.append(
                (
                    "total PSS sample",
                    (
                        f"{pss_before} -> {pss_after} kB over {PSS_SAMPLE_SECONDS:.0f}s "
                        f"(growth {pss_growth:+d} kB; budget {max_pss_growth_kb} kB); not battery or CPU evidence"
                    ),
                )
            )


def phase_palette_adaptation(
    serial: str, initial_night_mode: str, results: list[tuple[str, str]], failures: list[str]
) -> None:
    """Toggle night mode and verify hand visibility across palette transitions."""
    print("\n--- Phase: Palette Adaptation ---")
    target_mode = "yes" if initial_night_mode != "yes" else "no"
    run_adb(["shell", "cmd", "uimode", "night", target_mode], serial=serial)
    time.sleep(1.0)
    w_pal, h_pal, px_pal = capture_frame(serial=serial)
    angle_pal = detect_hand_angle(w_pal, h_pal, px_pal)
    # Restore mode
    run_adb(["shell", "cmd", "uimode", "night", initial_night_mode], serial=serial)
    time.sleep(0.5)
    if angle_pal is not None:
        results.append(("palette adaptation", f"hand detected at {angle_pal:.3f}° in night mode {target_mode}"))
    else:
        failures.append(f"Hand not found after night mode toggle to {target_mode}")


def phase_battery_baseline(serial: str, results: list[tuple[str, str]], failures: list[str]) -> None:
    """Check battery stats baseline availability."""
    print("\n--- Phase: Battery Baseline ---")
    try:
        run_adb(["shell", "dumpsys", "batterystats", "--reset"], serial=serial)
        results.append(("battery baseline", "batterystats reset successfully"))
    except (subprocess.SubprocessError, OSError) as error:
        failures.append(f"Failed to reset batterystats: {error_detail(error)}")


def phase_renderer_log_scan(
    serial: str, run_start_marker: str, results: list[tuple[str, str]], failures: list[str]
) -> bool:
    """Scan the run's renderer log lines and append the outcome to the results."""
    print("\n--- Phase 7: Renderer Log Scan ---")
    log_scan_inconclusive = False
    try:
        log_check = run_adb(
            ["logcat", "-d", "-T", run_start_marker, "-s", f"{SERVICE_LOG_TAG}:W", "DialRenderer:W"], serial=serial
        ).decode("utf-8")
        warnings = matching_renderer_warnings(log_check)
        if not warnings:
            log_scan_inconclusive = True
            log_result = "Inconclusive: no matching warning records; rendering was not verified"
            print("Renderer log scan inconclusive: no matching warning records.")
        else:
            log_result = f"{len(warnings)} matching warning/error record(s)"
            print(f"Renderer warning/error scan: {len(warnings)} record(s)")
            failures.append(f"{len(warnings)} unexpected warning(s) in logcat")
        results.append(("renderer log scan", log_result))
    except (subprocess.SubprocessError, OSError) as error:
        failures.append(f"Renderer log scan could not be collected: {error_detail(error)}")
        results.append(("renderer log scan", f"Failed to collect: {error_detail(error)}"))
        print(f"Renderer log scan failed: {error_detail(error)}", file=sys.stderr)
    return log_scan_inconclusive


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the harness's command-line interface."""
    parser = argparse.ArgumentParser(description="Astronomical Clock Wallpaper Device Checks (#6)")
    parser.add_argument("-s", "--serial", help="Target ADB serial", default=None)
    parser.add_argument(
        "--max-pss-growth-kb",
        type=non_negative_int,
        required=True,
        help="Agreed maximum total-PSS growth over the 10-second sample, in kB",
    )
    return parser


def read_device_baseline(requested_serial: str | None) -> DeviceBaseline:
    """Inspect the device before any mutation, exiting when a precondition cannot be read."""
    serial = select_target_serial(requested_serial)
    print(f"=== Starting Device Checks on target: {serial} ===")
    try:
        run_start_marker = run_adb(["shell", "date +'%m-%d %H:%M:%S.000'"], serial=serial).decode().strip()
        print(f"Run start timestamp: {run_start_marker}")
        physical_size, size_override = read_display_size(serial)
        screen_was_on = read_screen_on(serial)
        night_mode = read_night_mode(serial)
        keyguard_locked = read_keyguard_locked(serial)
        pid_start = get_wallpaper_pid(serial)
    except (subprocess.SubprocessError, OSError) as error:
        print(
            f"ERROR: Could not inspect the device before making changes: {error_detail(error)}",
            file=sys.stderr,
        )
        sys.exit(1)

    if physical_size is None:
        print("ERROR: could not read the physical display size; refusing to change device state.", file=sys.stderr)
        sys.exit(1)
    if screen_was_on is None:
        print("ERROR: could not read the initial screen state; refusing to wake the device.", file=sys.stderr)
        sys.exit(1)
    if night_mode is None:
        print("ERROR: could not read the initial night mode; refusing to change device state.", file=sys.stderr)
        sys.exit(1)

    if keyguard_locked is None:
        print(
            "ERROR: could not read the keyguard state; refusing to run on an unconfirmed lock state.",
            file=sys.stderr,
        )
        sys.exit(1)
    if keyguard_locked:
        print("ERROR: device is locked; unlock it before running device checks.", file=sys.stderr)
        sys.exit(1)

    print(f"Initial wallpaper PID: {pid_start}")
    if pid_start is None:
        print("ERROR: Wallpaper service is not running. Apply wallpaper before qualification.", file=sys.stderr)
        sys.exit(1)

    return DeviceBaseline(
        serial=serial,
        run_start_marker=run_start_marker,
        physical_size=physical_size,
        size_override=size_override,
        screen_was_on=screen_was_on,
        night_mode=night_mode,
        wallpaper_pid=pid_start,
    )


# Alias for backward compatibility
read_baseline = read_device_baseline


def print_check_report(results: list[tuple[str, str]]) -> None:
    """Print the results table a device report is assembled from."""
    print("\n=======================================================")
    print("              PHYSICAL-DEVICE CHECK REPORT             ")
    print("=======================================================")
    print("| Date | Check | Observed |")
    print("| --- | --- | --- |")
    today = time.strftime("%Y-%m-%d")
    for check, observed in results:
        print(f"| {today} | {check} | {observed} |")
    print("=======================================================\n")


def finish_run(results: list[tuple[str, str]], failures: list[str], *, log_scan_inconclusive: bool) -> None:
    """Print the report and exit non-zero when any check failed."""
    print_check_report(results)
    if failures:
        print("DEVICE CHECK FAILURES:", file=sys.stderr)
        for failure in failures:
            print(f"  - FAIL: {failure}", file=sys.stderr)
        sys.exit(1)
    if log_scan_inconclusive:
        print("Configured checks passed; renderer log scan was inconclusive.")
    else:
        print("ALL CONFIGURED DEVICE CHECKS PASSED.")


def main() -> None:
    """Inspect the device, run every check phase, restore the device, and report."""
    args = build_argument_parser().parse_args()
    baseline = read_device_baseline(args.serial)
    recreate_size = choose_recreate_size(baseline.physical_size, baseline.size_override)
    serial = baseline.serial

    results: list[tuple[str, str]] = []
    failures: list[str] = []
    restored = True
    current_phase = "environment setup"

    try:
        current_phase = "environment setup"
        reset_confirmed = phase_environment_setup(serial, failures)

        if reset_confirmed:
            current_phase = "baseline capture"
            phase_baseline_capture(serial, results, failures)

            current_phase = "screen-off / wake navigation"
            phase_screen_off_wake(serial, results, failures)

            current_phase = "preview navigation"
            phase_preview_navigation(serial, results, failures)

            current_phase = "surface recreation"
            phase_surface_recreation(serial, baseline.size_override, recreate_size, results, failures)

            current_phase = "process rebind"
            phase_process_rebind(serial, results, failures)

            current_phase = "virtual time travel"
            phase_time_travel(serial, results, failures)

            current_phase = "total PSS growth"
            phase_total_pss_growth(serial, args.max_pss_growth_kb, results, failures)
        else:
            print("Skipping phases 1-6: environment reset was not confirmed.", file=sys.stderr)

    except (subprocess.SubprocessError, OSError, RuntimeError) as error:
        failures.append(f"Run aborted during {current_phase}: {error_detail(error)}")
    finally:
        print("\n--- Restoring device state in finally block ---")
        restored = restore_device(
            serial,
            baseline.size_override,
            initial_screen_was_on=baseline.screen_was_on,
            initial_night_mode=baseline.night_mode,
        )
    if not restored:
        failures.append("Device restoration failed or could not be verified")

    current_phase = "renderer log scan"
    log_scan_inconclusive = phase_renderer_log_scan(serial, baseline.run_start_marker, results, failures)

    finish_run(results, failures, log_scan_inconclusive=log_scan_inconclusive)


if __name__ == "__main__":
    main()
