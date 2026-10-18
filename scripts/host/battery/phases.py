# SPDX-License-Identifier: Apache-2.0
"""Windowed battery measurement phases (`resources`, `hidden`, `visible`, `memory`, `pilot`)."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Final

from host import contract
from host.battery import probes, stats
from host.battery import snapshot as battery_snapshot
from host.device import probes as device_probes

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

# The launcher takes a moment to come forward after KEYCODE_HOME, so the readback that the home
# screen is in front is bounded exactly the way the service-log confirmations in `host.device.probes` are:
# five reads half a second apart, which covers the transition without holding the phase open.
HOME_CONFIRM_ATTEMPTS: Final = 5

HOME_CONFIRM_INTERVAL_SECONDS: Final = 0.5

SAMPLE_INTERVAL_SECONDS: Final = 30.0

# The longest a measurement window will hold the shared device, and the longest a pilot invocation —
# which is a run of windows rather than one — will. Both are read off `docs/battery-budget.md`, which
# requires that "no single invocation, and above all no single window, blocks for hours": the longest
# criterion its matrix documents is thirty minutes, so a window is bounded at forty-five, and the
# recorded six-pair pilot took ninety minutes, so an invocation is bounded at two hours. A bound is
# needed at all because a finite duration passes every test arithmetic can pose — `1e15` minutes is
# finite, positive, and one the sampling loop makes progress through — so neither finiteness nor
# progress is what makes a phase bounded.
MAXIMUM_WINDOW_MINUTES: Final = 45.0

MAXIMUM_PILOT_MINUTES: Final = 120.0

# The count the pilot will accept. It cannot bound the invocation on its own — a count at the floor
# with a window at the ceiling is far past the time bound — so `phase_pilot` checks the product as
# well; this is what bounds the rates and CPU lists the run accumulates, and what refuses an absurd
# count at the command line rather than after the device has been reached.
MAXIMUM_PILOT_RUNS: Final = int(MAXIMUM_PILOT_MINUTES // stats.MINIMUM_WINDOW_MINUTES)


def verify_arm(device: device_probes.AdbDevice, arm: stats.Arm, baseline: stats.Baseline | None) -> str:
    """
    Refuse a window whose device does not match the arm it is about to be recorded against.

    The component is the fact that decides the arm, and it is decidable: the home slot names the live
    service when the app is bound and the platform's static engine when it is not. Arm B therefore
    requires the platform engine by name rather than accepting anything that is not this app's
    service — a third-party live wallpaper satisfies "not this app" and would be recorded as the
    stock or black baseline. Which *static* image a baseline carries is not decidable this way, and
    the screen's own luminance does not decide it either — this device's OEM stock wallpaper is a
    dark starfield, so a brightness threshold would refuse valid stock windows while still not
    separating the two baselines. The luminance is recorded with every window as an observation and
    is not used to admit one.
    """
    component = device_probes.read_wallpaper_component(device.serial)
    if arm is stats.Arm.LIVE:
        if not probes.component_is_live(component):
            detail = (
                f"arm A was requested but the home wallpaper is {probes.component_name(component)}, not "
                f"{contract.SERVICE_NAME}"
            )
            raise device_probes.ProbeError(detail)
        return component
    if baseline is None:
        detail = "arm B needs --baseline stock or --baseline black to say which static wallpaper is bound"
        raise device_probes.ProbeError(detail)
    if probes.component_is_live(component):
        detail = f"arm B was requested but the live service is still bound as {probes.component_name(component)}"
        raise device_probes.ProbeError(detail)
    if not probes.component_is_static(component):
        detail = (
            f"arm B was requested but the bound wallpaper is {probes.component_name(component)}, which is "
            f"neither this app's service nor the platform's static engine "
            f"({contract.PLATFORM_STATIC_WALLPAPER}); another package's live wallpaper is not a "
            f"baseline"
        )
        raise device_probes.ProbeError(detail)
    return component


def arm_conditions(
    device: device_probes.AdbDevice, arm: stats.Arm, baseline: stats.Baseline | None
) -> dict[str, object]:
    """Describe the verified arm for the record, including the luminance recorded for it."""
    return {
        "arm": arm.value,
        "baseline": baseline.value if baseline else None,
        "wallpaper_component": device_probes.read_wallpaper_component(device.serial),
        "median_luma": round(probes.median_luma(device), 2),
        "median_luma_note": probes.MEDIAN_LUMA_NOTE,
    }


def sample_window_states(
    device: device_probes.AdbDevice,
    seconds: float,
    *,
    home_required: bool,
) -> tuple[list[bool | None], list[bool], list[bool | None], list[bool | None]]:
    """
    Sample the display state, the power source, and — for a visible window — the surface and keyguard.

    The display and the power source are sampled *through* the window rather than checked once before
    it, because either can change while it runs. The surface in front is the same kind of fact, and it
    was the one still checked only at the start. `device_probes.read_home_in_front` reads the foreground
    and the home package in two separate round trips, and says so itself: "a caller measuring a window
    must verify the surface at the points it requires rather than trusting this one answer for the
    whole window". Another app coming forward mid-window leaves the bound wallpaper component
    unchanged, so every other guard still passes and the window would be recorded as a home-screen
    B4/B5 measurement of a screen that is not the home screen — and, for B6, as a window on the live
    wallpaper while that wallpaper is not the surface being drawn.

    The keyguard is sampled alongside the surface for the same reason. `ensure_visible_home` reads it
    once before the window, but a screen that locks mid-window draws its lock surface over the home
    screen while the display stays lit and every other guard still passes; the window would then be
    recorded as a B4/B5/B6 measurement of the wallpaper the lock surface covers. A sample that shows
    the keyguard, or that cannot be read, refuses the window — the same three-valued rule the
    pre-window check uses.

    A hidden window turns the display off and has no surface to sample, so it passes
    `home_required=False` and gets empty lists back.
    """
    states: list[bool | None] = []
    on_battery: list[bool] = []
    homes: list[bool | None] = []
    locks: list[bool | None] = []
    remaining = seconds
    while remaining > 0:
        interval = min(SAMPLE_INTERVAL_SECONDS, remaining)
        time.sleep(interval)
        remaining -= interval
        states.append(device.read_screen_on())
        on_battery.append(battery_snapshot.device_on_own_battery(device))
        reading = f"  {seconds - remaining:6.0f}s: screen_on={states[-1]} on_battery={on_battery[-1]}"
        if home_required:
            homes.append(device.read_home_in_front())
            locks.append(device.read_keyguard_locked())
            reading += f" home_in_front={homes[-1]} keyguard_locked={locks[-1]}"
        print(reading, flush=True)
    return states, on_battery, homes, locks


def power_source_problem(on_battery: Sequence[bool]) -> str | None:
    """
    Return why a window is not a discharge measurement, or None when every sample was on battery.

    The same shape as the arm guard: a window whose device ended up on a charger is not a measurement
    of discharge, and recording it as one would be a fabricated result.
    """
    if not on_battery:
        return "the window took no power-source sample, so it is not known to have run on battery"
    if not all(on_battery):
        return f"the device reported a charger connected inside the window: {list(on_battery)}"
    return None


def wait_home_in_front(
    device: device_probes.AdbDevice,
    *,
    sleep: Callable[[float], None] | None = None,
) -> bool | None:
    """
    Read back that the home screen is in front, bounded the way the service-log confirmations are.

    `show_home` sends an input event and reports nothing about what it did; an event the system drops
    leaves the previous app in front, and every other check in `ensure_visible_home` still passes —
    the display is on, the keyguard is not locked, and the bound wallpaper component is the one the
    arm requested. The surface measured would then be that other app's, and the wallpaper the window
    claims to measure would not be the wallpaper on screen. The launcher takes a moment to come
    forward, so this re-reads a bounded number of times rather than once.

    Returns None when no read succeeded, which the caller must treat as a refusal: "could not be
    read" is not "the home screen is there".
    """
    saw_not_in_front = False
    sleep_fn = sleep if sleep is not None else time.sleep
    for attempt in range(HOME_CONFIRM_ATTEMPTS):
        reading = device.read_home_in_front()
        if reading is True:
            return True
        # A `False` is the device saying some other package is in front, which no later reading
        # retracts; a `None` is a read that said nothing. They are kept apart so that a run of
        # unreadable dumps is not reported as "another app is in front", and vice versa.
        saw_not_in_front = saw_not_in_front or reading is False
        if attempt + 1 < HOME_CONFIRM_ATTEMPTS:
            sleep_fn(HOME_CONFIRM_INTERVAL_SECONDS)
    return False if saw_not_in_front else None


def ensure_visible_home(
    device: device_probes.AdbDevice,
    *,
    sleep: Callable[[float], None] | None = None,
) -> None:
    """
    Put the device on the home screen with the display on, or refuse the window.

    A visible window means the home screen with the wallpaper showing. `wake_screen()` only confirms
    the display is lit — it does not dismiss a keyguard or bring the launcher forward — so a device
    that started locked, or with another app in front, would have its lock screen or that app measured
    while the bound component still matched the requested arm. The qualification harness establishes
    this state explicitly before its own screen-on phases, and this one now does too.

    The two checks after `show_home()` are what make the state *established* rather than requested,
    and they cover different failures: the keyguard read says no lock surface is covering the home
    screen, and the foreground read says the home screen is the thing in front at all. Neither
    implies the other — a device unlocked on another app's activity passes the first and fails the
    second — and both are three-valued, so an unreadable device is refused rather than assumed.

    The keyguard is also read *before* the device is touched at all, and a locked or unreadable one
    stops the phase there. `dismiss_keyguard()` below is a change to a shared device that this
    protocol never puts back, so the check that it was safe to make has to come first: read
    afterwards, it cannot tell a device that was already unlocked from one this call just unlocked,
    and the phase would pass its own guard having changed the device it was guarding.
    """
    if not device.wake_screen():
        detail = "the display could not be woken for a visible window"
        raise device_probes.ProbeError(detail)
    # The lock state is read *before* anything is changed, because `wm dismiss-keyguard` changes the
    # shared device and nothing here puts it back: the snapshot restores the display state, not the
    # lock state. Dismissing first and reading afterwards cannot tell "the device was already
    # unlocked" from "this call unlocked it", so a run started on a locked device would unlock it and
    # then pass its own guard. `scripts/device_qualification.py` refuses a locked device before
    # mutating for the same reason, and `docs/device-testing.md` says to start with the keyguard
    # unlocked.
    locked = device.read_keyguard_locked()
    if locked is None:
        detail = (
            "the keyguard state could not be read before the window was set up, so a locked device "
            "cannot be told from an unlocked one; refusing to dismiss a keyguard that may be there"
        )
        raise device_probes.ProbeError(detail)
    if locked:
        detail = (
            "the keyguard is showing, so the device is not in the state this phase measures in, and "
            "dismissing it would change a shared device that nothing here puts back; unlock the device "
            "and re-run"
        )
        raise device_probes.ProbeError(detail)
    device.dismiss_keyguard()
    device.show_home()
    if device.read_screen_on() is not True:
        detail = "the display did not read back as on while the home screen was being established"
        raise device_probes.ProbeError(detail)
    # The keyguard read is three-valued — locked, unlocked, and could not be determined — and only a
    # positive *unlocked* reading shows the home screen is what the window will measure. Treating an
    # unreadable dump as "not locked" is the same defect as reading an unparsable probe as a zero: a
    # locked device would have its lock screen measured for the whole window while the bound home
    # component still matched the requested arm.
    keyguard = device.read_keyguard_locked()
    if keyguard is True:
        detail = "the device is still locked after dismissing the keyguard, so the home screen is not displayed"
        raise device_probes.ProbeError(detail)
    if keyguard is None:
        detail = "the keyguard state could not be read, so it cannot be shown that the home screen is displayed"
        raise device_probes.ProbeError(detail)
    # `show_home()` above sent the event; this is what says it landed. The keyguard and the display
    # can both read as the visible home state wants while another app is still in front, because
    # neither of them names the surface: KEYCODE_HOME is an input event the system may drop, and a
    # dropped one leaves the previous app in front with the bound home component still matching the
    # requested arm. The readback is three-valued for the same reason the keyguard's is.
    in_front = wait_home_in_front(device, sleep=sleep)
    if in_front is False:
        detail = (
            f"another package is in front after KEYCODE_HOME: the device reports "
            f"{device.read_foreground_package()} where it resolves {device.read_home_package()} as home, "
            f"so the wallpaper is not the surface this window would measure"
        )
        raise device_probes.ProbeError(detail)
    if in_front is None:
        detail = "the foreground package could not be read, so it cannot be shown that the home screen is displayed"
        raise device_probes.ProbeError(detail)


def run_window(
    device: device_probes.AdbDevice,
    pid: int | None,
    minutes: float,
    *,
    screen_on: bool,
    clk_tck: int,
) -> tuple[battery_snapshot.Window, list[bool | None], list[bool], list[bool | None], list[bool | None]]:
    """Sample a bounded window, holding the requested display state for its whole duration."""
    if not screen_on:
        device.run_adb(["shell", "input", "keyevent", "KEYCODE_SLEEP"])
        time.sleep(2.0)
        # The sleep key event is a request, not the state: `device_probes.sleep_screen` reports that the
        # event was *delivered*, and a sleep that failed or merely lagged leaves the display on. The
        # first display sample is a whole sampling interval away from here, so a lag would be invisible
        # in the readings — every later one would be `False` while the start of the window was lit —
        # and B3 would be accepted for a window that was not screen-off throughout. This is the same
        # readback `wake_screen` makes for the opposite transition.
        if device.read_screen_on() is not False:
            detail = (
                "the display did not read back as off after the sleep key event, so the window would "
                "not be screen-off throughout"
            )
            raise device_probes.ProbeError(detail)
    start = probes.take_battery_sample(device, pid, clk_tck)
    seconds = minutes * 60.0
    # A window whose display is on is a window on the home screen, so the surface in front is sampled
    # with the rest of the state; see `sample_window_states`.
    states, on_battery, homes, locks = sample_window_states(device, seconds, home_required=screen_on)
    end = probes.take_battery_sample(device, pid, clk_tck)
    window = battery_snapshot.Window(
        start_sample=start, end_sample=end, duration_seconds=end.timestamp - start.timestamp
    )
    return window, states, on_battery, homes, locks


def phase_resources(device: device_probes.AdbDevice) -> battery_snapshot.Record:
    """Record B2: the wake locks of any type, alarms, and jobs the app holds, with their commands."""
    pid = probes.wallpaper_pid(device)
    uid = probes.read_process_uid(device, pid)
    print(f"$ adb -s {device.serial} shell pidof {contract.PACKAGE_NAME} -> {pid}")
    print(f"$ adb -s {device.serial} shell stat -c %u /proc/{pid} -> {uid}")
    if uid is None:
        detail = "the wallpaper has no live process, so its wake locks cannot be attributed"
        raise device_probes.ProbeError(detail)
    wake_locks = probes.count_held_wakelocks(device, uid)
    alarms = probes.count_alarms(device)
    jobs = probes.count_jobs(device)
    # The count is only evidence for the all-type budget if the record says so: a legacy partial-only
    # census wrote the same `wake_locks` key without this stamp, and `report` will not pass it under
    # the current budget. See `battery_report.WAKE_LOCK_COVERAGE`.
    print(f"$ adb -s {device.serial} shell dumpsys power   (every wake-lock type, uid={uid}) -> {wake_locks}")
    print(f"$ adb -s {device.serial} shell dumpsys alarm   ({contract.PACKAGE_NAME}) -> {alarms}")
    print(f"$ adb -s {device.serial} shell dumpsys jobscheduler   ({contract.PACKAGE_NAME}) -> {jobs}")
    summary = probes.read_batterystats_summary(device)
    print(f"  batterystats corroboration: {summary or 'no matching lines'}")
    record = probes.build_record(
        device,
        "resources",
        0.0,
        wake_locks=wake_locks,
        wake_lock_coverage=stats.WAKE_LOCK_COVERAGE,
        alarms=alarms,
        jobs=jobs,
        wallpaper_pid=pid,
        wallpaper_uid=uid,
        batterystats_summary=summary,
    )
    print(f"wake locks={wake_locks} (budget 0), alarms={alarms} (budget 0), jobs={jobs} (budget 0)")
    return record


def require_hidden_measurement(
    window: battery_snapshot.Window,
    states: Sequence[bool | None],
    on_battery: Sequence[bool],
) -> float:
    """
    Refuse a hidden window that is not a B3 measurement, returning the CPU it measured.

    A window whose display came on, that saw a charger, or whose process CPU could not be read is not
    the measurement B3 is defined on. These checks run after the phase's restore has been attempted,
    so each refusal is raised from here rather than beside that path: the caller runs this inside the
    `try` that persists the restore problems, and a refusal means the phase aborted with the device
    possibly still changed.
    """
    if not states or not all(state is False for state in states):
        detail = f"the display was not off for the whole window: {states}"
        raise device_probes.ProbeError(detail)
    charging = power_source_problem(on_battery)
    if charging is not None:
        detail = f"this window is not a valid measurement: {charging}"
        raise device_probes.ProbeError(detail)
    cpu_pct = window.cpu_pct
    if cpu_pct is None:
        detail = "the wallpaper process's CPU counters could not be read over the hidden window"
        raise device_probes.ProbeError(detail)
    return cpu_pct


def require_visible_measurement(  # noqa: PLR0913 — the window and the four state samples are all inputs
    window: battery_snapshot.Window,
    states: Sequence[bool | None],
    on_battery: Sequence[bool],
    home_in_front: Sequence[bool | None],
    arm: stats.Arm,
    *,
    keyguard_locked: Sequence[bool | None],
) -> float:
    """
    Refuse a visible window that is not a B4/B5 measurement, returning its discharge rate.

    `Window.discharge_rate_ua` is one of the refusals — it raises when the pack gained charge across
    the window — so it is read here, inside the same path as the others, rather than at the print that
    happens to need it first.

    The surface in front is checked over the whole window, not only before it: the guard that runs
    before the window establishes the home screen, and another app coming forward after that leaves
    the bound wallpaper component unchanged, so every other reading here would still pass while the
    screen measured is not the home screen. A sample that could not be read is a refusal for the same
    reason it is in `ensure_visible_home`.

    The keyguard is checked over the whole window for the same reason: a screen that locks mid-window
    covers the home screen with its lock surface while the display stays on. A sample that shows the
    keyguard or could not be read refuses the window, the same three-valued rule the pre-window check
    applies.
    """
    if states and not all(state is True for state in states):
        detail = f"the display was not on for the whole visible window: {states}"
        raise device_probes.ProbeError(detail)
    if home_in_front and not all(state is True for state in home_in_front):
        detail = f"the home screen was not the surface in front for the whole visible window: {home_in_front}"
        raise device_probes.ProbeError(detail)
    if keyguard_locked and not all(state is False for state in keyguard_locked):
        detail = f"the keyguard was showing or unreadable inside the visible window: {keyguard_locked}"
        raise device_probes.ProbeError(detail)
    charging = power_source_problem(on_battery)
    if charging is not None:
        detail = f"this is not a discharge measurement: {charging}"
        raise device_probes.ProbeError(detail)
    if arm is stats.Arm.LIVE and window.cpu_pct is None:
        detail = "the live wallpaper's CPU counters could not be read over a visible window"
        raise device_probes.ProbeError(detail)
    return window.discharge_rate_ua


def require_memory_measurement(  # noqa: PLR0913 — the four state samples and the two battery samples
    states: Sequence[bool | None],
    on_battery: Sequence[bool],
    home_in_front: Sequence[bool | None],
    before: battery_snapshot.BatterySample,
    after: battery_snapshot.BatterySample,
    *,
    keyguard_locked: Sequence[bool | None],
) -> int:
    """
    Refuse a memory window that is not a B6 measurement, returning the total-PSS growth in kB.

    B6 is defined over a window on the live wallpaper, so the surface in front is checked over the
    whole window for the reason `require_visible_measurement` gives: a different app in front means
    the wallpaper is not the surface being drawn, and the PSS growth recorded would be the growth of
    a wallpaper that was not on screen for the window the record claims. The keyguard is checked over
    the whole window for the same reason: a lock surface over the home screen means the wallpaper is
    not the surface being drawn, and a sample that shows it or cannot be read refuses the window.
    """
    if states and not all(state is True for state in states):
        detail = f"the display was not on for the whole memory window: {states}"
        raise device_probes.ProbeError(detail)
    if home_in_front and not all(state is True for state in home_in_front):
        detail = f"the home screen was not the surface in front for the whole memory window: {home_in_front}"
        raise device_probes.ProbeError(detail)
    if keyguard_locked and not all(state is False for state in keyguard_locked):
        detail = f"the keyguard was showing or unreadable inside the memory window: {keyguard_locked}"
        raise device_probes.ProbeError(detail)
    charging = power_source_problem(on_battery)
    if charging is not None:
        detail = f"this window is not a valid measurement: {charging}"
        raise device_probes.ProbeError(detail)
    if before.total_pss_kb is None or after.total_pss_kb is None:
        detail = "a total-PSS sample could not be parsed, so growth has no value"
        raise device_probes.ProbeError(detail)
    return after.total_pss_kb - before.total_pss_kb


def phase_hidden(
    device: device_probes.AdbDevice, minutes: float, *, recorder: battery_snapshot.Recorder
) -> battery_snapshot.Record:
    """Record B3: hidden-state CPU over a screen-off window, with the visibility sampled."""
    clk_tck = probes.require_clk_tck(device)
    snapshot = battery_snapshot.DeviceStateSnapshot.capture(device)
    problems: list[str] = []
    prior_power = battery_snapshot.read_power_source_lines(device)
    power_source = battery_snapshot.POWER_SOURCE_DEVICE
    simulated = False
    # The restore sits in its own `finally` inside the outer `try`, so it runs before the abort is
    # handled and the problems it collected are in hand when the record is written.
    try:
        try:
            # The live arm is verified here too. A hidden window is B3 evidence for the live engine, so
            # a static wallpaper bound at the time would make the CPU this window measures the
            # launcher's; `phase_visible` and `phase_memory` guard their arms and this phase used to
            # take the pid and open the window without asking what was bound.
            verify_arm(device, stats.Arm.LIVE, None)
            pid = probes.wallpaper_pid(device)
            snapshot.pin()
            # The decision is recorded before the override is applied: `cmd battery unplug` can take
            # effect and still fail on the way back, and a restore that read the flag afterwards would
            # skip the reset and leave the shared device simulated.
            power_source = battery_snapshot.power_mode_for(device)
            simulated = power_source == battery_snapshot.POWER_SOURCE_SIMULATED
            battery_snapshot.apply_power_mode(device, power_source)
            window, states, on_battery, _, _ = run_window(device, pid, minutes, screen_on=False, clk_tck=clk_tck)
        finally:
            problems = battery_snapshot.undo_phase_changes(device, snapshot, prior_power, simulated=simulated)
        # The acceptance checks and the record build sit inside this `try`, after the restore, rather
        # than after the `except`: a window this phase refuses once the restore has already run is
        # still an abort, and the restore problems it collected have to reach disk with it instead of
        # leaving the shared device changed with nothing saying so. That is why the checks are a
        # function of their own — they belong to that path rather than sitting beside it.
        cpu_pct = require_hidden_measurement(window, states, on_battery)
        print(f"hidden window {window.duration_seconds:.1f}s: screen_on readings={states}")
        print(f"CPU {cpu_pct:.4f}% of one core against the {stats.MAX_HIDDEN_CPU_PCT}% budget")
        record = probes.build_record(
            device,
            "hidden",
            window.duration_seconds,
            window_minutes=minutes,
            cpu_pct=cpu_pct,
            hidden_cpu_budget_pct=stats.MAX_HIDDEN_CPU_PCT,
            clk_tck=clk_tck,
            power_source=power_source,
            screen_on_samples=states,
            on_battery_samples=on_battery,
            restore_problems=problems,
        )
    except Exception as error:
        probes.emit_aborted_restore_record(recorder, device, "hidden", error, problems)
        raise
    return record


def phase_visible(
    device: device_probes.AdbDevice,
    *,
    arm: stats.Arm,
    baseline: stats.Baseline | None,
    minutes: float,
    recorder: battery_snapshot.Recorder,
) -> battery_snapshot.Record:
    """Record one B4/B5 window on the home screen after the arm guard admits it."""
    clk_tck = probes.require_clk_tck(device)
    # The snapshot is taken before the display is woken: a phase that starts with the display off has
    # to record that state, so its restore can put the device back to sleep instead of leaving it on.
    snapshot = battery_snapshot.DeviceStateSnapshot.capture(device)
    prior_power = battery_snapshot.read_power_source_lines(device)
    problems: list[str] = []
    power_source = battery_snapshot.POWER_SOURCE_DEVICE
    simulated = False
    # The restore sits in its own `finally` inside the outer `try`, so it runs before the abort is
    # handled and the problems it collected are in hand when the record is written.
    try:
        try:
            # The wake and the arm guard sit inside the try with the window, so a refusal after the
            # display has already been woken still runs the restore below.
            ensure_visible_home(device)
            verify_arm(device, arm, baseline)
            pid = probes.wallpaper_pid(device) if arm is stats.Arm.LIVE else None
            conditions = arm_conditions(device, arm, baseline)
            print(f"arm guard admitted {conditions['wallpaper_component']} (median luma {conditions['median_luma']})")
            snapshot.pin()
            # The decision is recorded before the override is applied: `cmd battery unplug` can take
            # effect and still fail on the way back, and a restore that read the flag afterwards would
            # skip the reset and leave the shared device simulated.
            power_source = battery_snapshot.power_mode_for(device)
            simulated = power_source == battery_snapshot.POWER_SOURCE_SIMULATED
            battery_snapshot.apply_power_mode(device, power_source)
            window, states, on_battery, homes, locks = run_window(device, pid, minutes, screen_on=True, clk_tck=clk_tck)
        finally:
            problems = battery_snapshot.undo_phase_changes(device, snapshot, prior_power, simulated=simulated)
        # The acceptance checks and the record build sit inside this `try`, after the restore, rather
        # than after the `except`: a window this phase refuses once the restore has already run is
        # still an abort, and the restore problems it collected have to reach disk with it instead of
        # leaving the shared device changed with nothing saying so. That is why the checks are a
        # function of their own — they belong to that path rather than sitting beside it.
        discharge_rate_ua = require_visible_measurement(window, states, on_battery, homes, arm, keyguard_locked=locks)
        print(f"window {window.duration_seconds:.1f}s: discharge {window.discharge_uah} uAh")
        print(f"discharge rate {discharge_rate_ua:.0f} uA, CPU {window.cpu_pct}% of one core")
        record = probes.build_record(
            device,
            "visible",
            window.duration_seconds,
            window_minutes=minutes,
            discharge_uah=window.discharge_uah,
            discharge_rate_ua=discharge_rate_ua,
            cpu_pct=window.cpu_pct,
            charge_counter_start_uah=window.start_sample.charge_counter_uah,
            charge_counter_end_uah=window.end_sample.charge_counter_uah,
            clk_tck=clk_tck,
            power_source=power_source,
            screen_on_samples=states,
            on_battery_samples=on_battery,
            home_in_front_samples=homes,
            keyguard_locked_samples=locks,
            restore_problems=problems,
            **conditions,
        )
    except Exception as error:
        probes.emit_aborted_restore_record(recorder, device, "visible", error, problems)
        raise
    return record


def phase_memory(
    device: device_probes.AdbDevice, minutes: float, *, recorder: battery_snapshot.Recorder
) -> battery_snapshot.Record:
    """Record B6: the total-PSS growth over a long window on the live wallpaper."""
    clk_tck = probes.require_clk_tck(device)
    # Captured before the wake, like the visible phase: a phase that found the display off records it
    # so its restore can put the device back the way it was.
    snapshot = battery_snapshot.DeviceStateSnapshot.capture(device)
    prior_power = battery_snapshot.read_power_source_lines(device)
    problems: list[str] = []
    states: list[bool | None] = []
    on_battery: list[bool] = []
    homes: list[bool | None] = []
    locks: list[bool | None] = []
    power_source = battery_snapshot.POWER_SOURCE_DEVICE
    simulated = False
    # The restore sits in its own `finally` inside the outer `try`, so it runs before the abort is
    # handled and the problems it collected are in hand when the record is written.
    try:
        try:
            ensure_visible_home(device)
            verify_arm(device, stats.Arm.LIVE, None)
            pid = probes.wallpaper_pid(device)
            snapshot.pin()
            # The decision is recorded before the override is applied: `cmd battery unplug` can take
            # effect and still fail on the way back, and a restore that read the flag afterwards would
            # skip the reset and leave the shared device simulated.
            power_source = battery_snapshot.power_mode_for(device)
            simulated = power_source == battery_snapshot.POWER_SOURCE_SIMULATED
            battery_snapshot.apply_power_mode(device, power_source)
            before = probes.take_battery_sample(device, pid, clk_tck)
            seconds = minutes * 60.0
            states, on_battery, homes, locks = sample_window_states(device, seconds, home_required=True)
            after = probes.take_battery_sample(device, pid, clk_tck)
        finally:
            problems = battery_snapshot.undo_phase_changes(device, snapshot, prior_power, simulated=simulated)
        # The acceptance checks and the record build sit inside this `try`, after the restore, rather
        # than after the `except`: a window this phase refuses once the restore has already run is
        # still an abort, and the restore problems it collected have to reach disk with it instead of
        # leaving the shared device changed with nothing saying so. That is why the checks are a
        # function of their own — they belong to that path rather than sitting beside it.
        growth_kb = require_memory_measurement(states, on_battery, homes, before, after, keyguard_locked=locks)
        print(f"total PSS {before.total_pss_kb} -> {after.total_pss_kb} kB over {minutes:.1f} min")
        print(f"growth {growth_kb} kB against the {stats.MAX_PSS_GROWTH_KB} kB budget")
        record = probes.build_record(
            device,
            "memory",
            # The span the samples were actually taken over, not the length that was requested. Both
            # other windowed phases record the measured span, and the report reads this field as a
            # measurement whose length has to hold up: a memory record carrying the requested value
            # instead would assert a window length it never measured.
            after.timestamp - before.timestamp,
            window_minutes=minutes,
            pss_start_kb=before.total_pss_kb,
            pss_end_kb=after.total_pss_kb,
            pss_growth_kb=growth_kb,
            pss_budget_kb=stats.MAX_PSS_GROWTH_KB,
            clk_tck=clk_tck,
            power_source=power_source,
            screen_on_samples=states,
            on_battery_samples=on_battery,
            home_in_front_samples=homes,
            keyguard_locked_samples=locks,
            restore_problems=problems,
        )
    except Exception as error:
        probes.emit_aborted_restore_record(recorder, device, "memory", error, problems)
        raise
    return record


def phase_pilot(  # noqa: PLR0913 — the arms, the window shape, and the sink are all its inputs
    device: device_probes.AdbDevice,
    *,
    arm: stats.Arm,
    baseline: stats.Baseline | None,
    runs: int,
    minutes: float,
    recorder: battery_snapshot.Recorder,
) -> list[battery_snapshot.Record]:
    """
    Record the repeated windows whose spread is the device's noise floor.

    Each window is persisted as soon as it completes, and the floor is emitted as its own record
    rather than merged into the first window's. Persisting per window is what makes the phase
    resumable: a pilot interrupted at window three keeps the windows it completed, instead of
    returning them to a `main` that never got to append them.

    A window that could not restore the device stops the run where it stands, after its record is on
    disk. The windows are one measurement of one device in one state, and the next window would be
    measured under whatever the failed restore left behind — a power override still applied, a display
    that never returned to the state it was found in. Reporting that at the end of the run, as `main`
    does with the accumulated problems, is reporting it after the later windows have already been
    taken on it.

    The run is bounded before the first window opens. `--runs` has a count bound and `--minutes` a
    length bound, but neither bounds this invocation on its own: a count at the floor with a window at
    the ceiling is hours past what `docs/battery-budget.md` allows an invocation to take, and refusing
    it here is refusing it before any window has been opened.
    """
    if runs * minutes > MAXIMUM_PILOT_MINUTES:
        detail = (
            f"{runs} windows of {minutes:g} minutes is {runs * minutes:g} minutes, longer than the "
            f"{MAXIMUM_PILOT_MINUTES:g} minutes a pilot invocation will hold the device for"
        )
        raise device_probes.ProbeError(detail)
    rates: list[float] = []
    cpu_values: list[float] = []
    for run in range(1, runs + 1):
        print(f"\n--- pilot window {run}/{runs} ---")
        record = phase_visible(device, arm=arm, baseline=baseline, minutes=minutes, recorder=recorder)
        record.values["run"] = run
        record.values["pilot"] = True
        record.values["runs"] = runs
        recorder.emit(record)
        # The window is persisted before the run is stopped, so stopping here loses no evidence. A
        # window whose restore failed left the device in a state this run no longer controls — a power
        # override that did not reset, a display that did not return to the state it was found in —
        # and every later window would be measured on it. `main` reports the accumulated problems, but
        # only once the whole pilot has returned, which for a full pilot is two hours of windows.
        restore_problems = record.values.get("restore_problems")
        if isinstance(restore_problems, list) and restore_problems:
            named = "; ".join(str(problem) for problem in restore_problems)
            detail = (
                f"pilot window {run} of {runs} did not restore the device ({named}), so the remaining "
                f"windows would be measured on a device this run does not control; stopping after "
                f"{run} window(s)"
            )
            raise device_probes.ProbeError(detail)
        rate = record.values.get("discharge_rate_ua")
        if not isinstance(rate, int | float):
            detail = "a visible window recorded no discharge rate, so the noise floor has no input"
            raise device_probes.ProbeError(detail)
        rates.append(float(rate))
        cpu_pct = record.values["cpu_pct"]
        if isinstance(cpu_pct, int | float):
            cpu_values.append(float(cpu_pct))
    mean, deviation, half_width = stats.two_sigma_noise_floor(rates)
    channel_measured = mean > 0
    values: dict[str, object] = {
        "run": 0,
        "pilot": True,
        "runs": runs,
        "discharge_channel_measured": channel_measured,
        "baseline_mean_rate_ua": mean,
    }
    if channel_measured:
        floor_pct = (half_width / mean) * 100.0
        values["noise_floor_pct"] = floor_pct
        values["noise_floor_rate_ua"] = half_width
        print(f"\nwindow discharge rate: mean {mean:.0f} uA, sigma {deviation:.0f} uA, 2 sigma {half_width:.0f} uA")
        print(f"noise floor as a share of the mean: {floor_pct:.2f}%")
    else:
        # A gauge that did not move across every window is the frozen counter the reports describe,
        # not a device with no noise: half-width zero divided by a zero mean says nothing at all, and
        # recording it as a 0% floor would let a later report present an unmeasured channel as a
        # perfectly quiet one. No floor is emitted and the channel is marked unmeasured instead.
        print(
            f"\nthe discharge channel did not move across {runs} windows (mean {mean:.0f} uA), so it is "
            "unmeasured and no noise floor is emitted for it; a threshold cannot be calibrated from a "
            "counter that never changed"
        )
    if cpu_values:
        cpu_mean, cpu_deviation, cpu_half_width = stats.two_sigma_noise_floor(cpu_values)
        values["cpu_mean_pct"] = cpu_mean
        values["cpu_noise_floor_pct"] = cpu_half_width
        print(f"CPU: mean {cpu_mean:.4f}%, sigma {cpu_deviation:.4f}, 2 sigma {cpu_half_width:.4f}")
    return [probes.build_record(device, "pilot_floor", 0.0, **values)]
