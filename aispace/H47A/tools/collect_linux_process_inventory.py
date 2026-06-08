#!/usr/bin/env python3
"""Collect Linux-side process inventory through adb and render markdown.

The final markdown intentionally omits PID/PPID because those are runtime
identifiers. They are only used inside the collector to resolve parent process
names and group repeated stable process identities.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import re
import shlex
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MD = ROOT / "linux_process_inventory.md"
DEFAULT_RAW = ROOT / "linux_process_inventory_raw.tsv"


REMOTE_COLLECTOR = r"""
self=$$
printf 'META\tself_pid\t%s\n' "$self"
for d in /proc/[0-9]*; do
    pid=${d#/proc/}
    [ "$pid" = "$self" ] && continue
    [ -r "$d/status" ] || continue

    status_name=
    status_state=
    status_ppid=
    status_uid=
    status_threads=
    status_kthread=
    status_rss=
    status_vsz=
    while IFS= read -r line; do
        case "$line" in
            Name:*) status_name=${line#Name:}; status_name=${status_name#	};;
            State:*) status_state=${line#State:}; status_state=${status_state#	};;
            PPid:*) status_ppid=${line#PPid:}; status_ppid=${status_ppid#	};;
            Uid:*) set -- $line; status_uid=$2;;
            Threads:*) status_threads=${line#Threads:}; status_threads=${status_threads#	};;
            Kthread:*) status_kthread=${line#Kthread:}; status_kthread=${status_kthread#	};;
            VmRSS:*) set -- $line; status_rss=$2;;
            VmSize:*) set -- $line; status_vsz=$2;;
        esac
    done < "$d/status"

    statline=$(cat "$d/stat" 2>/dev/null)
    cmdline=$(tr '\000' ' ' < "$d/cmdline" 2>/dev/null)
    exe=$(readlink "$d/exe" 2>/dev/null)
    cgroup=$(tr '\n' ';' < "$d/cgroup" 2>/dev/null)
    pss=
    if [ "${COLLECT_PSS:-0}" = "1" ] && [ "$status_kthread" != "1" ]; then
        pss=$(awk '/^Pss:/ {print $2; exit}' "$d/smaps_rollup" 2>/dev/null)
    fi

    sockets=
    devs=
    if [ "${COLLECT_FD:-0}" = "1" ] && [ "$status_kthread" != "1" ]; then
        sockets=0
        for f in "$d"/fd/*; do
            [ -e "$f" ] || continue
            link=$(readlink "$f" 2>/dev/null) || continue
            case "$link" in
                socket:*) sockets=$((sockets + 1));;
                /dev/*|/sys/*|/proc/device-tree/*)
                    case ";$devs;" in
                        *";$link;"*) ;;
                        *) devs="${devs};${link}" ;;
                    esac
                    ;;
            esac
        done
        devs=${devs#;}
    fi

    status_name=$(printf '%s' "$status_name" | tr '\t\r\n' '   ')
    status_state=$(printf '%s' "$status_state" | tr '\t\r\n' '   ')
    status_ppid=$(printf '%s' "$status_ppid" | tr '\t\r\n' '   ')
    status_uid=$(printf '%s' "$status_uid" | tr '\t\r\n' '   ')
    status_threads=$(printf '%s' "$status_threads" | tr '\t\r\n' '   ')
    status_kthread=$(printf '%s' "$status_kthread" | tr '\t\r\n' '   ')
    status_rss=$(printf '%s' "$status_rss" | tr '\t\r\n' '   ')
    status_vsz=$(printf '%s' "$status_vsz" | tr '\t\r\n' '   ')
    statline=$(printf '%s' "$statline" | tr '\t\r\n' '   ')
    cmdline=$(printf '%s' "$cmdline" | tr '\t\r\n' '   ')
    exe=$(printf '%s' "$exe" | tr '\t\r\n' '   ')
    cgroup=$(printf '%s' "$cgroup" | tr '\t\r\n' '   ')
    pss=$(printf '%s' "$pss" | tr '\t\r\n' '   ')
    devs=$(printf '%s' "$devs" | tr '\t\r\n' '   ')

    printf 'PROC\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$pid" "$status_ppid" "$status_name" "$status_state" "$status_uid" \
        "$status_threads" "$status_kthread" "$status_rss" "$status_vsz" \
        "$pss" "$sockets" "$devs" "$exe" "$cmdline" "$cgroup" "$statline"
done
"""


def run_adb(
    args: list[str],
    *,
    serial: str | None = None,
    stdin: str | None = None,
    check: bool = True,
) -> str:
    cmd = ["adb"]
    if serial:
        cmd.extend(["-s", serial])
    cmd.extend(args)
    proc = subprocess.run(
        cmd,
        input=stdin,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"command failed: {shlex.join(cmd)}\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}"
        )
    return proc.stdout


def run_adb_shell(command: str, *, serial: str | None = None, check: bool = False) -> str:
    return run_adb(["shell", command], serial=serial, check=check)


def list_adb_serials(devices_text: str) -> list[str]:
    serials: list[str] = []
    for line in devices_text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device" and not line.startswith("List of"):
            serials.append(parts[0])
    return serials


def detect_linux_serial(devices_text: str) -> str | None:
    serials = list_adb_serials(devices_text)
    if len(serials) == 1:
        return serials[0]
    for serial in serials:
        probe = run_adb_shell(
            "sh -c 'test -f /etc/os-release && command -v systemctl >/dev/null && echo PVM_LINUX'",
            serial=serial,
            check=False,
        )
        if "PVM_LINUX" in probe:
            return serial
    return None


def parse_passwd(text: str) -> dict[int, str]:
    users: dict[int, str] = {}
    for line in text.splitlines():
        parts = line.split(":")
        if len(parts) >= 3 and parts[2].isdigit():
            users[int(parts[2])] = parts[0]
    return users


ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def parse_service_descriptions(text: str) -> dict[str, str]:
    descriptions: dict[str, str] = {}
    for line in text.splitlines():
        line = ANSI_RE.sub("", line).strip()
        if not line:
            continue
        if line.startswith("●"):
            line = line[1:].strip()
        parts = line.split(None, 4)
        if len(parts) == 5 and parts[0].endswith(".service"):
            descriptions[parts[0]] = parts[4].strip()
    return descriptions


def parse_stat(statline: str) -> dict[str, str]:
    if not statline:
        return {}
    left = statline.find("(")
    right = statline.rfind(")")
    if left < 0 or right < left:
        return {}
    comm = statline[left + 1 : right]
    fields = statline[right + 2 :].split()
    result = {"stat_comm": comm}
    if len(fields) > 38:
        result.update(
            {
                "stat_state": fields[0],
                "stat_ppid": fields[1],
                "priority": fields[15],
                "nice": fields[16],
                "num_threads": fields[17],
                "rt_priority": fields[37],
                "policy": fields[38],
            }
        )
    return result


def short_state(status_state: str, stat_state: str) -> str:
    if status_state:
        match = re.match(r"([A-Z])\s+\(([^)]+)\)", status_state)
        if match:
            return f"{match.group(1)}/{match.group(2)}"
    return stat_state or status_state or "-"


POLICY_MAP = {
    "0": "SCHED_NORMAL",
    "1": "SCHED_FIFO",
    "2": "SCHED_RR",
    "3": "SCHED_BATCH",
    "5": "SCHED_IDLE",
    "6": "SCHED_DEADLINE",
}


def policy_name(value: str) -> str:
    return POLICY_MAP.get(value, value or "-")


def is_kernel(row: dict[str, str]) -> bool:
    if row.get("kthread") == "1":
        return True
    cmd = row.get("cmdline", "").strip()
    return not cmd and row.get("stat_comm", "")


GENERIC_COMM = {"main", "busybox", "sh", "bash", "python", "python3"}


def basename(path: str) -> str:
    return os.path.basename(path.rstrip("/"))


def first_cmd_token(cmdline: str) -> str:
    return cmdline.strip().split(" ", 1)[0] if cmdline.strip() else ""


def process_name(row: dict[str, str]) -> str:
    if is_kernel(row):
        return row.get("stat_comm") or row.get("status_name") or "-"

    cmdline = row.get("cmdline", "").strip()
    exe = row.get("exe", "").strip()
    status_name = row.get("status_name", "").strip()
    first = first_cmd_token(cmdline)

    if first.startswith("/") and basename(first):
        return basename(first)
    if exe and basename(exe) and (status_name in GENERIC_COMM or not status_name):
        return basename(exe)
    if status_name:
        return status_name
    if first:
        return basename(first)
    return "-"


def command_for_table(row: dict[str, str], full: bool) -> str:
    if is_kernel(row):
        return f"[{row.get('stat_comm') or row.get('status_name') or '-'}]"
    cmdline = row.get("cmdline", "").strip()
    exe = row.get("exe", "").strip()
    command = cmdline or exe or "-"
    if full or len(command) <= 180:
        return command
    return command[:177].rstrip() + "..."


def extract_unit(cgroup: str) -> str:
    candidates = re.findall(r"([^/;]+(?:\.service|\.scope))", cgroup)
    if candidates:
        return candidates[-1]
    return "-"


def extract_cmd_dev_nodes(cmdline: str) -> list[str]:
    nodes: list[str] = []
    for match in re.finditer(r"(/dev/[A-Za-z0-9_./:@+-]+)", cmdline):
        node = match.group(1).rstrip(",;")
        if node not in nodes:
            nodes.append(node)
    return nodes


HW_PATTERNS = [
    "irq/",
    "napi/",
    "vfio",
    "virtio",
    "qcom",
    "scmi",
    "smmu",
    "thermal",
    "sensor",
    "watchdog",
    "wdt",
    "ufs",
    "usb",
    "dwc3",
    "gpio",
    "i2c",
    "spi",
    "uart",
    "pcie",
    "emac",
    "eth",
    "wlan",
    "bluetooth",
    "touch",
    "display",
    "openwfd",
    "weston",
    "gpu",
    "kgsl",
    "camera",
    "cam",
    "audio",
    "fastrpc",
    "glink",
    "qdss",
    "qsee",
    "tpm",
    "dpu",
    "dprx",
    "eva",
    "gpce",
    "nsp",
    "ptp",
    "rtl9071",
]


def hardware_guess(row: dict[str, str], proc_name: str, devices: list[str]) -> tuple[str, str]:
    cmdline = row.get("cmdline", "")
    haystack = " ".join(
        [
            proc_name,
            row.get("stat_comm", ""),
            row.get("status_name", ""),
            cmdline,
            row.get("unit", ""),
            row.get("service_description", ""),
            " ".join(devices),
        ]
    ).lower()

    deps: list[str] = []
    for dev in devices:
        deps.append(dev)
    for keyword in HW_PATTERNS:
        if keyword in haystack and keyword not in deps:
            deps.append(keyword)

    if devices or any(keyword in haystack for keyword in HW_PATTERNS):
        return "是", ", ".join(deps[:8]) or "名称/命令体现硬件相关"
    if is_kernel(row) and proc_name.startswith(("kworker/", "kworker/R-", "kworker/u")):
        return "待确认", "内核工作队列，需结合wq名称/调用栈确认"
    if is_kernel(row):
        return "待确认", "内核线程，未发现明确设备线索"
    return "否", "-"


def infer_role(row: dict[str, str], proc_name: str) -> str:
    unit_desc = row.get("service_description", "")
    if unit_desc:
        return unit_desc

    name = proc_name.lower()
    cmd = row.get("cmdline", "").lower()

    if is_kernel(row):
        if name == "kthreadd":
            return "内核线程管理入口"
        if name.startswith("kworker"):
            return "内核workqueue任务"
        if name.startswith("irq/"):
            return "处理中断线程"
        if name.startswith("napi/"):
            return "网络NAPI收包轮询线程"
        if name.startswith("rcu"):
            return "RCU回调/宽限期处理"
        if name.startswith("migration/"):
            return "CPU任务迁移线程"
        if name.startswith("ksoftirqd/"):
            return "软中断处理线程"
        if name.startswith("cpuhp/"):
            return "CPU hotplug管理线程"
        if name.startswith("ktimers/"):
            return "内核定时器线程"
        if name.startswith("jbd2/"):
            return "ext4日志线程"
        if name == "nfsd":
            return "内核NFS服务线程"
        return "内核线程"

    if name == "systemd":
        return "systemd系统/用户管理进程"
    if "qcrosvm" in name:
        return "启动并承载Android GVM虚拟机"
    if "vhost" in name:
        return "为GVM提供vhost/virtio后端设备"
    if "someipd" in name:
        return "SOME/IP网络服务"
    if "weston" in name:
        return "Wayland显示合成器"
    if "openwfd" in name:
        return "OpenWFD显示服务"
    if "thermal" in name:
        return "热管理服务"
    if "diag" in name:
        return "诊断/日志通道服务"
    if "fastrpc" in name:
        return "FastRPC资源/音频通道服务"
    if "glink" in name:
        return "GLINK跨处理器通信服务"
    if "rpcbind" in name:
        return "RPC端口映射服务"
    if "nfs" in name or "rpc.mountd" in name or "rpc.statd" in name:
        return "NFS/RPC服务"
    if "adbd" in name:
        return "ADB调试连接服务"
    if "agetty" in name:
        return "登录终端"
    if "log" in name or "dlt" in name:
        return "日志采集/管理服务"
    if "touch" in name:
        return "触摸输入服务"
    if "cam" in name or "camera" in cmd:
        return "摄像头相关服务"
    if "display" in name:
        return "显示相关服务"
    if "power" in name:
        return "电源管理服务"
    if "update" in name:
        return "升级管理服务"
    return "待确认"


def md_escape(value: object) -> str:
    text = str(value) if value is not None else ""
    text = text.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    text = text.replace("|", r"\|")
    return text or "-"


def compact_values(values: list[str]) -> str:
    clean = [v for v in values if v not in ("", "-")]
    if not clean:
        return "-"
    unique = []
    for value in clean:
        if value not in unique:
            unique.append(value)
    if len(unique) == 1:
        return unique[0]
    return " / ".join(unique[:4]) + (" ..." if len(unique) > 4 else "")


def number_range(values: list[str]) -> str:
    nums = []
    for value in values:
        try:
            nums.append(int(value))
        except (TypeError, ValueError):
            pass
    if not nums:
        return "-"
    if min(nums) == max(nums):
        return str(nums[0])
    return f"{min(nums)}-{max(nums)}"


def parse_proc_rows(text: str, users: dict[int, str], services: dict[str, str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    reader = csv.reader(text.splitlines(), delimiter="\t")
    for fields in reader:
        if not fields or fields[0] != "PROC":
            continue
        if len(fields) < 17:
            continue
        row = {
            "pid": fields[1],
            "ppid": fields[2],
            "status_name": fields[3],
            "status_state": fields[4],
            "uid": fields[5],
            "threads": fields[6],
            "kthread": fields[7],
            "rss": fields[8],
            "vsz": fields[9],
            "pss": fields[10],
            "socket_count": fields[11],
            "fd_devices": fields[12],
            "exe": fields[13],
            "cmdline": fields[14],
            "cgroup": fields[15],
            "statline": fields[16],
        }
        row.update(parse_stat(row["statline"]))
        unit = extract_unit(row["cgroup"])
        row["unit"] = unit
        row["service_description"] = services.get(unit, "")
        try:
            uid_num = int(row["uid"])
            user_name = users.get(uid_num, str(uid_num))
        except ValueError:
            user_name = row["uid"] or "-"
        row["user"] = user_name
        rows.append(row)
    return rows


def service_for_process(proc_name: str, services: dict[str, str]) -> tuple[str, str]:
    candidates = [
        f"{proc_name}.service",
        f"{proc_name.replace('_', '-')}.service",
        f"{proc_name.replace('-', '_')}.service",
        f"{proc_name.replace('_', '')}.service",
    ]
    for candidate in candidates:
        if candidate in services:
            return candidate, services[candidate]
    return "-", ""


def parse_ps_rows(text: str, services: dict[str, str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    ps_marker = "ps -ww -eo pid=,ppid=,user=,stat=,policy=,pri=,ni=,nlwp=,rss=,vsz=,args="
    for line in text.splitlines():
        line = line.rstrip()
        if not line:
            continue
        parts = line.split(None, 10)
        if len(parts) < 11:
            continue
        pid, ppid, user, stat, policy, pri, ni, nlwp, rss, vsz, args = parts
        if ps_marker in args:
            continue
        if not pid.isdigit() or not ppid.isdigit():
            continue

        kernel = args.startswith("[") and args.endswith("]")
        stat_comm = args[1:-1] if kernel else ""
        first = first_cmd_token(args)
        exe = first if first.startswith("/") else ""
        status_name = stat_comm if kernel else (basename(first) if first else "-")

        row = {
            "pid": pid,
            "ppid": ppid,
            "status_name": status_name,
            "status_state": "",
            "uid": user,
            "threads": nlwp,
            "kthread": "1" if kernel else "0",
            "rss": rss,
            "vsz": vsz,
            "pss": "",
            "socket_count": "",
            "fd_devices": "",
            "exe": exe,
            "cmdline": "" if kernel else args,
            "cgroup": "",
            "statline": "",
            "stat_comm": stat_comm,
            "stat_state": stat,
            "stat_ppid": ppid,
            "priority": pri,
            "nice": ni,
            "num_threads": nlwp,
            "rt_priority": "",
            "policy": policy,
            "user": user,
        }
        proc_name = process_name(row)
        unit, desc = service_for_process(proc_name, services)
        row["unit"] = unit
        row["service_description"] = desc
        rows.append(row)
    return rows


SOCKET_TYPES = {"IPv4", "IPv6", "unix", "netlink", "sock"}
SKIP_DEVICE_PREFIXES = (
    "/dev/null",
    "/dev/zero",
    "/dev/full",
    "/dev/random",
    "/dev/urandom",
    "/dev/pts/",
    "/dev/ptmx",
)


def is_interesting_device(path: str) -> bool:
    if not path.startswith(("/dev/", "/sys/", "/proc/device-tree/")):
        return False
    return not path.startswith(SKIP_DEVICE_PREFIXES)


def collect_lsof_fd_summary(serial: str) -> tuple[dict[str, int], dict[str, list[str]]]:
    text = run_adb(["shell", "lsof", "-nP", "-F", "pftn"], serial=serial, check=True)
    socket_fds: dict[str, set[tuple[str, str, str]]] = defaultdict(set)
    devices: dict[str, list[str]] = defaultdict(list)

    pid = ""
    fd = ""
    fd_type = ""
    for line in text.splitlines():
        if not line:
            continue
        tag, value = line[0], line[1:]
        if tag == "p":
            pid = value
            fd = ""
            fd_type = ""
        elif tag == "f":
            fd = value
            fd_type = ""
        elif tag == "t":
            fd_type = value
        elif tag == "n" and pid:
            name = value
            if fd_type in SOCKET_TYPES:
                socket_fds[pid].add((fd, fd_type, name))
            if is_interesting_device(name) and name not in devices[pid]:
                devices[pid].append(name)

    return {pid: len(fds) for pid, fds in socket_fds.items()}, devices


def apply_fd_summary(
    rows: list[dict[str, str]],
    socket_counts: dict[str, int],
    devices: dict[str, list[str]],
) -> None:
    for row in rows:
        pid = row.get("pid", "")
        if pid in socket_counts:
            row["socket_count"] = str(socket_counts[pid])
        if pid in devices:
            row["fd_devices"] = ";".join(devices[pid])


def render_markdown(
    rows: list[dict[str, str]],
    *,
    output_raw: Path,
    full_cmd_in_md: bool,
    collect_fd: bool,
    collect_pss: bool,
    adb_devices: str,
    uname: str,
    hostname: str,
) -> str:
    by_pid = {row["pid"]: row for row in rows}

    enriched: list[dict[str, str]] = []
    for row in rows:
        proc_name = process_name(row)
        parent = by_pid.get(row.get("ppid", ""))
        parent_name = process_name(parent) if parent else ("-" if row.get("ppid") == "0" else "unknown")
        devices = []
        if row.get("fd_devices"):
            devices.extend([item for item in row["fd_devices"].split(";") if item])
        for dev in extract_cmd_dev_nodes(row.get("cmdline", "")):
            if dev not in devices:
                devices.append(dev)
        hw, deps = hardware_guess(row, proc_name, devices)
        role = infer_role(row, proc_name)

        enriched.append(
            {
                **row,
                "process_name": proc_name,
                "parent_name": parent_name,
                "command": command_for_table(row, full_cmd_in_md),
                "space_type": "kernel" if is_kernel(row) else "user",
                "state": short_state(row.get("status_state", ""), row.get("stat_state", "")),
                "policy_name": policy_name(row.get("policy", "")),
                "priority_display": (
                    f"{row.get('priority', '-')}/rt{row.get('rt_priority', '-')}"
                    if row.get("rt_priority") not in ("", "0", None)
                    else row.get("priority", "-")
                ),
                "nice_display": row.get("nice", "-"),
                "devices": "; ".join(devices[:8]) + (" ..." if len(devices) > 8 else ""),
                "hardware": hw,
                "deps": deps,
                "startup": row.get("unit") or "-",
                "role": role,
            }
        )

    groups: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    for row in enriched:
        key = (
            row["process_name"],
            row["parent_name"],
            row["command"],
            row["user"],
            row["space_type"],
            row["policy_name"],
            row["priority_display"],
            row["nice_display"],
            row["devices"],
            row["hardware"],
            row["deps"],
            row["startup"],
            row["role"],
        )
        groups[key].append(row)

    table_rows: list[list[str]] = []
    sorted_groups = sorted(
        groups.items(),
        key=lambda item: (
            0 if item[0][4] == "user" else 1,
            item[0][0].lower(),
            item[0][1].lower(),
            item[0][2].lower(),
        ),
    )
    for index, (key, members) in enumerate(sorted_groups, start=1):
        (
            proc_name,
            parent_name,
            command,
            user,
            space_type,
            sched_policy,
            priority,
            nice,
            devices,
            hardware,
            deps,
            startup,
            role,
        ) = key
        table_rows.append(
            [
                str(index),
                str(len(members)),
                proc_name,
                parent_name,
                command,
                user,
                space_type,
                compact_values([member["state"] for member in members]),
                sched_policy,
                priority,
                nice,
                number_range([member.get("threads", "") for member in members]),
                number_range([member.get("rss", "") for member in members]),
                number_range([member.get("vsz", "") for member in members]),
                number_range([member.get("pss", "") for member in members]),
                number_range([member.get("socket_count", "") for member in members]),
                devices or "-",
                hardware,
                deps,
                startup or "-",
                role,
                "自动采集；职责/硬件依赖为初判",
            ]
        )

    headers = [
        "序号",
        "实例数",
        "进程名",
        "父进程名",
        "命令/路径",
        "UID/用户",
        "空间类型",
        "状态",
        "调度策略",
        "优先级/PRI",
        "Nice",
        "线程数",
        "内存RSS(KB)",
        "内存VSZ(KB)",
        "内存PSS(KB)",
        "Socket数",
        "打开的关键设备节点",
        "是否硬件依赖",
        "依赖硬件/外设",
        "启动来源/服务",
        "进程职责",
        "证据/备注",
    ]

    now = dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
    space_counts = Counter(row["space_type"] for row in enriched)
    hw_counts = Counter(row["hardware"] for row in enriched)
    user_rows = space_counts.get("user", 0)
    kernel_rows = space_counts.get("kernel", 0)

    lines = [
        "# Linux进程信息清单",
        "",
        "目标：统计当前台架Linux侧全部进程，记录进程资源、调度属性、空间类型、职责和硬件依赖关系。",
        "",
        "## 采集信息",
        "",
        f"- 采集时间：{now}",
        f"- 设备：`{hostname.strip() or '-'}`",
        f"- 内核：`{uname.strip() or '-'}`",
        f"- adb设备：`{adb_devices.strip().replace(chr(10), '; ') or '-'}`",
        f"- 原始快照：[{output_raw.name}]({output_raw.resolve()})",
        f"- fd扫描：{'开启' if collect_fd else '关闭'}；PSS采集：{'开启' if collect_pss else '关闭'}",
        f"- 进程实例：{len(enriched)}，稳定表格行：{len(table_rows)}，user：{user_rows}，kernel：{kernel_rows}",
        f"- 硬件依赖初判：是 {hw_counts.get('是', 0)}，否 {hw_counts.get('否', 0)}，待确认 {hw_counts.get('待确认', 0)}",
        "",
        "## 进程表",
        "",
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in table_rows:
        lines.append("| " + " | ".join(md_escape(value) for value in row) + " |")

    lines.extend(
        [
            "",
            "## 字段口径",
            "",
            "- PID/PPID：只作为采集时的临时索引，不进入最终表格；最终表格保留稳定的进程名和父进程名。",
            "- 实例数：相同进程名、父进程名、命令/路径、用户、调度、设备节点和启动来源的进程会合并为一行。",
            "- 空间类型：内核线程标记为`kernel`，普通用户态进程标记为`user`。",
            "- 内存RSS/VSZ：来自`/proc/<pid>/status`；PSS来自`/proc/<pid>/smaps_rollup`，本次未开启PSS采集时为`-`。",
            "- Socket数：开启fd扫描时统计`/proc/<pid>/fd`中指向`socket:[...]`的fd数量；本次未开启fd扫描时为`-`。",
            "- 打开的关键设备节点：开启fd扫描时记录fd里的`/dev`、`/sys`、`/proc/device-tree`路径；未开启时仅从命令行提取`/dev`路径，最多展示8项。",
            "- 是否硬件依赖：基于设备节点、命令行、服务描述、内核线程名和常见硬件关键词自动初判，后续需要结合源码/日志复核。",
            "- 进程职责：优先使用systemd service Description；没有描述时按进程名和命令行做初步归类。",
        ]
    )
    return "\n".join(lines) + "\n"


def write_raw(rows: list[dict[str, str]], path: Path) -> None:
    headers = [
        "pid",
        "ppid",
        "status_name",
        "stat_comm",
        "user",
        "kthread",
        "state",
        "policy",
        "priority",
        "nice",
        "threads",
        "rss_kb",
        "vsz_kb",
        "pss_kb",
        "socket_count",
        "fd_devices",
        "exe",
        "cmdline",
        "cgroup",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "pid": row.get("pid", ""),
                    "ppid": row.get("ppid", ""),
                    "status_name": row.get("status_name", ""),
                    "stat_comm": row.get("stat_comm", ""),
                    "user": row.get("user", ""),
                    "kthread": row.get("kthread", ""),
                    "state": row.get("status_state", ""),
                    "policy": row.get("policy", ""),
                    "priority": row.get("priority", ""),
                    "nice": row.get("nice", ""),
                    "threads": row.get("threads", ""),
                    "rss_kb": row.get("rss", ""),
                    "vsz_kb": row.get("vsz", ""),
                    "pss_kb": row.get("pss", ""),
                    "socket_count": row.get("socket_count", ""),
                    "fd_devices": row.get("fd_devices", ""),
                    "exe": row.get("exe", ""),
                    "cmdline": row.get("cmdline", ""),
                    "cgroup": row.get("cgroup", ""),
                }
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", help="adb serial for the Linux/PVM side")
    parser.add_argument("--output-md", type=Path, default=DEFAULT_MD)
    parser.add_argument("--output-raw", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--full-cmd-in-md", action="store_true")
    parser.add_argument("--collect-pss", action="store_true")
    parser.add_argument("--collect-fd", action="store_true")
    args = parser.parse_args()

    adb_devices = run_adb(["devices", "-l"]).strip()
    serial = args.serial or detect_linux_serial(adb_devices)
    if not serial:
        print("cannot detect Linux/PVM adb serial; pass --serial", file=sys.stderr)
        return 1

    uname = run_adb_shell("uname -a", serial=serial, check=True).strip()
    hostname = run_adb_shell("hostname", serial=serial, check=False).strip()
    passwd = run_adb_shell("cat /etc/passwd", serial=serial, check=False)
    service_output = run_adb_shell(
        "env SYSTEMD_COLORS=0 SYSTEMD_PAGER=cat COLUMNS=1000 "
        "systemctl list-units --type=service --all --no-legend --no-pager --plain --full",
        serial=serial,
        check=False,
    )
    ps_output = run_adb_shell(
        "ps -ww -eo pid=,ppid=,user=,stat=,policy=,pri=,ni=,nlwp=,rss=,vsz=,args=",
        serial=serial,
        check=True,
    )

    users = parse_passwd(passwd)
    services = parse_service_descriptions(service_output)
    rows = parse_ps_rows(ps_output, services)
    if args.collect_fd:
        socket_counts, fd_devices = collect_lsof_fd_summary(serial)
        apply_fd_summary(rows, socket_counts, fd_devices)
    if not rows:
        print("no process rows collected", file=sys.stderr)
        return 1

    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_raw.parent.mkdir(parents=True, exist_ok=True)
    write_raw(rows, args.output_raw)
    markdown = render_markdown(
        rows,
        output_raw=args.output_raw,
        full_cmd_in_md=args.full_cmd_in_md,
        collect_fd=args.collect_fd,
        collect_pss=args.collect_pss,
        adb_devices=adb_devices,
        uname=uname,
        hostname=hostname,
    )
    args.output_md.write_text(markdown, encoding="utf-8")
    print(f"wrote {args.output_md}")
    print(f"wrote {args.output_raw}")
    print(f"collected {len(rows)} process instances")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
