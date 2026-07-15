#!/usr/bin/env python3
"""Repeatedly replay a symbolic Android getevent trace with sendevent.

The input may be captured with ``adb shell getevent -l``.  Event names and
8-digit hexadecimal values are converted to the numeric arguments expected by
Android's ``sendevent`` command.  The generated replay loop runs inside one
ADB shell session so that an ADB process is not started for every event.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import shlex
import subprocess
import sys
from typing import Iterable, Sequence


EVENT_TYPES = {
    "EV_SYN": 0x00,
    "EV_KEY": 0x01,
    "EV_REL": 0x02,
    "EV_ABS": 0x03,
    "EV_MSC": 0x04,
}

EVENT_CODES = {
    # EV_SYN
    "SYN_REPORT": 0x00,
    "SYN_CONFIG": 0x01,
    "SYN_MT_REPORT": 0x02,
    "SYN_DROPPED": 0x03,
    # EV_KEY (touch-related buttons)
    "BTN_TOOL_PEN": 0x140,
    "BTN_TOOL_RUBBER": 0x141,
    "BTN_TOOL_BRUSH": 0x142,
    "BTN_TOOL_PENCIL": 0x143,
    "BTN_TOOL_AIRBRUSH": 0x144,
    "BTN_TOOL_FINGER": 0x145,
    "BTN_TOOL_MOUSE": 0x146,
    "BTN_TOOL_LENS": 0x147,
    "BTN_TOUCH": 0x14A,
    "BTN_STYLUS": 0x14B,
    "BTN_STYLUS2": 0x14C,
    "BTN_TOOL_DOUBLETAP": 0x14D,
    "BTN_TOOL_TRIPLETAP": 0x14E,
    "BTN_TOOL_QUADTAP": 0x14F,
    "BTN_TOOL_QUINTTAP": 0x148,
    # EV_ABS
    "ABS_X": 0x00,
    "ABS_Y": 0x01,
    "ABS_PRESSURE": 0x18,
    "ABS_DISTANCE": 0x19,
    "ABS_TILT_X": 0x1A,
    "ABS_TILT_Y": 0x1B,
    "ABS_MT_SLOT": 0x2F,
    "ABS_MT_TOUCH_MAJOR": 0x30,
    "ABS_MT_TOUCH_MINOR": 0x31,
    "ABS_MT_WIDTH_MAJOR": 0x32,
    "ABS_MT_WIDTH_MINOR": 0x33,
    "ABS_MT_ORIENTATION": 0x34,
    "ABS_MT_POSITION_X": 0x35,
    "ABS_MT_POSITION_Y": 0x36,
    "ABS_MT_TOOL_TYPE": 0x37,
    "ABS_MT_BLOB_ID": 0x38,
    "ABS_MT_TRACKING_ID": 0x39,
    "ABS_MT_PRESSURE": 0x3A,
    "ABS_MT_DISTANCE": 0x3B,
    "ABS_MT_TOOL_X": 0x3C,
    "ABS_MT_TOOL_Y": 0x3D,
    # EV_MSC
    "MSC_SERIAL": 0x00,
    "MSC_PULSELED": 0x01,
    "MSC_GESTURE": 0x02,
    "MSC_RAW": 0x03,
    "MSC_SCAN": 0x04,
    "MSC_TIMESTAMP": 0x05,
}

VALUE_NAMES = {
    "UP": 0,
    "RELEASE": 0,
    "DOWN": 1,
    "PRESS": 1,
    "REPEAT": 2,
}

EVENT_RE = re.compile(
    r"(?P<device>/dev/input/event\d+):\s+"
    r"(?P<event_type>\S+)\s+(?P<code>\S+)\s+(?P<value>\S+)"
)
DEVICE_RE = re.compile(r"^/dev/input/(?:event\d+|by-[^/]+/.+)$")

EV_SYN = EVENT_TYPES["EV_SYN"]
EV_KEY = EVENT_TYPES["EV_KEY"]
EV_ABS = EVENT_TYPES["EV_ABS"]
SYN_REPORT = EVENT_CODES["SYN_REPORT"]
BTN_TOUCH = EVENT_CODES["BTN_TOUCH"]
BTN_TOOL_FINGER = EVENT_CODES["BTN_TOOL_FINGER"]
ABS_MT_TRACKING_ID = EVENT_CODES["ABS_MT_TRACKING_ID"]


class TraceError(ValueError):
    """Raised when a getevent trace cannot be converted safely."""


@dataclass(frozen=True)
class Event:
    device: str
    event_type: int
    code: int
    value: int
    line_number: int

    @property
    def is_sync_report(self) -> bool:
        return self.event_type == EV_SYN and self.code == SYN_REPORT

    @property
    def is_touch_release(self) -> bool:
        return (
            self.event_type == EV_KEY
            and self.code in (BTN_TOUCH, BTN_TOOL_FINGER)
            and self.value == 0
        ) or (
            self.event_type == EV_ABS
            and self.code == ABS_MT_TRACKING_ID
            and self.value == -1
        )

    @property
    def starts_contact(self) -> bool:
        return (
            self.event_type == EV_ABS
            and self.code == ABS_MT_TRACKING_ID
            and self.value >= 0
        )


def parse_nonnegative_int(text: str) -> int:
    value = int(text)
    if value < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return value


def parse_nonnegative_float(text: str) -> float:
    value = float(text)
    if value < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return value


def parse_hex_field(token: str, *, signed: bool) -> int:
    """Parse getevent's hexadecimal number, including ffffffff as -1."""

    if token.startswith("-"):
        try:
            return int(token, 10)
        except ValueError as exc:
            raise TraceError(f"invalid numeric value {token!r}") from exc

    normalized = token[2:] if token.lower().startswith("0x") else token
    if not normalized or not re.fullmatch(r"[0-9a-fA-F]+", normalized):
        raise TraceError(f"invalid hexadecimal value {token!r}")

    value = int(normalized, 16)
    if signed and value >= 1 << 31:
        if value >= 1 << 32:
            raise TraceError(f"value does not fit in a signed 32-bit integer: {token!r}")
        value -= 1 << 32
    return value


def parse_named_or_hex(token: str, names: dict[str, int], *, field: str) -> int:
    if token in names:
        return names[token]
    try:
        return parse_hex_field(token, signed=False)
    except TraceError as exc:
        raise TraceError(f"unknown {field} {token!r}") from exc


def parse_trace(lines: Iterable[str]) -> list[Event]:
    events: list[Event] = []
    for line_number, line in enumerate(lines, start=1):
        match = EVENT_RE.search(line)
        if match is None:
            continue

        try:
            event_type = parse_named_or_hex(
                match.group("event_type"), EVENT_TYPES, field="event type"
            )
            code = parse_named_or_hex(match.group("code"), EVENT_CODES, field="event code")
            value_token = match.group("value")
            value = VALUE_NAMES.get(value_token)
            if value is None:
                value = parse_hex_field(value_token, signed=True)
        except TraceError as exc:
            raise TraceError(f"line {line_number}: {exc}\n  {line.rstrip()}") from exc

        events.append(
            Event(
                device=match.group("device"),
                event_type=event_type,
                code=code,
                value=value,
                line_number=line_number,
            )
        )

    if not events:
        raise TraceError("no getevent records were found")
    return events


def select_source_device(events: Sequence[Event], source_device: str | None) -> list[Event]:
    devices = sorted({event.device for event in events})
    if source_device is not None:
        selected = [event for event in events if event.device == source_device]
        if not selected:
            choices = ", ".join(devices)
            raise TraceError(
                f"source device {source_device!r} was not found; trace contains: {choices}"
            )
        return selected

    if len(devices) > 1:
        choices = ", ".join(devices)
        raise TraceError(
            "the trace contains multiple devices; select one with --source-device: " + choices
        )
    return list(events)


def validate_target_device(device: str) -> None:
    if "\n" in device or "\r" in device or not DEVICE_RE.fullmatch(device):
        raise TraceError(
            f"invalid target device {device!r}; expected /dev/input/eventN or a /dev/input/by-* path"
        )


def milliseconds_to_sleep(milliseconds: float) -> str:
    seconds = milliseconds / 1000.0
    return f"{seconds:.6f}".rstrip("0").rstrip(".") or "0"


def trace_ends_released(events: Sequence[Event]) -> bool:
    tracking_id: int | None = None
    touch_down: bool | None = None
    for event in events:
        if event.event_type == EV_ABS and event.code == ABS_MT_TRACKING_ID:
            tracking_id = event.value
        elif event.event_type == EV_KEY and event.code == BTN_TOUCH:
            touch_down = event.value != 0
    tracking_released = tracking_id in (None, -1)
    key_released = touch_down in (None, False)
    return tracking_released and key_released and events[-1].is_sync_report


def shell_sleep(milliseconds: float, indent: str = "    ") -> list[str]:
    if milliseconds == 0:
        return []
    return [f"{indent}sleep {milliseconds_to_sleep(milliseconds)}"]


def build_device_script(
    events: Sequence[Event],
    *,
    target_device: str,
    count: int,
    frame_delay_ms: float,
    gesture_delay_ms: float,
    loop_delay_ms: float,
) -> str:
    quoted_device = shlex.quote(target_device)
    body: list[str] = []
    release_in_frame = False

    for event in events:
        body.append(f"    send {event.event_type} {event.code} {event.value}")
        release_in_frame = release_in_frame or event.is_touch_release
        if event.is_sync_report:
            delay = gesture_delay_ms if release_in_frame else frame_delay_ms
            body.extend(shell_sleep(delay))
            release_in_frame = False

    if not body:
        body.append("    :")

    lines = [
        "#!/system/bin/sh",
        "",
        f"DEVICE={quoted_device}",
        f"COUNT={count}",
        "",
        "if ! command -v sendevent >/dev/null 2>&1; then",
        "    echo 'error: sendevent was not found on the Android target' >&2",
        "    exit 127",
        "fi",
        "if [ ! -e \"$DEVICE\" ]; then",
        "    echo \"error: input device does not exist: $DEVICE\" >&2",
        "    exit 1",
        "fi",
        "",
        "send() {",
        "    sendevent \"$DEVICE\" \"$1\" \"$2\" \"$3\" || {",
        "        status=$?",
        "        echo \"error: sendevent failed (are adb/root permissions available?)\" >&2",
        "        exit \"$status\"",
        "    }",
        "}",
        "",
        "release_touch() {",
        f"    sendevent \"$DEVICE\" {EV_ABS} {ABS_MT_TRACKING_ID} -1 >/dev/null 2>&1 || :",
        f"    sendevent \"$DEVICE\" {EV_KEY} {BTN_TOUCH} 0 >/dev/null 2>&1 || :",
        f"    sendevent \"$DEVICE\" {EV_KEY} {BTN_TOOL_FINGER} 0 >/dev/null 2>&1 || :",
        f"    sendevent \"$DEVICE\" {EV_SYN} {SYN_REPORT} 0 >/dev/null 2>&1 || :",
        "}",
        "trap 'release_touch; exit 130' HUP INT TERM",
        "",
        "replay_once() {",
        *body,
        "}",
        "",
        "iteration=0",
        "if [ \"$COUNT\" -eq 0 ]; then",
        "    while :; do",
        "        iteration=$((iteration + 1))",
        "        echo \"touch replay iteration $iteration\" >&2",
        "        replay_once",
        *shell_sleep(loop_delay_ms, indent="        "),
        "    done",
        "else",
        "    while [ \"$iteration\" -lt \"$COUNT\" ]; do",
        "        iteration=$((iteration + 1))",
        "        echo \"touch replay iteration $iteration/$COUNT\" >&2",
        "        replay_once",
        "        if [ \"$iteration\" -lt \"$COUNT\" ]; then",
        *shell_sleep(loop_delay_ms, indent="            "),
        "        fi",
        "    done",
        "fi",
        "",
        "release_touch",
        "trap - HUP INT TERM",
        "",
    ]
    return "\n".join(lines)


def adb_shell_command(adb: str, serial: str | None, use_su: bool) -> list[str]:
    command = [adb]
    if serial:
        command.extend(["-s", serial])
    command.append("shell")
    if use_su:
        command.extend(["su", "0", "sh"])
    else:
        command.append("sh")
    return command


def run_adb_script(command: Sequence[str], script: str, release_script: str) -> int:
    try:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, text=True)
    except FileNotFoundError:
        print(f"error: executable not found: {command[0]}", file=sys.stderr)
        return 127

    assert process.stdin is not None
    try:
        process.stdin.write(script)
        process.stdin.close()
        return process.wait()
    except KeyboardInterrupt:
        print("\nStopping replay and releasing the active touch...", file=sys.stderr)
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

        try:
            subprocess.run(
                command,
                input=release_script,
                text=True,
                timeout=5,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return 130


def read_trace(path: str | None) -> list[str]:
    if path is None or path == "-":
        if sys.stdin.isatty():
            raise TraceError("no trace file was supplied and standard input is a terminal")
        return sys.stdin.readlines()

    try:
        return Path(path).read_text(encoding="utf-8").splitlines(keepends=True)
    except OSError as exc:
        raise TraceError(f"cannot read trace file {path!r}: {exc}") from exc


def make_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Repeatedly replay an Android getevent -l touch trace.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  %(prog)s touch_events.txt
  %(prog)s touch_events.txt --count 10 --loop-delay-ms 500
  %(prog)s touch_events.txt --device /dev/input/event2 --serial SERIAL
  %(prog)s touch_events.txt --su
  %(prog)s touch_events.txt --output replay_on_device.sh
  %(prog)s --dry-run < touch_events.txt

count 0 means repeat forever. Press Ctrl-C to stop and release the touch.
""",
    )
    parser.add_argument(
        "trace",
        nargs="?",
        help="getevent text file; use '-' or omit it to read standard input",
    )
    parser.add_argument(
        "-n",
        "--count",
        type=parse_nonnegative_int,
        default=0,
        help="number of complete replays (default: 0, repeat forever)",
    )
    parser.add_argument(
        "--frame-delay-ms",
        type=parse_nonnegative_float,
        default=8.0,
        help="delay after a non-release SYN_REPORT frame (default: 8 ms)",
    )
    parser.add_argument(
        "--gesture-delay-ms",
        type=parse_nonnegative_float,
        default=50.0,
        help="delay after a touch-release frame (default: 50 ms)",
    )
    parser.add_argument(
        "--loop-delay-ms",
        type=parse_nonnegative_float,
        default=1000.0,
        help="delay between complete trace replays (default: 1000 ms)",
    )
    parser.add_argument(
        "--source-device",
        help="select this source device if the input trace contains multiple devices",
    )
    parser.add_argument(
        "--device",
        help="target input device (default: the selected source device)",
    )
    parser.add_argument("--serial", help="ADB device serial, equivalent to adb -s SERIAL")
    parser.add_argument("--adb", default="adb", help="ADB executable (default: adb)")
    parser.add_argument(
        "--su",
        action="store_true",
        help="run the target script with 'su 0 sh' instead of plain 'sh'",
    )
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "--dry-run",
        action="store_true",
        help="print the generated Android shell script without running it",
    )
    output_group.add_argument(
        "-o",
        "--output",
        metavar="PATH",
        help="write a standalone Android shell script instead of running ADB",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="parse and validate the trace without generating or running a replay",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = make_argument_parser().parse_args(argv)
    try:
        events = select_source_device(
            parse_trace(read_trace(args.trace)), args.source_device
        )
        source_device = events[0].device
        target_device = args.device or source_device
        validate_target_device(target_device)
        if not trace_ends_released(events):
            raise TraceError(
                "the selected trace does not end with a released touch followed by SYN_REPORT; "
                "refusing to loop it because it could leave the screen pressed"
            )
    except TraceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    frames = sum(event.is_sync_report for event in events)
    contacts = sum(event.starts_contact for event in events)
    print(
        f"Parsed {len(events)} events, {frames} frames, {contacts} contacts "
        f"from {source_device}; target is {target_device}.",
        file=sys.stderr,
    )
    if args.validate_only:
        return 0

    script = build_device_script(
        events,
        target_device=target_device,
        count=args.count,
        frame_delay_ms=args.frame_delay_ms,
        gesture_delay_ms=args.gesture_delay_ms,
        loop_delay_ms=args.loop_delay_ms,
    )

    if args.dry_run:
        sys.stdout.write(script)
        return 0
    if args.output:
        output_path = Path(args.output)
        try:
            output_path.write_text(script, encoding="utf-8")
            output_path.chmod(output_path.stat().st_mode | 0o111)
        except OSError as exc:
            print(f"error: cannot write {args.output!r}: {exc}", file=sys.stderr)
            return 1
        print(f"Wrote Android replay script: {output_path}", file=sys.stderr)
        return 0

    release_script = build_device_script(
        [],
        target_device=target_device,
        count=1,
        frame_delay_ms=0,
        gesture_delay_ms=0,
        loop_delay_ms=0,
    )
    command = adb_shell_command(args.adb, args.serial, args.su)
    print(f"Running via: {shlex.join(command)}", file=sys.stderr)
    return run_adb_script(command, script, release_script)


if __name__ == "__main__":
    raise SystemExit(main())
