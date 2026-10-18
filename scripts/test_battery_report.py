#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for the report's decision rules: the budgets, the statistics, and the recorded identity.

These are the checks on `scripts/host/battery/report.py`, the half of the protocol that reads record dicts
and decides. They need no device, no window, and no phase: every input is a record as the state file
would carry it, which is what lets a criterion be tested without running one.
"""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

import pytest
import pytest_mock

from host.battery import cli as battery_cli
from host.battery import report as battery_report
from host.battery import stats as battery_stats
from host.device import probes as device_probes

INTEGER_IDENTITY_FIELDS: Final = ("api_level", "clk_tck")
TEXT_IDENTITY_FIELDS: Final = tuple(
    field for field in battery_report.IDENTITY_FIELDS if field not in INTEGER_IDENTITY_FIELDS
)
WRONG_KIND_IDENTITY_CASES: Final = (
    *(
        (field, value, "not the integer this field is written as")
        for field in INTEGER_IDENTITY_FIELDS
        for value in ("100", "36", "not-an-api-level", 3.0)
    ),
    *(
        (field, value, "not the text this field is written as")
        for field in TEXT_IDENTITY_FIELDS
        for value in (7, 100, 0.5)
    ),
)


def visible_record(  # noqa: PLR0913 - the arm, its readings, and the window shape are all its inputs
    arm: str,
    rate: object,
    *,
    cpu: object = None,
    pilot: object = False,
    baseline: str | None = None,
    duration: object = 900.0,
) -> dict[str, object]:
    """Build one visible-window record as the state file would carry it."""
    return {
        "phase": "visible",
        "arm": arm,
        "baseline": baseline,
        "discharge_rate_ua": rate,
        "cpu_pct": cpu,
        "pilot": pilot,
        "duration_seconds": duration,
        "revision": "rev",
        "api_level": 36,
    }


def pairs(count: int, live_rate: float, base_rate: float, *, cpu: float = 1.0) -> list[dict[str, object]]:
    """Build `count` whole A/B pairs in the order an alternation records them."""
    return [
        record
        for _ in range(count)
        for record in (
            visible_record("A", live_rate, cpu=cpu),
            visible_record("B", base_rate, baseline="stock"),
        )
    ]


def resources_record(**overrides: object) -> dict[str, object]:
    """Build one current-shape resources record, carrying the all-type wake-lock coverage stamp."""
    record: dict[str, object] = {
        "phase": "resources",
        "wake_locks": 0,
        "wake_lock_coverage": battery_stats.WAKE_LOCK_COVERAGE,
        "alarms": 0,
        "jobs": 0,
        "revision": "rev",
        "api_level": 36,
    }
    record.update(overrides)
    return record


def hidden_record(cpu_pct: object = 0.05, *, duration: object = 604.0, **overrides: object) -> dict[str, object]:
    """Build one hidden-window record as the state file would carry it."""
    record: dict[str, object] = {
        "phase": "hidden",
        "cpu_pct": cpu_pct,
        "duration_seconds": duration,
        "revision": "rev",
        "api_level": 36,
    }
    record.update(overrides)
    return record


def memory_record(pss_growth_kb: object = 992, *, duration: object = 1800.0, **overrides: object) -> dict[str, object]:
    """Build one memory-window record as the state file would carry it."""
    record: dict[str, object] = {
        "phase": "memory",
        "pss_growth_kb": pss_growth_kb,
        "duration_seconds": duration,
        "revision": "rev",
        "api_level": 36,
    }
    record.update(overrides)
    return record


def full_pass_records() -> list[dict[str, object]]:
    """Build a record set in which every criterion is measured and passes."""
    return [
        resources_record(),
        hidden_record(),
        memory_record(),
        *pairs(4, 1000.0, 1000.0),
    ]


def report_lines_text(records: Sequence[Mapping[str, object]]) -> list[str]:
    """Render the report's verdicts to their text lines."""
    return [verdict.line for verdict in battery_report.report_lines(records)]


def b2_row() -> str:
    """Return the acceptance matrix's B2 row."""
    budget = Path(__file__).resolve().parent.parent / "docs" / "battery-budget.md"
    return next(line for line in budget.read_text(encoding="utf-8").splitlines() if line.startswith("| **B2:"))


# --- Student t critical values (`t_critical_95`): degrees-of-freedom table & tail ---


@pytest.mark.parametrize(
    ("degrees_of_freedom", "expected"),
    [
        (1, 12.706),
        (2, 4.303),
        (3, 3.182),
        (4, 2.776),
        (30, 2.042),
    ],
)
def test_table_is_indexed_by_degrees_of_freedom(degrees_of_freedom: int, expected: float) -> None:
    assert battery_stats.t_critical_95(degrees_of_freedom) == pytest.approx(expected)


def test_the_tail_is_expanded_rather_than_replaced_by_the_normal_value() -> None:
    # The two-sided 95% t at 31 degrees of freedom is 2.0395; returning the normal 1.960 there
    # would understate the interval by about 4%.
    assert battery_stats.t_critical_95(31) == pytest.approx(2.0395, abs=1e-3)
    assert battery_stats.t_critical_95(60) == pytest.approx(2.0003, abs=1e-3)
    assert battery_stats.t_critical_95(31) > battery_stats.NORMAL_T_CRITICAL_95


def test_the_tail_tends_to_the_normal_value() -> None:
    assert battery_stats.t_critical_95(100_000) == pytest.approx(battery_stats.NORMAL_T_CRITICAL_95, abs=1e-3)
    assert battery_stats.t_critical_95(1000) > battery_stats.NORMAL_T_CRITICAL_95


@pytest.mark.parametrize("degrees_of_freedom", [1, 2])
def test_two_and_three_pairs_do_not_borrow_the_four_pair_value(degrees_of_freedom: int) -> None:
    # The old two-branch lookup returned 3.182 for every n below 5, which understates the
    # interval for two or three pairs.
    assert battery_stats.t_critical_95(degrees_of_freedom) != pytest.approx(3.182)


def test_refuses_a_sample_with_no_degrees_of_freedom() -> None:
    with pytest.raises(device_probes.ProbeError, match="0 degrees of freedom"):
        battery_stats.t_critical_95(0)


# --- Paired relative increase and its 95% interval (`paired_statistics`) ---


def test_identical_pairs_have_no_increase() -> None:
    rates = [100.0, 102.0, 99.0, 101.0]
    statistics = battery_stats.paired_statistics(rates, rates)
    assert statistics.relative_delta_pct == pytest.approx(0.0)
    assert statistics.ci_95_upper_pct == pytest.approx(0.0)
    assert statistics.degrees_of_freedom == len(rates) - 1


def test_uniform_increase_has_a_zero_width_interval() -> None:
    statistics = battery_stats.paired_statistics([100.0] * 4, [103.0] * 4)
    assert statistics.relative_delta_pct == pytest.approx(3.0)
    assert statistics.ci_95_upper_pct == pytest.approx(3.0)


def test_the_bound_uses_the_critical_value_for_the_actual_sample_count() -> None:
    baseline = [100.0] * 5
    treatment = [100.0, 100.0, 100.0, 100.0, 120.0]
    statistics = battery_stats.paired_statistics(baseline, treatment)
    assert statistics.degrees_of_freedom == len(baseline) - 1
    assert statistics.t_critical == pytest.approx(2.776)


@pytest.mark.parametrize(
    ("baseline", "treatment", "expected_match"),
    [
        pytest.param([100.0] * 3, [101.0] * 3, "at least 4 pairs", id="fewer_than_four_pairs"),
        pytest.param([100.0] * 4, [101.0] * 5, "equal arms", id="mismatched_arms"),
        pytest.param([0.0] * 4, [1.0] * 4, "not positive", id="non_positive_baseline"),
    ],
)
def test_paired_statistics_refuses_invalid_inputs(
    baseline: list[float],
    treatment: list[float],
    expected_match: str,
) -> None:
    with pytest.raises(device_probes.ProbeError, match=expected_match):
        battery_stats.paired_statistics(baseline, treatment)


# --- Pilot noise floor (`two_sigma_noise_floor`): mean, sigma, and two-sigma width ---


def test_reports_mean_sigma_and_two_sigma() -> None:
    mean, deviation, half_width = battery_stats.two_sigma_noise_floor([100.0, 102.0, 98.0, 100.0])
    assert mean == pytest.approx(100.0)
    assert deviation == pytest.approx(1.632993161855452)
    assert half_width == pytest.approx(2 * deviation)


def test_refuses_too_few_windows() -> None:
    with pytest.raises(device_probes.ProbeError, match="at least 4 windows"):
        battery_stats.two_sigma_noise_floor([100.0, 101.0, 99.0])


# --- Aggregate pass/fail lines against committed thresholds (`report_lines`) ---


def test_every_budget_is_not_measured_without_records() -> None:
    lines = report_lines_text([])
    for label in (
        "B2 wake locks",
        "B2 alarms",
        "B2 jobs",
        "B3 hidden CPU",
        "B4 vs stock",
        "B4 vs black",
        "B5 visible CPU",
        "B6 PSS growth",
    ):
        assert any(line.startswith(label) and "NOT MEASURED" in line for line in lines)


def test_b1_is_declared_out_of_scope() -> None:
    verdicts = battery_report.report_lines([])
    assert any(
        verdict.label == "B1 hidden frames"
        and verdict.status is battery_stats.VerdictStatus.OUT_OF_SCOPE
        and "NOT MEASURED HERE" in verdict.line
        for verdict in verdicts
    )


def test_zero_wake_locks_alarms_and_jobs_pass() -> None:
    lines = report_lines_text([resources_record()])
    for label in ("B2 wake locks", "B2 alarms", "B2 jobs"):
        assert any(line.startswith(label) and "PASS" in line for line in lines)


@pytest.mark.parametrize(
    ("overrides", "expected_prefix"),
    [
        pytest.param({"wake_locks": 1}, "B2 wake locks: FAIL", id="held_wake_lock"),
        pytest.param({"jobs": 2}, "B2 jobs: FAIL", id="held_job"),
    ],
)
def test_a_held_b2_resource_fails(overrides: dict[str, object], expected_prefix: str) -> None:
    lines = report_lines_text([resources_record(**overrides)])
    assert any(line.startswith(expected_prefix) for line in lines)


def test_the_b2_census_is_a_maximum_across_every_resources_record() -> None:
    # The state file is append-only, so a later clean rerun must not hide an earlier dirty one.
    lines = report_lines_text([resources_record(wake_locks=3, jobs=1), resources_record()])
    assert any(line.startswith("B2 wake locks") and "FAIL" in line for line in lines)
    assert any(line.startswith("B2 jobs") and "FAIL" in line for line in lines)


def test_a_legacy_partial_only_wake_lock_count_is_not_measured() -> None:
    # `wake_locks` meant `PARTIAL_WAKE_LOCK` alone before the probe widened to the census. The
    # count is a real measurement of the narrower criterion, so the report does not refuse it —
    # but it cannot bound a zero-wake-locks-of-any-type budget in either direction, and passing
    # it would report a budget nothing measured.
    records = [{"phase": "resources", "wake_locks": 0, "alarms": 0, "jobs": 0, "revision": "rev", "api_level": 36}]
    lines = report_lines_text(records)
    assert any(line.startswith("B2 wake locks: NOT MEASURED") for line in lines)
    assert any(line.startswith("B2 alarms: PASS") for line in lines)
    assert any(line.startswith("B2 jobs: PASS") for line in lines)


def test_a_legacy_partial_only_count_cannot_hide_behind_a_covered_one() -> None:
    # A mixed set is bounded by the records that measured the all-type census. The legacy count
    # is ignored rather than treated as a violation: it is not this budget's measurement, and
    # the covered record is the evidence the row rests on.
    records = [
        {"phase": "resources", "wake_locks": 5, "alarms": 0, "jobs": 0, "revision": "rev", "api_level": 36},
        resources_record(),
    ]
    lines = report_lines_text(records)
    assert any(line.startswith("B2 wake locks: PASS") for line in lines)


def test_a_coverage_stamp_that_is_not_a_string_is_refused() -> None:
    # The stamp is a classifier the report compares against one value, and a value of the wrong
    # type is corrupt state rather than a narrower measurement: reading it as "not measured"
    # would silently drop the record behind a readable one.
    records = [resources_record(wake_lock_coverage=True)]
    with pytest.raises(device_probes.ProbeError, match="wake_lock_coverage"):
        battery_report.report_lines(records)


@pytest.mark.parametrize(("cpu_pct", "expected_status"), [(0.05, "PASS"), (5.4, "FAIL")])
def test_hidden_cpu_is_checked_against_its_budget(cpu_pct: float, expected_status: str) -> None:
    lines = report_lines_text([hidden_record(cpu_pct)])
    assert any(line.startswith("B3 hidden CPU") and expected_status in line for line in lines)


def test_matched_arms_within_the_budget_pass() -> None:
    lines = report_lines_text(pairs(4, 1000.0, 1000.0))
    assert any(line.startswith("B4 vs stock point estimate") and "PASS" in line for line in lines)
    assert any(line.startswith("B4 vs stock CI upper bound") and "PASS" in line for line in lines)
    assert any(line.startswith("B5 visible CPU") and "PASS" in line for line in lines)


def test_the_interval_names_the_difference_sd_that_sizes_a_future_run() -> None:
    # The CI margin is t * sd / sqrt(n), so the sd is the number a later run's pair count is
    # computed from; a report that omitted it would leave n to be guessed.
    records = [
        record
        for live, base in ((1200.0, 1000.0), (1400.0, 1000.0), (1600.0, 1000.0), (1800.0, 1000.0))
        for record in (visible_record("A", live, cpu=1.0), visible_record("B", base, baseline="stock"))
    ]
    paired = battery_stats.alternation_pairs(records)
    statistics = battery_stats.paired_statistics(
        [battery_stats.window_rate(base) for _, base in paired],
        [battery_stats.window_rate(live) for live, _ in paired],
    )
    # Per-pair differences 200, 400, 600 and 800 uA: mean 500, sample sd 258.198 uA.
    assert statistics.standard_deviation == pytest.approx(258.199, abs=1e-2)
    line = next(verdict.line for verdict in battery_report.report_lines(records) if verdict.label == "B4 vs stock")
    assert "sigma_d" in line
    assert "of the baseline" in line


def test_a_large_increase_fails_both_b4_lines() -> None:
    lines = report_lines_text(pairs(4, 1200.0, 1000.0))
    assert any(line.startswith("B4 vs stock point estimate") and "FAIL" in line for line in lines)
    assert any(line.startswith("B4 vs stock CI upper bound") and "FAIL" in line for line in lines)


def test_visible_cpu_over_its_budget_fails() -> None:
    lines = report_lines_text(pairs(4, 1000.0, 1000.0, cpu=6.4))
    assert any(line.startswith("B5 visible CPU") and "FAIL" in line for line in lines)


def test_pilot_windows_are_excluded_from_the_final_comparison() -> None:
    records = [*pairs(4, 1000.0, 1000.0), visible_record("A", 99999.0, pilot=True)]
    lines = report_lines_text(records)
    assert any(line.startswith("B4 vs stock point estimate") and "PASS" in line for line in lines)


def test_a_silent_discharge_channel_is_reported_not_crashed() -> None:
    # The target device's fuel gauge reports a constant counter, so every window's rate is zero.
    # B4 is then unmeasurable, and the criteria that *were* measured must still be reported.
    lines = report_lines_text(pairs(4, 0.0, 0.0))
    assert any(line.startswith("B4 vs stock") and "NOT MEASURED" in line for line in lines)
    assert any(line.startswith("B5 visible CPU") for line in lines)
    assert not any(line.startswith("B4 vs stock point estimate") and "PASS" in line for line in lines)


def test_too_few_pairs_leaves_b4_unmeasured() -> None:
    lines = report_lines_text(pairs(3, 1000.0, 1000.0))
    assert any(line.startswith("B4 vs stock") and "NOT MEASURED" in line for line in lines)


@pytest.mark.parametrize(
    "pss_growth_kb",
    [
        pytest.param(992, id="positive_under_budget"),
        pytest.param(-512, id="negative_shrinkage"),
    ],
)
def test_pss_growth_within_budget_passes(pss_growth_kb: int) -> None:
    # Memory can shrink over a window, so B6's growth is signed, and the non-negative refusal the
    # other numeric readers take must not reach it: a memory record whose PSS fell says the
    # criterion is met, not that the file is corrupt.
    lines = report_lines_text([memory_record(pss_growth_kb)])
    assert any(line.startswith("B6 PSS growth") and "PASS" in line for line in lines)


def test_a_six_second_window_fails_and_does_not_qualify() -> None:
    # The CLI refuses `--minutes 0.1`, but the report reads a state file it did not write: a window
    # that ran for six seconds is not the fifteen minutes B4 is defined over, so it is named and
    # dropped rather than averaged in beside real ones.
    records = [
        visible_record("A", 1000.0, cpu=1.0, duration=6.0),
        visible_record("B", 1000.0, baseline="stock", duration=6.0),
    ] * 4
    lines = report_lines_text(records)
    assert any(line.startswith("WINDOW DURATIONS: FAIL") for line in lines)
    assert any(line.startswith("B4 vs stock") and "NOT MEASURED" in line for line in lines)
    assert not any(line.startswith("B4 vs stock point estimate") for line in lines)


def test_a_record_without_a_recorded_duration_is_not_measurable_either() -> None:
    record = hidden_record()
    del record["duration_seconds"]
    lines = report_lines_text([record])
    assert any(line.startswith("WINDOW DURATIONS: FAIL") for line in lines)
    assert any(line.startswith("B3 hidden CPU") and "NOT MEASURED" in line for line in lines)


def test_a_window_inside_the_length_tolerance_still_qualifies() -> None:
    # A 15-minute window records a few seconds either side of 900s; that jitter is not a short
    # window, and refusing it would fail every real run.
    records = [
        visible_record("A", 1000.0, cpu=1.0, duration=902.0),
        visible_record("B", 1000.0, baseline="stock", duration=898.0),
    ] * 4
    lines = report_lines_text(records)
    assert not any(line.startswith("WINDOW DURATIONS") for line in lines)
    assert any(line.startswith("B4 vs stock point estimate") and "PASS" in line for line in lines)


def test_an_increase_between_the_provisional_and_committed_threshold_passes() -> None:
    # The committed B4 threshold is 12.0123%, raised from the 5% provisional by the pilot's own
    # noise floor, and every other B4 case in this file sits at 0% or above 20% — so a regression
    # that put the provisional value back would pass the whole suite. +8% discriminates.
    assert pytest.approx(12.0123) == battery_stats.FINAL_MAX_VISIBLE_DELTA_PCT
    statuses = {(verdict.label, verdict.status) for verdict in battery_report.report_lines(pairs(4, 1080.0, 1000.0))}
    assert ("B4 vs stock point estimate", battery_stats.VerdictStatus.PASS) in statuses
    assert ("B4 vs stock CI upper bound", battery_stats.VerdictStatus.PASS) in statuses


def test_a_negative_point_estimate_and_interval_still_pass() -> None:
    # B4's verdict is a relative *increase*, and a decrease is the best result the criterion can
    # have: the recorded evidence in docs/battery-budget.md carries a -30.775% point estimate with
    # a -11.615% upper bound against the 12.0123% threshold. The rate reader's refusal of a
    # negative *rate* is a different statement from a refusal of a negative *verdict*, and this is
    # the guard that keeps the two apart: live 900 uA against a stock 1000 uA is a -10% point
    # estimate and a -10% interval upper bound, and both must pass.
    statuses = {(verdict.label, verdict.status) for verdict in battery_report.report_lines(pairs(4, 900.0, 1000.0))}
    assert ("B4 vs stock point estimate", battery_stats.VerdictStatus.PASS) in statuses
    assert ("B4 vs stock CI upper bound", battery_stats.VerdictStatus.PASS) in statuses


def test_a_sequence_that_is_not_an_ab_alternation_is_refused() -> None:
    # The document names this refusal as the reason the pairing means anything: pairing the nth
    # baseline with the nth live window by file order would pair windows taken under different
    # conditions, so a sequence that is not an alternation has no comparison in it.
    records = [
        visible_record("A", 1000.0, cpu=1.0),
        visible_record("B", 1000.0, baseline="stock"),
        visible_record("A", 1000.0, cpu=1.0),
        visible_record("A", 1000.0, cpu=1.0),
        visible_record("B", 1000.0, baseline="stock"),
        visible_record("B", 1000.0, baseline="stock"),
    ]
    with pytest.raises(device_probes.ProbeError, match="not an A/B alternation"):
        battery_stats.alternation_pairs(records)
    lines = report_lines_text(records)
    assert any(line.startswith("B4 pairing") and "NOT MEASURED" in line for line in lines)


def test_a_live_window_with_no_cpu_reading_leaves_b5_unmeasured() -> None:
    records = pairs(4, 1000.0, 1000.0, cpu=1.0)
    records[0]["cpu_pct"] = None
    lines = report_lines_text(records)
    assert any(line.startswith("B5 visible CPU") and "NOT MEASURED" in line for line in lines)


@pytest.mark.parametrize("cpu", [float("-inf"), True, -1])
def test_an_unreadable_visible_cpu_reading_leaves_b5_unmeasured(cpu: object) -> None:
    # `-inf` is the case the finding names: it satisfies the `isinstance` the reader checked and is
    # below every budget, so three real readings beside one `-inf` averaged to "PASS — -inf%". A
    # boolean reads as 1.0% and a negative percentage as a value below the budget, so all three
    # used to leave B5 reported as measured. None of them is a reading, so B5 has no input.
    records = pairs(4, 1000.0, 1000.0, cpu=1.0)
    records[0]["cpu_pct"] = cpu
    lines = report_lines_text(records)
    assert any(line.startswith("B5 visible CPU") and "NOT MEASURED" in line for line in lines)
    assert not any(line.startswith("B5 visible CPU (mean)") for line in lines)


def test_a_window_with_no_discharge_rate_leaves_b4_unmeasured() -> None:
    records = pairs(4, 1000.0, 1000.0, cpu=1.0)
    del records[1]["discharge_rate_ua"]
    lines = report_lines_text(records)
    assert any(line.startswith("B4 vs stock") and "NOT MEASURED" in line for line in lines)


def test_an_unmatched_live_window_does_not_discard_b5() -> None:
    # B5 is the live arm's own channel — the document's B5 row names the process ticks during a
    # visible window and no baseline — so it is read from the live windows and not from the A/B
    # pairs. An unmatched final live window makes the sequence a non-alternation, and B5 used to
    # lose every reading on the file with it: four pairs at 6.4% failed B5, and one more completed
    # live window replaced that failure with "no live window was recorded". B4's refusal stands.
    records = [*pairs(4, 1000.0, 1000.0, cpu=6.4), visible_record("A", 1000.0, cpu=6.4)]
    lines = report_lines_text(records)
    assert any(line.startswith("B4 pairing") and "NOT MEASURED" in line for line in lines)
    assert not any(line.startswith("B4 vs stock point estimate") for line in lines)
    assert any(line.startswith("B5 visible CPU (mean)") and "FAIL" in line for line in lines)


def test_a_live_window_without_a_baseline_still_measures_b5() -> None:
    # The other end of the same rule: a run that recorded live windows and no baseline has taken
    # B5 measurements, so B5 is measured from them even though the file holds no comparison.
    records = [visible_record("A", 1000.0, cpu=6.4) for _ in range(2)]
    lines = report_lines_text(records)
    assert not any(line.startswith("B5 visible CPU") and "NOT MEASURED" in line for line in lines)
    assert any(line.startswith("B5 visible CPU (mean)") and "FAIL" in line for line in lines)


def test_b5_weights_each_window_by_its_length() -> None:
    # B5 is a rate — visible CPU over at least 15 minutes — so the aggregate has to estimate one.
    # Three 15-minute windows at 1% of one core beside one 60-minute window at 8% is 2.75% counted
    # per window, which passed the 3% budget, and 5% over the time the readings came from, which is
    # what the device was doing across the run.
    records = [
        *[visible_record("A", 1000.0, cpu=1.0, duration=900.0) for _ in range(3)],
        visible_record("A", 1000.0, cpu=8.0, duration=3600.0),
    ]
    mean = next(line for line in report_lines_text(records) if line.startswith("B5 visible CPU (mean)"))
    assert "FAIL" in mean
    assert "5.0000%" in mean


def test_b5_is_unchanged_when_every_window_is_the_same_length() -> None:
    # The weighting exists for the windows whose lengths differ, not to move the ordinary case: a
    # run whose windows all ran their documented length must report exactly what it reported
    # before, since that equal-length shape is the one the committed threshold was derived from.
    records = [visible_record("A", 1000.0, cpu=1.0, duration=900.0) for _ in range(4)]
    lines = report_lines_text(records)
    assert any(line.startswith("B5 visible CPU (mean)") and "PASS — 1.0000%" in line for line in lines)


def test_an_unreadable_cpu_reading_is_not_reported_as_no_live_window() -> None:
    # Two verdicts for one criterion used to be emitted: the refusal naming the reading, and then
    # the absence message, which says no live window was recorded over a file that recorded one.
    # The second contradicts the input, and it is the line a reader would take as the reason.
    records = pairs(4, 1000.0, 1000.0, cpu=1.0)
    records[0]["cpu_pct"] = float("-inf")
    lines = [line for line in report_lines_text(records) if line.startswith("B5 visible CPU")]
    assert len(lines) == 1
    assert "not finite" in lines[0]
    assert "no live window was recorded" not in lines[0]


@pytest.mark.parametrize("rate", [True, float("inf"), float("nan")])
def test_an_unreadable_discharge_rate_leaves_b4_unmeasured(rate: object) -> None:
    # `True` is an `int`, so it passed `isinstance` and produced a passing comparison out of `true`;
    # `inf` and `nan` reached the arithmetic and reported `FAIL — nan%` over rates no window recorded.
    # None of them is a discharge measurement, so B4 is unmeasurable.
    records = pairs(4, 1000.0, 1000.0, cpu=1.0)
    for record in records:
        record["discharge_rate_ua"] = rate
    lines = report_lines_text(records)
    assert any(line.startswith("B4 vs stock") and "NOT MEASURED" in line for line in lines)
    assert not any(line.startswith("B4 vs stock point estimate") for line in lines)


@pytest.mark.parametrize(
    ("duration", "expected_reason"),
    [
        (float("inf"), "not a finite length of time"),
        (float("nan"), "not a finite length of time"),
        (float("-inf"), "not a finite length of time"),
        (True, "not a length of time"),
    ],
)
def test_an_invalid_window_length_is_not_a_long_window(duration: object, expected_reason: str) -> None:
    # `inf` and `nan` satisfy `isinstance` and neither is below the minimum; `true` is an `int` in
    # Python and would read as a 1.0-second window. All four are refused as invalid durations.
    record = visible_record("A", 1000.0, cpu=1.0, duration=duration)
    reason = battery_report.short_window_reason(record)
    assert reason is not None
    assert expected_reason in reason
    assert any(line.startswith("WINDOW DURATIONS: FAIL") for line in report_lines_text([record]))


def test_a_stock_only_run_reports_the_black_arm_as_unmeasured() -> None:
    # One block per documented baseline, not one per baseline the state file happens to carry: a
    # stock-only set used to read as a complete verdict with the secondary baseline simply absent.
    # And the absence is *unmeasured*, not exempt: a run that never attempted that arm leaves the
    # same state file as one on a device that cannot set a static wallpaper, so the exemption has
    # to be declared rather than inferred from the missing windows.
    lines = report_lines_text(full_pass_records())
    assert any(line.startswith("B4 vs black") and "NOT MEASURED" in line for line in lines)
    assert not any("DEVICE-LIMITED" in line for line in lines)
    assert any(line.startswith("B4 vs stock CI upper bound") and "PASS" in line for line in lines)


def test_a_declared_device_limit_exempts_the_black_arm_and_quotes_the_reason() -> None:
    verdicts = battery_report.report_lines(full_pass_records(), black_unavailable="the build has no root")
    line = next(verdict.line for verdict in verdicts if verdict.label == "B4 vs black")
    assert "DEVICE-LIMITED" in line
    assert "the build has no root" in line
    assert battery_report.report_exit_code(verdicts) == 0


def test_an_undeclared_black_baseline_gates_the_report() -> None:
    verdicts = battery_report.report_lines(full_pass_records())
    assert any(
        verdict.label == "B4 vs black" and verdict.status is battery_stats.VerdictStatus.NOT_MEASURED
        for verdict in verdicts
    )
    assert battery_report.report_exit_code(verdicts) == 1


def test_a_black_only_run_leaves_the_gated_comparison_unmeasured() -> None:
    records = [visible_record("A", 1000.0, cpu=1.0), visible_record("B", 1000.0, baseline="black")] * 4
    lines = report_lines_text(records)
    assert any(line.startswith("B4 vs stock") and "NOT MEASURED" in line for line in lines)
    assert any(line.startswith("B4 vs black CI upper bound") for line in lines)


# --- Finding 5: exit status derived from verdicts (`report_exit_code`, `phase_report`) ---


def test_a_fully_measured_passing_report_exits_zero() -> None:
    verdicts = battery_report.report_lines(full_pass_records(), black_unavailable="the build has no root")
    assert battery_report.report_exit_code(verdicts) == 0


@pytest.mark.parametrize("status", list(battery_stats.VerdictStatus))
def test_is_failure_agrees_with_the_exit_rule_on_every_status(status: battery_stats.VerdictStatus) -> None:
    # `is_failure` is the type's own answer to "should the report fail", and the exit code is built
    # from it: a status the two disagreed about would be a printed verdict whose text and exit
    # status parted company.
    verdict = battery_stats.Verdict("a criterion", status, f"a criterion: {status.value}")
    expected_exit_code = 1 if verdict.is_failure else 0
    assert battery_report.report_exit_code([verdict]) == expected_exit_code
    assert (
        battery_report.report_exit_code([battery_stats.Verdict("c", battery_stats.VerdictStatus.NOT_MEASURED, "c")])
        == 1
    )


def test_a_fail_exits_non_zero() -> None:
    verdicts = battery_report.report_lines(pairs(4, 1200.0, 1000.0))
    assert battery_report.report_exit_code(verdicts) == 1


def test_an_unmeasured_criterion_exits_non_zero() -> None:
    assert battery_report.report_exit_code(battery_report.report_lines([])) == 1


def test_a_lone_out_of_scope_criterion_is_not_a_failure() -> None:
    verdicts = [
        battery_stats.Verdict("B1 hidden frames", battery_stats.VerdictStatus.OUT_OF_SCOPE, "B1: not measured here")
    ]
    assert battery_report.report_exit_code(verdicts) == 0


def test_a_device_limited_criterion_is_recorded_but_does_not_gate() -> None:
    # The black baseline is required only where the device permits setting one, so its absence is
    # printed and carried by the verdict list without turning every run on this device into a
    # failure. It is emphatically not reported as a pass, which is what a silent omission did.
    verdicts = [
        battery_stats.Verdict("B4 vs black", battery_stats.VerdictStatus.DEVICE_LIMITED, "B4 vs black: NOT MEASURED"),
        battery_stats.Verdict("B4 vs stock", battery_stats.VerdictStatus.PASS, "B4 vs stock: PASS"),
    ]
    assert battery_report.report_exit_code(verdicts) == 0
    assert not verdicts[0].is_failure
    assert verdicts[0].status is not battery_stats.VerdictStatus.PASS
    assert verdicts[0].status is not battery_stats.VerdictStatus.NOT_MEASURED


def test_a_stock_only_full_pass_exits_zero_once_the_black_arm_is_declared() -> None:
    verdicts = battery_report.report_lines(full_pass_records(), black_unavailable="the build has no root")
    assert battery_report.report_exit_code(verdicts) == 0
    assert any(
        verdict.label == "B4 vs black" and verdict.status is battery_stats.VerdictStatus.DEVICE_LIMITED
        for verdict in verdicts
    )


def test_phase_report_returns_the_derived_status(capsys: pytest.CaptureFixture[str]) -> None:
    assert battery_report.phase_report(full_pass_records(), black_unavailable="no root") == 0
    assert battery_report.phase_report(pairs(4, 1200.0, 1000.0)) == 1
    assert "B4 vs stock" in capsys.readouterr().out


# --- Finding 1: a state file carrying a negative rate is not a discharge comparison ---
# The measuring half's own refusal — a `Window` whose pack gained charge — is
# `WindowDischargeRateTest` in `test_battery_protocol.py`.


def test_a_state_file_carrying_a_negative_rate_is_not_a_comparison() -> None:
    records = [visible_record("A", -1000.0, cpu=1.0), visible_record("B", 1000.0, baseline="stock")] * 4
    lines = report_lines_text(records)
    assert any(line.startswith("B4 vs stock") and "NOT MEASURED" in line for line in lines)
    assert not any(line.startswith("B4 vs stock point estimate") for line in lines)


# --- Finding: an arm B window naming an undocumented or absent baseline is refused ---
# The report prints one block per *documented* baseline, so a label neither block names is selected
# by neither, and the pair — with whatever it measured — would be absent from every line. An arm B
# window's baseline is also the one field whose *absence* is refused rather than guessed.


@pytest.mark.parametrize(
    ("baseline_label", "expected_match"),
    [
        pytest.param("unreadable", "unreadable", id="unknown_label"),
        pytest.param(None, "baseline", id="absent_label"),
    ],
)
def test_an_undocumented_or_absent_baseline_label_is_refused(
    baseline_label: str | None,
    expected_match: str,
) -> None:
    failing = pairs(1, 9000.0, 1000.0, cpu=1.0)
    if baseline_label is None:
        del failing[1]["baseline"]
    else:
        failing[1]["baseline"] = baseline_label
    with pytest.raises(device_probes.ProbeError, match=expected_match):
        battery_report.report_lines(pairs(4, 1000.0, 1000.0, cpu=1.0) + failing)


# --- Finding: a `pilot` flag that is not a boolean is refused ---
# Both selectors filter on truthiness, and `"false"` is a truthy string in Python. A non-boolean
# `pilot` flag is a corrupt record rather than a third way of saying "not a pilot".


@pytest.mark.parametrize("value", ["false", 0, None])
def test_a_non_boolean_pilot_flag_is_refused(value: object) -> None:
    records = [visible_record("A", 1000.0, cpu=1.0) for _ in range(4)]
    hot = [visible_record("A", 1000.0, cpu=10.0, pilot=value) for _ in range(4)]
    with pytest.raises(device_probes.ProbeError, match="pilot"):
        battery_report.report_lines(records + hot)


def test_a_non_boolean_pilot_flag_hides_no_b4_pair() -> None:
    failing = pairs(1, 9000.0, 1000.0, cpu=1.0)
    for record in failing:
        record["pilot"] = "false"
    with pytest.raises(device_probes.ProbeError, match="pilot"):
        battery_report.report_lines(pairs(4, 1000.0, 1000.0, cpu=1.0) + failing)


def test_an_absent_pilot_flag_is_not_a_pilot() -> None:
    # The visible phase does not write the flag at all — only the pilot phase does — so a record
    # that does not carry it is an ordinary measurement, and the refusal must not reach it.
    records = pairs(4, 1000.0, 1000.0, cpu=1.0)
    for record in records:
        del record["pilot"]
    lines = report_lines_text(records)
    assert any(line.startswith("B4 vs stock point estimate") and "PASS" in line for line in lines)
    assert any(line.startswith("B5 visible CPU (mean)") and "PASS" in line for line in lines)


# --- Finding 6: the acceptance matrix and the probe must describe the same budget ---


def test_the_matrix_budget_matches_what_the_probe_counts() -> None:
    # The probe counts every pending alarm the package holds, because the pending list does not
    # say whether an alarm repeats. A matrix row promising a narrower budget than the probe can
    # check would describe a criterion nothing measures.
    row = b2_row()
    assert "0 pending alarms of any kind" in row
    assert "repeating alarms" not in row


def test_the_row_names_every_resource_the_report_judges() -> None:
    # `report` emits a `B2 jobs` verdict and the probe reads `dumpsys jobscheduler`, so a row
    # naming only wake locks and alarms would judge a budget whose target and method the matrix
    # never states.
    row = b2_row()
    assert "0 JobScheduler jobs" in row
    assert "dumpsys jobscheduler" in row


# --- Corrupt-record rejections: a state file the report did not write is refused ---
# Every one of these is a field that is *present* and unreadable. The distinction matters: a field
# a record does not carry at all says an older revision had nothing to record, and the report must
# keep working on those. A field that is present and wrong is a corrupt or hand-edited file, and
# skipping it hides the record behind the ones that parsed.


@pytest.mark.parametrize(
    "wake_locks",
    [
        pytest.param("corrupt", id="non_numeric"),
        pytest.param(True, id="boolean"),
    ],
)
def test_a_non_numeric_or_boolean_resource_field_is_refused(wake_locks: object) -> None:
    # One valid zero and one unreadable value would otherwise report B2 as PASS, judged on the
    # records that happened to parse. `True` is an `int` in Python, so an unchecked reader takes
    # `"wake_locks": true` for one lock — or, worse here, for a value that sorts under the zero
    # budget as `1` does not.
    records = [
        {"phase": "resources", "wake_locks": 0, "alarms": 0, "jobs": 0},
        {"phase": "resources", "wake_locks": wake_locks, "alarms": 0, "jobs": 0},
    ]
    with pytest.raises(device_probes.ProbeError, match="wake_locks"):
        battery_report.report_lines(records)


@pytest.mark.parametrize("key", ["wake_locks", "alarms", "jobs"])
def test_a_negative_resource_count_is_refused(key: str) -> None:
    # A count of wake locks, alarms, or jobs cannot be negative, and one that is sorts under the
    # zero budget rather than failing it: an otherwise clean census carrying `-1` exited zero over
    # a value the device cannot have produced.
    records: list[dict[str, object]] = [{"phase": "resources", "wake_locks": 0, "alarms": 0, "jobs": 0}]
    records[0][key] = -1
    with pytest.raises(device_probes.ProbeError, match=key):
        battery_report.report_lines(records)


@pytest.mark.parametrize(
    "cpu_pct",
    [
        pytest.param(float("-inf"), id="non_finite"),
        pytest.param(-1, id="negative"),
    ],
)
def test_an_invalid_hidden_cpu_is_refused(cpu_pct: float) -> None:
    # `-inf` sorts below every budget, so it would pass a maximum-is-zero check it never measured.
    # A percentage of one core cannot be negative either, and one that is sits below the 0.1%
    # budget instead of failing it. The record needs a valid `duration_seconds` to reach the reader
    # at all, because a record dropped as short never bounds its budget.
    records = [hidden_record(cpu_pct, duration=600.0, apk_sha256="a")]
    with pytest.raises(device_probes.ProbeError, match="cpu_pct"):
        battery_report.report_lines(records)


def test_a_field_no_record_carries_is_still_not_bounded() -> None:
    # The refusal above must not extend to an absent field: a revision that never recorded one
    # has nothing to say about it, and a report over its records has to keep working. The
    # wake-lock row is the one this record measured, so it is the one that passes.
    records = [{"phase": "resources", "wake_locks": 0, "wake_lock_coverage": "all-types"}]
    lines = report_lines_text(records)
    assert any(line.startswith("B2 wake locks: PASS") for line in lines)
    assert any(line.startswith("B2 alarms: NOT MEASURED") for line in lines)
    assert any(line.startswith("B2 jobs: NOT MEASURED") for line in lines)


def test_a_wholly_unknown_identity_is_refused() -> None:
    # A set whose every record says "unknown build" is homogeneous and still cannot name what it
    # measured, so aggregating it produces a verdict whose subject is unnamed. The rule reads
    # each identity field, so one field is enough to refuse the set.
    records = [{"apk_sha256": None, "api_level": 36}, {"apk_sha256": None, "api_level": 36}]
    with pytest.raises(device_probes.ProbeError, match="apk_sha256"):
        battery_report.check_measurement_identity(records)


def test_an_identity_field_no_record_carries_is_still_not_bounded() -> None:
    # The refusal above must not extend to an absent field, or the `resources` census — which
    # carries neither `power_source` nor `clk_tck` — would stop being reportable.
    battery_report.check_measurement_identity([{"api_level": 36}, {"api_level": 36}])


@pytest.mark.parametrize("identity_field", battery_report.IDENTITY_FIELDS)
@pytest.mark.parametrize("value", [[], {}, set(), True])
def test_a_non_scalar_identity_value_is_refused(identity_field: str, value: object) -> None:
    # The identity check is a set per field, so the set is the comparison: a value it cannot hold
    # cannot be shown to agree with any other, and one it can hold but no record writes — a
    # boolean, which is an `int` in Python — would be compared as a build or a tick rate. A list
    # made the set construction raise `TypeError: unhashable type` out of the caller as a
    # traceback rather than the named refusal every other corrupt-record reader gives. Every
    # identity field is covered, not only the one the defect was reported against, because they
    # are all read by the same rule.
    records = [{"phase": "resources", identity_field: value}]
    with pytest.raises(device_probes.ProbeError, match=identity_field):
        battery_report.check_measurement_identity(records)


@pytest.mark.parametrize("identity_field", battery_report.IDENTITY_FIELDS)
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_a_non_finite_identity_value_is_refused(identity_field: str, value: float) -> None:
    # The state file is JSON Lines read with `json.loads`, which accepts `NaN` and `Infinity` by
    # default, so a corrupt file really does reach here. Both are floats, and no identity field is
    # written as one, so they are refused by the kind check — see below for the rule they fall
    # under. Left at the wrong kind, `inf` would compare equal to itself and a set of them would
    # be read as agreement, with `inf` printed as the identity the run was measured under.
    records = [{"phase": "resources", identity_field: value}]
    with pytest.raises(device_probes.ProbeError, match=identity_field):
        battery_report.check_measurement_identity(records)
    # The refusal must not reach a finite number, which is what every state file carries.
    battery_report.check_measurement_identity([{"phase": "resources", "clk_tck": 100, "api_level": 36}])


@pytest.mark.parametrize(("identity_field", "value", "expected_message"), WRONG_KIND_IDENTITY_CASES)
def test_an_identity_value_of_the_wrong_kind_is_refused(
    identity_field: str,
    value: object,
    expected_message: str,
) -> None:
    # Each identity field is written as one kind of thing, and the report is fed a state file it
    # did not write. A scalar of the other kind is a value no phase produces: read as an identity,
    # it passes the gate and the report prints it as the identity the run was measured under —
    # `API levels: not-an-api-level` — which is the complaint the check already makes about a set
    # whose every value is `null`. The kinds are the writers' own, not the report's invention.
    assert set(battery_report.IDENTITY_FIELDS) == set(INTEGER_IDENTITY_FIELDS) | set(TEXT_IDENTITY_FIELDS)
    # And the table the rule reads is the writers' own, so it cannot drift away from them.
    assert set(INTEGER_IDENTITY_FIELDS) == set(battery_report.INTEGER_IDENTITY_FIELDS)
    records = [{"phase": "resources", identity_field: value}]
    with pytest.raises(device_probes.ProbeError, match=expected_message):
        battery_report.check_measurement_identity(records)


def test_the_kinds_the_phase_writers_use_are_still_accepted() -> None:
    # The rule has to admit what the phases actually write, or the report stops reading its own
    # state files: the two integers and the three strings of the record below, which is a record
    # from the 2026-10-16 device pass. The `null` a pre-build record carries is admitted by this
    # reader as well, and refused by the identity check above it when it is the only value the
    # set holds — which is that check's decision, not this reader's.
    record = {
        "phase": "resources",
        "device_id": "2ec5a940ef5f",
        "apk_sha256": "a" * 64,
        "api_level": 36,
        "power_source": "simulated",
        "clk_tck": 100,
    }
    battery_report.check_measurement_identity([record, dict(record)])
    assert battery_report.identity_value({"phase": "resources", "apk_sha256": None}, "apk_sha256") is None


@pytest.mark.parametrize(
    "restore_problems",
    [
        pytest.param("airplane mode was not restored", id="string"),
        pytest.param(None, id="explicit_null"),
    ],
)
def test_a_non_list_restore_problems_is_refused(restore_problems: object) -> None:
    # A failed restore is the one thing on a record that says the device was left changed, and
    # reading a string where the phases write a list as "no problems" would let the report exit
    # zero over an explicitly recorded failure. `dict.get` answers `None` both for a record that
    # never carried the key and for one that carries it with a null, so the absence check must be a
    # membership test; a present value has to be a list.
    records = [{"phase": "hidden", "restore_problems": restore_problems}]
    with pytest.raises(device_probes.ProbeError, match="not a list"):
        battery_report.collect_restore_problems(records)


def test_an_absent_restore_problems_is_no_problem() -> None:
    assert battery_report.collect_restore_problems([{"phase": "hidden"}]) == []
    assert battery_report.collect_restore_problems([{"phase": "hidden", "restore_problems": ["x"]}]) == ["x"]


# --- Report CLI forwarding (`main_report`): one `--option=value` token per parsed value ---


def test_dash_prefixed_values_survive_forwarding(mocker: pytest_mock.MockerFixture) -> None:
    # Two tokens (`--state`, `-reports`) make argparse read the second as an unknown option, so a
    # dash-prefixed state directory or reason could not be forwarded at all.
    main = mocker.patch.object(battery_cli, "main", return_value=0)
    assert battery_cli.main_report(["--state=-reports", "--black-unavailable=--reason"]) == 0
    main.assert_called_once_with(["--state=-reports", "report", "--black-unavailable=--reason"])
