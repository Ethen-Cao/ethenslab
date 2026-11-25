#!/usr/bin/env python3
"""Deploy a VLESS/REALITY endpoint and its matching Clash Verge Rev profile."""

import argparse
import base64
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid


VERSION = "1.14.4"
DIGESTS = {
    "amd64": "4e9b8809aed0e3ac78ad14fa3a0af533402425d736f0cc9dc75b1c03d381b614",
    "arm64": "8f52525d84ff0f4fd2cec4bb12ed330590fc741ea5250fe7cfc94ae1f1069ac2",
}
ROOT = Path("/opt/vps-reality")
UNIT = "vps-reality.service"
UNIT_PATH = Path("/etc/systemd/system") / UNIT
PROFILE = "VPS-Reality.yaml"
SERVICE = """[Unit]
Description=VPS VLESS REALITY proxy
After=network-online.target
Wants=network-online.target

[Service]
DynamicUser=yes
StateDirectory=vps-reality
WorkingDirectory=/var/lib/vps-reality
LoadCredential=config.json:/opt/vps-reality/private/server.json
ExecStart=/opt/vps-reality/sing-box run -c %d/config.json
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
AmbientCapabilities=CAP_NET_BIND_SERVICE
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
"""


def output(*cmd):
    return subprocess.check_output(cmd, text=True).strip()


def save(path, data, mode=0o600):
    path.write_text(data, encoding="utf-8")
    path.chmod(mode)


def download_binary(stage, binary):
    arch = output("dpkg", "--print-architecture")
    if arch not in DIGESTS:
        raise ValueError(f"支持 amd64/arm64，当前架构为 {arch}")
    name = f"sing-box_{VERSION}_linux_{arch}.deb"
    url = f"https://github.com/SagerNet/sing-box/releases/download/v{VERSION}/{name}"
    package = stage / name
    digest = hashlib.sha256()
    print(f"下载并校验 sing-box {VERSION} ({arch})", flush=True)
    with urllib.request.urlopen(url, timeout=60) as response, package.open("wb") as out:
        for chunk in iter(lambda: response.read(1024 * 1024), b""):
            digest.update(chunk)
            out.write(chunk)
    if digest.hexdigest() != DIGESTS[arch]:
        raise ValueError("官方发行包 SHA-256 不匹配，已中止")
    extracted = stage / "package"
    subprocess.run(["dpkg-deb", "-x", package, extracted], check=True)
    shutil.copyfile(extracted / "usr/bin/sing-box", binary)
    binary.chmod(0o755)


def write_configs(private, server, port, sni, binary):
    pair = dict(line.split(": ", 1) for line in output(binary, "generate", "reality-keypair").splitlines())
    secret, public = pair["PrivateKey"], pair["PublicKey"]
    for key in (secret, public):
        if len(base64.urlsafe_b64decode(key + "=")) != 32:
            raise ValueError("REALITY 密钥生成失败")
    user = str(uuid.uuid4())
    short = secrets.token_hex(8)
    listen = "::" if ipaddress.ip_address(server).version == 6 else "0.0.0.0"
    inbound = {
        "type": "vless", "listen": listen, "listen_port": port,
        "users": [{"uuid": user, "flow": "xtls-rprx-vision"}],
        "tls": {"enabled": True, "server_name": sni, "reality": {
            "enabled": True, "handshake": {"server": sni, "server_port": 443},
            "private_key": secret, "short_id": [short],
        }},
    }
    config = {
        "log": {"level": "warn", "timestamp": True},
        "dns": {"servers": [{"type": "local", "tag": "system-dns"}]},
        "inbounds": [inbound],
        "outbounds": [{"type": "direct", "tag": "direct"}],
        "route": {"default_domain_resolver": "system-dns", "final": "direct"},
    }
    save(private / "server.json", json.dumps(config, indent=2) + "\n")
    save(private / PROFILE, f"""mixed-port: 7890
allow-lan: false
mode: rule
log-level: info
proxies:
  - name: VPS-Reality
    type: vless
    server: "{server}"
    port: {port}
    uuid: "{user}"
    network: tcp
    udp: true
    tls: true
    flow: xtls-rprx-vision
    servername: "{sni}"
    client-fingerprint: chrome
    packet-encoding: xudp
    reality-opts:
      public-key: "{public}"
      short-id: "{short}"
proxy-groups:
  - name: PERSONAL
    type: select
    proxies: [VPS-Reality, DIRECT]
rules:
  - DOMAIN-SUFFIX,local,DIRECT
  - IP-CIDR,127.0.0.0/8,DIRECT,no-resolve
  - IP-CIDR,10.0.0.0/8,DIRECT,no-resolve
  - IP-CIDR,172.16.0.0/12,DIRECT,no-resolve
  - IP-CIDR,192.168.0.0/16,DIRECT,no-resolve
  - IP-CIDR6,::1/128,DIRECT,no-resolve
  - IP-CIDR6,fc00::/7,DIRECT,no-resolve
  - IP-CIDR6,fe80::/10,DIRECT,no-resolve
  - MATCH,PERSONAL
""")


def check_target(sni):
    ctx = ssl.create_default_context()
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    with socket.create_connection((sni, 443), timeout=8) as conn:
        with ctx.wrap_socket(conn, server_hostname=sni):
            pass


def listeners(port):
    return output("ss", "-H", "-lntp", f"sport = :{port}")


def unit_property(name):
    # systemctl may return a nonzero code for a unit that does not exist.
    result = subprocess.run(["systemctl", "show", UNIT, "-p", name, "--value"],
                            capture_output=True, text=True)
    if result.returncode and not result.stdout.strip():
        raise ValueError(result.stderr.strip() or "无法读取 systemd 服务状态")
    return result.stdout.strip()


def deploy(server, port, sni):
    desired = {"format": 1, "sing_box": VERSION, "server": server, "port": port, "sni": sni}
    binary = ROOT / "sing-box"
    private = ROOT / "private"
    known_unit = (ROOT.is_dir() and not UNIT_PATH.is_symlink() and UNIT_PATH.is_file()
                  and UNIT_PATH.read_text() == SERVICE)
    fragment = unit_property("FragmentPath")
    if ((os.path.lexists(UNIT_PATH) and not known_unit)
            or (fragment and Path(fragment) != UNIT_PATH)):
        raise ValueError(f"已有同名 systemd 服务，保留原服务：{UNIT}")
    if unit_property("DropInPaths"):
        raise ValueError(f"检测到 {UNIT} 的外部 systemd 覆盖配置，请先检查")

    if os.path.lexists(ROOT):
        manifest = private / "install.json"
        if ROOT.is_symlink() or not manifest.is_file() or json.loads(manifest.read_text()) != desired:
            raise ValueError(f"{ROOT} 已存在且部署参数或来源不同，保留原文件")
        if not (private / PROFILE).is_file() or not binary.is_file():
            raise ValueError("已有安装文件不完整，请从备份恢复")
        subprocess.run([binary, "check", "-c", private / "server.json"], check=True)
    else:
        if listeners(port):
            raise ValueError(f"TCP {port} 已被占用；选其他端口或先确认现有服务")
        check_target(sni)
        if not ROOT.parent.exists():
            ROOT.parent.mkdir()
            ROOT.parent.chmod(0o755)
        with tempfile.TemporaryDirectory(prefix=".vps-reality-", dir=ROOT.parent) as temp:
            stage = Path(temp)
            payload = stage / "payload"
            payload.mkdir()
            (payload / "private").mkdir(mode=0o700)
            download_binary(stage, payload / "sing-box")
            write_configs(payload / "private", server, port, sni, payload / "sing-box")
            subprocess.run([payload / "sing-box", "check", "-c", payload / "private/server.json"], check=True)
            save(payload / "private/install.json", json.dumps(desired, indent=2) + "\n")
            payload.chmod(0o755)
            payload.rename(ROOT)

    active = unit_property("ActiveState") == "active"
    if not active and listeners(port):
        raise ValueError(f"TCP {port} 被其他进程占用，现有服务和密钥已保留")
    if not known_unit:
        with tempfile.NamedTemporaryFile(dir=UNIT_PATH.parent, mode="w") as tmp:
            tmp.write(SERVICE)
            tmp.flush()
            os.fchmod(tmp.fileno(), 0o644)
            os.link(tmp.name, UNIT_PATH)
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    try:
        subprocess.run(["systemctl", "start", UNIT], check=True)
        for _ in range(40):
            pid = unit_property("MainPID")
            if pid.isdigit() and int(pid) and f"pid={pid}," in listeners(port):
                break
            time.sleep(0.2)
        else:
            raise ValueError(f"未确认服务持有 TCP {port}，请查 journalctl -u {UNIT}")
    except (ValueError, subprocess.CalledProcessError):
        if not active:
            subprocess.run(["systemctl", "stop", UNIT], check=False)
        raise
    subprocess.run(["systemctl", "enable", UNIT], check=True)
    if shutil.which("ufw") and "Status: active" in output("ufw", "status").splitlines():
        subprocess.run(["ufw", "allow", f"{port}/tcp"], check=True)
    print(f"{UNIT} 已监听 TCP {port} 并启用开机启动。")
    print(f"请在云面板放行入站 TCP {port}；客户端文件：{private / PROFILE}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", required=True, type=ipaddress.ip_address, help="客户端可达的 VPS 公网 IP")
    parser.add_argument("--port", type=int, default=443)
    parser.add_argument("--sni", default="www.cloudflare.com", help="REALITY TLS 握手目标域名")
    args = parser.parse_args()
    sni = args.sni.lower().rstrip(".")
    labels = sni.split(".")
    if not (1 <= args.port <= 65535 and len(labels) > 1 and len(sni) <= 253
            and all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels)):
        parser.error("端口须为 1–65535，SNI 须为有效的 ASCII 域名")
    if (args.server.is_unspecified or args.server.is_multicast or args.server.is_link_local
            or "%" in str(args.server)):
        parser.error("请提供客户端可直接连接的单播 IP 地址")
    if os.geteuid() != 0 or not Path("/run/systemd/system").is_dir():
        parser.error("请在使用 systemd 的 VPS 上以 root 或 sudo 运行")
    os.environ["LC_ALL"] = "C"
    os.umask(0o077)
    with open("/run/vps-reality-deploy.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        deploy(str(args.server), args.port, sni)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        sys.exit(f"部署未完成：{exc}")
