#!/usr/bin/env python3
import argparse
import collections
import dataclasses
import json
import re
import shlex
import struct
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Deque, Dict, List, Optional, Tuple


GIB = 1024 * 1024 * 1024
MIB = 1024 * 1024
KIB = 1024

DEFAULT_CONFIG = {
    "sample_interval_sec": 1,
    "process_dmabuf_limit_bytes": int(1.8 * GIB),
    "process_dmabuf_consecutive_sec": 5,
    "process_dmabuf_baseline_margin_bytes": 512 * MIB,
    "total_dmabuf_soft_limit_bytes": 20 * GIB,
    "total_dmabuf_soft_consecutive_sec": 2,
    "total_dmabuf_hard_limit_bytes": 22 * GIB,
    "screencap_interval_sec": 10,
    "black_ratio_threshold": 0.98,
    "black_luma_threshold": 8.0,
    "black_pixel_threshold": 8,
    "black_screen_consecutive_samples": 6,
    "fd_limit_ratio": 0.85,
    "fd_absolute_limit": 8192,
    "fd_consecutive_sec": 3,
    "sync_file_growth_limit_per_60s": 3000,
    "lmk_limit_per_30s": 5,
    "swapfree_low_bytes": 64 * MIB,
    "cmafree_low_bytes": 16 * MIB,
    "memavailable_low_bytes": 512 * MIB,
    "systemui_pid_change_prior_window_sec": 60,
    "graphics_error_limit_per_10s": 5,
    "transition_error_limit_per_30s": 10,
    "weak_black_screen_consecutive_samples": 2,
    "process_dmabuf_weak_limit_bytes": int(1.2 * GIB),
    "total_dmabuf_weak_limit_bytes": 18 * GIB,
    "c_snapshot_cooldown_sec": 60,
    "c_snapshot_join_timeout_sec": 5,
    "command_timeout_sec": 12,
    "dump_timeout_sec": 35,
    "post_stop_logcat_delay_sec": 5,
}

DEFAULT_MONKEY_ARGS = (
    "--pkg-blacklist-file /log/blacklist.txt "
    "--ignore-crashes "
    "--ignore-timeouts "
    "--ignore-security-exceptions "
    "--ignore-native-crashes "
    "--pct-touch 60 "
    "--pct-motion 30 "
    "--pct-trackball 0 "
    "--pct-syskeys 0 "
    "--pct-nav 0 "
    "--pct-majornav 0 "
    "--pct-appswitch 10 "
    "--pct-anyevent 0 "
    "--throttle 300 "
    "-s 988441 "
    "-v -v -v "
    "1152000000"
)

TARGET_PROCESSES = {
    "system_server": "system_server",
    "systemui": "com.android.systemui",
    "surfaceflinger": "surfaceflinger",
}

EXCLUDED_LAYER_KEYWORDS = (
    "ScreenDecor",
    "CarSystemBar",
    "SystemBar",
    "NavigationBar",
    "StatusBar",
    "Gesture Monitor",
    "PointerEventDispatcher",
    "Input Overlays",
    "Display Overlays",
    "Accessibility Overlays",
    "Wallpaper",
    "ImeContainer",
    "ImePlaceholder",
    "ActivityRecordInputSink",
)

GRAPHICS_KEYWORDS = (
    "dequeueBuffer failed",
    "EGL_BAD_ALLOC",
    "GraphicBufferAllocator",
    "gralloc",
    "BufferQueue",
    "dmabuf",
    "ion",
    "kgsl",
    "hwcomposer",
    "DPU",
)

TRANSITION_KEYWORDS = (
    "transition is null",
    "AutoTaskStackController",
    "PanelAutoTaskStackTransitionHandler",
    "startMultiProfileAppWithDisplayId",
    "pauseBackTasks",
    "Transition timeout",
)


@dataclasses.dataclass
class CommandResult:
    returncode: int
    stdout: bytes
    stderr: bytes
    timed_out: bool = False

    @property
    def text(self) -> str:
        return self.stdout.decode("utf-8", errors="replace")


@dataclasses.dataclass
class ProcessSample:
    key: str
    name: str
    pid: Optional[int]
    pid_changed: bool = False
    sample_error: Optional[str] = None
    total_fd: Optional[int] = None
    dmabuf_fd_count: Optional[int] = None
    sync_file_fd_count: Optional[int] = None
    dmabuf_bytes: Optional[int] = None
    fd_size: Optional[int] = None
    vmrss_kb: Optional[int] = None
    threads: Optional[int] = None


@dataclasses.dataclass
class BlackSample:
    ts: float
    hit: bool
    reason: str
    black_ratio: Optional[float] = None
    avg_luma: Optional[float] = None
    max_luma: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    display_on: Optional[bool] = None
    brightness_nonzero: Optional[bool] = None
    resumed_activity: Optional[str] = None
    wms_visible_app_windows: int = 0
    sf_visible_app_layers: int = 0


class JsonlWriter:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()
        self.fh = path.open("a", encoding="utf-8")

    def write(self, obj: dict) -> None:
        with self.lock:
            self.fh.write(json.dumps(obj, ensure_ascii=False, sort_keys=True) + "\n")
            self.fh.flush()

    def close(self) -> None:
        with self.lock:
            self.fh.close()


class Adb:
    def __init__(self, adb_path: str = "adb", serial: Optional[str] = None):
        self.adb_path = adb_path
        self.serial = serial

    def base(self) -> List[str]:
        cmd = [self.adb_path]
        if self.serial:
            cmd += ["-s", self.serial]
        return cmd

    def run(
        self,
        args: List[str],
        timeout: Optional[float] = None,
        input_bytes: Optional[bytes] = None,
    ) -> CommandResult:
        cmd = self.base() + args
        try:
            p = subprocess.run(
                cmd,
                input=input_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                check=False,
            )
            return CommandResult(p.returncode, p.stdout, p.stderr, False)
        except subprocess.TimeoutExpired as exc:
            return CommandResult(
                124,
                exc.stdout or b"",
                exc.stderr or f"timeout after {timeout}s".encode(),
                True,
            )

    def shell(self, command: str, timeout: Optional[float] = None) -> CommandResult:
        return self.run(["shell", command], timeout=timeout)

    def exec_out(self, args: List[str], timeout: Optional[float] = None) -> CommandResult:
        return self.run(["exec-out"] + args, timeout=timeout)

    def popen(self, args: List[str], **kwargs) -> subprocess.Popen:
        return subprocess.Popen(self.base() + args, **kwargs)


class LogcatCollector:
    def __init__(self, adb: Adb, run_dir: Path, events: JsonlWriter):
        self.adb = adb
        self.run_dir = run_dir
        self.events = events
        self.proc: Optional[subprocess.Popen] = None
        self.thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.recent: Deque[Tuple[float, str, str]] = collections.deque(maxlen=20000)
        self.log_file = None
        self.cutoff_dt: Optional[datetime] = None

    def start(self, clear_logcat: bool = False) -> None:
        log_dir = self.run_dir / "logcat"
        log_dir.mkdir(parents=True, exist_ok=True)
        if clear_logcat:
            self.adb.run(["logcat", "-b", "all", "-c"], timeout=10)
        self.cutoff_dt = datetime.now()
        self.log_file = (log_dir / "all.log").open("ab", buffering=0)
        self.proc = self.adb.popen(
            ["logcat", "-b", "all", "-v", "threadtime"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        self.thread = threading.Thread(target=self._reader, name="logcat-reader", daemon=True)
        self.thread.start()

    def _reader(self) -> None:
        assert self.proc is not None
        assert self.proc.stdout is not None
        while not self.stop_event.is_set():
            line = self.proc.stdout.readline()
            if not line:
                if self.proc.poll() is not None:
                    break
                continue
            if self.log_file:
                self.log_file.write(line)
            text = line.decode("utf-8", errors="replace").rstrip("\n")
            if not self._is_after_cutoff(text):
                continue
            now = time.time()
            categories = categorize_logcat(text)
            if categories:
                with self.lock:
                    for category in categories:
                        self.recent.append((now, category, text))
                        self.events.write(
                            {
                                "ts": now,
                                "type": "logcat_match",
                                "category": category,
                                "line": text,
                            }
                        )

    def count(self, category: str, window_sec: float) -> int:
        cutoff = time.time() - window_sec
        with self.lock:
            return sum(1 for ts, cat, _ in self.recent if cat == category and ts >= cutoff)

    def has(self, category: str, window_sec: float) -> bool:
        return self.count(category, window_sec) > 0

    def stop(self) -> None:
        self.stop_event.set()
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        if self.thread:
            self.thread.join(timeout=3)
        if self.log_file:
            self.log_file.flush()
            self.log_file.close()

    def _is_after_cutoff(self, line: str) -> bool:
        if self.cutoff_dt is None:
            return True
        m = re.match(r"(\d{2})-(\d{2})\s+(\d{2}):(\d{2}):(\d{2})\.(\d+)", line)
        if not m:
            return False
        month, day, hour, minute, second, micros = m.groups()
        dt = datetime(
            self.cutoff_dt.year,
            int(month),
            int(day),
            int(hour),
            int(minute),
            int(second),
            int((micros + "000000")[:6]),
        )
        return dt >= self.cutoff_dt


def categorize_logcat(line: str) -> List[str]:
    categories = []
    lower = line.lower()
    if "no space left on device" in lower and "binder" in lower:
        categories.append("binder_enospc")
    if "binder transaction failure" in line or "FAILED BINDER TRANSACTION" in line:
        categories.append("binder_failure")
    if "Large outgoing transaction" in line or "Large data transaction" in line:
        categories.append("large_transaction")
    if "lowmemorykiller" in lower or "lmkd" in lower or "low on memory" in lower:
        categories.append("lmk")
    if any(k in line for k in GRAPHICS_KEYWORDS):
        categories.append("graphics")
    if any(k in line for k in TRANSITION_KEYWORDS):
        categories.append("transition")
    return categories


def parse_int(text: str) -> Optional[int]:
    try:
        return int(text.strip())
    except (ValueError, AttributeError):
        return None


def now_id() -> str:
    return datetime.now().strftime("run-%Y%m%d-%H%M%S")


def script_dir() -> Path:
    return Path(__file__).resolve().parent


def resolve_local_path(path: Optional[Path]) -> Optional[Path]:
    if path is None:
        return None
    if path.is_absolute() or path.exists():
        return path
    candidate = script_dir() / path
    return candidate if candidate.exists() else path


def load_config(path: Optional[Path]) -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if path:
        with path.open("r", encoding="utf-8") as fh:
            cfg.update(json.load(fh))
    return cfg


def parse_status(text: str) -> Dict[str, int]:
    result: Dict[str, int] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        parts = value.strip().split()
        if not parts:
            continue
        if key in ("FDSize", "VmRSS", "VmHWM", "Threads"):
            val = parse_int(parts[0])
            if val is not None:
                result[key] = val
    return result


def parse_meminfo(text: str) -> Dict[str, int]:
    result: Dict[str, int] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        parts = value.strip().split()
        if not parts:
            continue
        val = parse_int(parts[0])
        if val is not None:
            result[key] = val * KIB
    return result


def parse_total_dmabuf(text: str) -> Optional[int]:
    m = re.search(r"dmabuf total:\s+(\d+)\s+kB", text)
    if not m:
        return None
    return int(m.group(1)) * KIB


def pidof(adb: Adb, process_name: str, timeout: float) -> Optional[int]:
    res = adb.shell(f"pidof {shlex.quote(process_name)}", timeout=timeout)
    if res.returncode != 0:
        return None
    first = res.text.strip().split()
    if not first:
        return None
    return parse_int(first[0])


def fd_count_command(pid: int) -> str:
    return f"ls -l /proc/{pid}/fd"


def parse_fd_counts(text: str) -> Tuple[int, int, int]:
    total_fd = 0
    dmabuf_count = 0
    sync_count = 0
    for line in text.splitlines():
        if " -> " not in line:
            continue
        total_fd += 1
        _left, target = line.split(" -> ", 1)
        if "dmabuf" in target:
            dmabuf_count += 1
        elif "sync_file" in target:
            sync_count += 1
    return total_fd, dmabuf_count, sync_count


def parse_process_dmabuf_dump(text: str) -> Optional[int]:
    if "dmabuf info not found" in text:
        return 0
    totals = re.findall(r"PROCESS TOTAL\s+(\d+)\s+kB", text)
    if totals:
        return int(totals[-1]) * KIB
    m = re.search(r"userspace_rss:\s+(\d+)\s+kB", text)
    if m:
        return int(m.group(1)) * KIB
    return None


def sample_process(
    adb: Adb,
    key: str,
    name: str,
    last_pid: Optional[int],
    timeout: float,
) -> ProcessSample:
    pid = pidof(adb, name, timeout)
    sample = ProcessSample(key=key, name=name, pid=pid, pid_changed=pid is not None and last_pid not in (None, pid))
    if pid is None:
        sample.sample_error = "pid_not_found"
        return sample

    status = adb.shell(f"cat /proc/{pid}/status", timeout=timeout)
    if status.returncode == 0:
        parsed = parse_status(status.text)
        sample.fd_size = parsed.get("FDSize")
        sample.vmrss_kb = parsed.get("VmRSS")
        sample.threads = parsed.get("Threads")
    else:
        sample.sample_error = (status.stderr.decode("utf-8", errors="replace") or "status_failed").strip()

    fd = adb.shell(fd_count_command(pid), timeout=timeout)
    if fd.returncode == 0:
        try:
            total, dmabuf_count, sync_count = parse_fd_counts(fd.text)
            sample.total_fd = total
            sample.dmabuf_fd_count = dmabuf_count
            sample.sync_file_fd_count = sync_count
        except Exception as exc:  # noqa: BLE001
            sample.sample_error = f"fd_parse_error:{exc}"
    else:
        msg = fd.stderr.decode("utf-8", errors="replace").strip()
        sample.sample_error = msg or "fd_summary_failed"

    dmabuf_dump = adb.shell(f"dmabuf_dump {pid}", timeout=timeout)
    if dmabuf_dump.returncode == 0:
        sample.dmabuf_bytes = parse_process_dmabuf_dump(dmabuf_dump.text)
    elif sample.dmabuf_fd_count == 0:
        sample.dmabuf_bytes = 0
    elif sample.sample_error is None:
        msg = dmabuf_dump.stderr.decode("utf-8", errors="replace").strip()
        sample.sample_error = msg or "dmabuf_dump_pid_failed"
    return sample


def parse_display_id(sf_displays: str, preferred_resolution: Optional[str]) -> Optional[str]:
    blocks = re.split(r"\n(?=Display \d+)", sf_displays)
    candidates = []
    for block in blocks:
        m_id = re.search(r"^Display\s+(\d+)", block)
        if not m_id:
            continue
        display_id = m_id.group(1)
        m_res = re.search(r"resolution=(\d+x\d+)", block)
        res = m_res.group(1) if m_res else ""
        internal = "connectionType=Internal" in block
        area = 0
        if "x" in res:
            w, h = (parse_int(x) or 0 for x in res.split("x", 1))
            area = w * h
        candidates.append((display_id, res, internal, area))
    if preferred_resolution:
        for display_id, res, _, _ in candidates:
            if res == preferred_resolution:
                return display_id
    internal_candidates = [c for c in candidates if c[2]]
    selected = max(internal_candidates or candidates, key=lambda c: c[3], default=None)
    return selected[0] if selected else None


def capture_raw_screencap(adb: Adb, display_id: str, timeout: float) -> CommandResult:
    return adb.exec_out(["screencap", "-d", str(display_id)], timeout=timeout)


def compute_black_stats(raw: bytes, black_pixel_threshold: int) -> Tuple[int, int, float, float, float]:
    if len(raw) < 16:
        raise ValueError("raw screencap too short")
    width, height, fmt, _colorspace = struct.unpack_from("<IIII", raw, 0)
    if width <= 0 or height <= 0:
        raise ValueError(f"invalid raw header width={width} height={height}")
    pixel_count = width * height
    data = raw[16:]
    if len(data) < pixel_count * 4:
        raise ValueError(f"raw screencap data too short: {len(data)} for {width}x{height} fmt={fmt}")
    step = max(1, pixel_count // 500000)
    black = 0
    total = 0
    luma_sum = 0.0
    max_luma = 0.0
    for idx in range(0, pixel_count, step):
        off = idx * 4
        r = data[off]
        g = data[off + 1]
        b = data[off + 2]
        luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
        if r <= black_pixel_threshold and g <= black_pixel_threshold and b <= black_pixel_threshold:
            black += 1
        luma_sum += luma
        if luma > max_luma:
            max_luma = luma
        total += 1
    return width, height, black / total if total else 0.0, luma_sum / total if total else 0.0, max_luma


def parse_ams_resumed(activity_dump: str, logical_display_id: int) -> Optional[str]:
    section = extract_logical_display_section(activity_dump, logical_display_id)
    for text in (section, activity_dump):
        m = re.search(r"topResumedActivity=(ActivityRecord\{[^\n]+)", text)
        if m:
            return m.group(1).strip()
        m = re.search(r"ResumedActivity:\s+(ActivityRecord\{[^\n]+)", text)
        if m:
            return m.group(1).strip()
    return None


def extract_logical_display_section(text: str, display_id: int) -> str:
    marker = f"Display #{display_id}"
    start = text.find(marker)
    if start < 0:
        return ""
    next_match = re.search(r"\nDisplay #\d+", text[start + 1 :])
    end = start + 1 + next_match.start() if next_match else len(text)
    return text[start:end]


def parse_wms_visible_windows(window_dump: str, logical_display_id: int) -> Tuple[int, List[str]]:
    pattern = re.compile(rf"Display #{logical_display_id}:\s+\[(.*)\]")
    m = pattern.search(window_dump)
    windows: List[str] = []
    if m:
        content = m.group(1)
        for pkg in re.findall(r"([a-zA-Z0-9_]+\.[a-zA-Z0-9_./]+)", content):
            if not is_excluded_window(pkg):
                windows.append(pkg)
    if windows:
        return len(windows), windows
    section = extract_logical_display_section(window_dump, logical_display_id)
    for m_focus in re.finditer(r"mCurrentFocus=Window\{[^\s]+\s+u\d+\s+([^}\s]+)", section or window_dump):
        name = m_focus.group(1)
        if not is_excluded_window(name):
            windows.append(name)
    return len(windows), windows


def is_excluded_window(name: str) -> bool:
    return any(k in name for k in ("SystemBar", "ScreenDecor", "InputMethod", "Toast", "Wallpaper"))


def parse_sf_layers(sf_dump: str, physical_display_id: str) -> Tuple[int, List[str], Optional[bool]]:
    section = extract_physical_display_section(sf_dump, physical_display_id)
    if not section:
        return 0, [], None
    power_on = None
    m_power = re.search(r"powerMode=([A-Za-z]+)", section)
    if m_power:
        power_on = m_power.group(1).lower() == "on"
    layers: List[str] = []
    for line in section.splitlines():
        if "Output Layer" not in line:
            continue
        m = re.search(r"Output Layer [^(]+\((.*)\)\s*$", line.strip())
        if not m:
            continue
        name = m.group(1)
        if is_app_layer(name):
            layers.append(name)
    return len(layers), layers, power_on


def extract_physical_display_section(sf_dump: str, display_id: str) -> str:
    marker = f"Display {display_id} (physical"
    start = sf_dump.find(marker)
    if start < 0:
        marker = f"Display {display_id}"
        start = sf_dump.find(marker)
    if start < 0:
        return ""
    next_match = re.search(r"\nDisplay \d+", sf_dump[start + 1 :])
    end = start + 1 + next_match.start() if next_match else len(sf_dump)
    return sf_dump[start:end]


def is_app_layer(name: str) -> bool:
    if any(k in name for k in EXCLUDED_LAYER_KEYWORDS):
        return False
    return "com." in name or "ActivityRecord" in name or "Splash Screen" in name or "SurfaceView[" in name


def parse_display_on(display_dump: str, sf_power_on: Optional[bool]) -> Optional[bool]:
    if sf_power_on is not None:
        return sf_power_on
    if re.search(r"\b(state|mScreenState)=ON\b", display_dump):
        return True
    if re.search(r"\b(state|mScreenState)=OFF\b", display_dump):
        return False
    return None


def parse_brightness_nonzero(display_dump: str) -> Optional[bool]:
    for pattern in (r"Display Brightness=([0-9.]+)", r"mBrightnessState=([0-9.]+)"):
        m = re.search(pattern, display_dump)
        if m:
            try:
                return float(m.group(1)) > 0
            except ValueError:
                return None
    return None


def sample_black_state(
    adb: Adb,
    display_id: str,
    logical_display_id: int,
    cfg: dict,
    dump_timeout: float,
) -> BlackSample:
    ts = time.time()
    raw = capture_raw_screencap(adb, display_id, timeout=max(15, cfg["screencap_interval_sec"] - 1))
    if raw.returncode != 0:
        reason = raw.stderr.decode("utf-8", errors="replace").strip() or "screencap_failed"
        return BlackSample(ts=ts, hit=False, reason=reason)
    try:
        width, height, black_ratio, avg_luma, max_luma = compute_black_stats(
            raw.stdout, cfg["black_pixel_threshold"]
        )
    except Exception as exc:  # noqa: BLE001
        return BlackSample(ts=ts, hit=False, reason=f"screencap_parse_error:{exc}")

    activity = adb.shell("dumpsys activity activities", timeout=dump_timeout).text
    window = adb.shell("dumpsys window", timeout=dump_timeout).text
    sf = adb.shell("dumpsys SurfaceFlinger", timeout=dump_timeout).text
    display = adb.shell("dumpsys display", timeout=dump_timeout).text

    resumed = parse_ams_resumed(activity, logical_display_id)
    visible_windows, _window_names = parse_wms_visible_windows(window, logical_display_id)
    visible_layers, _layer_names, sf_power_on = parse_sf_layers(sf, display_id)
    display_on = parse_display_on(display, sf_power_on)
    brightness_nonzero = parse_brightness_nonzero(display)

    black_image = (
        black_ratio >= cfg["black_ratio_threshold"]
        and avg_luma <= cfg["black_luma_threshold"]
    )
    state_ok = (
        black_image
        and (display_on is not False)
        and (brightness_nonzero is not False)
        and resumed is not None
        and visible_windows > 0
        and visible_layers == 0
    )
    reason = "hit" if state_ok else "not_hit"
    return BlackSample(
        ts=ts,
        hit=state_ok,
        reason=reason,
        black_ratio=black_ratio,
        avg_luma=avg_luma,
        max_luma=max_luma,
        width=width,
        height=height,
        display_on=display_on,
        brightness_nonzero=brightness_nonzero,
        resumed_activity=resumed,
        wms_visible_app_windows=visible_windows,
        sf_visible_app_layers=visible_layers,
    )


def process_to_json(sample: ProcessSample) -> dict:
    return dataclasses.asdict(sample)


class Monitor:
    def __init__(self, args: argparse.Namespace, cfg: dict):
        self.args = args
        self.cfg = cfg
        self.adb = Adb(args.adb, args.serial)
        self.run_dir = Path(args.output_root) / (args.run_id or now_id())
        self.run_dir.mkdir(parents=True, exist_ok=True)
        (self.run_dir / "triggers").mkdir(exist_ok=True)
        self.monitor_writer = JsonlWriter(self.run_dir / "monitor.jsonl")
        self.events_writer = JsonlWriter(self.run_dir / "events.jsonl")
        self.logcat = LogcatCollector(self.adb, self.run_dir, self.events_writer)
        self.last_pids: Dict[str, Optional[int]] = {k: None for k in TARGET_PROCESSES}
        self.baseline_dmabuf: Dict[str, Optional[int]] = {k: None for k in TARGET_PROCESSES}
        self.proc_high_counts: Dict[str, int] = collections.defaultdict(int)
        self.fd_high_counts: Dict[str, int] = collections.defaultdict(int)
        self.total_dmabuf_high_count = 0
        self.black_hit_count = 0
        self.weak_black_hit_count = 0
        self.history: Deque[dict] = collections.deque(maxlen=600)
        self.trigger_index = 0
        self.trigger_index_lock = threading.Lock()
        self.c_snapshot_threads: List[threading.Thread] = []
        self.last_c_snapshot: Dict[str, float] = {}
        self.monkey_proc: Optional[subprocess.Popen] = None
        self.monkey_stdout = None
        self.monkey_pids_before: set[int] = set()
        self.display_id: Optional[str] = args.display_id

    def setup(self) -> None:
        if self.args.adb_root:
            self.adb.run(["root"], timeout=15)
            self.adb.run(["wait-for-device"], timeout=20)
        if not self.display_id:
            res = self.adb.shell("dumpsys SurfaceFlinger --displays", timeout=self.cfg["dump_timeout_sec"])
            self.display_id = parse_display_id(res.text, self.args.preferred_resolution)
        if not self.display_id:
            raise RuntimeError("cannot determine physical display id; pass --display-id")
        config_out = dict(self.cfg)
        config_out.update(
            {
                "adb": self.args.adb,
                "serial": self.args.serial,
                "display_id": self.display_id,
                "logical_display_id": self.args.logical_display_id,
                "target_processes": TARGET_PROCESSES,
                "monkey_args": self.args.monkey_args,
                "clear_logcat": self.args.clear_logcat,
                "adb_root": self.args.adb_root,
                "blacklist_file": str(self.args.blacklist_file) if self.args.blacklist_file else None,
                "device_blacklist_path": self.args.device_blacklist_path,
            }
        )
        (self.run_dir / "config.json").write_text(json.dumps(config_out, ensure_ascii=False, indent=2), encoding="utf-8")

    def start(self) -> None:
        self.logcat.start(clear_logcat=self.args.clear_logcat)
        if not self.args.oneshot:
            self.prepare_blacklist()
            self.start_monkey()

    def prepare_blacklist(self) -> None:
        if self.args.no_push_blacklist:
            return
        local = resolve_local_path(self.args.blacklist_file)
        if local is None:
            return
        if not local.exists():
            raise RuntimeError(f"blacklist file not found: {local}")
        remote = self.args.device_blacklist_path
        remote_dir = str(Path(remote).parent)
        self.adb.shell(f"mkdir -p {shlex.quote(remote_dir)}", timeout=self.cfg["command_timeout_sec"])
        res = self.adb.run(["push", str(local), remote], timeout=self.cfg["dump_timeout_sec"])
        if res.returncode != 0:
            err = (res.stderr or res.stdout).decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"failed to push blacklist {local} to {remote}: {err}")
        self.events_writer.write(
            {
                "ts": time.time(),
                "type": "blacklist_pushed",
                "local": str(local),
                "remote": remote,
                "adb_output": res.text.strip(),
            }
        )

    def start_monkey(self) -> None:
        self.monkey_pids_before = self.current_monkey_pids()
        monkey_args = shlex.split(self.args.monkey_args)
        full_cmd = self.adb.base() + ["shell", "monkey"] + monkey_args
        (self.run_dir / "monkey.cmd").write_text(shlex.join(full_cmd) + "\n", encoding="utf-8")
        self.monkey_stdout = (self.run_dir / "monkey.log").open("ab", buffering=0)
        self.monkey_proc = self.adb.popen(
            ["shell", "monkey"] + monkey_args,
            stdout=self.monkey_stdout,
            stderr=subprocess.STDOUT,
        )

    def current_monkey_pids(self) -> set[int]:
        res = self.adb.shell("pidof com.android.commands.monkey", timeout=self.cfg["command_timeout_sec"])
        if res.returncode != 0:
            return set()
        return {int(x) for x in res.text.strip().split() if x.isdigit()}

    def stop_monkey(self) -> None:
        current = self.current_monkey_pids()
        ours = current - self.monkey_pids_before
        target = ours or (current if not self.monkey_pids_before else set())
        for pid in sorted(target):
            self.adb.shell(f"kill -TERM {pid}", timeout=5)
        time.sleep(3)
        remaining = self.current_monkey_pids() & target
        for pid in sorted(remaining):
            self.adb.shell(f"kill -KILL {pid}", timeout=5)
        if self.monkey_proc and self.monkey_proc.poll() is None:
            self.monkey_proc.terminate()
            try:
                self.monkey_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.monkey_proc.kill()
        if self.monkey_stdout:
            self.monkey_stdout.flush()
            self.monkey_stdout.close()

    def run(self) -> None:
        self.setup()
        self.start()
        next_sample = 0.0
        next_black = 0.0
        started_at = time.time()
        stop_reason: Optional[dict] = None
        try:
            if self.args.oneshot:
                sample = self.sample_once(force_black=True)
                self.monitor_writer.write(sample)
                self.capture_snapshot("oneshot", {"rule_id": "ONESHOT", "sample": sample}, stop_action=False)
                return
            while True:
                now = time.time()
                if self.args.max_duration_sec and now - started_at >= self.args.max_duration_sec:
                    stop_reason = {
                        "rule_id": "MAX_DURATION",
                        "rule_name": "Configured max duration reached",
                        "ts": now,
                        "elapsed_sec": now - started_at,
                    }
                    break
                if self.monkey_proc and self.monkey_proc.poll() is not None:
                    stop_reason = {"rule_id": "MONKEY_EXITED", "rule_name": "Monkey process exited", "ts": now}
                    break
                if now >= next_sample:
                    force_black = now >= next_black
                    sample = self.sample_once(force_black=force_black)
                    if force_black:
                        next_black = now + self.cfg["screencap_interval_sec"]
                    self.monitor_writer.write(sample)
                    self.history.append(sample)
                    stop_reason = self.evaluate(sample)
                    if stop_reason:
                        break
                    next_sample = now + self.cfg["sample_interval_sec"]
                time.sleep(0.1)
        finally:
            if stop_reason:
                self.handle_stop(stop_reason)
            else:
                self.shutdown()

    def sample_once(self, force_black: bool = False) -> dict:
        ts = time.time()
        processes = {}
        for key, name in TARGET_PROCESSES.items():
            sample = sample_process(
                self.adb,
                key,
                name,
                self.last_pids.get(key),
                timeout=self.cfg["command_timeout_sec"],
            )
            processes[key] = process_to_json(sample)
            if sample.pid is not None:
                self.last_pids[key] = sample.pid
            if sample.dmabuf_bytes is not None and self.baseline_dmabuf[key] is None:
                self.baseline_dmabuf[key] = sample.dmabuf_bytes

        meminfo_res = self.adb.shell("cat /proc/meminfo", timeout=self.cfg["command_timeout_sec"])
        meminfo = parse_meminfo(meminfo_res.text) if meminfo_res.returncode == 0 else {}
        dmabuf_res = self.adb.shell("dmabuf_dump", timeout=self.cfg["dump_timeout_sec"])
        total_dmabuf = parse_total_dmabuf(dmabuf_res.text) if dmabuf_res.returncode == 0 else None

        black = None
        if force_black:
            assert self.display_id is not None
            black_sample = sample_black_state(
                self.adb,
                self.display_id,
                self.args.logical_display_id,
                self.cfg,
                self.cfg["dump_timeout_sec"],
            )
            black = dataclasses.asdict(black_sample)
            if black_sample.hit:
                self.black_hit_count += 1
                self.weak_black_hit_count += 1
            else:
                self.black_hit_count = 0
                self.weak_black_hit_count = 0

        return {
            "ts": ts,
            "iso_time": datetime.fromtimestamp(ts).isoformat(timespec="seconds"),
            "processes": processes,
            "meminfo": meminfo,
            "total_dmabuf_bytes": total_dmabuf,
            "black_sample": black,
            "black_hit_count": self.black_hit_count,
            "weak_black_hit_count": self.weak_black_hit_count,
            "logcat_counts": {
                "binder_enospc_10s": self.logcat.count("binder_enospc", 10),
                "binder_failure_10s": self.logcat.count("binder_failure", 10),
                "large_transaction_10s": self.logcat.count("large_transaction", 10),
                "lmk_30s": self.logcat.count("lmk", 30),
                "graphics_10s": self.logcat.count("graphics", 10),
                "transition_30s": self.logcat.count("transition", 30),
            },
        }

    def evaluate(self, sample: dict) -> Optional[dict]:
        ts = sample["ts"]
        processes = sample["processes"]
        total_dmabuf = sample.get("total_dmabuf_bytes")
        log_counts = sample.get("logcat_counts", {})

        for key, proc in processes.items():
            dmabuf = proc.get("dmabuf_bytes")
            if dmabuf is not None:
                threshold = self.cfg["process_dmabuf_limit_bytes"]
                baseline = self.baseline_dmabuf.get(key)
                if baseline is not None and baseline >= threshold:
                    threshold = baseline + self.cfg["process_dmabuf_baseline_margin_bytes"]
                if dmabuf >= threshold:
                    self.proc_high_counts[key] += 1
                    self.maybe_c_snapshot("C_PROCESS_DMABUF_SINGLE", sample)
                else:
                    self.proc_high_counts[key] = 0
                if self.proc_high_counts[key] >= self.cfg["process_dmabuf_consecutive_sec"]:
                    return self.reason("A1", f"{key} dmabuf high", sample, process=key, value=dmabuf, threshold=threshold)

            total_fd = proc.get("total_fd")
            fd_limit_hit = False
            fd_limit = self.cfg["fd_absolute_limit"]
            fd_soft_limit = int(fd_limit * self.cfg["fd_limit_ratio"])
            if total_fd is not None:
                if total_fd >= fd_soft_limit or total_fd >= fd_limit:
                    fd_limit_hit = True
            self.fd_high_counts[key] = self.fd_high_counts[key] + 1 if fd_limit_hit else 0
            if self.fd_high_counts[key] >= self.cfg["fd_consecutive_sec"]:
                return self.reason(
                    "A4",
                    f"{key} fd near limit",
                    sample,
                    process=key,
                    value=total_fd,
                    fd_limit=fd_limit,
                    fd_soft_limit=fd_soft_limit,
                )

            growth = self.fd_growth(key, sample, 60)
            if growth and (
                growth.get("dmabuf_fd_growth", 0) >= self.cfg["sync_file_growth_limit_per_60s"]
                or growth.get("sync_file_fd_growth", 0) >= self.cfg["sync_file_growth_limit_per_60s"]
            ):
                return self.reason("A4", f"{key} fd growth high", sample, process=key, growth=growth)

        if total_dmabuf is not None:
            if total_dmabuf >= self.cfg["total_dmabuf_hard_limit_bytes"]:
                return self.reason("A2", "total dmabuf hard limit", sample, value=total_dmabuf)
            if total_dmabuf >= self.cfg["total_dmabuf_soft_limit_bytes"]:
                self.total_dmabuf_high_count += 1
            else:
                self.total_dmabuf_high_count = 0
            if self.total_dmabuf_high_count >= self.cfg["total_dmabuf_soft_consecutive_sec"]:
                return self.reason("A2", "total dmabuf soft limit", sample, value=total_dmabuf)

        if self.black_hit_count >= self.cfg["black_screen_consecutive_samples"]:
            return self.reason("A3", "black screen mismatch", sample)
        if sample.get("black_sample") and sample["black_sample"].get("black_ratio", 0) >= self.cfg["black_ratio_threshold"]:
            self.maybe_c_snapshot("C_BLACK_SAMPLE", sample)

        sysui = processes.get("systemui", {})
        if sysui.get("pid_changed") and self.systemui_prior_abnormal(sample):
            return self.reason("A6", "SystemUI pid changed after resource abnormality", sample)

        mem = sample.get("meminfo", {})
        if log_counts.get("lmk_30s", 0) >= self.cfg["lmk_limit_per_30s"]:
            if mem.get("SwapFree", 1 << 60) < self.cfg["swapfree_low_bytes"]:
                return self.reason("A7", "LMK with low swap", sample)
            if mem.get("CmaFree", 1 << 60) < self.cfg["cmafree_low_bytes"] and log_counts.get("graphics_10s", 0) > 0:
                return self.reason("A7", "LMK/CMA graphics pressure", sample)
            if mem.get("MemAvailable", 1 << 60) < self.cfg["memavailable_low_bytes"] and self.any_resource_growing(sample):
                return self.reason("A7", "LMK low MemAvailable and resource growth", sample)

        weak = self.weak_condition(sample)
        if log_counts.get("transition_30s", 0) >= self.cfg["transition_error_limit_per_30s"] and weak:
            self.maybe_c_snapshot("A9", sample, "transition errors with weak resource/black condition")

        if log_counts.get("large_transaction_10s", 0) > 0:
            self.maybe_c_snapshot("C_LARGE_TRANSACTION", sample)
        return None

    def fd_growth(self, key: str, sample: dict, window_sec: float) -> Optional[dict]:
        now = sample["ts"]
        current = sample["processes"].get(key, {})
        oldest = None
        for item in self.history:
            if now - item["ts"] >= window_sec:
                oldest = item
                break
        if not oldest:
            return None
        prev = oldest["processes"].get(key, {})
        if current.get("dmabuf_fd_count") is None or prev.get("dmabuf_fd_count") is None:
            return None
        return {
            "dmabuf_fd_growth": current.get("dmabuf_fd_count", 0) - prev.get("dmabuf_fd_count", 0),
            "sync_file_fd_growth": current.get("sync_file_fd_count", 0) - prev.get("sync_file_fd_count", 0),
        }

    def systemui_prior_abnormal(self, sample: dict) -> bool:
        cutoff = sample["ts"] - self.cfg["systemui_pid_change_prior_window_sec"]
        for item in reversed(self.history):
            if item["ts"] < cutoff:
                break
            sysui = item["processes"].get("systemui", {})
            if (sysui.get("dmabuf_bytes") or 0) >= self.cfg["process_dmabuf_weak_limit_bytes"]:
                return True
            if (sysui.get("sync_file_fd_count") or 0) >= 1000:
                return True
            if item.get("logcat_counts", {}).get("binder_enospc_10s", 0) > 0:
                return True
        return False

    def any_resource_growing(self, sample: dict) -> bool:
        for key in TARGET_PROCESSES:
            growth = self.fd_growth(key, sample, 60)
            if growth and (growth.get("dmabuf_fd_growth", 0) > 0 or growth.get("sync_file_fd_growth", 0) > 0):
                return True
        return False

    def weak_condition(self, sample: dict) -> bool:
        if self.weak_black_hit_count >= self.cfg["weak_black_screen_consecutive_samples"]:
            return True
        if (sample.get("total_dmabuf_bytes") or 0) >= self.cfg["total_dmabuf_weak_limit_bytes"]:
            return True
        if sample.get("logcat_counts", {}).get("binder_enospc_10s", 0) > 0:
            return True
        if sample.get("logcat_counts", {}).get("large_transaction_10s", 0) >= 3:
            return True
        for proc in sample.get("processes", {}).values():
            if (proc.get("dmabuf_bytes") or 0) >= self.cfg["process_dmabuf_weak_limit_bytes"]:
                return True
        return False

    def maybe_c_snapshot(self, rule_id: str, sample: dict, rule_name: str = "C class snapshot") -> None:
        now = time.time()
        last = self.last_c_snapshot.get(rule_id, 0)
        if now - last < self.cfg["c_snapshot_cooldown_sec"]:
            return
        self.last_c_snapshot[rule_id] = now
        reason = self.reason(rule_id, rule_name, sample)
        self.c_snapshot_threads = [t for t in self.c_snapshot_threads if t.is_alive()]
        thread = threading.Thread(
            target=self.capture_snapshot_guarded,
            args=(rule_id.lower(), reason, False),
            name=f"c-snapshot-{rule_id.lower()}",
            daemon=True,
        )
        self.c_snapshot_threads.append(thread)
        thread.start()

    def capture_snapshot_guarded(self, label: str, reason: dict, stop_action: bool) -> None:
        try:
            self.capture_snapshot(label, reason, stop_action)
        except Exception as exc:  # noqa: BLE001
            self.events_writer.write(
                {
                    "ts": time.time(),
                    "type": "snapshot_error",
                    "label": label,
                    "error": repr(exc),
                }
            )

    def reason(self, rule_id: str, name: str, sample: dict, **extra) -> dict:
        return {
            "rule_id": rule_id,
            "rule_name": name,
            "ts": time.time(),
            "iso_time": datetime.now().isoformat(timespec="seconds"),
            "recent_samples": list(self.history)[-10:],
            "current_sample": sample,
            **extra,
        }

    def handle_stop(self, reason: dict) -> None:
        self.capture_snapshot("pre_stop", reason, stop_action=True)
        self.stop_monkey()
        time.sleep(self.cfg["post_stop_logcat_delay_sec"])
        self.capture_snapshot("post_stop", reason, stop_action=True)
        self.shutdown()

    def capture_snapshot(self, label: str, reason: dict, stop_action: bool) -> None:
        with self.trigger_index_lock:
            self.trigger_index += 1
            trigger_index = self.trigger_index
        out = self.run_dir / "triggers" / f"{trigger_index:04d}_{label}"
        out.mkdir(parents=True, exist_ok=True)
        reason = dict(reason)
        reason["stop_action"] = stop_action
        reason["display_id"] = self.display_id
        (out / "reason.json").write_text(json.dumps(reason, ensure_ascii=False, indent=2), encoding="utf-8")

        commands = {
            "dumpsys_activity.txt": "dumpsys activity activities",
            "dumpsys_window.txt": "dumpsys window",
            "dumpsys_surfaceflinger.txt": "dumpsys SurfaceFlinger",
            "dumpsys_surfaceflinger_list.txt": "dumpsys SurfaceFlinger --list",
            "dumpsys_surfaceflinger_displays.txt": "dumpsys SurfaceFlinger --displays",
            "dumpsys_display.txt": "dumpsys display",
            "meminfo.txt": "cat /proc/meminfo",
            "dmabuf_full.txt": "dmabuf_dump",
            "ps_A.txt": "ps -A",
        }
        for filename, command in commands.items():
            res = self.adb.shell(command, timeout=self.cfg["dump_timeout_sec"])
            write_bytes(out / filename, res.stdout + res.stderr)

        if self.display_id:
            png = self.adb.exec_out(["screencap", "-p", "-d", str(self.display_id)], timeout=20)
            write_bytes(out / "screencap.png", png.stdout + png.stderr)

        for key, name in TARGET_PROCESSES.items():
            pid = self.last_pids.get(key) or pidof(self.adb, name, self.cfg["command_timeout_sec"])
            proc_dir = out / key
            proc_dir.mkdir(exist_ok=True)
            if not pid:
                (proc_dir / "missing.txt").write_text(f"{name} pid not found\n", encoding="utf-8")
                continue
            proc_cmds = {
                "status.txt": f"cat /proc/{pid}/status",
                "fd.txt": f"ls -l /proc/{pid}/fd",
                "fdinfo_all.txt": dump_fdinfo_command(pid),
                "dmabuf_pid.txt": f"dmabuf_dump {pid}",
            }
            for filename, command in proc_cmds.items():
                res = self.adb.shell(command, timeout=self.cfg["dump_timeout_sec"])
                write_bytes(proc_dir / filename, res.stdout + res.stderr)

    def shutdown(self) -> None:
        try:
            self.join_c_snapshots()
            self.logcat.stop()
        finally:
            self.monitor_writer.close()
            self.events_writer.close()

    def join_c_snapshots(self) -> None:
        deadline = time.time() + self.cfg["c_snapshot_join_timeout_sec"]
        for thread in list(self.c_snapshot_threads):
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            thread.join(timeout=remaining)
        still_alive = [thread.name for thread in self.c_snapshot_threads if thread.is_alive()]
        if still_alive:
            self.events_writer.write(
                {
                    "ts": time.time(),
                    "type": "snapshot_threads_still_running",
                    "threads": still_alive,
                }
            )


def dump_fdinfo_command(pid: int) -> str:
    return f"""for f in /proc/{pid}/fdinfo/*; do
  echo "===== $f ====="
  cat "$f" 2>&1
done
"""


def write_bytes(path: Path, data: bytes) -> None:
    path.write_bytes(data)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Monkey and stop on dmabuf/black-screen conditions.")
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--serial", default=None)
    parser.add_argument("--output-root", default="runs")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--display-id", default=None)
    parser.add_argument("--preferred-resolution", default="6400x1800")
    parser.add_argument("--logical-display-id", type=int, default=0)
    parser.add_argument("--clear-logcat", action="store_true")
    parser.add_argument("--adb-root", dest="adb_root", action="store_true", default=True)
    parser.add_argument("--no-adb-root", dest="adb_root", action="store_false")
    parser.add_argument("--oneshot", action="store_true", help="Collect one sample/snapshot without starting Monkey.")
    parser.add_argument("--blacklist-file", type=Path, default=Path("blacklist.txt"))
    parser.add_argument("--device-blacklist-path", default="/log/blacklist.txt")
    parser.add_argument("--no-push-blacklist", action="store_true")
    parser.add_argument("--max-duration-sec", type=float, default=None)
    parser.add_argument(
        "--monkey-args",
        default=DEFAULT_MONKEY_ARGS,
        help="Arguments passed after 'adb shell monkey'. Quote as one string.",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    cfg = load_config(args.config)
    monitor = Monitor(args, cfg)
    try:
        monitor.run()
        print(str(monitor.run_dir))
        return 0
    except KeyboardInterrupt:
        monitor.stop_monkey()
        monitor.shutdown()
        return 130
    except Exception as exc:  # noqa: BLE001
        try:
            monitor.events_writer.write({"ts": time.time(), "type": "fatal", "error": repr(exc)})
            monitor.shutdown()
        except Exception:
            pass
        print(f"fatal: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
