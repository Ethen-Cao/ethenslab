# 在新 VPS 上部署 VLESS + REALITY，并接入 Clash Verge Rev

在本机通过 SSH 运行一条命令，即可在新 VPS 上安装 sing-box，生成该节点的密钥和 Clash Verge Rev 配置。以后增加 VPS 时，使用同一份脚本并填入新机器的公网 IP。可直接使用同目录的 [deploy.py](./deploy.py)，单独保存本文时也可以复制附录中的完整脚本。

## 1. 准备服务器

- 使用 Ubuntu 22.04 / 24.04 或 Debian 12 / 13，架构为 amd64 或 arm64。服务器需以 systemd 启动（247 或更高），具备 Python 3、`dpkg-deb`、`ss`（iproute2）及系统 CA 证书（ca-certificates）。SSH 账号使用 root 或具备 sudo 权限。
- 准备客户端可达的公网 IPv4 或 IPv6 地址，并在云厂商安全组放行所选入站 **TCP** 端口，默认 443。保留已有的 SSH 规则。使用端口映射的 VPS 还需将该公网端口转发至 VPS 的相同 TCP 端口。
- 服务端需要能下载官方软件包，并能访问 REALITY 的 TLS 1.3 握手目标，默认 `www.cloudflare.com:443`。客户端连接的是 VPS，`--sni` 指定的是握手使用的目标主机名。部署无需自有域名、网站或证书。[sing-box 的 VLESS 配置](https://sing-box.sagernet.org/configuration/inbound/vless/) · [REALITY 握手字段](https://sing-box.sagernet.org/configuration/shared/tls/#reality-fields)

如果精简镜像缺少以上工具，在 VPS 上先运行 `sudo apt-get update && sudo apt-get install -y python3 ca-certificates iproute2`。标准 Debian/Ubuntu 镜像自带 `dpkg` 和 `dpkg-deb`。

## 2. 通过 SSH 一键安装

在本机 Linux 或 macOS 终端进入本仓库的 `work/vps` 目录。把下面的示例地址替换成新 VPS 的真实公网 IP。

```bash
VPS_IP='203.0.113.10'
ssh root@"$VPS_IP" "python3 - --server '$VPS_IP'" < ./deploy.py
```

如要在**首次部署**时选用其他端口或握手目标，例如端口 8443，用下面的命令替换上一条 SSH 命令。自选握手目标时，填写从 VPS 可访问、支持 TLS 1.3 且证书匹配的主机名。

```bash
ssh root@"$VPS_IP" "python3 - --server '$VPS_IP' --port 8443 --sni www.cloudflare.com" < ./deploy.py
```

已经将脚本放在服务器上时，可在该服务器运行 `sudo python3 deploy.py --server "$VPS_IP"`。变量须在执行命令的终端中定义。`--server` 接受 IP 字面值。IPv6 填裸地址，脚本按其地址族监听。首次安装发现端口冲突时，先用 `sudo ss -ltnp` 核对占用者，再选择空闲端口。若同名的 systemd 服务属于其他安装，脚本会停止。现有伦敦节点的服务名为 `evoxt-london.service`，下文的 `vps-reality.service` 用于新节点。

**用普通 SSH 账号安装。** 如果云镜像要求先以 `ubuntu` 或 `debian` 登录，可将脚本复制到该账号，再通过交互式 sudo 安装。以下命令也适用于 IPv6，`scp` 连接串中的 IPv6 使用方括号。

```bash
SSH_USER=ubuntu
SCP_HOST="$VPS_IP"
case "$VPS_IP" in *:*) SCP_HOST="[$VPS_IP]" ;; esac
scp ./deploy.py "$SSH_USER@$SCP_HOST:deploy-vps-reality.py" &&
  ssh -t "$SSH_USER@$VPS_IP" "sudo python3 ./deploy-vps-reality.py --server '$VPS_IP'"
```

脚本按架构下载固定版本 sing-box 1.14.4 的官方 `.deb`，核对内置 SHA-256，仅提取可执行文件到 `/opt/vps-reality/sing-box`。systemd 以动态用户运行服务，通过 `LoadCredential=config.json:/opt/vps-reality/private/server.json` 读取服务端凭据。部署后可执行 `sudo systemctl is-active vps-reality.service` 和 `sudo systemctl is-enabled vps-reality.service`，预期分别为 `active` 和 `enabled`。若 UFW 已启用，脚本会为所选 TCP 端口添加放行规则。其他主机防火墙和云安全组需单独设置。[sing-box 1.14.4 官方发布](https://github.com/SagerNet/sing-box/releases/tag/v1.14.4) · [systemd 服务凭据](https://www.freedesktop.org/software/systemd/man/250/systemd.exec.html#Credentials)

## 3. 取回客户端配置

服务器生成的 `/opt/vps-reality/private/VPS-Reality.yaml` 已含连接所需的 UUID、公钥、short ID、SNI 和端口。将它作为登录凭据保管。服务端私钥留在服务器上。

**root 登录**时，在本机设置下载来源。

```bash
SSH_USER=root
REMOTE_PROFILE=/opt/vps-reality/private/VPS-Reality.yaml
```

**普通账号登录**时，在本机设置以下变量，并先用 sudo 生成一份仅该账号可读的副本。sudo 密码在交互式终端输入。

```bash
SSH_USER=ubuntu
REMOTE_PROFILE=.vps-reality-export/VPS-Reality.yaml
ssh -t "$SSH_USER@$VPS_IP" 'mkdir -p -m 700 "$HOME/.vps-reality-export" && sudo install -m 600 -o "$(id -un)" /opt/vps-reality/private/VPS-Reality.yaml "$HOME/.vps-reality-export/VPS-Reality.yaml"'
```

然后在本机下载。不同公网 IP 的配置分别保存。只有传输成功且文件有内容时才会替换已有配置。

```bash
SCP_HOST="$VPS_IP"
case "$VPS_IP" in *:*) SCP_HOST="[$VPS_IP]" ;; esac
(
  set -e
  umask 077
  dir="$HOME/.config/vps-reality/$VPS_IP"
  mkdir -p "$dir"
  tmp=$(mktemp "$dir/.profile.XXXXXX")
  trap 'rm -f "$tmp"' EXIT
  scp "$SSH_USER@$SCP_HOST:$REMOTE_PROFILE" "$tmp"
  test -s "$tmp"
  chmod 600 "$tmp"
  mv "$tmp" "$dir/VPS-Reality.yaml"
  printf '%s\n' "$dir/VPS-Reality.yaml"
)
```

## 4. 导入 Clash Verge Rev，确认流量走 VPS

1. 在 Clash Verge Rev 打开 **订阅（Profiles）**，把上一步得到的 `VPS-Reality.yaml` 拖入并选中。打开 **代理（Proxies）**，选择 **规则（Rule）**，确认 `PERSONAL` 组选中 `VPS-Reality`。[本地配置导入](https://www.clashverge.dev/guide/profile.html)
2. 打开 **系统代理（System Proxy）** 后，支持系统代理的浏览器等应用即可使用节点。对于需手工指定代理的软件，填写 `127.0.0.1` 和 Clash Verge Rev 设置中显示的混合端口。配置默认 `7890`，GUI 可能覆盖为 `7897` 等端口。[Clash Verge Rev 快速入门](https://www.clashverge.dev/guide/quickstart.html)
3. 在**本机**用实际混合端口发起两次 HTTPS 请求。第一条预期返回 `204`。第二条显示外站看到的出口 `ip=` 和地区 `loc=`。可在 VPS 上直接运行 `curl -fsS --noproxy '*' https://www.cloudflare.com/cdn-cgi/trace` 比对出口。IPv6 优先或云厂商 NAT 都可能使出口与 SSH 入口 IP 不同。

```bash
MIXED_PORT=7890
curl --noproxy '' --proxy "http://127.0.0.1:$MIXED_PORT" --max-time 20 \
  -sS -o /dev/null -w '%{http_code}\n' https://www.google.com/generate_204
curl --noproxy '' --proxy "http://127.0.0.1:$MIXED_PORT" --max-time 20 \
  -fsS https://www.cloudflare.com/cdn-cgi/trace | sed -n '/^ip=/p; /^loc=/p'
```

规则模式下，`.local`、IPv4 回环（`127.0.0.0/8`）和三个私网网段（`10.0.0.0/8`、`172.16.0.0/12`、`192.168.0.0/16`）直连。IPv6 回环（`::1/128`）、本地唯一地址（`fc00::/7`）和链路本地地址（`fe80::/10`）也直连。其余流量由最后一条 `MATCH,PERSONAL` 交给 VPS。若要让某个公司域名直连，在这条兜底规则前加入 `DOMAIN-SUFFIX,corp.example,DIRECT`，将示例域名换成实际值。[Mihomo 路由规则](https://wiki.metacubex.one/en/config/rules/)

生成配置时，脚本会让服务端和客户端使用同一个 UUID、SNI、Short ID 及 `xtls-rprx-vision`。REALITY 私钥只写入服务端 JSON，配对的公钥写入客户端 YAML。客户端的 `server` 是新 VPS 的公网地址。公网只需开放 TCP 入站，代理的 UDP 数据通过同一个连接使用 XUDP 传输。[Mihomo VLESS 字段](https://wiki.metacubex.one/config/proxies/vless/)

## 5. 重跑、备份与恢复

在同一台 VPS 用相同的 IP、端口和 SNI 再次运行脚本，会复用已有身份和客户端配置，运行中的服务继续工作。已停止或尚未启用的服务可以通过重跑启动并设置开机自启。已有安装的参数不一致时，脚本会退出并提示。若仅升级系统里的 APT 软件包，这份独立安装的 sing-box 仍使用脚本固定的版本。

备份时同时保存服务端身份、客户端文件、二进制和 systemd 服务文件。在 VPS 上执行下面的命令，再通过 SSH 将压缩包存放到受控的备份位置。压缩包包含私钥。

```bash
sudo sh -c 'umask 077; tar -C / -czf "/root/vps-reality-$(date -u +%Y%m%dT%H%M%SZ).tar.gz" opt/vps-reality etc/systemd/system/vps-reality.service'
```

要在同架构、仍可使用原公网地址的干净系统中恢复，把选定归档上传并命名为 `/root/vps-reality-restore.tar.gz`。以下命令在目标 VPS 上执行。归档包含 `/etc/systemd/system/vps-reality.service`。若只恢复了完整的 `/opt/vps-reality` 目录，也可用原参数重跑脚本，重建缺失的服务文件。恢复后重新检查云安全组和防火墙，再执行上一节的 HTTPS 验证。

```bash
sudo tar -C / -xzpf /root/vps-reality-restore.tar.gz
sudo systemctl daemon-reload
sudo systemctl enable --now vps-reality.service
```

## 常见问题

| 现象 | 如何定位 |
| --- | --- |
| 安装提示端口被占用 | 在 VPS 上运行 `sudo ss -ltnp` 查找端口和进程。若 443 已供网站或现有节点使用，在新部署中指定空闲的 `--port`，并同步放行该 TCP 端口。 |
| 服务启动失败或启动后退出 | 查看 `sudo systemctl status vps-reality.service --no-pager` 和 `sudo journalctl -u vps-reality.service -b -n 60 --no-pager`。若提示凭据加载失败，核对 `/opt/vps-reality/private/server.json` 是否从备份完整恢复。 |
| 节点连接超时 | 先检查 VPS 监听地址族及端口，再检查云安全组、UFW 和公网端口映射。IPv6 节点要求客户端网络具有可达的 IPv6 路由。 |
| TCP 能连上，REALITY 握手失败 | 确认客户端启用的是本机刚导出的配置，核对端口、SNI 及服务端日志。两端同步系统时间。VPS 上可用 `timedatectl status` 查时钟，用 `openssl s_client -tls1_3 -connect www.cloudflare.com:443 -servername www.cloudflare.com </dev/null` 检查握手目标，按实际 SNI 替换域名。 |
| curl 显示本机连接被拒绝，或浏览器出口未变 | 核对 GUI 的实际混合端口和活动配置。先执行显式指定 `--proxy` 的两条命令。若成功，检查浏览器的系统代理设置、规则模式和 `PERSONAL` 组。 |
| 怀疑偶发断线 | 记录故障时间、客户端和使用的网络。用同一客户端通过 Wi-Fi 和手机热点分别执行上一节两条 HTTPS 检查，并对照同一时刻的 Clash 日志和 VPS 服务日志。 |

## 本版验证记录

2026 年 11 月 25 日，在全新 Debian 12 amd64 虚拟机中，用默认握手目标和 TCP 443 连续运行同一份脚本两次。服务处于 `active` 和 `enabled` 状态，第二次部署保留了服务进程 PID，服务端 JSON 和客户端 YAML 的 SHA-256 也保持一致。随后关闭虚拟机并用同一块磁盘冷启动，systemd 自动恢复了 443 监听，原节点凭据仍然有效。

在独立的回环网络测试中，Mihomo 1.19.33 使用生成的节点，通过 sing-box 1.14.4 完成 REALITY 握手，HTTP 和 UDP/XUDP 请求均收到预期响应。停止服务后，对照请求失败。新 VPS 的公网连通性仍需从自己的网络按第 4 节验证。arm64 已核对官方发行包摘要，本次运行测试使用 amd64。

## 附录　完整部署脚本

将下列内容另存为 `deploy.py`，即可执行第 2 节的命令。

<details>
<summary>展开 deploy.py</summary>

```python
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
```

</details>
