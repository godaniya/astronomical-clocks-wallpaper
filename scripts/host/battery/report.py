# SPDX-License-Identifier: Apache-2.0
"""
Judgement half of the battery protocol: records in, verdicts out.

`scripts/battery_protocol.py` measures; this module decides. Everything here takes the record dicts
a phase wrote and turns them into the lines `docs/battery-budget.md` is read against — the committed
budgets and their arithmetic, the pairing rule, the measurement identity a set has to share, and the
report's own exit status. None of it touches a device, and it imports nothing from the measuring
half, so the decision rules can be read and tested without one.

The dependency runs one way. `host.battery.cli` imports this module; this module imports only the
standard library, `host.battery.stats`, and `host.device.probes`.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Final

from host.battery import stats
from host.device import probes

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

# The fields that say a record was taken from the same device, build, configuration, and channel, so
# aggregating a set that mixes them would combine measurements that are not comparable. Both the
# threshold and the noise floor behind it are per device, so the device itself is part of the
# identity: two devices at the same build and API level are still two measurements. `revision` is
# deliberately not one of them: a harness revision that changes only documentation or the report's
# own aggregation does not change how a window was measured, and the reports say when that happened.
IDENTITY_FIELDS: Final = ("device_id", "apk_sha256", "api_level", "power_source", "clk_tck")

# The identity fields the phases write as integers; the other three are text. The reader below checks
# the kind against this, because the report is fed a state file it did not write: a scalar of the
# *other* kind — `"clk_tck": "100"`, `"power_source": 7` — is a value no phase produces, and reading
# it as an identity puts a value the run never measured at the head of the report's own verdicts. The
# kinds are the writers' own, checked against the records of the 2026-10-16 device pass.
INTEGER_IDENTITY_FIELDS: Final = ("api_level", "clk_tck")


def identity_value(record: Mapping[str, object], identity_field: str) -> object:
    """
    Return one record's value for an identity field, refusing a value that is not a scalar.

    The identity readers below all compare their field through a set, so the set *is* the
    deduplication: a value it cannot hold cannot be compared with any other, and one it can hold but
    no record writes — a boolean — would be compared as though it named a build or a tick rate.
    Either way the field cannot be shown to agree, which is the only thing the checks are for, so
    both are refused here rather than read.

    It is refused here rather than at each set, because the refusal is not one site's business:
    `check_measurement_identity` builds a set that raises `TypeError: unhashable type` out of a
    traceback for a list, dict or set — not the named `ERROR` this module's readers promise for
    state it did not write — and `phase_report` builds two more from `IDENTITY_FIELDS` whose
    validity today rests only on that first check happening to run before them. Stating the rule
    once means no site depends on call ordering to be correct.

    What it admits is exactly what the phase writers put in these fields, because the report is fed a
    state file it did not write. Each field is written as one kind of thing — `api_level` and
    `clk_tck` are integers, `device_id`, `apk_sha256` and `power_source` are text, and any of them may
    be `null` — so a scalar of the *other* kind is refused for the reason a `bool` is: it is a value
    no record writes. `"clk_tck": "100"` and `"power_source": 7` are the cases, and admitting them
    would let a corrupt state file pass the gate while the report printed the value as the identity
    the run was measured under — the complaint the identity check already makes about a set whose
    every value is `null`.

    That check settles the non-finite case without a rule of its own: `NaN` and `inf` are floats, and
    no identity field is written as one. It is not a hypothetical — the state file is JSON Lines read
    with `json.loads`, which accepts `NaN` and `Infinity` by default, so a hand-edited file reaches
    here with a float in an identity field.

    `bool` is refused for the reason `finite_number` gives: it is an `int` in Python, so
    `"clk_tck": true` would read as one tick and `"api_level": false` as API 0. It is, strictly, a
    scalar, and that is exactly why it has to be named: nothing a record writes for an identity
    field is a truth value. A null is admitted, because `"apk_sha256": null` is the legitimate
    "unknown build" every pre-build record carries — refusing an unknown identity is the identity
    check's decision, not this reader's.
    """
    value = record.get(identity_field)
    if isinstance(value, bool) or (value is not None and not isinstance(value, str | int | float)):
        detail = (
            f"a {record.get('phase')!r} record's {identity_field} is {value!r}, which is not a scalar, "
            "so it cannot be read as a measurement identity"
        )
        raise probes.ProbeError(detail)
    expected = int if identity_field in INTEGER_IDENTITY_FIELDS else str
    if value is not None and not isinstance(value, expected):
        written_as = "integer" if expected is int else "text"
        detail = (
            f"a {record.get('phase')!r} record's {identity_field} is {value!r}, which is not the "
            f"{written_as} this field is written as, so it cannot be read as a measurement identity"
        )
        raise probes.ProbeError(detail)
    return value


def check_measurement_identity(records: Sequence[Mapping[str, object]]) -> None:
    """
    Refuse a record set that mixes builds, API levels, power modes, or tick rates.

    Every record names the identity it was measured under. Aggregating records that disagree on any of
    it would combine measurements that are not comparable, so the report refuses and names the
    distinct values instead of producing one verdict from two builds. A field a record does not carry
    at all is not a disagreement: an older phase record that never recorded the field simply does not
    bound it. A field the record *does* carry with a null value is a value, not an absence — a record
    written before the APK was built carries `"apk_sha256": null`, meaning "unknown build", and that
    must not aggregate with a named one.

    A value that is not a scalar of the kind the field is written as is neither compared nor skipped:
    `identity_value` refuses it, because the set is the comparison, and a value the set cannot hold,
    or holds without that value being an identity of that field, cannot be shown to agree with the
    others.
    """
    for identity_field in IDENTITY_FIELDS:
        values = {identity_value(record, identity_field) for record in records if identity_field in record}
        if not values:
            continue
        if values == {None}:
            # Every record that carries the field says "unknown", which is not an identity any more
            # than two disagreements are: the set is homogeneous and still cannot say which build it
            # measured, so aggregating it would produce a verdict whose subject is unnamed.
            detail = (
                f"every record that carries {identity_field} records no value for it, so the set cannot "
                "say which measurement identity it was taken under; re-run the phases against one build "
                "and configuration"
            )
            raise probes.ProbeError(detail)
        if len(values) > 1:
            named = ", ".join("unknown" if value is None else str(value) for value in sorted(values, key=str))
            detail = (
                f"the record set mixes {identity_field} values ({named}), so it combines measurements "
                "from different measurement identities; re-run the phases against one build and configuration"
            )
            raise probes.ProbeError(detail)


def check_budget(label: str, value: float | None, budget: float, unit: str) -> stats.Verdict:
    """Build one pass/fail verdict, refusing to pass a budget that was never measured."""
    if value is None:
        return stats.Verdict(
            label,
            stats.VerdictStatus.NOT_MEASURED,
            f"{label}: NOT MEASURED — no value was recorded, so the budget is neither passed nor failed",
        )
    status = stats.VerdictStatus.PASS if value <= budget else stats.VerdictStatus.FAIL
    return stats.Verdict(label, status, f"{label}: {status.value} — {value:.4f}{unit} against {budget}{unit}")


def collect_restore_problems(records: Sequence[Mapping[str, object]]) -> list[str]:
    """
    Collect every restore problem the records carry, so a failed restore is never silent.

    A record that does not carry the field is a record whose phase collected no problems, which is
    what the field being absent means. That absence is a membership test and not `record.get(...) is
    None`, because `dict.get` conflates the two cases: it answers `None` for a record that never had
    the key and for an explicit `"restore_problems": null` alike, so a null would have been skipped as
    though the phase had written a list of no problems. The key being present is what makes its value
    readable, and a present value has to be a list. A record that carries it with something other than
    a list is refused rather than ignored: a failed restore is the one thing on a record that says the
    device was left changed, and reading `"airplane mode was not restored"` — a string where the
    phases write a list — as no problem would let the report exit zero over an explicitly recorded
    one.
    """
    problems: list[str] = []
    for record in records:
        if "restore_problems" not in record:
            continue
        found = record["restore_problems"]
        if not isinstance(found, list):
            detail = (
                f"a {record.get('phase')!r} record carries restore_problems={found!r}, which is not a "
                "list, so whether its restore succeeded cannot be read from this state file"
            )
            raise probes.ProbeError(detail)
        problems.extend(str(problem) for problem in found)
    return problems


def short_window_reason(record: Mapping[str, object]) -> str | None:
    """
    Return why a record's window is not the length its criterion documents, or None when it is.

    The CLI refuses a `--minutes` below the documented minimum, but the report is fed a state file it
    did not write: it may have been recorded by an older harness, by a hand-edit, or by a phase whose
    clock was not the one asked for. A record that cannot be shown to have run for its documented
    length is not the measurement the criterion is defined on, so it is named and excluded from the
    aggregation rather than averaged in as though a six-second window were a fifteen-minute one.
    """
    phase = str(record.get("phase"))
    minimum = stats.MINIMUM_SECONDS_BY_PHASE.get(phase)
    if minimum is None:
        return None
    duration = record.get("duration_seconds")
    threshold = minimum * stats.MINIMUM_DURATION_TOLERANCE
    # This reader is deliberately not routed through `finite_number`: its refusal is a returned reason
    # rather than a raised `ProbeError`, and a negative duration is a legitimate input that the
    # below-threshold branch already names. The `bool` check is still `finite_number`'s first rule, for
    # the same reason — `true` is an `int`, so it would reach the threshold comparison below as a
    # 1.0-second window and be reported as a window that ran one second, a length the record does not
    # record. The guard covers absence and a value that is not a length of time alike, so its message
    # names the value it saw rather than asserting the field is missing.
    if isinstance(duration, bool) or not isinstance(duration, int | float):
        return (
            f"a {phase} record carries {duration!r} for `duration_seconds`, which is not a length of "
            f"time, so its window cannot be shown to be the documented {minimum / 60.0:.0f} minutes"
        )
    # `inf` and `nan` are written by a hand-edit or a corrupt record and neither is below the
    # threshold — `nan` is not below anything — so a comparison alone would admit them as windows of
    # the documented length. The CLI refuses them by name for the same reason; so does this.
    if not math.isfinite(duration):
        return (
            f"a {phase} record's window ran {duration!r}s, which is not a finite length of time, so it "
            f"cannot be shown to be the documented {minimum / 60.0:.0f} minutes"
        )
    if duration < threshold:
        return (
            f"a {phase} record's window ran {duration:.1f}s, below the documented "
            f"{minimum / 60.0:.0f} minutes ({threshold:.0f}s at the {stats.MINIMUM_DURATION_TOLERANCE:.0%} tolerance)"
        )
    return None


def black_baseline_verdict(declared_reason: str | None) -> stats.Verdict:
    """
    Build B4's secondary-baseline verdict from the run's declaration, or from its absence.

    The black static baseline is required only where the device permits setting one, and the harness
    cannot tell "this device cannot set a static wallpaper" from "this run did not try": both leave the
    state file without those windows. Inferring the exemption from that absence is what let a run skip
    the document's secondary baseline and still exit zero, so the exemption is a declaration instead \u2014
    `report --black-unavailable <reason>`. A run without one carries the criterion as unmeasured, which
    gates like any other unmeasured criterion; a run with one has the reason quoted into the line, so
    the declaration is part of the output the report document carries.
    """
    if declared_reason:
        return stats.Verdict(
            "B4 vs black",
            stats.VerdictStatus.DEVICE_LIMITED,
            "B4 vs black: NOT MEASURED (DEVICE-LIMITED) \u2014 the run declared that this device cannot "
            f"set a static wallpaper: {declared_reason}. That baseline is required only where the device "
            "permits setting one, so the dark-image comparison is left uncalibrated rather than assumed "
            "equal to stock",
        )
    return stats.Verdict(
        "B4 vs black",
        stats.VerdictStatus.NOT_MEASURED,
        "B4 vs black: NOT MEASURED - no black baseline windows were recorded and the run did not "
        "declare the device unable to set one, so the document's secondary baseline is unmeasured "
        "rather than exempt; pass --black-unavailable <reason> to record that the device is the reason",
    )


def b4_baseline_verdicts(
    pairs: Sequence[tuple[Mapping[str, object], Mapping[str, object]]],
    *,
    black_unavailable: str | None = None,
) -> list[stats.Verdict]:
    """
    Build B4's verdicts, one block per documented baseline rather than one per recorded baseline.

    A block per *observed* baseline is what let a stock-only state file carry a complete-looking
    verdict: the secondary comparison was simply absent, and nothing in the report said so. The stock
    comparison is the one B4 is gated on. The black static baseline is the document's secondary one, so
    a run without those windows says so explicitly instead of leaving the reader to notice a missing
    block \u2014 and says whether the device or the run is the reason (see `black_baseline_verdict`).

    That one-block-per-documented-baseline shape is also why a label the document does not name is
    refused rather than skipped: an arm B window labeled something else is selected by no block, so the
    pair and every measurement in it would be absent from the whole report. The label is the one field
    here whose *absence* is refused too. Everywhere else a missing field means an older revision had
    nothing to record, but an arm B window's baseline is what places the pair in a comparison at all,
    and inferring the primary baseline from a missing label would be guessing what the file meant.
    """
    verdicts: list[stats.Verdict] = []
    baseline_labels = (stats.Baseline.STOCK.value, stats.Baseline.BLACK.value)
    for _, base in pairs:
        label = base.get("baseline")
        if label not in baseline_labels:
            detail = (
                f"a visible arm B window carries baseline={label!r}, which is not one of the document's "
                f"baselines ({' and '.join(baseline_labels)}), so the pair it belongs to stands outside "
                "every comparison this report prints"
            )
            raise probes.ProbeError(detail)
    for baseline in baseline_labels:
        selected = [(live, base) for live, base in pairs if base.get("baseline") == baseline]
        if not selected:
            if baseline == stats.Baseline.BLACK.value:
                verdicts.append(black_baseline_verdict(black_unavailable))
            else:
                verdicts.append(
                    stats.Verdict(
                        f"B4 vs {baseline}",
                        stats.VerdictStatus.NOT_MEASURED,
                        f"B4 vs {baseline}: NOT MEASURED - no {baseline} baseline windows were "
                        "recorded, so the comparison the criterion is gated on was not measured",
                    )
                )
            continue
        try:
            statistics = stats.paired_statistics(
                [stats.window_rate(base) for _, base in selected], [stats.window_rate(live) for live, _ in selected]
            )
        except probes.ProbeError as error:
            verdicts.append(
                stats.Verdict(
                    f"B4 vs {baseline}",
                    stats.VerdictStatus.NOT_MEASURED,
                    f"B4 vs {baseline}: NOT MEASURED - {error} ({len(selected)} pairs recorded)",
                )
            )
            continue
        verdicts.append(
            stats.Verdict(
                f"B4 vs {baseline}",
                stats.VerdictStatus.INFO,
                f"B4 vs {baseline} relative increase: {statistics.relative_delta_pct:.3f}% "
                f"(95% CI upper {statistics.ci_95_upper_pct:.3f}%, {statistics.sample_count} pairs, "
                f"df {statistics.degrees_of_freedom}, t {statistics.t_critical}, "
                f"sigma_d {statistics.standard_deviation:.0f} uA = "
                f"{statistics.standard_deviation / statistics.mean_baseline * 100:.3f}% of the baseline)",
            )
        )
        verdicts.extend(
            check_budget(f"B4 vs {baseline} {label}", value, stats.FINAL_MAX_VISIBLE_DELTA_PCT, "%")
            for label, value in (
                ("point estimate", statistics.relative_delta_pct),
                ("CI upper bound", statistics.ci_95_upper_pct),
            )
        )
    return verdicts


def report_lines(
    records: Sequence[Mapping[str, object]], *, black_unavailable: str | None = None
) -> list[stats.Verdict]:
    """Build the pass/fail verdicts against the committed thresholds."""
    verdicts: list[stats.Verdict] = []
    problems = collect_restore_problems(records)
    if problems:
        verdicts.append(
            stats.Verdict(
                "device restore",
                stats.VerdictStatus.FAIL,
                f"DEVICE RESTORE: FAIL - {len(problems)} problem(s) were recorded",
            )
        )
        verdicts.extend(stats.Verdict("device restore detail", stats.VerdictStatus.INFO, f"  - {p}") for p in problems)

    # A window below its documented length is not the measurement its criterion is defined on, so it
    # is failed and dropped before anything is aggregated from it.
    measured = [record for record in records if short_window_reason(record) is None]
    short = [str(reason) for record in records if (reason := short_window_reason(record)) is not None]
    if short:
        verdicts.append(
            stats.Verdict(
                "window durations",
                stats.VerdictStatus.FAIL,
                f"WINDOW DURATIONS: FAIL - {len(short)} record(s) below their documented minimum",
            )
        )
        verdicts.extend(
            stats.Verdict("window duration detail", stats.VerdictStatus.INFO, f"  - {problem}") for problem in short
        )

    # B2 is a maximum across every resources record, not the last one: the state file is append-only,
    # so a rerun after a nonzero census must not hide the earlier failure behind a later clean run.
    # A count and a percentage of one core are non-negative, so `-1` is a corrupt reading rather than a
    # comfortably passing one: it sorts under B2's zero budget and under B3's 0.1% alike, so an
    # otherwise clean set carrying one would exit zero over a value the device cannot have produced.
    # The wake-lock row is bounded only by records that measured the all-type census; see
    # `wake_lock_values` for why a partial-only count is not evidence for this budget.
    wake_locks = stats.wake_lock_values(measured)
    verdicts.append(check_budget("B2 wake locks", max(wake_locks) if wake_locks else None, 0.0, ""))
    for label, key in (("B2 alarms", "alarms"), ("B2 jobs", "jobs")):
        values = stats.numeric_values(measured, "resources", key, non_negative=True)
        verdicts.append(check_budget(label, max(values) if values else None, 0.0, ""))

    hidden = stats.numeric_values(measured, "hidden", "cpu_pct", non_negative=True)
    verdicts.append(check_budget("B3 hidden CPU", max(hidden) if hidden else None, stats.MAX_HIDDEN_CPU_PCT, "%"))

    try:
        pairs = stats.alternation_pairs(measured)
    except probes.ProbeError as error:
        # Only B4 needs the pairing. The refusal is reported under B4's own label rather than a joint
        # one, because B5 is measured from the live windows themselves and is reported either way.
        verdicts.append(
            stats.Verdict("B4 pairing", stats.VerdictStatus.NOT_MEASURED, f"B4 pairing: NOT MEASURED - {error}")
        )
        pairs = []

    verdicts.extend(b4_baseline_verdicts(pairs, black_unavailable=black_unavailable))

    # B5 is the average visible CPU of the document's matrix, so the average is what is checked — one
    # line per outcome, so an unreadable reading and an absent window cannot both be reported as the
    # reason B5 has no verdict. The worst window is reported beside the mean as the observation it is.
    windows = stats.live_windows(measured)
    if not windows:
        verdicts.append(
            stats.Verdict(
                "B5 visible CPU",
                stats.VerdictStatus.NOT_MEASURED,
                "B5 visible CPU: NOT MEASURED - no live window was recorded",
            )
        )
    else:
        try:
            samples = stats.live_cpu_values(windows)
            mean_cpu_pct = stats.duration_weighted_mean(samples)
        except probes.ProbeError as error:
            verdicts.append(
                stats.Verdict(
                    "B5 visible CPU", stats.VerdictStatus.NOT_MEASURED, f"B5 visible CPU: NOT MEASURED - {error}"
                )
            )
        else:
            verdicts.append(check_budget("B5 visible CPU (mean)", mean_cpu_pct, stats.FINAL_MAX_VISIBLE_CPU_PCT, "%"))
            verdicts.append(
                stats.Verdict(
                    "B5 worst window",
                    stats.VerdictStatus.INFO,
                    f"B5 worst window observed: {max(sample.cpu_pct for sample in samples):.4f}% "
                    f"over {len(samples)} windows",
                )
            )

    # B6's growth is signed on purpose — memory can shrink over a window, and a negative growth is the
    # best result the criterion can have — so this reader is the one that does not ask for the
    # non-negative refusal.
    growth_values = stats.numeric_values(measured, "memory", "pss_growth_kb")
    verdicts.append(
        check_budget(
            "B6 PSS growth (worst run)", max(growth_values) if growth_values else None, stats.MAX_PSS_GROWTH_KB, " kB"
        )
    )
    verdicts.append(
        stats.Verdict(
            "B1 hidden frames",
            stats.VerdictStatus.OUT_OF_SCOPE,
            "B1 hidden frames: NOT MEASURED HERE - the frame counter is #125 criterion 1, which "
            "records its own producer-trace evidence under docs/testing/reports/; this protocol "
            "does not own a console that could make a zero-frame claim",
        )
    )
    return verdicts


def report_exit_code(verdicts: Sequence[stats.Verdict]) -> int:
    """
    Derive the report's exit status from its verdicts rather than from its text.

    Every verdict that is not one of `NON_GATING_STATUSES` is non-zero: a criterion that was never
    measured has not established the acceptance. The exceptions are the two statuses that name *why*
    the absence is not a failure of this run — a criterion explicitly out of scope for it (B1, which is
    #125's), and a criterion the device cannot measure at all (the black static baseline, and only
    where the run has declared the device the reason). Both are printed by the report rather than
    dropped, so the absence is recorded even though it does not gate. The rule lives on `Verdict` so
    that this function and `Verdict.is_failure` cannot disagree about it.
    """
    return 1 if any(verdict.is_failure for verdict in verdicts) else 0


def phase_report(records: Sequence[Mapping[str, object]], *, black_unavailable: str | None = None) -> int:
    """Print the aggregate report and every unrun check it can see, returning its exit status."""
    check_measurement_identity(records)
    revisions = {str(record.get("revision")) for record in records}
    api_levels = {identity_value(record, "api_level") for record in records}
    print(f"records: {len(records)}")
    print(f"source revisions: {', '.join(sorted(revisions))}")
    print(f"API levels: {', '.join(str(level) for level in sorted(api_levels, key=str))}")
    for identity_field in IDENTITY_FIELDS:
        if identity_field == "api_level":
            continue
        values = sorted(
            {identity_value(record, identity_field) for record in records if record.get(identity_field) is not None},
            key=str,
        )
        if values:
            print(f"{identity_field}: {', '.join(str(value) for value in values)}")
    print(f"committed B4 threshold: {stats.FINAL_MAX_VISIBLE_DELTA_PCT}% relative increase")
    print(f"committed B5 threshold: {stats.FINAL_MAX_VISIBLE_CPU_PCT}% of one core")
    floors = [record for record in records if record.get("phase") == "pilot_floor"]
    if floors:
        latest_floor = floors[-1]
        if latest_floor.get("noise_floor_rate_ua") is None:
            print("pilot floors in this state file: the discharge channel did not move, so it is unmeasured")
        else:
            print(
                f"pilot floors in this state file: discharge 2 sigma {latest_floor.get('noise_floor_rate_ua')} uA, "
                f"CPU 2 sigma {latest_floor.get('cpu_noise_floor_pct')}% of one core"
            )
    else:
        print(
            f"pilot floors committed with the thresholds: discharge 2 sigma {stats.PILOT_DISCHARGE_NOISE_FLOOR_UA} uA, "
            f"CPU 2 sigma {stats.PILOT_CPU_NOISE_FLOOR_PCT}% of one core ({stats.PILOT_REPORT})"
        )
    print()
    verdicts = report_lines(records, black_unavailable=black_unavailable)
    for verdict in verdicts:
        print(verdict.line)
    return report_exit_code(verdicts)
