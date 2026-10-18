# SPDX-License-Identifier: Apache-2.0
"""
Statistical comparisons, noise-floor calculation, and budget thresholds for the battery protocol.

`scripts/battery_protocol.py` measures; `host.battery.stats` and `host.battery.report` decide.
None of this module touches a device, and it imports nothing from the measuring half, so the
statistical rules and budget constants can be read and tested without one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from host.device import probes

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

# The window lengths the acceptance matrix documents. They are minimums rather than defaults: a
# shorter window is a different measurement, so `--minutes` refuses one and `report` refuses a record
# that carries one. The default is the minimum because that is the documented cost of the criterion,
# not because a longer window is worse.
MINIMUM_HIDDEN_MINUTES: Final = 10.0

MINIMUM_WINDOW_MINUTES: Final = 15.0

MINIMUM_MEMORY_MINUTES: Final = 30.0

DEFAULT_WINDOW_MINUTES: Final = MINIMUM_WINDOW_MINUTES

DEFAULT_HIDDEN_MINUTES: Final = MINIMUM_HIDDEN_MINUTES

DEFAULT_MEMORY_MINUTES: Final = MINIMUM_MEMORY_MINUTES

# The recorded wall-clock of a window that ran as documented lands within a few seconds of its
# requested length on either side; scheduling jitter is seconds and an interrupted window is minutes,
# so a 5% shortfall is the widest gap that still means "this window ran for its whole length".
MINIMUM_DURATION_TOLERANCE: Final = 0.95

# Each windowed phase's documented minimum, keyed by the phase name its records carry, so `report`
# can check a recorded duration against it without knowing how the window was requested.
MINIMUM_SECONDS_BY_PHASE: Final = {
    "hidden": MINIMUM_HIDDEN_MINUTES * 60.0,
    "visible": MINIMUM_WINDOW_MINUTES * 60.0,
    "memory": MINIMUM_MEMORY_MINUTES * 60.0,
}

# Budgets from docs/battery-budget.md. B1 is #125 criterion 1 and is deliberately not measured here:
# the frame console is that issue's, and it lands its own evidence under docs/testing/reports/
# (2026-10-12-test-125-hidden-frames-and-reboot.md) rather than through this protocol.
MAX_HIDDEN_CPU_PCT: Final = 0.1

PROVISIONAL_MAX_VISIBLE_DELTA_PCT: Final = 5.0

PROVISIONAL_MAX_VISIBLE_CPU_PCT: Final = 3.0

MAX_PSS_GROWTH_KB: Final = 6144

# The coverage a `resources` record's wake-lock count was measured with. The budget is zero wake
# locks *of any type*, so a count bounds it only when the probe reconciled every `<TYPE>_WAKE_LOCK`
# entry against the dump's census. An earlier revision enumerated `PARTIAL_WAKE_LOCK` alone and
# recorded that count under the same `wake_locks` key; those records are real measurements of the
# narrower criterion, but they are not measurements of this budget, so the record carries the
# coverage it actually had and `report` can tell the two apart. A record written before the stamp
# existed is not refused — it is simply not measured for this row.
WAKE_LOCK_COVERAGE: Final = "all-types"

# Committed before the final run from the pilot's observed noise floors, per the document's own
# anti-tuning rule; `report` reads these two constants, so a change here is what "committing the
# threshold" means. The 2026-10-13 pilot measured the live discharge channel on a device that was
# genuinely discharging: four 15-minute arm-A windows gave a mean of 366265 uA with a 2 sigma of
# 43997 uA, which is 12.0123% of the mean. That floor is wider than the provisional 5%, so the B4
# threshold rises to it, which is the document's rule working as intended: a larger tolerated
# increase makes the criterion **more permissive**, not harder, because a live-versus-baseline
# increase up to 12.0123% can now pass where 5% would have failed it. What the wider floor buys is
# honesty rather than leniency: below it this device cannot tell a real difference from its own
# variation, so the alternative to a permissive threshold is a criterion that reports a difference it
# has not resolved. The floor is a property of this device's gauge and load rather than evidence
# about the wallpaper: a worn cell and a gauge whose own step is 4.5 mAh both widen it, and it
# has to be re-measured per device. The CPU channel's floor is 0.0894% of one core, below the
# provisional 3%, so the B5 threshold stays as stated.
FINAL_MAX_VISIBLE_DELTA_PCT: Final = 12.0123  # greater of the provisional 5% and the measured floor

FINAL_MAX_VISIBLE_CPU_PCT: Final = PROVISIONAL_MAX_VISIBLE_CPU_PCT  # the floor is below the provisional

# The pilot's floors are part of the commitment, not of the working state: a state file is reset
# between the pilot and the final run precisely so the calibration cannot enter the result, so the
# floors are carried here where the thresholds they justify are.
PILOT_DISCHARGE_NOISE_FLOOR_UA: Final = 43997.06

PILOT_CPU_NOISE_FLOOR_PCT: Final = 0.0894

PILOT_REPORT: Final = "docs/testing/reports/2026-10-13-test-126-drain-comparison-on-battery.md"

# Two-sided 95% Student t critical values by degrees of freedom, from the table in NIST/SEMATECH
# e-Handbook of Statistical Methods, section 1.3.6.7.3 (retrieved 2026-10-12), which is the free
# redistillation of the standard tables. Past 30 degrees of freedom the table stops and the expansion
# at `T_TAIL_TERMS` takes over; the normal value is deliberately *not* used there.
T_CRITICAL_95_BY_DF: Final = {
    1: 12.706,
    2: 4.303,
    3: 3.182,
    4: 2.776,
    5: 2.571,
    6: 2.447,
    7: 2.365,
    8: 2.306,
    9: 2.262,
    10: 2.228,
    11: 2.201,
    12: 2.179,
    13: 2.160,
    14: 2.145,
    15: 2.131,
    16: 2.120,
    17: 2.110,
    18: 2.101,
    19: 2.093,
    20: 2.086,
    21: 2.080,
    22: 2.074,
    23: 2.069,
    24: 2.064,
    25: 2.060,
    26: 2.056,
    27: 2.052,
    28: 2.048,
    29: 2.045,
    30: 2.042,
}

NORMAL_T_CRITICAL_95: Final = 1.960

# Above the table the normal value is not good enough: the two-sided 95% t at 31 degrees of freedom
# is 2.040, and returning 1.960 there would understate the interval by 4%. The Cornish-Fisher
# expansion of the t quantile in powers of 1/nu is used instead, which reproduces the table to three
# decimals at its top and tends to the normal value as nu grows.
T_TAIL_TERMS: Final = (4.0, 96.0)

MIN_PAIRED_SAMPLES: Final = 4


class Arm(StrEnum):
    """Which wallpaper a window is recorded against."""

    LIVE = "A"
    BASELINE = "B"


class Baseline(StrEnum):
    """Which static baseline an arm B window is recorded against."""

    STOCK = "stock"
    BLACK = "black"


class VerdictStatus(StrEnum):
    """How one criterion, or one observation, came out."""

    PASS = "PASS"  # noqa: S105 — a verdict label, not a credential
    FAIL = "FAIL"
    NOT_MEASURED = "NOT MEASURED"
    # A criterion that belongs to another issue and is deliberately not measured here, so its absence
    # is not a failure of this run. B1 is #125's frame counter.
    OUT_OF_SCOPE = "OUT OF SCOPE"
    # A criterion the device cannot measure at all, so its absence is recorded rather than gated and
    # rather than left to look measured. The black static baseline is the one case: the harness never
    # swaps a wallpaper, setting one rewrites the home image, and on a production build without root
    # there is no way to put the stock image back — so the document requires that secondary baseline
    # only where the device permits setting one, and its absence is not a failure of the run while the
    # comparison the criterion is gated on stays the stock one. The report has to say so out loud,
    # which is what this status is for: silence here would read as a complete verdict. It is granted
    # only on the run's own declaration — `report --black-unavailable <reason>` — never inferred from
    # the windows being absent, because a run that simply skipped that arm leaves the same state file
    # as one on a device that cannot set a static wallpaper.
    DEVICE_LIMITED = "NOT MEASURED (DEVICE-LIMITED)"
    # A line the report prints beside the verdicts but that is not itself a pass/fail criterion.
    INFO = "INFO"


# The statuses a report may still exit zero on. This is an allowlist rather than a list of the ones
# that gate: a member added later describes something this protocol has not established, and the safe
# default for an unestablished criterion is to gate until it is deliberately listed here.
NON_GATING_STATUSES: Final = frozenset(
    {
        VerdictStatus.PASS,
        VerdictStatus.INFO,
        VerdictStatus.OUT_OF_SCOPE,
        VerdictStatus.DEVICE_LIMITED,
    }
)


@dataclass(frozen=True)
class Verdict:
    """
    One line of the report, as data rather than as text.

    The report's exit status is derived from these, so a FAIL can never be printed and still leave
    the command exiting zero: automation reads the status, not the printed string.
    """

    label: str
    status: VerdictStatus
    line: str

    @property
    def is_failure(self) -> bool:
        """Whether this verdict should make the report exit non-zero."""
        return self.status not in NON_GATING_STATUSES


@dataclass(frozen=True)
class PairedStatistics:
    """A paired comparison of two equal-length series of window rates."""

    sample_count: int
    degrees_of_freedom: int
    t_critical: float
    mean_baseline: float
    mean_treatment: float
    relative_delta_pct: float
    ci_95_upper_pct: float
    # The sd of the per-pair differences, in the same unit as the means. The interval's width is
    # `t * sd / sqrt(n)`, so this is the one number that says how many pairs a future run needs —
    # a report that carries it lets the next run's n be computed instead of guessed.
    standard_deviation: float


def t_critical_95(degrees_of_freedom: int) -> float:
    """
    Return the two-sided 95% Student t critical value for `degrees_of_freedom`.

    The table is tabulated to 30 degrees of freedom. Past it the value is *not* the normal 1.960, which
    would understate the interval: the Cornish-Fisher expansion of the t quantile in powers of 1/nu is
    used instead, as the terms above it describe. Every tabulated value is returned as tabulated, so a
    caller with two or three pairs reads 4.303 or 3.182 rather than the four-pair 3.182 the previous
    two-branch lookup collapsed them to. How many pairs a comparison needs is enforced by
    `paired_statistics`, which is where the sample count is known.
    """
    if degrees_of_freedom < 1:
        detail = f"{degrees_of_freedom} degrees of freedom admits no interval at all"
        raise probes.ProbeError(detail)
    tabulated = T_CRITICAL_95_BY_DF.get(degrees_of_freedom)
    if tabulated is not None:
        return tabulated
    z = NORMAL_T_CRITICAL_95
    first, second = T_TAIL_TERMS
    return (
        z
        + (z**3 + z) / (first * degrees_of_freedom)
        + (5 * z**5 + 16 * z**3 + 3 * z) / (second * degrees_of_freedom**2)
    )


def paired_statistics(baseline_rates: Sequence[float], treatment_rates: Sequence[float]) -> PairedStatistics:
    """
    Compare paired baseline and treatment window rates, with a 95% interval on the increase.

    The interval is the paired one: the per-pair differences remove the drift both arms share, so
    the bound reflects the measurement actually being asked about.
    """
    if len(baseline_rates) != len(treatment_rates):
        detail = f"pairing needs equal arms but got {len(baseline_rates)} and {len(treatment_rates)} windows"
        raise probes.ProbeError(detail)
    if len(baseline_rates) < MIN_PAIRED_SAMPLES:
        detail = (
            f"{len(baseline_rates)} alternations were recorded but the budget mandates at least "
            f"{MIN_PAIRED_SAMPLES} pairs"
        )
        raise probes.ProbeError(detail)
    diffs = [treatment - baseline for baseline, treatment in zip(baseline_rates, treatment_rates, strict=True)]
    mean_baseline = sum(baseline_rates) / len(baseline_rates)
    mean_treatment = sum(treatment_rates) / len(treatment_rates)
    if mean_baseline <= 0:
        detail = "the baseline mean discharge rate is not positive, so no relative increase exists"
        raise probes.ProbeError(detail)
    degrees_of_freedom = len(diffs) - 1
    t_value = t_critical_95(degrees_of_freedom)
    mean_diff = sum(diffs) / len(diffs)
    variance = sum((diff - mean_diff) ** 2 for diff in diffs) / degrees_of_freedom
    standard_error = math.sqrt(variance / len(diffs))
    relative_delta_pct = (mean_diff / mean_baseline) * 100.0
    margin_pct = (t_value * standard_error / mean_baseline) * 100.0
    return PairedStatistics(
        sample_count=len(diffs),
        degrees_of_freedom=degrees_of_freedom,
        t_critical=t_value,
        mean_baseline=mean_baseline,
        mean_treatment=mean_treatment,
        relative_delta_pct=relative_delta_pct,
        ci_95_upper_pct=relative_delta_pct + margin_pct,
        standard_deviation=math.sqrt(variance),
    )


def two_sigma_noise_floor(values: Sequence[float]) -> tuple[float, float, float]:
    """Return the mean, the sample standard deviation, and the 2-sigma half-width of a series."""
    if len(values) < MIN_PAIRED_SAMPLES:
        detail = f"a noise floor needs at least {MIN_PAIRED_SAMPLES} windows but got {len(values)}"
        raise probes.ProbeError(detail)
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    deviation = math.sqrt(variance)
    return mean, deviation, 2.0 * deviation


def finite_number(value: object, *, what: str, non_negative: bool = False) -> float:
    """
    Return one recorded field as a float, refusing a value that cannot be a measurement of it.

    Every reader in this module reads numbers out of a state file it did not write, and every one of
    them has to refuse the same things. Four of them used to hand-roll a partially overlapping guard
    of their own, and three of those were weaker than the others, so the rule lives here instead —
    one place that can be read, tested, and cannot drift from itself.

    `bool` is refused first because it is an `int` in Python: `"wake_locks": true` would otherwise
    read as one lock, and `"discharge_rate_ua": true` as a 1 uA rate. A non-number is refused because
    there is no measurement in it. A non-finite value is refused because it is the dangerous kind of
    wrong rather than merely absent: `-inf` sorts below every budget, so it passes a maximum-is-zero
    check it never measured, and `nan` is not above anything.

    `non_negative` is off by default and has to be asked for at each call site, because a signed
    quantity is the commoner case here: B6's PSS growth is signed because memory can legitimately
    shrink, and B4's verdict is a relative increase that may legitimately be negative. Only a field
    that cannot go below zero — a wake-lock count, a percentage of one core — asks for the refusal,
    so leaving it off is the default an unsigned caller gets by saying nothing.
    """
    if isinstance(value, bool) or not isinstance(value, int | float):
        detail = f"{what} is {value!r}, which is not a number, so it cannot be read as a measurement"
        raise probes.ProbeError(detail)
    if not math.isfinite(value):
        detail = f"{what} is {value!r}, which is not finite, so it cannot be read as a measurement"
        raise probes.ProbeError(detail)
    if non_negative and value < 0:
        detail = f"{what} is {value!r}, which is negative, and this field cannot be below zero"
        raise probes.ProbeError(detail)
    return float(value)


def numeric_values(
    records: Sequence[Mapping[str, object]], phase: str, key: str, *, non_negative: bool = False
) -> list[float]:
    """
    Collect one numeric field across a phase's records, refusing a value that is not a number.

    A record of another phase is not asked for the field, and a record that does not carry it at all
    does not bound it — an older revision that never recorded the field has nothing to say. A record
    that *does* carry the field with something else is a different thing: corrupt or hand-edited
    state. Skipping it would judge the budget on whichever records happened to parse, so a set
    holding one valid zero and one unreadable value would report a pass, and the unreadable record
    would be hidden behind the readable one rather than named.

    What "not a number" means is `finite_number`'s rule, so this reader, the visible-window readers,
    and the duration reader refuse the same values for the same reasons. `non_negative` is passed
    through rather than decided here, because it is a property of the field and not of the phase: B2's
    counts and B3's percentage ask for it, and B6's signed growth does not.
    """
    return [
        finite_number(record[key], what=f"a {phase} record's `{key}`", non_negative=non_negative)
        for record in records
        if record.get("phase") == phase and key in record
    ]


def wake_lock_values(records: Sequence[Mapping[str, object]]) -> list[float]:
    """
    Return the wake-lock counts that can bound the all-type budget.

    Every `resources` record's count is still read through `finite_number`, so a count that is
    present and unreadable is refused wherever it appears — including on a record that does not carry
    a coverage stamp, which is the same corrupt-state refusal `numeric_values` makes for the alarms
    and jobs rows. Only the counts whose record says it enumerated every lock type are *returned*:
    a partial-only census measures a narrower criterion, and its number cannot stand for the all-type
    count in either direction. A set holding only those records reports the row as NOT MEASURED
    rather than passing a budget nothing measured; a set that mixes them bounds the budget with the
    records that did measure it and ignores the ones that did not.
    """
    values: list[float] = []
    for record in records:
        if record.get("phase") != "resources" or "wake_locks" not in record:
            continue
        count = finite_number(record["wake_locks"], what="a resources record's `wake_locks`", non_negative=True)
        if "wake_lock_coverage" not in record:
            continue
        coverage = record["wake_lock_coverage"]
        if not isinstance(coverage, str):
            detail = f"a resources record carries wake_lock_coverage={coverage!r}, which is not a string"
            raise probes.ProbeError(detail)
        if coverage == WAKE_LOCK_COVERAGE:
            values.append(count)
    return values


def is_pilot(record: Mapping[str, object]) -> bool:
    """
    Return whether a visible record is a pilot window, refusing a `pilot` flag that is not a boolean.

    A record that does not carry the flag is a measurement. The flag is written by the pilot phase and
    not by the visible phase, so an absent key is the ordinary shape of a visible record rather than a
    revision that had nothing to record, and it means "not a pilot". A record that carries the flag
    with anything but a boolean is refused, because both selectors below filter on truthiness and
    `"false"` is a truthy string in Python: a hot live window carrying one would be filed as
    calibration and dropped from B4 and B5 alike, and a failing pair carrying one would leave the
    report exiting zero over measurements it never judged.
    """
    if "pilot" not in record:
        return False
    pilot = record["pilot"]
    if not isinstance(pilot, bool):
        detail = f"a {record.get('phase')!r} record carries pilot={pilot!r}, which is not a boolean"
        raise probes.ProbeError(detail)
    return pilot


def alternation_pairs(
    records: Sequence[Mapping[str, object]],
) -> list[tuple[Mapping[str, object], Mapping[str, object]]]:
    """
    Pair live and baseline windows from their recorded order, refusing a malformed sequence.

    Pairing the nth baseline window with the nth live window by file order would silently pair
    windows that were not taken under the same conditions; the sequence has to be an alternation
    before that pairing means anything. Pilot windows are excluded: they are the calibration, not
    the comparison, and `is_pilot` is what decides that — a flag that is not a boolean is refused
    there rather than read as one.
    """
    sequence = [record for record in records if record.get("phase") == "visible" and not is_pilot(record)]
    if not sequence:
        return []
    arms = [str(record.get("arm")) for record in sequence]
    expected = [Arm.LIVE.value, Arm.BASELINE.value] * (len(sequence) // 2)
    if len(sequence) % 2 != 0 or arms != expected:
        detail = f"the visible windows are not an A/B alternation: recorded arms {arms}"
        raise probes.ProbeError(detail)
    return list(zip(sequence[::2], sequence[1::2], strict=True))


def window_rate(record: Mapping[str, object]) -> float:
    """
    Read one window's discharge rate, refusing a record that has none or a negative one.

    An absent field and an unreadable one are separate cases because they are separate things in the
    state file: a window that recorded no rate at all — the field deleted, or written null — is one
    an older revision or a silent gauge wrote, while `true`, `-inf`, or a string is a corrupt field.
    Both refuse, and each says which it saw rather than sharing one message. The
    negative case keeps a branch of its own rather than taking `finite_number`'s, because the reason
    it is refused is this reader's: a rate below zero means the pack gained charge across the window,
    so the record is not a discharge comparison at all. That is a different statement from "this is
    not a number", and `NegativeDischargeRecordTest` pins it.
    """
    rate = record.get("discharge_rate_ua")
    if rate is None:
        detail = "a visible window recorded no discharge rate, so no comparison can be computed"
        raise probes.ProbeError(detail)
    value = finite_number(rate, what="a visible window's `discharge_rate_ua`")
    if value < 0:
        detail = (
            f"a visible window recorded a negative discharge rate ({value:.0f} uA), which means the pack "
            "gained charge across it; a state file carrying one is not a discharge comparison"
        )
        raise probes.ProbeError(detail)
    return value


def live_windows(records: Sequence[Mapping[str, object]]) -> list[Mapping[str, object]]:
    """
    Return the visible live windows that are B5 measurements, in recorded order.

    B5 is the live arm's own CPU channel — the document's B5 row names the process ticks during a
    visible home-screen window and no baseline — so its input is the live windows and not the A/B
    pairs. A live window's `cpu_pct` is the same reading whether or not the window it follows recorded
    a baseline, and B4's pairing rule is a rule about what can be *compared*: reading B5 from the pairs
    made a criterion that needs no comparison depend on one, so an unmatched final live window — which
    makes the sequence a non-alternation — discarded every live reading on the file and left B5 saying
    no live window had been recorded. Pilots are excluded for the same reason they are excluded from
    the comparison: they are the calibration, not the measurement.
    """
    return [
        record
        for record in records
        if record.get("phase") == "visible" and not is_pilot(record) and record.get("arm") == Arm.LIVE.value
    ]


@dataclass(frozen=True)
class CpuSample:
    """One live window's CPU reading, with the length of time that reading was averaged over."""

    cpu_pct: float
    duration_seconds: float


def live_cpu_values(windows: Sequence[Mapping[str, object]]) -> list[CpuSample]:
    """
    Collect each qualifying live window's CPU reading together with the window it was measured over.

    The window's length travels with the reading because B5 is a rate and the windows need not be the
    same length: the pilot's own four recorded windows ran 918.7 s, 919.8 s, 917.8 s and 914.7 s, and
    a run may ask for a different `--minutes` per window. `duration_weighted_mean` is what turns the
    samples back into the share of one core the budget is stated in.

    A percentage of one core cannot be negative, so this reader asks `finite_number` for that refusal
    too. The case that matters most here is the non-finite one: `-inf` satisfies an `isinstance`
    check and sorts below the budget, so three real readings beside one `-inf` used to average to a
    pass over a reading nothing measured.
    """
    samples: list[CpuSample] = []
    for window in windows:
        cpu = window.get("cpu_pct")
        if cpu is None:
            detail = "a live window recorded no CPU reading, so B5 has no input"
            raise probes.ProbeError(detail)
        duration = window.get("duration_seconds")
        if duration is None:
            detail = "a live window recorded no `duration_seconds`, so its CPU reading cannot be weighed"
            raise probes.ProbeError(detail)
        samples.append(
            CpuSample(
                cpu_pct=finite_number(cpu, what="a live window's `cpu_pct`", non_negative=True),
                duration_seconds=finite_number(duration, what="a live window's `duration_seconds`", non_negative=True),
            )
        )
    return samples


def duration_weighted_mean(samples: Sequence[CpuSample]) -> float:
    """
    Return the share of one core the live windows were used at, each reading weighted by its window.

    A mean over the windows counts a 60-minute window the same as a 15-minute one, which is not the
    quantity the budget is stated in: three 15-minute windows at 1% beside one 60-minute window at 8%
    is 2.75% counted per window and 5% over the time the readings came from. The criterion is a rate —
    visible CPU over at least 15 minutes — so the aggregate has to be the one that estimates a rate
    from windows of different lengths, and the unweighted mean does not.
    """
    total_seconds = sum(sample.duration_seconds for sample in samples)
    if total_seconds <= 0.0:
        detail = "the live windows add up to no measured time, so B5 has no rate to average"
        raise probes.ProbeError(detail)
    return sum(sample.cpu_pct * sample.duration_seconds for sample in samples) / total_seconds
