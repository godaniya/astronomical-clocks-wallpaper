# SPDX-License-Identifier: Apache-2.0
"""Battery, CPU, PSS, wake-lock, alarm, job, luma, and device-identity probes for the battery protocol."""

from __future__ import annotations

import datetime as dt
import hashlib
import re
import subprocess
import sys
import time
from typing import TYPE_CHECKING, Final

from host import contract
from host.battery import snapshot
from host.device import frame
from host.device import probes as device_probes

if TYPE_CHECKING:
    from collections.abc import Sequence

CHARGE_COUNTER_PATTERN: Final = re.compile(rf"^[ \t]*Charge counter:[ \t]*({snapshot.DIGITS})[ \t]*$", re.MULTILINE)

BATTERY_LEVEL_PATTERN: Final = re.compile(rf"^[ \t]*level:[ \t]*({snapshot.DIGITS})[ \t]*$", re.MULTILINE)

# Anchored to the field name so that `Max charging voltage:` can never be read as the pack voltage.
BATTERY_VOLTAGE_PATTERN: Final = re.compile(rf"^[ \t]*voltage:[ \t]*({snapshot.DIGITS})[ \t]*$", re.MULTILINE)

# The separators are `[ \t]` and not `\s` for the reason the census patterns give: `\s` matches a
# newline, so `\s+` after `TOTAL` would let a truncated `TOTAL` line reach the next line for its number
# and report an unrelated figure as the app's total PSS. The trailing lookahead is what keeps the
# *captured* value from doing the same thing: this is the one capture with no other field name or
# anchor after it, so without a boundary the `123` of a corrupted `TOTAL 123oops` would match and be
# recorded as a reading. A real line continues with more columns after horizontal whitespace.
TOTAL_PSS_PATTERN: Final = re.compile(rf"^[ \t]*TOTAL[ \t]+({snapshot.DIGITS})(?=[ \t]|$)", re.MULTILINE)

SDK_PATTERN: Final = re.compile(rf"^({snapshot.DIGITS})$")

# Every shape `dumpsys jobscheduler` prints a job line in, taken from the test device's own dump.
# The two components at the end of a job line are a `<hash> <component>` pair; the component is
# either `<pkg>/<class>` or `<ns>@<pkg>/<class>`, and one legacy line on this device is tagged
# rather than component-shaped (`DownloadManager:<pkg>`). The old pattern recognised the plain
# `JOB #<uid>/<id>` form only, which matched 74 of the 521 job lines this device lists: the
# namespaced form (`androidx.work.systemjobscheduler:<uid>/<id>`, `SyncManager:<uid>/<id>`) is where
# WorkManager and the sync adapters keep their jobs, so an app's own jobs could be silently dropped
# from the count. Group 1 is the package the job belongs to, which is what attributes it to the app.
JOB_LINE_PATTERN: Final = re.compile(
    r"^\s*JOB \S+/-?\d+:\s+\S+\s+(?:@[\w.]+@)?(?:[A-Za-z][\w.]*:)?([\w.\-]+)(?:[/:]|$)",
    re.MULTILINE,
)

# The job *entry* predicate: one line per job, whatever its shape. It is deliberately wider than
# JOB_LINE_PATTERN, so that a job line the attribution cannot parse shows up as a count mismatch or
# as an unparsable entry rather than being dropped silently.
JOB_ENTRY_PATTERN: Final = re.compile(r"^\s*JOB \S+/-?\d+:", re.MULTILINE)

# The wake-lock entry predicate counts every lock type, not `PARTIAL_WAKE_LOCK` alone. The census
# counts the whole device, and this device's `Wake Locks: size=1` is a `DOZE_WAKE_LOCK`, so an
# app-scoped count of partial locks can never equal the census and the census could never be
# checked against it.
WAKE_LOCK_ENTRY_PATTERN: Final = re.compile(r"^\s*\w+_WAKE_LOCK\b", re.MULTILINE)

# The alarm entry predicate: the census block prints one `<TYPE> #<n>: Alarm{...}` header per
# pending alarm. It must be read inside the census block only, because a later section lists alarms
# of its own in exactly this shape — this device prints `Past-due non-wakeup alarms: 1` followed by
# `ELAPSED #1: Alarm{...}` — and a whole-dump scan counts that one too.
ALARM_ENTRY_PATTERN: Final = re.compile(r"^\s*\w+\s*#\d+:\s*Alarm\{", re.MULTILINE)

# A `dumpsys jobscheduler` dump that has been read at all prints a `Registered <n> jobs:` census line
# before the job list; requiring it is what separates "the app has no jobs" from "this is not a
# jobscheduler dump", so an unparsable probe is an error rather than a zero.
#
# The line must *end* after the count, as the power and alarm census patterns below already require,
# with the same `[ \t]` trailing class. Anchored at the start only, this matched a malformed line such
# as `Registered 0 jobs: CORRUPT` and read its leading zero as the census — a count from a line the
# probe never actually read, which for a zero is a B2 pass.
JOBSCHEDULER_CENSUS_PATTERN: Final = re.compile(rf"^[ \t]*Registered ({snapshot.DIGITS}) jobs:[ \t]*$", re.MULTILINE)

# A `dumpsys power` that has been read at all prints its wake-lock census before listing the locks,
# the same way `dumpsys jobscheduler` prints its job census. Requiring it is what separates "the app
# holds no wake locks" from "this is not a power dump", so a truncated or reshaped dump is an error
# rather than a zero.
#
# The leading and trailing whitespace classes are `[ \t]` and not `\s`. `\s` matches a newline, so a
# pattern anchored `^\s*` on a census line can begin its match at the blank line *above* the census and
# run into it — the match then starts one line early, and a parser that locates the censused block from
# the match start reads the block from the wrong line. Requiring a line's own spaces keeps the match on
# the census line.
POWER_WAKELOCK_CENSUS_PATTERN: Final = re.compile(rf"^[ \t]*Wake Locks: size=({snapshot.DIGITS})[ \t]*$", re.MULTILINE)

# `dumpsys alarm` likewise prints a census before listing the pending alarms, and that census is what
# makes an alarm count trustworthy. The line is taken from the test device's own dump, which reads
# `  164 pending alarms: ` — count first, no `Pending alarm batches:` line anywhere in it. The count
# is a count of entries and not the highest entry index: the block below this census is numbered `#1`
# onwards, and on five consecutive reads of one device the declared count and the number of entry
# lines agreed exactly, which is what `census_entry_block` holds them to.
ALARM_CENSUS_PATTERN: Final = re.compile(rf"^[ \t]*({snapshot.DIGITS}) pending alarms:[ \t]*$", re.MULTILINE)

# A count a device prints that cannot be negative — a UID from `stat -c %u`, or the utime and stime
# ticks from `/proc/<pid>/stat`. It is a pattern of its own rather than the signed one above, because a
# read that failed or was malformed can answer `-1` and `int()` would take it. Both callers then treat a
# negative reading as a measurement: `phase_resources` refuses only `None` and would build the wake-lock
# predicate `uid=-1`, which matches no lock and reports a B2 pass the app did not earn, while a negative
# utime makes a window's CPU delta larger than the CPU the process actually spent.
UNSIGNED_INT_PATTERN: Final = re.compile(snapshot.DIGITS)

COMMAND_TIMEOUT_SECONDS: Final = 60

PROC_STAT_UTIME_INDEX: Final = 11

PROC_STAT_INDEX_STIME: Final = 12

MIN_PROC_STAT_FIELDS: Final = 13

# `/proc/<pid>/stat` counts CPU in kernel clock ticks, and the ticks per second is a kernel constant
# (`getconf CLK_TCK`) that is not 100 on every device. It is probed per run through
# `device_probes.AdbDevice.read_process_cpu_clock_ticks` and the run fails when the probe cannot
# answer, because scaling a CPU percentage by an assumed rate misreports every CPU criterion.


# The arm guard's two provable facts. The live component is a deterministic read — the home slot
# names it in full — while which static image a baseline carries is not, so the baseline's identity is
# bounded by the median luminance of the home screen, which refuses rather than guesses when it lands
# between the two. The live arm is compared as a whole component rather than by a substring of its
# text: another package shipping a service with the same class name would otherwise be admitted as the
# wallpaper under test, and every CPU and drain figure this protocol records would be attributed to
# the wrong process.
COMPONENT_INFO_PATTERN: Final = re.compile(r"^ComponentInfo\{(.*)\}$")

LUMA_STRIDE: Final = 8

LUMA_WEIGHTS: Final = (0.2126, 0.7152, 0.0722)

LUMA_MAX: Final = 255.0

MEDIAN_LUMA_NOTE: Final = "recorded, not gated: the OEM stock wallpaper on this device is a dark image"

# How the device's identity is recorded. The digest is salted so that it is meaningful only inside
# this project's own state files, and truncated because it is only ever compared for equality.
DEVICE_ID_SALT: Final = "godaniya-126 device|"

DEVICE_ID_CHARS: Final = 12


def parse_battery_output(output: str) -> tuple[int, int, int]:
    """
    Extract charge counter (uAh), level (%), and voltage (mV) from `dumpsys battery`.

    Every field is required. A missing field is raised rather than defaulted, because a battery
    probe that stopped reporting would otherwise look like a device drawing nothing.
    """
    values: list[int] = []
    for pattern, name in (
        (CHARGE_COUNTER_PATTERN, "Charge counter"),
        (BATTERY_LEVEL_PATTERN, "level"),
        (BATTERY_VOLTAGE_PATTERN, "voltage"),
    ):
        match = pattern.search(output)
        if match is None:
            detail = f"dumpsys battery output carried no {name} field; refusing to read it as zero"
            raise device_probes.ProbeError(detail)
        values.append(int(match.group(1)))
    return values[0], values[1], values[2]


def parse_unsigned_int(raw: str) -> int | None:
    """Read a device's non-negative decimal integer, or None when the text is not one."""
    return int(raw) if UNSIGNED_INT_PATTERN.fullmatch(raw) else None


def parse_proc_stat_cpu_seconds(stat_content: str, clk_tck: int) -> float | None:
    """
    Parse utime + stime from a `/proc/<pid>/stat` line and return total CPU seconds.

    `clk_tck` is required rather than defaulted: the tick rate is a kernel constant that is not 100 on
    every device, and scaling by a guess would misreport every CPU percentage the budget is judged on.
    """
    if clk_tck <= 0:
        detail = f"a CPU-tick rate of {clk_tck} cannot scale a tick count"
        raise device_probes.ProbeError(detail)
    close = stat_content.rfind(")")
    if close == -1:
        return None
    parts = stat_content[close + 1 :].split()
    # After the closing parenthesis the first field is `state`, so utime (field 14) and stime
    # (field 15) are at indices 11 and 12. Splitting on whitespace instead would misparse whenever
    # the parenthesised comm field contains a space.
    if len(parts) < MIN_PROC_STAT_FIELDS:
        return None
    # The tokens are read as non-negative decimals, not handed to `int()`: a tick count cannot be
    # negative, and `int()` would take one. A start below zero would make the window's delta larger
    # than the CPU the process actually spent, and the delta is the only check downstream — it refuses
    # a counter that went *backwards*, not one that began below the origin.
    utime = parse_unsigned_int(parts[PROC_STAT_UTIME_INDEX])
    stime = parse_unsigned_int(parts[PROC_STAT_INDEX_STIME])
    if utime is None or stime is None:
        return None
    return (utime + stime) / float(clk_tck)


def parse_total_pss_kb(mem_output: str) -> int | None:
    """Return the `TOTAL` PSS line of a `dumpsys meminfo` dump, in kB."""
    match = TOTAL_PSS_PATTERN.search(mem_output)
    return int(match.group(1)) if match else None


def parse_api_level(output: str) -> int:
    """Read the SDK level from `getprop ro.build.version.sdk`, refusing anything unexpected."""
    stripped = output.strip()
    if not SDK_PATTERN.match(stripped):
        detail = f"ro.build.version.sdk read back as {stripped!r}, which is not an API level"
        raise device_probes.ProbeError(detail)
    return int(stripped)


def wallpaper_pid(device: device_probes.AdbDevice) -> int | None:
    """
    Read the wallpaper process id, refusing an answer that cannot be read as one.

    `device_probes.get_wallpaper_pid` reads `pidof` and answers `None` when nothing matches. A token
    that is *not* a process id is a different thing, and that reader converts it with `int()` after
    an `isdigit()` test, so a digit run past `int()`'s limit raises `ValueError` from inside it.
    `ValueError` is not one `main` catches, so a corrupted response reached the operator as a
    traceback rather than the `ERROR:` line every other unreadable probe produces.

    The translation is made here rather than in the device-layer reader because that reader is shared
    with the repository's other harnesses and carries the same unbounded conversion at four sites;
    widening its contract is its own change, and this slice owes its own callers the named refusal.
    `None` still means exactly what it means there — no live wallpaper process — because a response
    nobody could read is not evidence of one.
    """
    try:
        return device.get_wallpaper_pid()
    except ValueError as error:
        detail = (
            f"the wallpaper process id probe answered something that is not a process id ({error}), so "
            "the wallpaper's process cannot be identified; refusing rather than reading it as no live "
            "process"
        )
        raise device_probes.ProbeError(detail) from error


def read_process_uid(device: device_probes.AdbDevice, pid: int | None) -> int | None:
    """
    Read the owning UID of a process from `/proc/<pid>`, or None when it cannot be read.

    A UID is non-negative, so a negative read is a failed or malformed one rather than a process's
    owner. Returning it would not stop at this function: `phase_resources` refuses only `None`, and the
    wake-lock predicate would be built as `uid=-1`, which matches no lock and reports the app as
    holding none — a B2 pass from a read that answered nothing.
    """
    if pid is None or pid <= 0:
        return None
    output = device.run_adb(["shell", "stat", "-c", "%u", f"/proc/{pid}"]).decode(errors="replace").strip()
    return parse_unsigned_int(output)


def require_clk_tck(device: device_probes.AdbDevice) -> int:
    """
    Probe the device's kernel clock-tick rate, refusing to run without a real one.

    `device_probes.read_process_cpu_clock_ticks` reads `getconf CLK_TCK`. When it cannot answer, the
    CPU criteria cannot be scaled correctly, so the run fails loudly instead of assuming 100.

    "Cannot answer" includes answering with something that cannot be converted: that reader tests the
    text with `str.isdigit()` and then hands it to `int()`, so a digit run past `int()`'s limit — or a
    character `isdigit()` accepts and `int()` does not, such as `"²"` — raises `ValueError` from
    inside it. `ValueError` is not one `main` catches, so a corrupted response reached the operator as
    a traceback rather than the `ERROR:` line this refusal is. The translation is made here rather
    than in the device-layer reader because that reader is shared with the repository's other
    harnesses and carries the same unbounded conversion at four sites; widening its contract is its
    own change, and this slice owes its own callers the named refusal.
    """
    try:
        clk_tck = device.read_process_cpu_clock_ticks()
    except ValueError as error:
        detail = (
            f"the CLK_TCK probe answered something that is not a tick rate ({error}), so process CPU "
            "ticks cannot be converted to seconds; refusing to scale every CPU criterion by an "
            "assumed rate"
        )
        raise device_probes.ProbeError(detail) from error
    if clk_tck is None or clk_tck <= 0:
        detail = (
            "the device did not report its CLK_TCK rate, so process CPU ticks cannot be converted to "
            "seconds; refusing to scale every CPU criterion by an assumed rate"
        )
        raise device_probes.ProbeError(detail)
    return clk_tck


def take_battery_sample(device: device_probes.AdbDevice, pid: int | None, clk_tck: int) -> snapshot.BatterySample:
    """Read the battery fuel gauge plus the process CPU and PSS counters."""
    battery_output = device.run_adb(["shell", "dumpsys", "battery"]).decode(errors="replace")
    charge_uah, level_pct, voltage_mv = parse_battery_output(battery_output)

    cpu_seconds: float | None = None
    if pid is not None and pid > 0:
        stat_output = device.run_adb(["shell", "cat", f"/proc/{pid}/stat"]).decode(errors="replace")
        cpu_seconds = parse_proc_stat_cpu_seconds(stat_output, clk_tck)

    mem_output = device.run_adb(["shell", "dumpsys", "meminfo", contract.PACKAGE_NAME]).decode(errors="replace")
    return snapshot.BatterySample(
        # Monotonic, not wall time: the window's duration and every rate derived from it come from the
        # difference of two of these, and a clock correction during a fifteen-minute window would
        # otherwise rescale the current or make the window negative. Wall time is for `recorded_at`.
        timestamp=time.monotonic(),
        charge_counter_uah=charge_uah,
        level_pct=level_pct,
        voltage_mv=voltage_mv,
        process_cpu_seconds=cpu_seconds,
        total_pss_kb=parse_total_pss_kb(mem_output),
    )


def census_entry_block(  # noqa: PLR0913 — the dump, the two patterns, and the three names it refuses by
    dump: str,
    census_pattern: re.Pattern[str],
    entry_pattern: re.Pattern[str],
    *,
    probe: str,
    census_line: str,
    entry_shape: str,
) -> list[str]:
    """
    Return the entry lines of a censused dump section, refusing unless they account for the census.

    The census alone is not a check. A dump truncated after its census line still carries the count,
    and a parser that reads only "does the census exist" then reports a legitimate zero from output
    that lists nothing at all — a fabricated pass for the budget that measures it. Requiring the
    enumerated entries to *equal* the declared count is what makes the census mean something, and it
    fails in both directions: fewer entries is a truncated dump, more is a shape the probe does not
    know that the count was never meant to include.

    The block runs from the census line to the first line that is neither an entry nor indented
    deeper than the census, so a later section cannot inflate it. That boundary is not hypothetical:
    this device's alarm dump prints `Past-due non-wakeup alarms: 1` followed by
    `ELAPSED #1: Alarm{...}` in exactly the entry shape, four hundred lines below the pending-alarm
    census, and a scan of the whole dump counts it. Multi-line entries are why the boundary is drawn
    by indentation rather than by "the first line that is not an entry": an alarm entry is an
    `Alarm{...}` header followed by six or more `key=value` continuation lines, none of which are
    entries.

    A line inside the block that is neither an entry nor a continuation of one is a third failure and
    is refused too, because reconciliation alone cannot see it: a block holding a malformed entry
    beside exactly the declared number of recognised ones reconciles perfectly. A continuation is
    identified by indentation — it is deeper than the entry it belongs to — which is the only
    structural fact the three dumps share, so it is what the check is built on.

    `probe` names the dump for the message, `census_line` is the literal line required of it, and
    `entry_shape` is what one entry looks like, so that a refusal says which failure it is rather
    than only that something was wrong.
    """
    census = census_pattern.search(dump)
    if census is None:
        detail = (
            f"the {probe} carried no {census_line} census, so it cannot be read as a count of its "
            f"entries; refusing to report a zero from output that lists none"
        )
        raise device_probes.ProbeError(detail)
    declared = int(census.group(1))
    lines = dump.splitlines()
    census_index = dump.count("\n", 0, census.start())
    census_text = lines[census_index] if census_index < len(lines) else ""
    indent = len(census_text) - len(census_text.lstrip())
    entries: list[str] = []
    entry_indent: int | None = None
    for line in lines[census_index + 1 :]:
        if not line.strip():
            continue
        if entry_pattern.match(line):
            entries.append(line)
            entry_indent = len(line) - len(line.lstrip())
            continue
        line_indent = len(line) - len(line.lstrip())
        if line_indent <= indent:
            break
        # A line inside the block that is not an entry is a continuation of one — the alarm dump
        # prints six or more `key=value` lines under each `Alarm{...}` header, and the jobscheduler
        # dump more below each `JOB`. A continuation is *deeper indented than the entry it belongs
        # to*, which is what tells it apart from an entry or a header the pattern did not recognise:
        # such a line either appears before any entry (a block that holds content under a census of
        # zero) or sits at the entry's own depth. Skipping those silently was the same defect as
        # reading a count from a line that was never the census: a malformed entry could sit in the
        # block while the recognised ones reconciled exactly, so the dump was accepted and the
        # unrecognised entry counted as nothing.
        if entry_indent is None or line_indent <= entry_indent:
            detail = (
                f"the {probe}'s {census_line} census block holds a line that is neither an entry "
                f"shaped like {entry_shape} nor a continuation of one: {line.strip()!r}; the census "
                "cannot be reconciled against a block it does not describe"
            )
            raise device_probes.ProbeError(detail)
    if len(entries) < declared:
        detail = (
            f"the {probe} declares {declared} entries but the block below its {census_line} census "
            f"lists {len(entries)}: the dump is truncated, or an entry shaped like {entry_shape} was "
            f"not recognised"
        )
        raise device_probes.ProbeError(detail)
    if len(entries) > declared:
        detail = (
            f"the {probe} declares {declared} entries but its census block lists {len(entries)}: a "
            f"line matching {entry_shape} that the census does not count is inside the block"
        )
        raise device_probes.ProbeError(detail)
    return entries


def parse_wakelock_count(dump: str, app_uid: int) -> int:
    """
    Count the wake locks a `dumpsys power` dump attributes to one UID.

    The dump's own `Wake Locks: size=<n>` census is required *and* the enumerated locks must account
    for it, for the reason `census_entry_block` gives. A dump that carries the census and no lock for
    this UID is a real zero.

    Every lock type is counted before the UID is applied, not `PARTIAL_WAKE_LOCK` alone. The census
    counts the whole device and this device's `Wake Locks: size=1` is a `DOZE_WAKE_LOCK`, so a
    partial-only scan could never be reconciled with the census and the census would go unchecked.
    The B2 budget is about locks the app holds, whatever their type, so widening the predicate to
    match the census also matches the budget.
    """
    entries = census_entry_block(
        dump,
        POWER_WAKELOCK_CENSUS_PATTERN,
        WAKE_LOCK_ENTRY_PATTERN,
        probe="power dump",
        census_line="`Wake Locks: size=`",
        entry_shape="`<TYPE>_WAKE_LOCK '<name>' ACQ=… (uid=<uid> …)`",
    )
    # The uid is matched as a whole token, not as a prefix of one: a lock line for uid 10026 contains
    # the text `uid=1002`, so a prefix test would attribute another process's wake lock to an app
    # whose own uid happens to be a prefix of it, and report a B2 failure the app did not cause.
    uid_field = re.compile(rf"\buid={app_uid}\b")
    return sum(1 for line in entries if uid_field.search(line))


def parse_alarm_count(dump: str, package: str = contract.PACKAGE_NAME) -> int:
    """
    Count the pending alarms a `dumpsys alarm` dump attributes to one package.

    As with the power and jobscheduler probes, the dump's own `<n> pending alarms:` census is
    required *and* the enumerated alarms must account for it, for the reason `census_entry_block`
    gives.
    """
    entries = census_entry_block(
        dump,
        ALARM_CENSUS_PATTERN,
        ALARM_ENTRY_PATTERN,
        probe="alarm dump",
        census_line="`pending alarms:`",
        entry_shape="`<TYPE> #<n>: Alarm{…}`",
    )
    # The package is matched as a whole token, not as a substring, for the reason the uid is: an alarm
    # owned by a package such as `…astronomicalclockswallpaper.debug2` contains this app's name as a
    # prefix, and counting it would report a B2 failure the app did not cause. The dump prints the
    # package as the last token inside `Alarm{...}`, so it is delimited there in the text.
    #
    # Attribution runs over the census block rather than the whole dump, which is what stops an alarm
    # that is *not* pending from counting as one: this device's `Past-due non-wakeup alarms:` section
    # lists fired alarms that still name their owner in the same `Alarm{...}` shape.
    package_field = re.compile(rf"(?<![\w.]){re.escape(package)}(?![\w.])")
    return sum(1 for line in entries if package_field.search(line))


def count_held_wakelocks(device: device_probes.AdbDevice, app_uid: int | None) -> int:
    """Count the wake locks of any type `dumpsys power` attributes to the app's UID."""
    if app_uid is None:
        detail = "no UID was resolved for the wallpaper process, so wake locks cannot be attributed"
        raise device_probes.ProbeError(detail)
    output = device.run_adb(["shell", "dumpsys", "power"]).decode(errors="replace")
    return parse_wakelock_count(output, app_uid)


def count_alarms(device: device_probes.AdbDevice) -> int:
    """Count the pending alarms `dumpsys alarm` attributes to the wallpaper package."""
    output = device.run_adb(["shell", "dumpsys", "alarm"]).decode(errors="replace")
    return parse_alarm_count(output)


def parse_job_count(dump: str, package: str = contract.PACKAGE_NAME) -> int:
    """
    Count the JobScheduler jobs a package holds in a `dumpsys jobscheduler` dump.

    The dump's own `Registered <n> jobs:` census is required *and* the enumerated jobs must account
    for it, for the reason `census_entry_block` gives. A dump that carries the census and no job for
    the package is a real zero.

    Every job line must also be attributable to a package. The census check counts entries, so a job
    line the attribution cannot parse would otherwise be counted towards the census, dropped from the
    per-package total, and reported as "the app holds no such job" — the silent drop this refusal
    replaces.
    """
    entries = census_entry_block(
        dump,
        JOBSCHEDULER_CENSUS_PATTERN,
        JOB_ENTRY_PATTERN,
        probe="jobscheduler dump",
        census_line="`Registered <n> jobs:`",
        entry_shape="`JOB [<namespace>:]#<uid>/<id>: <hash> <component>`",
    )
    unattributable = [line for line in entries if JOB_LINE_PATTERN.match(line) is None]
    if unattributable:
        detail = (
            f"the jobscheduler dump lists {len(unattributable)} job lines whose component cannot be "
            f"attributed to a package, so the per-package count would silently drop them; the first "
            f"is {unattributable[0].strip()!r}"
        )
        raise device_probes.ProbeError(detail)
    # Every entry line was shown above to match exactly once, so counting over the rejoined block is
    # the same as counting per line, and it keeps the pattern's own match object for the package.
    return sum(1 for match in JOB_LINE_PATTERN.finditer("\n".join(entries)) if match.group(1) == package)


def count_jobs(device: device_probes.AdbDevice) -> int:
    """Count the JobScheduler jobs `dumpsys jobscheduler` attributes to the wallpaper package."""
    output = device.run_adb(["shell", "dumpsys", "jobscheduler"]).decode(errors="replace")
    return parse_job_count(output)


def read_batterystats_summary(device: device_probes.AdbDevice) -> str | None:
    """Read the historical per-app CPU lines from `dumpsys batterystats` as corroborating evidence."""
    output = device.run_adb(["shell", "dumpsys", "batterystats", contract.PACKAGE_NAME]).decode(errors="replace")
    keys = ("Total cpu time:", "Fg Service for:", "Total running:")
    lines = [line.strip() for line in output.splitlines() if any(key in line for key in keys)]
    return ", ".join(lines) if lines else None


def read_source_revision() -> str:
    """Read the source revision of this working tree."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],  # noqa: S607
        capture_output=True,
        check=True,
        text=True,
    )
    return result.stdout.strip()


def read_apk_sha256(device: device_probes.AdbDevice) -> str:
    """
    Read the SHA-256 of the APK as it is *installed on the device*, or refuse.

    The record's `apk_sha256` is the identity of the build a window measured, and every report row
    that aggregates windows is gated on it: `check_measurement_identity` refuses a set that mixes
    two. Hashing the host checkout's `app/build/outputs/apk/debug/app-debug.apk` answered a
    different question — the digest of the artifact on this machine, which need not be the build the
    device is running — and answered it with `None` on a machine that never built the APK, so a
    record could carry "unknown build" as though that were an identity.

    Both steps are required to answer: a package that is not installed has no `base.apk` to hash, and
    a device without `sha256sum` returns a shell error that is not a digest. Either is a refusal
    rather than a null, because a null is what the field must never carry for a window that ran.
    """
    digest = device.read_installed_apk_sha256()
    if digest is None:
        detail = (
            f"the SHA-256 of {contract.PACKAGE_NAME}'s installed base.apk could not be read, so the "
            f"record cannot say which build this window measured"
        )
        raise device_probes.ProbeError(detail)
    return digest


# adb presents a wirelessly-debugged device under more than one selector. An explicit connection is
# `host:port`; the devices adb discovers itself are published as mDNS service names shaped
# `adb-<serial>-<suffix>._adb-tls-connect._tcp` (the older pairing form is `_adb._tcp`). Neither
# names the hardware: the port and the service suffix belong to the transport and change with it, so
# a digest of either splits one device's records or merges two devices'.
TRANSPORT_SERVICE_MARKERS: Final = ("._adb-tls-connect._tcp", "._adb._tcp")


def is_transport_selector(serial: str) -> bool:
    """Return whether an adb serial is a transport selector rather than a hardware serial."""
    if ":" in serial:
        return True
    return serial.startswith("adb-") and any(marker in serial for marker in TRANSPORT_SERVICE_MARKERS)


def read_hardware_serial(device: device_probes.AdbDevice) -> str | None:
    """
    Read the device's own serial property, or None when no stable handle can be read.

    This is the identity behind a transport selector rather than a second opinion on a USB serial:
    `adb devices` reports a wirelessly-debugged device as `host:port` or as an mDNS service name,
    which are endpoints of the transport and not properties of the hardware. The serial property is
    the handle the device itself reports, and it survives a reconnect that changes either.
    """
    for prop in ("ro.serialno", "ro.boot.serialno"):
        try:
            output = device.run_adb(["shell", "getprop", prop])
        except (subprocess.SubprocessError, OSError):
            # One property being unreadable does not mean the other is: a device that does not
            # expose `ro.serialno` may still answer for `ro.boot.serialno`, and the refusal below
            # names the case where neither could be read.
            continue
        value = output.decode(errors="replace").strip()
        # `getprop` prints an empty line for an unset property, and some builds print `unknown`;
        # neither is a device handle, so neither is hashed as though it named one.
        if value and value != "unknown":
            return value
    return None


def device_identity(device: device_probes.AdbDevice) -> str:
    """
    Name the device a record was measured on, without naming the device.

    The serial is the only stable handle the harness has on which physical device a window ran on,
    and it cannot be recorded as it stands: `docs/device-testing.md` keeps the model, OEM, and serial
    off public surfaces, and `phase_report` prints every identity field. A salted digest distinguishes
    one device from another while disclosing neither, and it is what stops two devices' records from
    aggregating into one verdict.

    A `host:port` serial or an `adb-…._adb-tls-connect._tcp` service name is adb's wireless-debugging
    *transport selector*, not a device handle: the port and the service suffix change on every
    reconnect, and an address can be reused by another device. Hashing either would make one
    physical device's records look like several devices' — which `report` refuses as a mixed set —
    and two devices' records look like one. When the serial is a selector, the digest is taken from
    the hardware serial the device reports; when that cannot be read, the record is refused rather
    than stamped with a selector that says nothing about the device.
    """
    serial = device.serial
    if not serial:
        detail = "the target device reported no serial, so a record cannot say which device it measured"
        raise device_probes.ProbeError(detail)
    if is_transport_selector(serial):
        hardware_serial = read_hardware_serial(device)
        if hardware_serial is None:
            detail = (
                f"the target device was reached over the transport selector {serial!r}, and its own "
                "serial property could not be read, so a record cannot say which device it measured"
            )
            raise device_probes.ProbeError(detail)
        serial = hardware_serial
    return hashlib.sha256(f"{DEVICE_ID_SALT}{serial}".encode()).hexdigest()[:DEVICE_ID_CHARS]


def build_record(
    device: device_probes.AdbDevice, phase: str, duration_seconds: float, **values: object
) -> snapshot.Record:
    """Assemble one record, stamping the device and build identity every report row has to carry."""
    api_level = parse_api_level(device.run_adb(["shell", "getprop", "ro.build.version.sdk"]).decode(errors="replace"))
    revision_val = values.pop("revision", None)
    revision = str(revision_val) if revision_val is not None else read_source_revision()
    return snapshot.Record(
        phase=phase,
        recorded_at=dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        revision=revision,
        apk_sha256=read_apk_sha256(device),
        api_level=api_level,
        duration_seconds=duration_seconds,
        # The device is stamped here rather than passed in: every record has to carry it, so there is
        # no call site that could forget it.
        values={**values, "device_id": device_identity(device)},
    )


def emit_aborted_restore_record(
    recorder: snapshot.Recorder,
    device: device_probes.AdbDevice,
    phase: str,
    error: BaseException,
    problems: Sequence[str],
) -> None:
    """
    Persist a failed phase's restore problems when it aborted before building its own record.

    A phase collects its restore problems in a `finally` so that a failing write cannot skip the rest,
    but an exception raised by the measurement itself leaves through that same `finally` and takes the
    collected problems with it: the device is left changed and nothing on disk says so, so `report`
    cannot flag it and the next phase measures a device nobody restored. This writes the problems as a
    record of their own, named for the phase that did not finish, which is all `report` needs to print
    its device-restore failure.

    A record is written only when there is at least one problem: the record exists to carry them, and
    an empty one would look like a measurement of a phase that never ran. Building it can itself fail
    when the abort was the device going away, so that is swallowed — the original error is the one
    worth reporting, and `main` still exits non-zero on it.
    """
    if not problems:
        return
    try:
        record = build_record(
            device,
            f"{phase}_aborted",
            0.0,
            aborted=str(error),
            restore_problems=list(problems),
        )
    except (device_probes.ProbeError, subprocess.SubprocessError, OSError):
        print(f"restore problems could not be persisted for the aborted {phase} phase: {problems}", file=sys.stderr)
        return
    recorder.emit(record)


def median_luma(device: device_probes.AdbDevice) -> float:
    """
    Return the median luminance of a freshly captured screen, a bounded proxy for what is shown.

    This reads the raw screencap rather than the dial-validated capture, because a baseline arm has
    no dial to validate: the validated read raises when the live wallpaper is not the one on screen,
    which is exactly the state the baseline arms are in.

    A capture that cannot be decoded is refused as a probe error. `decode_frame` raises
    `frame.ScreencapError`, which is this module's sibling in `host.device.frame` rather than one of
    the refusals `main` catches, so it would leave the CLI printing a traceback instead of the named
    `ERROR` a garbled capture deserves — and a truncated `screencap` payload is exactly the transport
    wobble this must survive as a report rather than as a stack trace.
    """
    try:
        _, _, pixels = frame.decode_frame(device.run_adb(["exec-out", "screencap"]))
    except frame.ScreencapError as error:
        detail = f"the captured screen could not be decoded into a frame: {device_probes.error_detail(error)}"
        raise device_probes.ProbeError(detail) from error
    # The shortest channel slice covers exactly the complete triples, so the outer zip is non-strict.
    stride = contract.PIXEL_STRIDE * LUMA_STRIDE
    luma = sorted(
        sum(weight * channel for weight, channel in zip(LUMA_WEIGHTS, rgb, strict=True))
        for rgb in zip(pixels[0::stride], pixels[1::stride], pixels[2::stride], strict=False)
    )
    if not luma:
        detail = "the captured frame carried no pixels to measure"
        raise device_probes.ProbeError(detail)
    middle = len(luma) // 2
    return luma[middle] if len(luma) % 2 else (luma[middle - 1] + luma[middle]) / 2.0


def component_name(component: str) -> str:
    """Return the `package/class` inside a `ComponentInfo{...}` wrapper, or the text unchanged."""
    stripped = component.strip()
    match = COMPONENT_INFO_PATTERN.match(stripped)
    # `captured_text` is the shared helper for this: a match group is `Any`, and returning it
    # unchanged would let a non-string through a function the arm guard depends on.
    return device_probes.captured_text(match, 1) if match else stripped


def component_is_live(component: str) -> bool:
    """
    Report whether a home-wallpaper component is exactly this app's live service.

    The comparison is on the whole `package/class`, not on whether the text contains the service's
    class name: `ComponentInfo{other.pkg/…AstronomicalClocksWallpaperService}` is a different
    wallpaper, and admitting it as arm A would attribute its CPU and drain to this app.
    """
    return component_name(component) == contract.SERVICE_NAME


def component_is_static(component: str) -> bool:
    """
    Report whether a home-wallpaper component is the platform's own static wallpaper engine.

    Arm B accepts a component on the strength of it not being this app's live service, which admits
    *another package's* live wallpaper: a third-party live service is neither this app nor a static
    image, and a window measured on one would be recorded as the stock or black baseline while
    draining whatever that service costs. Requiring the platform engine closes that, and it is the
    strongest statement the component supports — which static *image* the engine carries is a
    separate, undecidable question, so this predicate does not claim one.
    """
    return component_name(component) == contract.PLATFORM_STATIC_WALLPAPER
