# SPDX-License-Identifier: Apache-2.0
"""
Device settings snapshot, power-mode pinning, restore verification, and JSONL record persistence.

Captures the device state a battery measurement phase touches, pins settings for the window,
verifies every restored setting on exit, and persists phase records to the JSON Lines state file.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Final

from host.device import probes as device_probes

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

# A run of digits as a device prints one, bounded. Every pattern below that captures a number is handed
# to `int()`, and `int()` refuses a value of more than about 4300 digits by *raising* rather than
# converting it — so an unbounded `\d+` turns a dump that lost its mind into a traceback instead of the
# named refusal the harness promises. No field, census, or tick count this harness reads is 18 digits
# wide, so the bound costs nothing that a real dump has.
#
# The trailing lookahead is what makes the bound a refusal rather than a truncation: in a pattern with
# no trailing anchor — `TOTAL_PSS_PATTERN` is the one — `\d{1,18}` would happily match the first
# eighteen digits of a longer run and report them as the reading, which is the silent misreading the
# bound exists to prevent. `(?!\d)` refuses the run instead.
DIGITS: Final = r"\d{1,18}(?!\d)"

POWERED_LINE_PATTERN: Final = re.compile(r"^\s*(\w+) powered:\s*(true|false)\s*$", re.MULTILINE)

# The four power sources `dumpsys battery` reports. A reading is only complete when all four are
# present: a dump that lost three of them must not be read as "the remaining one is false, so the
# device is on battery", which is what a per-line scan would conclude from a truncated dump.
EXPECTED_POWER_SOURCES: Final = ("AC", "USB", "Wireless", "Dock")

# A decimal integer as a device prints one, bounded so that a long run of digits is refused rather
# than handed to `int()`. `str.isdigit()` is not the same question: `"²"` is a digit but not a decimal
# one, and it reaches `int()` as a `ValueError`, as does any value of more than a few thousand digits.
# A device setting is never 18 digits wide, so the bound costs nothing and makes "unreadable" the
# answer for everything the pattern does not match. The sign is accepted here because
# `screen_brightness` is legitimately `-1` on a device using automatic brightness.
DECIMAL_INT_PATTERN: Final = re.compile(rf"[+-]?{DIGITS}")

# What `settings get <namespace> <key>` prints for a key that was never set. It is the only reading
# that means "unset", which is why it is a literal of its own rather than "anything that is not a
# decimal integer" — that reading is also what a settings service that did not answer looks like, and
# treating the two alike loses a value the restore was supposed to put back.
UNSET_SETTING_TEXT: Final = "null"

DEFAULT_STATE_DIR: Final = Path("build/reports/battery")

RECORD_FILE_NAME: Final = "records.jsonl"

PINNED_BRIGHTNESS: Final = 128

# Stay awake on every power source; see DeviceStateSnapshot.pin.
STAY_ON_ALWAYS: Final = 7

# A whole hour, so it comfortably exceeds the longest documented window (30 minutes) rather
# than expiring at the same instant the window closes.
LONG_SCREEN_TIMEOUT_MS: Final = 3_600_000

RESTORE_SETTLE_SECONDS: Final = 2.0

# The discharge window's power source. A device that is genuinely on its own battery has a live fuel
# gauge and its counter moves; a device held on USB only reports battery when `cmd battery unplug`
# overrides the power source, and on some devices that freezes the gauge. Which one a window was
# measured under is part of the measurement's identity, so it is recorded and checked.
POWER_SOURCE_DEVICE: Final = "device"

POWER_SOURCE_SIMULATED: Final = "simulated"


@dataclass(frozen=True)
class BatterySample:
    """Instantaneous battery and process telemetry reading."""

    timestamp: float
    charge_counter_uah: int
    level_pct: int
    voltage_mv: int
    process_cpu_seconds: float | None
    total_pss_kb: int | None


@dataclass(frozen=True)
class Window:
    """One bounded measurement period under constant display and workload conditions."""

    start_sample: BatterySample
    end_sample: BatterySample
    duration_seconds: float

    @property
    def discharge_uah(self) -> int:
        """Net microampere-hours consumed during the window."""
        return self.start_sample.charge_counter_uah - self.end_sample.charge_counter_uah

    @property
    def discharge_rate_ua(self) -> float:
        """
        Average current draw over the window, in microamperes.

        The counter must have fallen. A gauge that reports the pack gaining charge across a window is
        not measuring a discharge at all — the device was charging, or the gauge recalibrated — and
        returning the negative draw would let that window enter the comparison as a live arm that
        looked cheaper, so it is refused at the source rather than judged downstream.
        """
        if self.duration_seconds <= 0:
            detail = "a window with no elapsed time has no discharge rate"
            raise device_probes.ProbeError(detail)
        if self.discharge_uah < 0:
            detail = (
                f"the charge counter rose by {-self.discharge_uah} uAh across the window "
                f"({self.start_sample.charge_counter_uah} to {self.end_sample.charge_counter_uah} uAh), "
                "so the pack gained charge and this is not a discharge measurement"
            )
            raise device_probes.ProbeError(detail)
        return (self.discharge_uah / self.duration_seconds) * 3600.0

    @property
    def cpu_pct(self) -> float | None:
        """Average CPU across one core during the window, or None when the process was not read."""
        start = self.start_sample.process_cpu_seconds
        end = self.end_sample.process_cpu_seconds
        if start is None or end is None or self.duration_seconds <= 0:
            return None
        if end < start:
            detail = (
                f"the process CPU counter went backwards ({start:.3f}s to {end:.3f}s), which means the "
                "process restarted or the pid was recycled inside the window; the window is not a measurement"
            )
            raise device_probes.ProbeError(detail)
        return ((end - start) / self.duration_seconds) * 100.0


@dataclass(frozen=True)
class Record:
    """One phase invocation's result, as written to the state file."""

    phase: str
    recorded_at: str
    revision: str
    apk_sha256: str | None
    api_level: int | None
    duration_seconds: float
    values: dict[str, object] = field(default_factory=dict)


class DeviceStateSnapshot:
    """
    The device state a phase changes, captured so it can be put back and checked.

    The screen's own power state is part of it: a hidden window turns the display off, and a phase
    that returned that way would leave the device dark.
    """

    def __init__(  # noqa: PLR0913
        self,
        device: device_probes.AdbDevice,
        *,
        brightness: int | None,
        brightness_mode: int | None,
        screen_timeout: int | None,
        airplane_mode: int | None,
        stay_on: int | None,
        screen_on: bool | None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        """Hold the values read before a phase changed anything."""
        self.device = device
        self.brightness = brightness
        self.brightness_mode = brightness_mode
        self.screen_timeout = screen_timeout
        self.airplane_mode = airplane_mode
        self.stay_on = stay_on
        self.screen_on = screen_on
        self._sleep = sleep

    @classmethod
    def capture(
        cls,
        device: device_probes.AdbDevice,
        *,
        sleep: Callable[[float], None] | None = None,
    ) -> DeviceStateSnapshot:
        """
        Read the state a measurement phase pins, including the display's own power state.

        Four of the settings `pin()` writes are required rather than best-effort: a value that could
        not be read is a value the restore cannot put back, and skipping it would leave the shared
        device changed by a phase that reported success. The stay-awake setting is the one exception —
        it is legitimately unset on a device that never had it, and an unset value *is* captured, as
        `None`, and restored by deleting the key. The exception is only for the setting's *unset*
        reading, not for an unreadable one: `read_unsettable_int_setting` tells the device's `null`
        from a service that did not answer, and refuses the second before anything is pinned.
        """
        return cls(
            device,
            brightness=require_int_setting(device, "system", "screen_brightness"),
            brightness_mode=require_int_setting(device, "system", "screen_brightness_mode"),
            screen_timeout=require_int_setting(device, "system", "screen_off_timeout"),
            airplane_mode=require_int_setting(device, "global", "airplane_mode_on"),
            stay_on=read_unsettable_int_setting(device, "global", "stay_on_while_plugged_in"),
            screen_on=device.read_screen_on(),
            sleep=sleep,
        )

    def pin(self) -> None:
        """Pin the display conditions a visible window is measured under."""
        self.device.run_adb(["shell", "settings", "put", "system", "screen_brightness_mode", "0"])
        self.device.run_adb(["shell", "settings", "put", "system", "screen_brightness", str(PINNED_BRIGHTNESS)])
        self.device.run_adb(["shell", "settings", "put", "system", "screen_off_timeout", str(LONG_SCREEN_TIMEOUT_MS)])
        # The timeout alone does not hold the display: a device that reports itself as running on
        # battery ignores the plugged-in stay-awake setting, which is exactly the state a discharge
        # simulation puts it in. Staying awake on every power source is what keeps a visible window
        # visible, and it is restored below like everything else.
        self.device.run_adb(["shell", "settings", "put", "global", "stay_on_while_plugged_in", str(STAY_ON_ALWAYS)])
        set_airplane_mode(self.device, enabled=True)

    def restore(self) -> list[str]:
        """Put every pinned value back, isolating each step so none can skip the others."""
        problems: list[str] = []
        problems.extend(self._restore_settings())
        problems.extend(self._restore_display())
        return problems

    def _restore_settings(self) -> list[str]:
        """Undo the settings writes, reporting each one that could not be verified."""
        problems: list[str] = []
        steps: list[tuple[str, list[str], str, str, int | None]] = [
            (
                # Restored to the value it was found with, not to off: a device that had airplane
                # mode on before the phase must still have it on afterwards.
                "airplane mode",
                [
                    "shell",
                    "cmd",
                    "connectivity",
                    "airplane-mode",
                    "enable" if self.airplane_mode else "disable",
                ],
                "global",
                "airplane_mode_on",
                self.airplane_mode,
            ),
            (
                "brightness mode",
                ["shell", "settings", "put", "system", "screen_brightness_mode", str(self.brightness_mode)],
                "system",
                "screen_brightness_mode",
                self.brightness_mode,
            ),
            (
                "brightness",
                ["shell", "settings", "put", "system", "screen_brightness", str(self.brightness)],
                "system",
                "screen_brightness",
                self.brightness,
            ),
            (
                "screen timeout",
                ["shell", "settings", "put", "system", "screen_off_timeout", str(self.screen_timeout)],
                "system",
                "screen_off_timeout",
                self.screen_timeout,
            ),
        ]
        for description, command, namespace, key, expected in steps:
            if expected is None:
                continue
            problems.extend(self._apply(description, command, namespace, key, expected))
        problems.extend(self._restore_stay_on())
        return problems

    def _restore_stay_on(self) -> list[str]:
        """Put the stay-awake setting back, including removing it when it was unset."""
        if self.stay_on is None:
            try:
                self.device.run_adb(["shell", "settings", "delete", "global", "stay_on_while_plugged_in"])
            except (subprocess.SubprocessError, OSError) as error:
                return [f"stay-awake restore failed: {device_probes.error_detail(error)}"]
            # The readback is inside its own guard: a transport failure here used to escape the whole
            # restore and skip the display step that follows it. The reader's refusal is caught here
            # with it, and that is the point of using this reader rather than `read_int_setting`: a
            # readback of `""` or any other unreadable text reads as `None` there — indistinguishable
            # from the unset value the delete was meant to produce — so a delete nobody could verify
            # was reported as a clean restore. Here it is a problem like any other.
            try:
                remaining = read_unsettable_int_setting(self.device, "global", "stay_on_while_plugged_in")
            except (subprocess.SubprocessError, OSError, device_probes.ProbeError) as error:
                return [f"stay-awake restore could not be verified: {device_probes.error_detail(error)}"]
            if remaining is not None:
                return ["global/stay_on_while_plugged_in did not return to unset"]
            return []
        return self._apply(
            "stay-awake",
            ["shell", "settings", "put", "global", "stay_on_while_plugged_in", str(self.stay_on)],
            "global",
            "stay_on_while_plugged_in",
            self.stay_on,
        )

    def _apply(self, description: str, command: list[str], namespace: str, key: str, expected: int) -> list[str]:
        """Run one restore step and verify it, converting a failure into a reported problem."""
        try:
            self.device.run_adb(command)
            sleep_fn = self._sleep if self._sleep is not None else time.sleep
            sleep_fn(RESTORE_SETTLE_SECONDS)
        except (subprocess.SubprocessError, OSError) as error:
            return [f"{description} restore failed: {device_probes.error_detail(error)}"]
        # The readback is guarded too: an uncaught transport failure here used to escape the whole
        # restore and skip the display restoration.
        try:
            actual = read_int_setting(self.device, namespace, key)
        except (subprocess.SubprocessError, OSError) as error:
            return [f"{description} restore could not be verified: {device_probes.error_detail(error)}"]
        if actual != expected:
            return [f"{namespace}/{key} did not read back as {expected}"]
        return []

    def _restore_display(self) -> list[str]:
        """
        Return the display to the power state it was found in.

        The reads are guarded the way the settings steps are, and for the same reason. `restore()` is
        reached from `undo_phase_changes` through `problems.extend(...)`, so a read that raised here
        would discard every problem the settings steps had already collected — `extend` never runs and
        the caller reports one generic failure in their place — and the sleep below would be skipped.
        """
        if self.screen_on is None:
            return ["the display state could not be read before the phase, so it cannot be restored"]
        if self.screen_on:
            if not self.device.wake_screen():
                return ["the display was on before the phase and could not be woken again"]
            return []
        problem = self._sleep_display()
        return [problem] if problem is not None else []

    def _sleep_display(self) -> str | None:
        """Put a display that started off back to sleep, or say why it could not be."""
        try:
            if self.device.read_screen_on() is False:
                return None
        except (subprocess.SubprocessError, OSError) as error:
            return f"the display state could not be read to restore it: {device_probes.error_detail(error)}"
        self.device.sleep_screen()
        try:
            if self.device.read_screen_on() is not False:
                return "the display was off before the phase and could not be put back to sleep"
        except (subprocess.SubprocessError, OSError) as error:
            return f"the display state could not be read back after the sleep: {device_probes.error_detail(error)}"
        return None


def undo_phase_changes(
    device: device_probes.AdbDevice,
    snapshot: DeviceStateSnapshot,
    prior_power: tuple[str, ...] | None = None,
    *,
    simulated: bool = False,
) -> list[str]:
    """
    Undo a phase's device changes, isolating each step so none can skip the others.

    The `cmd battery` reset runs only when this phase applied the override. A device that was already
    on its own battery is never put under the override, so there is nothing to clear, and clearing it
    would be a write to a device whose state is already correct.

    The reset and the readback that verifies it are two steps rather than one. `power_source_restored`
    reads a battery dump, and a dump that cannot be parsed raises `ProbeError` from there; sharing the
    reset's guard meant an unparsable readback escaped this function entirely, so the settings restore
    below never ran and the problems list stayed empty — the shared device left pinned with nothing on
    disk for `report` to print.
    """
    problems: list[str] = []
    if simulated:
        try:
            reset_battery_simulation(device)
        except (subprocess.SubprocessError, OSError) as error:
            problems.append(f"battery simulation reset failed: {device_probes.error_detail(error)}")
        if prior_power is not None:
            try:
                restored = power_source_restored(device, prior_power)
            except (subprocess.SubprocessError, OSError, device_probes.ProbeError) as error:
                problems.append(f"the restored power sources could not be read: {device_probes.error_detail(error)}")
            else:
                if not restored:
                    problems.append("the reported power sources did not return to their pre-phase state")
    try:
        problems.extend(snapshot.restore())
    except (subprocess.SubprocessError, OSError) as error:
        problems.append(f"device settings restore failed: {device_probes.error_detail(error)}")
    return problems


def read_setting_text(device: device_probes.AdbDevice, namespace: str, key: str) -> str:
    """Read one device setting as the text `settings get` printed for it, stripped."""
    return device.run_adb(["shell", "settings", "get", namespace, key]).decode(errors="replace").strip()


def read_int_setting(device: device_probes.AdbDevice, namespace: str, key: str) -> int | None:
    """
    Read one integer device setting, or None when it is unset or not a decimal integer.

    The readback runs inside the restore as well as before it, and the restore's contract is that no
    step can abort the ones after it. A readback that raised here would do exactly that — the settings
    restore would stop at this step and the display restore would never run — so text that cannot be
    read is `None`, which the restore already reports as a value that did not read back.

    That conflation is the right reading for a *comparison* — `None` is never the value a step wrote,
    so it fails one — but not for deciding what a setting was worth. `read_unsettable_int_setting` is
    the reader that tells the two apart, and the stay-awake setting is captured through it.
    """
    return parse_signed_int(read_setting_text(device, namespace, key))


def read_unsettable_int_setting(device: device_probes.AdbDevice, namespace: str, key: str) -> int | None:
    """
    Read one integer device setting that is legitimately unset, refusing an unreadable reading.

    `settings get` prints `null` for a key that was never set, and a decimal integer for one that was,
    so those are the only two readings that say anything about the setting's value. Anything else is
    a settings service that did not answer — and `read_int_setting` reports it as `None`, which is
    exactly the sentinel for "never set". Nothing downstream can tell them apart afterwards: the
    capture stores it, `pin()` overwrites the setting anyway, and the restore then *deletes* a key
    that may have held a real value, reporting a clean restore of a device it left changed. The
    distinction has to be made where the text is, so it is made here and an unreadable reading stops
    the phase before it pins anything — the same refusal `require_int_setting` makes for the four
    settings that cannot be captured as unset, for the same reason.
    """
    raw = read_setting_text(device, namespace, key)
    if raw == UNSET_SETTING_TEXT:
        return None
    value = parse_signed_int(raw)
    if value is None:
        detail = (
            f"{namespace}/{key} read back as {raw!r}, which is neither a decimal integer nor the "
            f"device's {UNSET_SETTING_TEXT} for an unset setting, so whether it held a value to "
            "restore cannot be read from this device"
        )
        raise device_probes.ProbeError(detail)
    return value


def require_int_setting(device: device_probes.AdbDevice, namespace: str, key: str) -> int:
    """
    Read one device setting the pre-phase capture cannot do without.

    `pin()` overwrites every one of these, and the restore can only put back a value that was
    captured. A phase that pinned a setting it could not read would leave the shared device changed
    and still report success, so an unreadable value stops the phase before it touches anything.
    """
    value = read_int_setting(device, namespace, key)
    if value is None:
        detail = (
            f"{namespace}/{key} could not be read before the phase, so whatever value it had could not "
            "be restored; refusing to pin a setting whose original value is unknown"
        )
        raise device_probes.ProbeError(detail)
    return value


def set_airplane_mode(device: device_probes.AdbDevice, *, enabled: bool) -> None:
    """Turn airplane mode on or off through the connectivity service."""
    device.run_adb(["shell", "cmd", "connectivity", "airplane-mode", "enable" if enabled else "disable"])


def require_complete_power_sources(lines: Sequence[str]) -> None:
    """
    Refuse a power-source reading that is missing any of the four sources `dumpsys battery` reports.

    One `powered:` line is not a reading. A dump that named only `Dock powered: false` would look
    exactly like a device on its own battery to a per-line scan, and the identity of a discharge
    measurement rests on this reading, so an incomplete one is raised rather than filled in.
    """
    present = {match.group(1) for match in POWERED_LINE_PATTERN.finditer("\n".join(lines))}
    missing = [source for source in EXPECTED_POWER_SOURCES if source not in present]
    if missing:
        detail = (
            f"the battery dump carried no {' or '.join(missing)} powered: field, so the power source is "
            "not a complete reading; refusing to infer the device's state from the fields that remain"
        )
        raise device_probes.ProbeError(detail)


def read_power_source_lines(device: device_probes.AdbDevice) -> tuple[str, ...]:
    """Read the battery dump's power-source lines, which `cmd battery unplug` rewrites."""
    output = device.run_adb(["shell", "dumpsys", "battery"]).decode(errors="replace")
    lines = tuple(line.strip() for line in output.splitlines() if POWERED_LINE_PATTERN.match(line.strip()))
    require_complete_power_sources(lines)
    return lines


def power_source_restored(device: device_probes.AdbDevice, before: tuple[str, ...]) -> bool:
    """
    Report whether the reported power sources match what they were before the simulation.

    Comparing against the pre-simulation reading is what separates "the override is gone" from
    "this device happens to be running on its own battery", which look identical in the dump.
    """
    return read_power_source_lines(device) == before


def power_lines_show_battery(lines: Sequence[str]) -> bool:
    """
    Report whether a battery dump's `powered:` fields all read false, i.e. the device is on battery.

    Every source is required. A dump that named fewer than the four sources is raised rather than
    read as "no charger is connected", because a probe that stopped reporting some of them would
    otherwise look like a device that is discharging.
    """
    require_complete_power_sources(lines)
    return all(match.group(2) == "false" for match in POWERED_LINE_PATTERN.finditer("\n".join(lines)))


def device_on_own_battery(device: device_probes.AdbDevice) -> bool:
    """Report whether the device is already discharging on its own battery rather than on a charger."""
    return power_lines_show_battery(read_power_source_lines(device))


def power_mode_for(device: device_probes.AdbDevice) -> str:
    """
    Name the discharge state a window needs, reading the device without changing it.

    A device that is genuinely discharging already has the live fuel gauge this measurement wants,
    and `cmd battery unplug` would replace that with a frozen override — the very artefact the
    simulation was invented to work around. The override is therefore chosen only when the device is
    on a charger, and the mode is recorded in the window as part of its identity.

    Deciding is separate from applying because applying can fail *after* the device has obeyed: a
    dropped transport or a timeout on `cmd battery unplug` leaves the override on the device while the
    call raises. The caller records what this returned before anything is written, so the restore
    knows a reset is owed even when the call that applied it came back with an error.
    """
    return POWER_SOURCE_DEVICE if device_on_own_battery(device) else POWER_SOURCE_SIMULATED


def apply_power_mode(device: device_probes.AdbDevice, mode: str) -> None:
    """Apply the mode `power_mode_for` named, which its caller has already recorded."""
    if mode == POWER_SOURCE_SIMULATED:
        simulate_unplug(device)


def parse_signed_int(raw: str) -> int | None:
    """
    Read a device's signed decimal integer, or None when the text is not one.

    A parse rather than a `str.isdigit()` test: `isdigit()` answers a different question, and the
    guard built on it here — `raw.lstrip("-").isdigit()` — accepted `"--5"` and `"²"`, both of which
    then raised `ValueError` from `int()` at a call site whose caller treats "unreadable" as a value.
    """
    return int(raw) if DECIMAL_INT_PATTERN.fullmatch(raw) else None


def simulate_unplug(device: device_probes.AdbDevice) -> None:
    """Make the device report itself as running on battery while it stays on USB for telemetry."""
    device.run_adb(["shell", "cmd", "battery", "unplug"])


def reset_battery_simulation(device: device_probes.AdbDevice) -> None:
    """Clear any `cmd battery` override so the device reports its real state again."""
    device.run_adb(["shell", "cmd", "battery", "reset"])


def record_path(state_dir: Path) -> Path:
    """Return the JSON Lines file the phase records accumulate in."""
    return state_dir / RECORD_FILE_NAME


def append_record(state_dir: Path, record: Record) -> Path:
    """Append one record to the state file, creating the directory when it is missing."""
    state_dir.mkdir(parents=True, exist_ok=True)
    path = record_path(state_dir)
    payload: dict[str, object] = {"phase": record.phase, "recorded_at": record.recorded_at, "revision": record.revision}
    payload["apk_sha256"] = record.apk_sha256
    payload["api_level"] = record.api_level
    payload["duration_seconds"] = record.duration_seconds
    payload.update(record.values)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
    return path


def load_records(state_dir: Path) -> list[dict[str, object]]:
    """Read back every record written so far, refusing to guess at a malformed line."""
    path = record_path(state_dir)
    if not path.is_file():
        detail = f"no records at {path}; run the measurement phases before the report"
        raise device_probes.ProbeError(detail)
    # The decode is guarded like the parse below it. An append interrupted mid-character leaves a
    # partial UTF-8 sequence, which `read_text` raises `UnicodeDecodeError` on — the same corrupt
    # state file the JSON branch names, failing one step earlier and as a traceback.
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        detail = f"{path} is not valid UTF-8 ({error}); the record file is truncated or corrupt"
        raise device_probes.ProbeError(detail) from error
    records: list[dict[str, object]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except ValueError as error:
            # A truncated write is a state file the run can be told about, not a traceback: the
            # phases append as they go, so the last line is the one an interrupted run leaves short.
            # `JSONDecodeError` is caught here as the `ValueError` it is, and so is the other
            # `ValueError` `json` raises — a number with more digits than `int()` will convert.
            detail = f"{path}:{number} is not valid JSON ({error}); the record is truncated or corrupt"
            raise device_probes.ProbeError(detail) from error
        if not isinstance(parsed, dict):
            detail = f"{path}:{number} is not a JSON object"
            raise device_probes.ProbeError(detail)
        records.append(parsed)
    return records


class Recorder:
    """
    Writes each record to the state file as it is produced, and keeps them for the caller.

    Persisting per record is what makes the phases resumable: a phase interrupted part-way leaves the
    records it completed on disk rather than holding them in a list until a `main` that may never
    reach its append loop.
    """

    def __init__(self, state_dir: Path) -> None:
        """Bind the recorder to the state directory its records accumulate in."""
        self.state_dir = state_dir
        self.records: list[Record] = []

    def emit(self, record: Record) -> Record:
        """Append one record, print where it went, and return it for the caller to keep using."""
        path = append_record(self.state_dir, record)
        self.records.append(record)
        print(f"recorded {record.phase} -> {path}")
        return record
