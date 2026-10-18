# SPDX-License-Identifier: Apache-2.0
"""
Producer accounting for a hidden window (#125 criterion 1).

A frame count has to come from the wallpaper's own producer pipeline, not from its lifecycle
state: `mVisible=false` is what the framework was told, and a bounded CPU reading can still
contain rendered frames. `atrace` on the app's own process is the console this device exposes.
The window is always bracketed by a visible control, so a zero count inside it is distinguishable
from a trace that silently produced nothing: a control that finds no frames is an error, never a
zero, because a counter that was never read cannot evidence anything.
"""

import math
import re
import subprocess
import sys
import time
from collections import Counter
from dataclasses import dataclass
from typing import Final

from host.device import probes

# A trace dump moves the whole trace buffer over the transport, which a plain shell call cannot.
ADB_TRACE_TIMEOUT_SECONDS: Final = 120

TRACE_WINDOW_SECONDS: Final = 30.0
TRACE_DISPLAY_SAMPLE_SECONDS: Final = 2.0
# This probe holds a shared device for the whole window with an atrace running, so both durations are
# bounded to the range a real measurement can lie in rather than trusted to be sane. The bound is
# what makes the arithmetic total: within it `seconds / sample_seconds` is finite and well-scaled, so
# it can neither overflow to inf — which `math.ceil` would turn into an OverflowError the caller does
# not catch — nor underflow to 0.0, which would start a trace that takes no display reads and return
# a window with no display evidence. The floor is the interval at which the count reaches the cap:
# a 600 s window sampled every 0.1 s is exactly the 6000 reads this probe will make, so the read
# count the loop can run to is bounded by construction, not by a check on a rounded quotient.
MIN_TRACE_DURATION_SECONDS: Final = 0.1
MAX_TRACE_WINDOW_SECONDS: Final = 600.0
MAX_TRACE_SAMPLES: Final = 6000
TRACE_CATEGORIES: Final = ("gfx", "view")
# The text trace marks each event with a `B|<pid>|<name>` / `E|<pid>` pair, so only one half is
# counted or every event would be doubled. The begin half carries the name and the end half is
# emitted nameless, which is why the name is read from `B`; both were checked against a real trace
# from this device rather than assumed.
TRACE_MARK_PATTERN: Final = re.compile(r"tracing_mark_write:\s*B\|\s*(\d+)\|([^\s|]+)")
# A produced frame is the buffer the producer hands to the consumer; the dequeue is recorded
# alongside it because a draw that never commits shows up as a dequeue without a queue.
PRODUCER_QUEUE_EVENT: Final = "queueBuffer"
PRODUCER_TRACKED_EVENTS: Final = frozenset({PRODUCER_QUEUE_EVENT, "dequeueBuffer"})


@dataclass(frozen=True)
class ProducerWindow:
    """
    One bounded producer-trace window, with the display state sampled inside it.

    `window_seconds` is the local monotonic span from the clock read before `atrace --async_start`
    was issued to the return of the dump, so the trace ran inside it: the frame count describes a
    window at least as wide as the duration asked for, and never one wider than this.
    """

    window_seconds: float
    pid: int
    event_counts: dict[str, int]
    trace_lines: int
    display_states: tuple[bool | None, ...]

    @property
    def frame_count(self) -> int:
        """The number of frames the traced process handed to the consumer during the window."""
        return self.event_counts.get(PRODUCER_QUEUE_EVENT, 0)

    @property
    def display_off_at_every_sample(self) -> bool:
        """
        Whether every sample taken inside the window found the display off.

        This is a sequence of discrete reads, not a continuous record: a display that came on and
        went off again between two samples would leave no trace here. The name says what the
        evidence is so that a caller, and a report built from it, cannot read it as more.
        """
        return bool(self.display_states) and all(state is False for state in self.display_states)

    @property
    def display_on_at_every_sample(self) -> bool:
        """
        Whether every sample taken inside the window found the display on.

        Discrete reads, with the same limitation as [display_off_at_every_sample].
        """
        return bool(self.display_states) and all(state is True for state in self.display_states)

    @property
    def display_unknown_samples(self) -> int:
        """How many samples could not be read at all."""
        return sum(1 for state in self.display_states if state is None)


def parse_producer_events(trace_text: str, pid: int) -> dict[str, int]:
    """Count one process's producer buffer events in an `atrace` text trace."""
    return Counter(
        name
        for match in TRACE_MARK_PATTERN.finditer(trace_text)
        if (captured_pid := probes.captured_text(match, 1)).isdigit()
        and int(captured_pid) == pid
        and (name := probes.captured_text(match, 2)) in PRODUCER_TRACKED_EVENTS
    )


def capture_producer_window(
    serial: str,
    pid: int,
    *,
    seconds: float = TRACE_WINDOW_SECONDS,
    sample_seconds: float = TRACE_DISPLAY_SAMPLE_SECONDS,
) -> ProducerWindow:
    """
    Trace a process's producer pipeline for a bounded window, sampling the display throughout.

    The trace runs on the device while this loop samples the display state, so the record covers the
    display *inside* the window rather than only at its endpoints. An unusable trace is raised: a
    window with no usable trace is not a window in which nothing was drawn. Both durations must be
    in [MIN_TRACE_DURATION_SECONDS, MAX_TRACE_WINDOW_SECONDS]. `seconds` paces the reads; the
    returned window reports the local span the trace ran inside, measured, which those reads make at
    least `seconds` wide. A window whose reads cannot be taken inside it is refused rather than
    returned with samples that do not span its width.
    """
    # Non-finite values are named explicitly rather than left to the range test, which also excludes
    # them (`nan` fails every comparison and `inf` exceeds the ceiling) but would bury the intent in
    # comparison semantics. The range is what bounds the loop: with both durations in
    # [MIN_TRACE_DURATION_SECONDS, MAX_TRACE_WINDOW_SECONDS] the quotient is finite and well-scaled,
    # so it can neither overflow to inf nor underflow to 0.0, and the count is in
    # [1, MAX_TRACE_SAMPLES] — the smallest ratio still rounds up to one read, and the largest
    # (MAX_TRACE_WINDOW_SECONDS / MIN_TRACE_DURATION_SECONDS) is exactly the cap.
    if not (
        math.isfinite(seconds)
        and math.isfinite(sample_seconds)
        and MIN_TRACE_DURATION_SECONDS <= seconds <= MAX_TRACE_WINDOW_SECONDS
        and MIN_TRACE_DURATION_SECONDS <= sample_seconds <= MAX_TRACE_WINDOW_SECONDS
    ):
        detail = (
            f"a trace window needs finite durations between {MIN_TRACE_DURATION_SECONDS} and "
            f"{MAX_TRACE_WINDOW_SECONDS:.0f} s but got seconds={seconds}, sample_seconds={sample_seconds}"
        )
        raise probes.ProbeError(detail)
    sample_count = math.ceil(seconds / sample_seconds)
    start_command = ["shell", "atrace", "--async_start", "-a", str(pid)]
    start_command.extend(TRACE_CATEGORIES)
    try:
        # The clock is read before the start call rather than after it: the trace is already active
        # while `atrace --async_start` is in flight, so an anchor taken once it returns would leave
        # that latency out of the schedule and out of the span reported below, which brackets the
        # trace. The start is inside this guard, and on the trace timeout the dump and stop use, so a
        # start that raises after the device has begun tracing cannot strand an active trace on a
        # shared device with nothing to stop it.
        started = time.monotonic()
        probes.run_adb(start_command, serial=serial, timeout=ADB_TRACE_TIMEOUT_SECONDS)
        states: list[bool | None] = []
        # The reads are paced against a monotonic deadline fixed when the trace starts, rather than
        # by sleeping a fixed interval between them: a read slower than its interval then shortens
        # the next sleep instead of pushing every later read out by its own latency, so read latency
        # cannot accumulate across the window. A read that outlasts its own interval still pushes the
        # reads after it, which is why the span is measured rather than assumed.
        for index in range(sample_count):
            deadline = started + min((index + 1) * sample_seconds, seconds)
            remaining = deadline - time.monotonic()
            if remaining > 0:
                time.sleep(remaining)
            elif index + 1 < sample_count and time.monotonic() >= started + seconds:
                # The read count bounds how many reads are owed, not how long each may take: a read
                # spends up to two adb timeouts, so a slow transport could hold `atrace` open for a
                # multiple of the window's width. A read that would start after the window's own end
                # is therefore not taken and the window is refused rather than returned with samples
                # that do not span the width it was asked for. The last read is exempt because it is
                # scheduled at that end and is the sample that closes the window, so the window can
                # overrun by that one read at most — bounded in turn by its own adb timeouts.
                overrun = time.monotonic() - (started + seconds)
                detail = (
                    f"the {seconds} s trace window could not take its display reads inside the "
                    f"window: read {index + 1} of {sample_count} would have started {overrun:.1f} s "
                    "after the window ended, so the samples would not span the width it was asked for"
                )
                raise probes.ProbeError(detail)
            states.append(probes.read_screen_on(serial))
        dump = probes.run_adb(["shell", "atrace", "--async_dump"], serial=serial, timeout=ADB_TRACE_TIMEOUT_SECONDS)
        # The display reads and this dump run inside the trace, so the trace covers at least
        # `seconds`. Reporting the requested duration would advertise a window narrower than the one
        # the frame count describes, so what is reported is the span measured locally here — the
        # tightest bound available without reading the trace's own timestamps, since it opens before
        # the start call and closes after the dump returns, and the trace lies inside it.
        window_seconds = time.monotonic() - started
    finally:
        try:
            probes.run_adb(["shell", "atrace", "--async_stop"], serial=serial, timeout=ADB_TRACE_TIMEOUT_SECONDS)
        except (subprocess.SubprocessError, OSError) as stop_error:
            # A stop that failed fails the window: an unstopped trace keeps filling the buffer the
            # next window's dump reads, which would attribute this window's frames to that one. It is
            # reported before it is raised, because the failure the caller records will name the stop
            # and nothing else will say the trace may still be running on the shared device.
            print(
                f"WARNING: atrace --async_stop failed and a trace may still be active: "
                f"{probes.error_detail(stop_error)}",
                file=sys.stderr,
            )
            raise
    trace_text = dump.decode("utf-8", errors="replace")
    if "tracing_mark_write" not in trace_text:
        # The check is on the buffer, not on the pid: a window in which the process drew nothing
        # legitimately holds no marks of its own, while this one holds none from any process, which
        # means the tracer captured nothing to count rather than that nothing was drawn. Reading the
        # count out of it would be reading a counter that was never filled.
        detail = (
            f"the atrace window produced no mark lines at all, so it cannot evidence a frame count "
            f"for pid {pid}; check that atrace is permitted on this build before reading the window"
        )
        raise probes.ProbeError(detail)
    return ProducerWindow(
        window_seconds=window_seconds,
        pid=pid,
        event_counts=parse_producer_events(trace_text, pid),
        trace_lines=len(trace_text.splitlines()),
        display_states=tuple(states),
    )
