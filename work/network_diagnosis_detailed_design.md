# 智能座舱网络诊断 — 详细设计（LLD，决策推导版）

> ⚠️ **本文档已被 `network_diagnosis_final_design.md` 替代为最终交付正本。**
> 本文档保留作为**决策推导版**，记录从需求到最终设计的完整演进过程：
> - v1.0 评审修订点（review F1-F18 + 补充评审 G1-G20）
> - v1.1 B 系列决策讨论（B1 fault_id 生成 / B2.③a Boot 补归因 / B3.② 上云策略 / B4.③ fault 演化）
> - 各章节的"修正集"标注与跨章节交叉引用
>
> 编码、测试、部署请以 **`network_diagnosis_final_design.md`** 为权威依据；本文档仅供追溯设计决策的来源。

> 文档定位：**详细设计文档（决策推导版）**，记录 v1.0 到 v1.1 的演进。
> 上游文档：
> - 需求：`network_diagnosis_requirements.md`
> - 拓扑基线：`network_topology.md`
> - 系统设计（HLD）：`network_diagnosis_sys_design.md`
> - 评审意见：`network_diagnosis_sys_design_review.md`、`network_diagnosis_detailed_design_review.md`
> 附件：
> - `baseline-pvm.json`（PVM 拓扑基线全展开）
> - `baseline-gvm.json`（GVM 拓扑基线全展开）
> 平台：SA8397 智能座舱 — PVM Linux 6.6.110-rt61 PREEMPT_RT + GVM Android（qcrosvm Hypervisor）
> 架构方案：方案 E（专用 VSOCK + PVM 单一事件出口 + GVM 轻量采集）
> 文档版本：**1.1 / 2026-05-11**

## 阅读指南（v1.1 章节地图）

| 主题 | v1.0 基础章节 | v1.1 详细增量 |
|---|---|---|
| 通信协议 NDGA 扩展 | §4 | §25.2（hello 字段）/ §26.5（fault_alert push） |
| 检查项 Registry | §6 | §24.3（L4-FW-006/007、L4-NAT-005、L5-PORT-006） |
| 事件与因果聚合 | §8 | §25.4（cls/fp/refined/dq）/ §25.1（fault_id 规则）/ §27（fault 演化）/ §26（上云策略）|
| Watchdog | §9 | §24.4（3 新 PVM 信号 + 1 GVM 信号） |
| 采集器命令白名单 | §11 | §24.5（conntrack_state_stats 等 4 sections） |
| 取证目录 manifest | §12 | §27.3（evolution[] 段） |
| 时钟与时序 | §13 | §25.1（pvm_boot_id 全局 epoch） |
| GVM 启动 + 补归因 | §3.2.3 | §25.5（Boot 早期补归因完整时序） |
| 性能预算 | §17 | §24.6 + §25.9 + §26.7 + §27.7 |
| 测试用例 | §19 | §24.7（TC-NET-024/025） |
| 风险降级 | §20 | §26.8（GVM 假在线兜底） |
| polaris 团队对齐 | §21 | §28（最终收敛清单） |
| 全 v1.1 决策清单 | — | §28（B1-B4 + DOWNSTREAM 综合总结） |
| 版本与未决项 | §23 | v1.0 → v1.1 changelog |

**v1.1 详细增量章节命名规则**：
- §24 — 下行回包丢失检测能力
- §25 — Fault ID 体系与 Boot 早期补归因
- §26 — Polaris 事件上云策略
- §27 — Fault 演化轨迹与因果链
- §28 — 决策汇总与 polaris 对齐清单

---

## 0. 文档读法与变更

### 0.1 跟系统设计（HLD）的关系

| 维度 | HLD `network_diagnosis_sys_design.md` | 本 LLD |
|---|---|---|
| 定位 | 让人理解"做什么 / 为什么这么做" | 让工程师能"照着写代码、不再做架构决策" |
| 完整度 | 章节齐全但每节是粗粒度 | 每节细到字段级、协议级、性能级 |
| 报告模板 | §14.1 含 Markdown 报告 | **删除**：端侧不出 Markdown，仅生成事件 payload + JSON 结构数据，云端负责渲染 |
| 检查项 | 列出 74 项 ID + 1 项配置示例 | 74 项每项独立设计：数据源 / parser / comparator / 性能预算 / BLOCKED 等级 |
| Watchdog | 列出信号源 | 含每条信号的内核 API、采样模型、误差分析、降级路径 |
| 性能 | 资源限制基本约束 | 常态/异常态/30s SLA 三档量化预算 + 保护机制 |

### 0.2 跟评审意见的对齐

本文档强制吸收以下评审修正：

- 已有 review F1-F5、§7.1 必改清单
- 补充评审 G1-G20

### 0.3 范围边界

- **包含**：网络诊断模块自身（PVM/GVM 两进程 + 通道协议 + 配置 + check + SHU + watchdog + probe）
- **不包含**：① mmhab 视频帧通路诊断（终止于 `eth0.15` + Camera Server 进程存活，参 G19）；② polarisd 内部实现（仅约束扩展接口）；③ 云端渲染（端侧只产生结构化数据，不出 Markdown）

---

## 1. 设计前提与全局约束

### 1.1 实机环境前提（已实测验证）

| 前提 | 来源 |
|---|---|
| PVM 用户态是 BusyBox v1.36.1，命令行参数语法受限 | 实测 |
| PVM 上 `ethtool/iptables/tcpdump/ss/ip` 都存在；无 `conntrack` 工具 | 实测 |
| `/proc/net/stat/nf_conntrack` 在该平台**不存在** | 实测，影响 NET-DIAG-FW-004 |
| GVM virtio MAC 启动相关，每次启动可变 | 实测，G4 修正 |
| Android NetId↔VLAN 按注册顺序分配，每次启动可变 | 实测 |
| GVM 上 `default dev dummy0 table dummy0` 是 Android 16 fallback 网络 | 实测 |
| PVM 关键网关 ARP 实测全部 PERMANENT（静态注入） | 实测 |
| GVM 当前为 userdebug+Permissive，量产 user 镜像可能 enforcing | 实测 |
| polaris VSOCK 事件方向 PVM→GVM（云出口在 GVM PolarisAgent） | 源码确认 |
| polaris VSOCK 命令方向 GVM→PVM（无反向命令通道） | 源码确认 |
| 当前 polaris client SDK 是单工 send-only；daemon 端 IPC 是双工 | 源码确认 |

### 1.2 全局约束

| ID | 约束 | 影响 |
|---|---|---|
| C1 | **只读模式**：诊断模块绝不修改网络配置 | 命令白名单、参数校验 |
| C2 | **PREEMPT_RT 让让权**：诊断进程绝不阻塞实时任务 | Nice=10，IO best-effort，长操作分片 |
| C3 | **单一出口**：所有诊断事件经 PVM polarisd 出云 | 通道 C 必备 |
| C4 | **VSOCK 不依赖 IP 网络**：诊断对象坏掉时控制面仍工作 | 通道 A 9101 + 通道 B 9001 都基于 VSOCK |
| C5 | **故障可独立上报**：单个组件挂掉不阻塞其他事件 | 各 watchdog 独立线程；进程崩溃自重启 |
| C6 | **Boot warmup**：开机首 120s 默认 INFO 不告警 | 全局 warmup 期 + 每信号 warmup_sec |
| C7 | **时钟使用规则**：内部状态机用 `CLOCK_BOOTTIME`；事件附 `boot_id`+`ts_boot`+`ts_unix` 三字段 | G6 修正 |
| C8 | **事件因果聚合**：单一物理故障产生根事件 + 派生事件清单，不灌爆 polaris | G7 修正 |
| C9 | **BLOCKED 分级**：环境性 BLOCKED-L1 / 异常 BLOCKED-L2 / 间歇 BLOCKED-L3 | G15 修正 |

---

## 2. 端到端架构

### 2.1 通道总览（与 HLD §2 一致，确认通道用途）

```
┌── Cloud ───┐   ↑事件 ↓命令
│            │
└─PolarisAgent (GVM Java)
  │
  ├── A. VSOCK 9101 (NDGA)         GVM_diag ↔ PVM_diag         双向 RPC + push
  ├── B. VSOCK 9001 (PLP)          GVM_polarisd ↔ PVM_polarisd  command(GVM→PVM) + event(PVM→GVM)
  └── C. UDS                        PVM_polarisd ↔ PVM_diag      forward command + report event
```

### 2.2 进程拓扑

```
GVM:  PolarisAgent ── android_native_polarisd ── android_net_diagd
                                                        │
                                            VSOCK 9101 NDGA
                                                        │
PVM:  linux_polarisd ── (UDS) ── linux_net_diagd ───────┘
              │
   VSOCK 9001 PLP (event PVM→GVM, command GVM→PVM)
              │
              ↑
          GVM polarisd
```

### 2.3 全局事件路径（4 路）

| 路径 | 触发 | 含义 |
|---|---|---|
| ① | PVM 自感知（watchdog/probe） | 立即采 PVM → 上报 |
| ② | GVM 主动推送 | GVM 推 → PVM 加料 → 上报 |
| ③ | 云命令下发 | 云 → PolarisAgent → ... → PVM_diag → 协调采集 → 上报 |
| ④ | 应用主动报障 | App `Polaris.reportNetworkTrouble()` → 触发 SHU 关联检查 |

---

## 3. 进程详细设计

### 3.1 PVM 进程 `linux_net_diagd`

#### 3.1.1 模块划分（C++17 单一进程，多线程）

```
linux_net_diagd
├── core/
│   ├── Bootstrap          启动协调器（顺序：Config → Capability → Clock → Channels → Schedulers → Listeners）
│   ├── Clock              CLOCK_BOOTTIME / CLOCK_REALTIME 双时钟，boot_id 读取，时间偏差检测
│   ├── Config             JSON-with-comments 解析，schema 校验，热重载（v2）
│   ├── Capability         能力探测（ethtool/tcpdump/sd-journal/dumpsys 等）
│   ├── ResourceGuard      CPU/Memory/Bandwidth 自我保护（高 conntrack 跳重操作）
│   └── MaintenanceMode    维护模式开关（G17）
├── transport/
│   ├── VsockServer        VSOCK 9101 listen + accept + framing + heartbeat
│   ├── PolarisdClient     UDS 持久连接 + 命令接收 + 事件上报（用扩展 SDK 或 LSP 直连）
│   └── NdgaProtocol       NDGA 帧编解码（含 fetch_log 分块协议）
├── watchdog/
│   ├── NetlinkReactor     RTNLGRP_LINK / RTNLGRP_IPV4_ROUTE / RTNLGRP_IPV4_IFADDR / RTNLGRP_NEIGH 监听
│   ├── InotifyReactor     /sys/class/net/*/operstate + /proc/sys/net/ipv4/ip_forward 等
│   ├── JournalReactor     sd-journal 订阅（kmsg + systemd ActiveState）
│   ├── ProcessWatcher     pid_t kill(0) 5s 轮询（qcrosvm + 服务进程）
│   └── ConntrackPoller    /proc/sys/net/netfilter/nf_conntrack_count 10s 轮询
├── probe/
│   ├── ProbeScheduler     时间轮 + 加紧策略 + per-SHU coalesce
│   ├── IcmpProbe          含 PMTU 边界包（G2）
│   ├── DnsProbe
│   ├── HttpProbe          v2
│   ├── ArpProbe           v2
│   ├── GvmPerspectiveProbe  PVM 模拟 GVM 视角 probe（G1）
│   ├── RttBurstProbe      间歇故障检测，1s/包持续 30s（G3）
│   └── ProbeRecorder      JSONL 滚动窗口
├── collector/
│   ├── CommandRunner      只读命令执行 + 超时 + 输出截断 + 并行调度
│   ├── NetfilterCollector iptables/nft 抽象（G8），下接 IptablesAdapter / NftAdapter
│   ├── SysctlCollector
│   ├── ProcNetCollector   /proc/net/{dev,netstat,nf_conntrack,...}
│   ├── EthtoolCollector
│   └── TcpdumpRunner      限时限包数 + pcap 写入 incident_dir
├── checker/
│   ├── BaselineDiff       与配置基线对比，应用 diff_policy（BASE-003）
│   ├── CheckRunner        74 项 check 调度器
│   ├── L1Link / L2Vlan / L3Route / L4NatFw / VirtLink / L5Service / Perf / Security / Base
│   └── ShuEvaluator       SHU 健康评分聚合
├── analyzer/
│   ├── EventCorrelator    事件因果聚合（G7），根事件 + 派生事件 ID 列表
│   ├── IncidentDeduper    incident 去重键 + 30s 窗口归并
│   ├── RootCauseSolver    跨 PVM/GVM/probe 三源合并 + 路径分析
│   └── VlanImpactMap      故障接口 → 影响 VLAN 集合
├── report/
│   ├── EventComposer      事件 payload 组装（含 boot_id/ts_boot/ts_unix/data_quality）
│   ├── IncidentDirWriter  原子目录创建 + 文件写入
│   ├── SensitivityRedact  取证脱敏（G18，MAC 后两段、conntrack peer IP）
│   └── JsonReport         端侧只生成 report.json，不生成 markdown
└── main.cpp
```

#### 3.1.2 线程模型

| 线程 | 数量 | 职责 |
|---|---|---|
| Main | 1 | 启动/停止协调，信号处理，监督 |
| ScanScheduler | 1 | timerfd 驱动 60s 轻量 + 1h 全量巡检 |
| WatchdogReactor | 1 | epoll 多路：NetlinkReactor/InotifyReactor/ConntrackPoller/ProcessWatcher |
| JournalReactor | 1 | sd-journal blocking poll（独立线程避免阻塞 epoll） |
| ProbeScheduler | 1 | timerfd 驱动 probe 调度，加紧时短期切高频 |
| VsockServer | 1 | 9101 accept/read/write，单 peer 并发 |
| PolarisdClient | 1 | UDS connect + 接收命令 + 发送事件 |
| WorkerPool | 4 | 命令并行执行（采集/抓包/取证），bounded queue size=32 |

线程间通信：

- `WatchdogReactor` / `ProbeScheduler` 检测到事件 → 投递到 `EventBus`（lock-free MPSC queue）
- `EventCorrelator` 在 Main 线程消费 EventBus → 决策是否触发 collect → 派 WorkerPool 执行
- 所有日志走 `Log::Info/Warn/Error`（线程安全，写 syslog）

#### 3.1.3 启动流程（含 Boot Warmup，G5/G12）

```
T+0      : systemd 拉起，main() 入口
T+0-2s   : Bootstrap::Phase1
           - 解析 cmdline, 加载 /etc/polaris/network-diag-pvm.json
           - schema 校验，失败则 exit 1（systemd Restart 退避 2s）
           - 初始化 Clock（读取 /proc/sys/kernel/random/boot_id）
           - 读取 baseline_version / config_version
T+2-5s   : Bootstrap::Phase2 - Capability probe
           - which ethtool, tcpdump, conntrack
           - test -f /proc/net/stat/nf_conntrack
           - sd-journal 可用性
           - 缓存 capability 表
T+5-10s  : Bootstrap::Phase3 - Channels
           - VSOCK 9101 listen
           - UDS connect /run/polaris/network-diag.sock（带退避，最多 30 次重试）
           - 失败也继续运行（fallback 模式）
T+10s    : Bootstrap::Phase4 - 进入 Boot Warmup 期（默认 120s）
           - 启动 ScanScheduler / WatchdogReactor / ProbeScheduler / WorkerPool
           - 所有信号源开始采样，但事件输出降级 INFO，不发 polaris
           - 仅写本地 `/log/perf/network_diag/boot_warmup.log` 供事后分析
T+130s   : Boot Warmup 结束
           - 触发首次全量 baseline diff
           - 上报 INFO `NETDIAG_SCAN_REPORT`
           - 进入正常运行模式
```

**Warmup 期内特例**：

- 物理 link DOWN 仍立即 FAIL（这是真实硬件故障，不能等）
- conntrack table full 仍立即 FAIL
- 其他故障类（network/route/probe failures）降级 INFO

#### 3.1.4 关闭流程

```
SIGTERM 收到
 → Bootstrap::Shutdown
   - 停止接受新命令（PolarisdClient::stopAccept）
   - WorkerPool 等待当前任务完成（最多 5s）
   - flush 待发事件到 polarisd（最多 3s）
   - 关闭 VSOCK / UDS
 → exit 0

SIGKILL：systemd 兜底，10s 超时强杀
```

#### 3.1.5 资源配额（修正 review F5）

```ini
# /usr/lib/systemd/system/network-diag.service [Service]
Type=simple
ExecStart=/usr/bin/network-diag-pvm --config /etc/polaris/network-diag-pvm.json
Restart=always
RestartSec=2s
StartLimitBurst=5
StartLimitIntervalSec=60s

# 软限制（始终生效）
Nice=10
IOSchedulingClass=best-effort
IOSchedulingPriority=7

# 内存硬上限（防泄漏）
MemoryMax=128M

# CPU 限制：常态软限，incident 模式放宽
CPUWeight=20            # 默认相对低权重
# CPUQuota=20%          # 上限改宽，从 5% → 20%；incident 期间临时取消（运行时 sd_notify 调整）

AmbientCapabilities=CAP_NET_RAW CAP_NET_ADMIN
RuntimeDirectory=polaris/network-diag
RuntimeDirectoryMode=0750
ReadWritePaths=/log/perf/network_diag
User=root
Group=root
```

> review F5 + G13 联合考量：常态用 CPUWeight=20 软限；incident 处理时 ResourceGuard 检测到 conntrack ≥80% 自动跳过 `iptables -L -nv` 等重操作，避免资源争用。

### 3.2 GVM 进程 `android_net_diagd`

#### 3.2.1 模块划分（精简版，约 PVM 1/3 体量）

```
android_net_diagd
├── core/{Bootstrap, Clock, Config, Capability, MaintenanceMode}
├── transport/
│   ├── VsockClient        connect CID=2:9101，重连退避，heartbeat
│   ├── NdgaProtocol       帧编解码 + fetch_log 服务端
│   └── PolarisFallback    polaris client SDK，仅兜底用
├── watchdog/
│   ├── NetlinkReactor     RTNLGRP_LINK + RTNLGRP_IPV4_IFADDR + RTNLGRP_NEIGH
│   ├── ConnectivityWatcher  ConnectivityService callback（实现见 G9）
│   ├── ProcessWatcher     netd / resolver pid 5s 轮询
│   └── DnsResolverWatcher resolver 错误事件订阅
├── collector/
│   ├── CommandRunner      ip/ss/dumpsys/ndc 等
│   └── DumpsysSnapshot    dumpsys connectivity 智能解析
├── push/
│   ├── AlertBuilder       gvm_alert payload 组装（含 snapshot_brief 分层 G4）
│   └── SnapshotPackager   snap_dir 写入 + 脱敏
└── main.cpp
```

#### 3.2.2 线程模型

| 线程 | 数量 | 职责 |
|---|---|---|
| Main | 1 | 启动/停止 |
| ScanScheduler | 1 | 60s 轻量 + 1h 全量 |
| WatchdogReactor | 1 | epoll: Netlink + Inotify + ProcessWatcher |
| VsockClient | 1 | 9101 connect/read/write |
| ConnectivityListener | 1 | callback 路径（见 G9 实现选项） |
| WorkerPool | 2 | 命令并行执行 |

#### 3.2.3 启动流程

```
T+0     : init.rc 拉起，main()
T+0-2s  : Phase1 - 加载 /system/etc/polaris/network-diag-gvm.json
T+2-5s  : Phase2 - Capability probe
          - which dumpsys ndc ip ss
          - ConnectivityService callback 通路检测（PolarisAgent 桥接 vs 直 binder vs poll）
T+5-15s : Phase3 - VSOCK 9101 connect to CID=2:9101，最多 30 次退避
T+15s   : Phase4 - Boot Warmup（与 PVM 同步策略，120s）
T+135s  : Boot Warmup 结束，进入正常运行
```

#### 3.2.4 init.rc 与 sepolicy

```
# /vendor/etc/init/network-diag.rc
service network-diag-gvm /system/bin/network-diag-gvm \
    --config /system/etc/polaris/network-diag-gvm.json
    class main
    user system
    group system net_admin net_raw inet readproc log
    capabilities NET_RAW NET_ADMIN DAC_READ_SEARCH
    task_profiles ServiceCapacityLow
    ioprio be 7
    seclabel u:r:network_diag:s0
    oneshot false
```

```
# device/voyah/.../sepolicy/network_diag.te
type network_diag, domain;
type network_diag_exec, exec_type, vendor_file_type, file_type;
init_daemon_domain(network_diag)

# VSOCK 出向到 host CID=2 port=9101
allow network_diag self:vsock_socket { create connect read write };

# 读 /proc/net/*
allow network_diag proc_net:file { open read };

# 读 /sys/class/net/*
allow network_diag sysfs_net:dir search;
allow network_diag sysfs_net:file { open read };

# 执行 ip / ss / ndc / dumpsys
allow network_diag system_file:file execute;

# 写 /log/perf/network_diag
allow network_diag log_file:dir { create_dir_perms };
allow network_diag log_file:file { create_file_perms };

# binder 调 ConnectivityService（仅 G9 选项 b 时启用）
# binder_call(network_diag, system_server)
```

---

## 4. 通信协议详细设计

### 4.1 通道 A：VSOCK 9101 NDGA 协议

#### 4.1.1 帧格式（订正 sys_design §5.1，加版本字段）

```
+---------+---------+---------+---------+----------------+
| magic   | version | length  | flags   | json payload   |
| 4 bytes | 2 bytes | 4 bytes | 2 bytes | length bytes   |
+---------+---------+---------+---------+----------------+
magic   = 0x4E444741 ("NDGA")
version = 1（uint16_t big-endian）
length  = uint32_t big-endian, max = 4 MiB
flags   = bitmask（第 0 位 = COMPRESSED, 第 1 位 = LAST_CHUNK, 第 2 位 = HAS_CHECKSUM, 其余保留）
```

帧解析必须先校验 magic + version；不匹配立即关闭连接。

#### 4.1.2 消息类型（订正 + 完整化）

| msg | 方向 | 用途 | 关键字段 |
|---|---|---|---|
| `hello` | 双向 | 连接建立后第一帧 | version, role, peer_diag_version, peer_config_version |
| `request` | 双向 | 同步 RPC | req_id, method, args, timeout_ms |
| `response` | 双向 | RPC 回包 | req_id, code, errmsg, data, log_ref |
| `push` | 双向 | 单向通知 | type, ts_unix, ts_boot, boot_id, payload, log_ref |
| `chunk` | 双向 | 大文件分块（fetch_log 用） | req_id, chunk_seq, total_chunks, total_bytes, sha256_partial, data_b64 |
| `ack` | 双向 | chunk 确认 | req_id, chunk_seq, ok |

#### 4.1.3 RPC method 完整清单

| method | 发起方 | args | 返回 data |
|---|---|---|---|
| `collect` | PVM→GVM | `{sections: [...]}` | 各 section 内容（≤2 MiB inline，超出用 `log_ref` + `fetch_log`） |
| `probe` | PVM→GVM | `{type:icmp, target, count, interface}` | `{rtt_ms[], loss_pct, raw_log_ref}` |
| `snapshot` | PVM→GVM | `{reason, full_or_brief}` | snap_dir 写入完成，返回 `log_ref` |
| `fetch_log` | 双向 | `{log_ref, files:[...]}` | 触发 chunk 流（见 4.1.5） |
| `ping` | 双向 | 无 | 无（用于心跳） |
| `set_maintenance` | PVM→GVM | `{enable, scope, duration_sec}` | `{ack:true}`（G17） |
| `dynamic_target` | 双向 | `{shu, probe_targets:[...]}` | `{ack:true}`（G16，按 SKU 切换 probe 目标） |

#### 4.1.4 GVM alert push payload（修正 G4 数据质量分层）

```json
{
  "msg":     "push",
  "type":    "gvm_alert",
  "ts_unix": 1747764000,
  "ts_boot": 18234567,
  "boot_id": "f0b8...",
  "payload": {
    "alert_id":      "VLAN3_GATEWAY_UNREACHABLE",
    "severity":      "FAIL",
    "shu":           "SHU_VLAN3_INTERNET",
    "target":        "10.10.103.1",
    "via_iface":     "eth1.3",
    "consec_fails":  5,

    "snapshot_layer1": {
      "_source":           "netlink_direct",
      "_data_quality":     "high",
      "_collect_time_ms":  3,
      "iface_up":          true,
      "ip":                "10.10.103.40/24",
      "neigh_state":       "FAILED",
      "carrier_changes":   1
    },

    "snapshot_layer2": {
      "_source":           "dumpsys_connectivity",
      "_data_quality":     "ok | timeout | unparseable",
      "_collect_time_ms":  450,
      "default_netid":     102,
      "default_dns":       ["10.10.103.20"],
      "default_route":     "via 10.10.103.1 dev eth1.3"
    }
  },
  "log_ref": "/log/perf/network_diag/snaps/snap_20260509_153000_VLAN3GW"
}
```

**关键约束**：
- `snapshot_layer1` 是 netlink 直读（永远可用，<10ms）
- `snapshot_layer2` 是 `dumpsys` 解析（可能 hang），独立超时 500ms，超时填 `_data_quality:"timeout"` 而非空字符串
- 整条 push payload ≤ 4 KiB；大数据走 `log_ref` + `fetch_log`

#### 4.1.5 fetch_log 大文件协议（补 review F4）

请求：

```json
{
  "msg":"request","req_id":42,"method":"fetch_log","timeout_ms":30000,
  "args":{
    "log_ref":"/log/perf/network_diag/snaps/snap_xxx",
    "files":["dumpsys_connectivity.txt","ip_route_all.txt"],
    "max_bytes_per_file": 1048576,
    "redact":"on"
  }
}
```

响应链：

```
1. response                  {req_id:42, code:0, data:{file_index:[{name, size, sha256}, ...]}}
2. chunk msg×N (per file)    {req_id:42, file:"...", chunk_seq:0..K, total_chunks:K+1, total_bytes:N, data_b64:"..."}
3. chunk msg with LAST_CHUNK flag for each file
4. final response or ack flow
```

约束：

- 单 chunk size ≤ 256 KiB（控制内存峰值）
- 接收方对每个 chunk 发 `ack`；发送方未收到 ack ≥ 5s 重发该 chunk（最多 3 次）
- 整次 fetch_log 总传输 ≤ 16 MiB（防恶意请求耗尽 VSOCK）
- 每个文件附 `sha256` 校验，最后一帧 LAST_CHUNK 才返回完整 hash 验证
- `redact:"on"` 触发 `SensitivityRedact` 在发送前脱敏（G18）

错误码：

| code | 含义 |
|---|---|
| 0 | OK |
| -2 | log_ref 不存在 |
| -3 | 文件不可读（perm/SELinux） |
| -4 | 超出 max_bytes_per_file |
| -5 | 超出 16 MiB 总量 |
| -6 | chunk ack 超时 |
| -7 | sha256 校验失败 |
| -8 | 维护模式拒绝 |

#### 4.1.6 连接管理（订正）

| 项 | 规范 |
|---|---|
| 角色 | PVM=server `listen(2)` on `VMADDR_CID_HOST(2):9101`；GVM=client `connect(2)` to `CID_HOST:9101` |
| 单连接 | server 同一时刻只接受 1 个 client，新 client 进来挤掉旧的 |
| 心跳 | 30s 双向 ping/pong；连续 3 次未响应 close+reconnect |
| 重连退避 | 1s/2s/4s/8s/16s/30s 封顶 |
| Hello 验证 | 双方 hello 都必须含 version 与 peer_diag_version；version 不兼容直接 close |
| 维护模式 | server 收到 `set_maintenance` 后将相关 alert 降级 INFO，duration_sec 内有效 |
| Fallback | client 持续断连 60s → 进入 polaris event 链兜底（轻量化，仅根级 alert） |

### 4.2 通道 B：polaris VSOCK 9001（复用，不展开）

直接复用 polaris 现有 PLP 协议。本模块只关心两件事：

- **事件出口**：经 `polaris_report_raw()` 发到 PVM polarisd → 自动经 VSOCK 上行
- **命令接收**：经 polarisd `NetdiagBridgeAction` → UDS → 本进程

### 4.3 通道 C：UDS PVM polarisd ↔ PVM_diag

#### 4.3.1 路径与传输

- 路径：`/run/polaris/network-diag.sock`（systemd RuntimeDirectory 创建）
- 类型：`SOCK_SEQPACKET`，非阻塞
- 协议：复用 polarisd 现有 LSP Codec（12-byte header + JSON payload）
- 连接：`network-diag-pvm` 启动后主动 connect；断线 1s 重连，最多无限退避（3s/5s/10s/30s 封顶）

#### 4.3.2 消息格式

```jsonc
// polarisd → diag (msgType=CMD_REQ 0x0020)
{
  "req_id":   123,
  "action":   "netdiag.run",
  "args": {
    "scope":     "full" | "vlan" | "scenario" | "shu" | "diagnose_one_check",
    "target":    "SHU_VLAN3_INTERNET" | "VLAN:4" | ...,
    "verbose":   false,
    "deadline_ms": 25000
  },
  "issued_ts_unix": 1747764000
}

// diag → polarisd (msgType=CMD_RESP 0x0021)
{
  "req_id":  123,
  "code":    0,
  "errmsg":  "OK",
  "data":    {"incident_dir":"/log/perf/network_diag/incidents/incident_xxx", "shu_status":"PASS"}
}

// diag → polarisd (msgType=POLARIS_EVENT 0x0030)
{
  "event_id":     "0x4E5E0008",
  "json_body":    "{\"event\":\"NETDIAG_GATEWAY_UNREACHABLE\",...}",
  "log_path":     "/log/perf/network_diag/incidents/incident_xxx",
  "ts_unix":      1747764000,
  "ts_boot":      18234567,
  "boot_id":      "..."
}
```

#### 4.3.3 polaris client SDK 扩展接口（review G + 与 polaris 团队对齐项）

新增 C API（替代 sys_design §6.1 注释中"v1 临时直连 LspCodec"的方案）：

```c
typedef int (*polaris_command_handler_fn)(
    const char* action,        // "netdiag.run"
    const char* args_json,     // JSON 字符串
    uint32_t    req_id,
    void*       user);
typedef int (*polaris_command_responder_fn)(
    uint32_t    req_id,
    int32_t     code,
    const char* errmsg,
    const char* data_json);

// 新增：
int polaris_command_listener_register(
    const char*                    action_filter,   // "netdiag.*" 通配符
    polaris_command_handler_fn     handler,
    polaris_command_responder_fn*  out_responder,
    void*                          user);

int polaris_command_listener_unregister(const char* action_filter);
```

接入示例：

```c
static int on_netdiag_command(const char* action, const char* args, uint32_t req_id, void* u) {
    auto* self = static_cast<NetDiag*>(u);
    return self->dispatch(action, args, req_id);
}

polaris_command_responder_fn responder = nullptr;
polaris_command_listener_register("netdiag.*", on_netdiag_command, &responder, this);
// later:
responder(req_id, 0, "OK", result_json);
```

---

## 5. 配置详细设计

### 5.1 配置文件清单

| 文件 | 部署 | 拥有方 |
|---|---|---|
| `network-diag-pvm.json` | `/etc/polaris/network-diag-pvm.json` | PVM_diag |
| `network-diag-gvm.json` | `/system/etc/polaris/network-diag-gvm.json` | GVM_diag |
| `scenario-registry.json` | `/etc/polaris/scenario-registry.json`（PVM）+ 同名（GVM） | 共享 |

> 拆分理由：① PVM/GVM 各自基线不同 → 各持一份；② scenario registry 在两端都需要被读取（PVM 评估结果，GVM 知道 push 时关联到哪个 scenario） → 强制双端同步、文件 sha256 校验。

### 5.2 PVM 主配置完整 schema

```jsonc
{
  "version":          "1.0",
  "config_version":   "v1.0-2026-05-09",   // 配置文件本身版本
  "baseline_version": "v1.0-2026-05-09",   // 拓扑基线版本（独立演进）
  "platform":         "SA8397",
  "side":             "PVM",
  "sku":              "DEFAULT",            // 用于 probe 目标按区域选择 (G16)

  /* ============ 全局策略 ============ */
  "policy": {
    "boot_warmup_sec":         120,           // C6
    "scan_interval_light_sec": 60,
    "scan_interval_full_sec":  3600,
    "trigger_min_gap_sec":     30,
    "global_min_interval_sec": 10,
    "incident_retention_days": 7,
    "incident_max_count":      50,
    "incident_max_size_mb":    200,
    "incident_single_max_mb":  50,
    "snapshots_retention_h":   24,
    "probes_retention_h":      24,
    "tcpdump_max_sec":         10,
    "tcpdump_max_pkts":        2000,
    "command_timeout_sec":     5,
    "command_parallel_max":    4,             // G + 8.2 修正
    "readonly_only":           true,
    "probe_max_pps":           100,
    "dns_probe_max_per_min":   5,
    "fetch_log_max_total_mb":  16,
    "fetch_log_chunk_kb":      256,
    "maintenance_max_sec":     3600           // 维护模式最长持续 (G17)
  },

  /* ============ 时钟模型 ============ */
  "clock": {
    "internal_clock":         "BOOTTIME",     // C7
    "skew_warn_ms":           5000,           // RPT-005
    "skew_fail_ms":           60000
  },

  /* ============ 拓扑基线 ============ */
  "baseline": { /* 见 §5.3 */ },

  /* ============ 关键服务基线 ============ */
  "services": { /* 见 §5.4 */ },

  /* ============ 差异策略（review F2 + BASE-003） ============ */
  "diff_policy": { /* 见 §5.5 */ },

  /* ============ 检查项 registry ============ */
  "checks": { /* 见 §5.6 */ },

  /* ============ SHU registry ============ */
  "shus": [ /* 见 §5.7 */ ],

  /* ============ Watchdog 信号源 ============ */
  "watchdogs": [ /* 见 §5.8 */ ],

  /* ============ Probe 配置 ============ */
  "probes": { /* 见 §5.9 */ },

  /* ============ 事件 ID 映射 ============ */
  "event_ids": { /* 见 §8.1 */ },

  /* ============ 敏感性策略 (G18) ============ */
  "sensitivity": {
    "redact_mac_last_octets":     2,
    "redact_conntrack_peer_ip":   true,
    "tcpdump_payload_strip":      true,
    "field_levels": {
      "low":  ["interface_name", "vlan_id", "service_name"],
      "med":  ["pvm_ip", "gvm_ip", "gateway_ip"],
      "high": ["mac_address", "external_peer_ip", "tcpdump_payload"]
    }
  }
}
```

### 5.3 baseline 段 — 引用外部附件（v1.1 G1 修订）

> **v1.0 → v1.1 变更**：baseline 内容从主配置文件内联展开 → 抽出独立附件，主配置仅引用。原因：review F8（基线不可省略），完整展开 200+ 行 baseline 在主配置里影响可读性；独立附件便于：① 单独 review；② 机器可读；③ 双端各持一份并 sha256 互校。
>
> 主配置 `network-diag-pvm.json` 中 baseline 段简化为：

```jsonc
"baseline": {
  "pvm_baseline_file":  "/etc/polaris/baseline-pvm.json",
  "gvm_baseline_file":  "/etc/polaris/baseline-gvm.json",
  "pvm_baseline_sha256":"<填充实际 sha256>",     // 启动时校验，防止外部篡改
  "gvm_baseline_sha256":"<填充实际 sha256>",     // GVM 端通过 NDGA hello 上报，PVM 验证
  "_note":"完整展开见附件文件；schema 见 §5.3.1 / §5.3.2"
}
```

GVM 端 `network-diag-gvm.json` 同理：

```jsonc
"baseline": {
  "gvm_baseline_file":  "/system/etc/polaris/baseline-gvm.json",
  "pvm_baseline_file":  "/mnt/vendor/etc/polaris/baseline-pvm.json",  // 通过共享路径访问 PVM 视角
  "gvm_baseline_sha256":"<填充实际 sha256>",
  "pvm_baseline_sha256":"<填充实际 sha256>"
}
```

#### 5.3.1 baseline-pvm.json schema（完整附件）

附件路径：`work/baseline-pvm.json`（git）→ 部署到 PVM `/etc/polaris/baseline-pvm.json`

包含字段（详见附件文件完整内容）：

| 段 | 内容 |
|---|---|
| `phys_ifaces` | 2 个：`eth0`（emac0/PCIE/P11/P6/ADCU）+ `eth1`（emac1/USXGMII/P9/P5/VCM trunk）+ MAC + 速率 + MTU |
| `vlan_ifaces` | **12 个**完整展开：`eth1.3/4/6/7/8/10/11/12/13/14`、`eth0.15/19`，每项含 IP/parent/MTU/role/gateway/SHU/pvm_only 标记 |
| `vmtap` | **7 个**完整展开：`vmtap0`、`vmtap1`、`vmtap1.3/4/6/7/8`，每项含 IP/peer_gvm_iface |
| `main_table` | `default via 172.16.103.20` + 18 条 connected route |
| `policy_route` | 3 条 prio 217/218/219 + table 106/107/108 内容 |
| `table_220` | 标 `expected_empty:true`（已知 FIB does not exist） |
| `gateways` | 4 个：VLAN3_TBOX/VLAN6_ADCU/VLAN7_OTA/VLAN8_ADAS，每项含 IP + via_iface + expected_neigh 状态白名单 |
| `kernel_params` | 4 个全局：`ip_forward`/`conf.all.forwarding`/`conf.all.rp_filter`/`conf.all.proxy_arp` |
| `per_iface_params` | **21 个**完整展开：所有 NAT 路径接口 + vmtap，每项 `forwarding`/`rp_filter`/`proxy_arp` |
| `conntrack_params` | `nf_conntrack_max`/`buckets` 强校验 + timeout 类仅记录 |
| `iptables_nat` | PREROUTING **6 条** DNAT（含 VLAN4 IDPS 例外顺序约束）+ POSTROUTING **10 条** SNAT，每条 must_contain + 结构化字段 |
| `iptables_filter` | 默认策略 + FORWARD **10 条**双向规则，每条 must_contain + 结构化字段 |
| `pvm_only_vlans` | `[10,11,12,13,14,15,19]` |
| `expected_absent_components` | SAIL_HSGMII_P10 千兆预留位 |
| `services.required` | **15 个**必须服务：xdja_idps + 13 个 someipd 实例 + amblightserver + qcrosvm |
| `services.documented_bind_any` | **13 个**已知 0.0.0.0 监听服务（含 prod_action: close/document）|
| `diff_policy` | ignore / info / warn / fail 四级字段路径列表 |

#### 5.3.2 baseline-gvm.json schema（完整附件）

附件路径：`work/baseline-gvm.json`（git）→ 部署到 GVM `/system/etc/polaris/baseline-gvm.json`

包含字段：

| 段 | 内容 |
|---|---|
| `mac_policy` | `check_nonzero_and_consistent_across_subifaces`（不固定 MAC 数值，仅校验非零 + 子接口一致 + boot 内稳定） |
| `vlan_ifaces` | **7 个**完整展开：`eth0`、`eth1`、`eth1.3/4/6/7/8`，每项含 IP/parent/pvm_peer_iface/pvm_gateway/external_gateway/role/SHU |
| `main_table.no_default_route_expected` | true（Android multinetwork 设计）|
| `dummy0_fallback.exclude_from_default_check` | true（Android 16 fallback 不算 default route 漂移）|
| `default_route_strategy` | 未标记流量 fwmark=0x0 → eth1.3 (VLAN 3) |
| `netid_template` | 4 个角色映射（default/adcu_park/ota/adas），**不硬编码 NetId 数字** |
| `ip_rule_expected` | 结构期望：prio 0 to-rules + prio 16000 fwmark-rules（动态推断）+ prio 31000 默认 |
| `placeholder_ifaces_filter` | **12 个** Android 内核默认 DOWN 设备列表（dummy0/ifb*/tunl0/gre*/erspan*/sit*/...）|
| `services.required` | **4 个**必须服务：doip_server + vlm-agent-tcp + vlm-agent-udp + gftpd |
| `services.documented_bind_any` | **7 个**已知 0.0.0.0 监听（含 qqlive.audiobox 三个端口 prod_action:close） |
| `services.dhcpv6_clients` | rkstack 在 eth1.{3,6,7,8} 监听 546，**不含 eth1.4** |
| `pvm_only_must_not_appear` | 7 个 iface + 7 个 IP subnet 黑名单 + 4 个检查目标说明 |
| `diff_policy` | ignore / info / warn / fail 字段路径列表 |

#### 5.3.3 baseline 文件部署与校验

| 步骤 | PVM | GVM |
|---|---|---|
| 部署位置 | `/etc/polaris/baseline-pvm.json` + `/etc/polaris/baseline-gvm.json`（参考） | `/system/etc/polaris/baseline-gvm.json` + `/mnt/vendor/etc/polaris/baseline-pvm.json`（共享挂载读 PVM 视角） |
| 文件 mode | `0644`（仅 root 写） | 同左 |
| 启动时校验 | 计算 sha256 → 与主配置中的 expected sha256 比对；不匹配 → FAIL 启动 | 同左 |
| 跨端互校 | NDGA hello 时双端互发 baseline-* 各自 sha256；不一致 → 双端各打告警，但仍按自己的 baseline 继续工作（避免单点失败）|
| 升级流程 | OTA / Polaris 配置下发时整体替换，重启 network-diag 进程 | 同左 |

### 5.3 完结 — baseline 附件与主配置分工总结

| 文件 | 内容 | 维护方 |
|---|---|---|
| `network-diag-pvm.json` | 主配置：policy 阈值 + checks registry + SHU + watchdog 配置 + 事件 ID 映射 + baseline 引用 | 网络诊断模块团队 |
| `network-diag-gvm.json` | 同上，GVM 视角 | 同上 |
| `baseline-pvm.json` | PVM 拓扑全展开（接口/IP/NAT/服务/etc） | 平台/网络团队（拓扑变更同步） |
| `baseline-gvm.json` | GVM 拓扑全展开 | 同上 |
| `fault_class_dict.json` | fault_class 枚举 + target_key 抽取规则 | 网络诊断模块团队 |
| `fault_causation_graph.json` | 因果依赖图 | 同上 |
| `scenario-registry.json` | 业务场景 A-L 与 check 集合映射 | 同上 |

### 5.4 services 段（识别量产/暴露面）

```jsonc
"services": {
  "pvm": [
    // 关键业务监听
    {"name":"xdja_idps","bind":"172.16.104.40:30006","proto":"tcp","required":true,"impacts_shu":["SHU_VLAN4_DOIP"]},
    {"name":"someipd","instances":[
      {"comm_match":"someipd","bind":"172.16.110.40:30490","proto":"udp","mcast":"239.5.1.2"},
      {"comm_match":"someipd","bind":"172.16.110.40:51000","proto":"tcp"},
      // ... 7 个实例（含 G20 进程级建模）
      {"comm_match":"someipd","bind":"172.16.119.41:55005","proto":"tcp"}
    ],"required":true,"impacts_shu":["SHU_SOMEIP_BUS"]},
    {"name":"amblightserver","bind":"10.10.200.1:55498","proto":"udp","required":true,"impacts_shu":["SHU_HOST_GUEST"]}
  ],
  "gvm": [
    {"name":"doip_server","bind":"10.10.104.40:13400","proto":"tcp,udp","required":true,"impacts_shu":["SHU_VLAN4_DOIP"]},
    {"name":"vlm-agent","bind":"10.10.104.40:5062","proto":"tcp","required":true,"impacts_shu":["SHU_VLAN4_DOIP"]},
    {"name":"vlm-agent","bind":"10.10.104.40:5064","proto":"udp","required":true,"impacts_shu":["SHU_VLAN4_DOIP"]},
    {"name":"gftpd","bind":"10.10.104.40:58046","proto":"tcp","required":true,"impacts_shu":["SHU_VLAN4_DOIP"]}
  ],
  "security_sensitive_bind_any": [
    {"bind":"*:22","svc":"sshd","prod_action":"close","userdebug_action":"document"},
    {"bind":"*:23","svc":"telnetd","prod_action":"close","userdebug_action":"document"},
    {"bind":"*:21","svc":"proftpd","prod_action":"document","userdebug_action":"document"},
    {"bind":"*:111","svc":"rpcbind","prod_action":"document","userdebug_action":"document"},
    {"bind":"*:2049","svc":"nfs","prod_action":"document","userdebug_action":"document"},
    {"bind":"*:5555","svc":"adbd","prod_action":"document","userdebug_action":"document"},
    {"bind":"*:18795","svc":"qqlive.audiobox","prod_action":"close","userdebug_action":"document"},
    {"bind":"*:8753","svc":"qqlive.audiobox","prod_action":"close","userdebug_action":"document"},
    {"bind":"*:1888","svc":"qqlive.audiobox","prod_action":"close","userdebug_action":"document"},
    {"bind":"*:15002","svc":"awe_linuxproxy","prod_action":"document","userdebug_action":"document"}
  ],
  "process_health": {
    "pvm": [
      {"name":"xdja_idps","systemd_unit":"xdja_idps.service","required":true},
      {"name":"someipd","comm":"someipd","instances_min":7,"instances_max":7},
      {"name":"qcrosvm","comm":"qcrosvm","required":true,"event_on_exit":"NETDIAG_HYPERVISOR_DOWN"}
    ],
    "gvm": [
      {"name":"netd","required":true},
      {"name":"resolver"}
    ]
  }
}
```

### 5.5 diff_policy 段（review F2 BASE-003 修正）

```jsonc
"diff_policy": {
  "ignore_fields": [
    "gvm.phys_mac",                    // virtio MAC 启动相关
    "gvm.netid_runtime",                // NetId 动态分配
    "gvm.dummy0_fallback_route",        // Android 16 内置
    "gvm.placeholder_ifaces"            // dummy0/ifb*/tunl0/...
  ],
  "info_if_changed": [
    "pvm.conntrack_count",
    "pvm.iptables_counters",
    "pvm.carrier_changes_total"
  ],
  "warn_if_changed": [
    "pvm.iptables.filter.policy_default",
    "services.pvm.security_sensitive_bind_any[*].observed",
    "gvm.netid_to_vlan_mapping"
  ],
  "fail_if_changed": [
    "pvm.vlan_ifaces[*].ip",
    "pvm.vmtap[*].ip",
    "pvm.policy_route",
    "pvm.gateways[*].ip",
    "pvm.phys_mac",
    "pvm.kernel_params",
    "pvm.per_iface_params",
    "pvm_only_vlans"
  ],
  "fail_if_missing": [
    "pvm.vlan_ifaces",
    "pvm.iptables.nat.PREROUTING.rule_VLAN3_DNAT",
    "pvm.iptables.nat.PREROUTING.rule_VLAN4_TCP_EXCEPT_30006_DNAT"
  ]
}
```

### 5.6/5.7/5.8/5.9 — 见 §6（检查项）/ §7（SHU）/ §11（Watchdog）/ §12（Probe）

---

## 6. 检查项 Registry（74 项详细设计）

### 6.1 通用检查项 schema

```jsonc
{
  "id":              "L4-NAT-001",                // 内部 ID
  "req_ids":         ["NET-DIAG-NAT-001"],        // 需求文档 ID（可多个）
  "title":           "VLAN 3/4/6/7/8 双向 NAT 规则完整性",
  "layer":           "L4",
  "side":            "PVM",                        // PVM | GVM | BOTH
  "enable":          true,
  "severity":        "FAIL",                       // PASS / INFO / WARN / FAIL / BLOCKED
  "blocked_severity":"L1_env",                     // L1_env / L2_anomaly / L3_intermittent (G15)
  "event_id_on_fail":"0x4E5E0005",
  "shu_impact":      ["SHU_VLAN3_INTERNET","SHU_VLAN4_DOIP","SHU_VLAN6_ADCU_PARK","SHU_VLAN7_OTA","SHU_VLAN8_ADAS"],
  "data_source": {
    "type":    "command",                          // command / sysctl / netlink / proc_file / dumpsys / capability
    "command": "iptables -t nat -S",
    "timeout_sec": 5,
    "max_output_kb": 128,
    "fallback_on_blocked": "nft list ruleset"      // G8 备选
  },
  "parser":          "nat_rules_v1",
  "expect": { /* 检查规则，因 check 而异 */ },
  "evidence_files":  ["pvm/iptables_nat_S.txt","pvm/iptables_nat_Lnv.txt"],
  "suggestion":      "...",
  "recheck_cmd":     "...",
  "perf_budget": {
    "cpu_ms_p95":          120,
    "io_kb":               4,
    "network_packets":     0,
    "skip_when_conntrack_pct_above": 80   // G13 / 18.4
  }
}
```

### 6.2 L1 物理链路（6 项）

| ID | 需求 ID | 数据源 | parser | expect | 性能预算 |
|---|---|---|---|---|---|
| L1-LINK-001 | LINK-001 | netlink `RTNLGRP_LINK`（实时） + `cat /sys/class/net/eth{0,1}/{operstate,carrier}` | iface_state | `state UP && carrier=1` for eth0,eth1 | 1 ms |
| L1-LINK-002 | LINK-002 | `ethtool eth0/eth1`（capability gated） | ethtool_v1 | `Speed:1000Mb/s, Duplex:Full` | 200 ms（首次执行） |
| L1-LINK-003 | LINK-003 | `cat /proc/net/dev` + `/sys/class/net/*/statistics/{rx_errors,tx_errors,rx_dropped,tx_dropped,rx_crc_errors,collisions}` | counter_delta | 两次采样间无递增；递增→FAIL | 10 ms |
| L1-LINK-004 | LINK-004 | `/sys/class/net/*/carrier_changes` + 内部状态机 | flapping_v1 | 5min 内 ≥3 次变化 → FAIL（一次性诊断模式下 BLOCKED-L1_env） | 5 ms |
| L1-LINK-005 | LINK-005 | `ethtool` capability check | ethtool_capability | 平台支持 → ethtool 输出；不支持 → BLOCKED-L1_env | 1 ms |
| L1-LINK-006 | LINK-006 | `ip -d link show eth0/eth1` | mac_match | `eth0=02:df:53:00:00:09 && eth1=02:df:53:00:00:04`（或符合 OUI 白名单） | 5 ms |

### 6.3 L2 VLAN/二层（7 项）

| ID | 需求 ID | 数据源 | parser | expect |
|---|---|---|---|---|
| L2-VLAN-001 | VLAN-001 | `ip -d link show` | vlan_iface_v1 | PVM `eth1.{3,4,6,7,8,10..14}` + `eth0.{15,19}` 全存在 + UP + 父接口正确 |
| L2-VLAN-002 | VLAN-002 | `ip -d link show` | vlan_iface_v1 | PVM `vmtap1.{3,4,6,7,8}` 全存在 + UP（state=UNKNOWN 但 operstate UP 视为 UP） |
| L2-VLAN-003 | VLAN-003 | GVM `ip -d link show`（远端 collect） | vlan_iface_v1 | GVM `eth1.{3,4,6,7,8}` 全存在 + UP |
| L2-VLAN-004 | VLAN-004 | 跨端：PVM eth1.X / vmtap1.X / GVM eth1.X 三侧 vlan id 比对 | vlan_consistency_v1 | 同 VLAN id 三侧一致；缺一项 FAIL |
| L2-VLAN-005 | VLAN-005 | `ip neigh show` | neigh_state_v1 | 业务网关均 REACHABLE/STALE/PERMANENT；INCOMPLETE/FAILED → FAIL |
| L2-VLAN-006 | VLAN-006 | 报告中 hint，给出 tcpdump 命令模板 | suggestion_only | INFO 级 |
| L2-VLAN-007 | VLAN-007 | `ip neigh show` 关键网关条目 | gateway_neigh_v1 | TBOX/ADCU/OTA/ADAS 网关均 REACHABLE 等价；FAILED → FAIL |

### 6.4 L3 IP/路由（11 项，含 IP-005 修正）

| ID | 需求 ID | 数据源 | parser | expect |
|---|---|---|---|---|
| L3-IP-001 | IP-001 | `ip -br addr` | ip_baseline_v1 | PVM 各 VLAN IP 完全匹配 baseline |
| L3-IP-002 | IP-002 | GVM `ip -br addr`（远端 collect） | ip_baseline_v1 | GVM 各 VLAN IP 完全匹配 baseline |
| L3-IP-003 | IP-003 | `sysctl net.ipv4.ip_forward` | sysctl_eq | =1 |
| L3-IP-004 | IP-004 | 多个 sysctl + `/proc/sys/net/ipv4/conf/*/forwarding,rp_filter` | sysctl_per_iface_v1 | `conf.all.forwarding=1`，所有 NAT 路径 iface 各自 forwarding=1，rp_filter ∈ {0,2}；rp_filter=1 在 NAT 路径 → FAIL |
| **L3-IP-005** | **IP-005**（新闭环 review F2） | `/proc/sys/net/ipv4/conf/*/proxy_arp` 全采集 | sysctl_per_iface_v1 | 与 baseline 比较；偏离 → INFO/WARN（按 diff_policy 决定） |
| L3-ROUTE-001 | ROUTE-001 | `ip route show table main` | route_v1 | `default via 172.16.103.20 dev eth1.3` 存在；各 connected route 完整 |
| L3-ROUTE-002 | ROUTE-002 | `ip route show table 106/107/108` + `ip rule` | policy_route_v1 | `iif vmtap1.{6,7,8} → table 106/107/108` + `default via 172.16.10X.20 dev eth1.X` |
| L3-ROUTE-003 | ROUTE-003 | `ip route show table 220` | empty_table | `FIB does not exist`；如开始注入 → WARN |
| L3-ROUTE-004 | ROUTE-004 | GVM `ip route show table main` | gvm_main_no_default | main 表无 default；`default dev dummy0 table dummy0` 排除 |
| L3-ROUTE-005 | ROUTE-005 | GVM `dumpsys connectivity` + `ip rule` | netid_vlan_dynamic_v1 | NetId↔VLAN 通过 dumpsys 动态推断后比对模板（default/ota/adas/adcu_park）；不匹配 → FAIL |
| L3-ROUTE-006 | ROUTE-006 | `ip route get` 多目标 | route_get_v1 | `172.16.106.x → eth1.6`、`172.16.103.20 → eth1.3` 等预期出口 |

### 6.5 L4 NAT/防火墙（9 项，含 FW-005 修正 + G13 性能保护）

| ID | 需求 ID | 数据源 | parser | expect | 性能保护 |
|---|---|---|---|---|---|
| L4-NAT-001 | NAT-001 | `iptables -t nat -S` | nat_rules_v1 | 6 条 PREROUTING DNAT must_contain；VLAN 4 顺序：`! --dport 30006` before `! -p tcp` | — |
| L4-NAT-002 | NAT-002 | `iptables -t nat -S` | nat_rules_v1 | POSTROUTING SNAT 5 条（eth1.3/4/6/7/8 出向）must_contain | — |
| L4-NAT-003 | NAT-003 | `iptables -t nat -S` | nat_rules_v1 | 5 条 vmtap1.X 回程 SNAT 必含 | — |
| L4-NAT-004 | NAT-004 | `iptables -t nat -L -nv`（仅全量巡检，G13） | counter_growth | 执行专项连通性测试后规则计数应增长 | **conntrack ≥80% 跳过** |
| L4-FW-001 | FW-001 | `iptables -S` | filter_default_policy | `-P FORWARD ACCEPT` → WARN（暴露面） | — |
| L4-FW-002 | FW-002 | 解析 NAT DNAT 完整透传范围 | port_exposure_v1 | 列出 VLAN3/4/6/7/8 对 GVM 全端口 DNAT 暴露面 → 输出 INFO 报告 + WARN | — |
| L4-FW-003 | FW-003 | `cat /proc/sys/net/netfilter/nf_conntrack_count,_max` | conntrack_pct | count/max ≥80% WARN，≥95% FAIL | — |
| L4-FW-004 | FW-004 | dual-source: ① sd-journal kmsg `nf_conntrack: table full`；② `/proc/net/stat/nf_conntrack`（不存在则降级） | conntrack_full_v1 | 任一信号命中 → FAIL；`/proc/net/stat/nf_conntrack` 不存在 → BLOCKED-L1_env，仅看 dmesg | — |
| **L4-FW-005** | **FW-005**（新闭环） | sysctl 多个 conntrack 参数：buckets/tcp_timeout_established/udp_timeout/udp_timeout_stream | sysctl_record_v1 | 采集并记录到 incident 证据；偏离 baseline 给 INFO/WARN（不强校验数值） | — |

### 6.6 虚拟化链路（7 项）

| ID | 需求 ID | 数据源 | parser | expect |
|---|---|---|---|---|
| VM-001 | VM-001 | `pidof qcrosvm` + `ip -d link show vmtap*` | qcrosvm_v1 | qcrosvm 进程存在 + vmtap 设备齐全 |
| VM-002 | VM-002 | PVM `ping -c3 10.10.200.40`（vmtap0 出向） | host_guest_ping_v1 | 全通；丢包→FAIL |
| VM-003 | VM-003 | PVM `ping -I vmtap1.X -c3 10.10.10X.40` 5 个 | gvm_vlan_ping_v1 | 各 VLAN 通；丢包→FAIL |
| VM-004 | VM-004 | `cat /proc/net/dev` 增量 vs 跨端对比 + 协议层 echo（G11） | unidirectional_v1 | 30s 内 RX/TX 单向增长 → 重做 echo 验证；echo 失败 → FAIL |
| VM-005 | VM-005 | GVM `ip addr` 检查 | pvm_only_isolation_v1 | GVM 不应出现 VLAN 10-14/15/19 接口或 IP；出现→FAIL |
| VM-006 | VM-006 | PVM `vmtap0` + GVM `eth0` 双端基线对账 | host_guest_baseline_v1 | vmtap0=10.10.200.1 UP；GVM eth0=10.10.200.40 UP；缺/异常→FAIL |
| VM-007 | VM-007 | `ip -d link show vmtap1` + GVM `eth1` | trunk_parent_v1 | vmtap1 + GVM eth1 都 UP；任一 DOWN → FAIL（影响 VLAN 3-8） |

### 6.7 L5 服务（12 项）

| ID | 需求 ID | 数据源 | parser | expect |
|---|---|---|---|---|
| SVC-001 | SVC-001 | `ip route get 8.8.8.8 mark 0x0`（GVM）+ NAT 计数（PVM） | default_internet_v1 | GVM 路由命中 eth1.3；NAT 命中计数活跃；TBOX 网关可达 |
| SVC-002 | SVC-002 | tcpdump（按需）+ `ss -ltnp` GVM | doip_chain_v1 | PVM eth1.4 入包 + vmtap1.4 入包匹配；GVM `10.10.104.40:13400` LISTEN |
| SVC-003 | SVC-003 | PVM `ss -ltnp` + DNAT 规则解析 | idps_bypass_v1 | PVM `172.16.104.40:30006/tcp` LISTEN by xdja_idps；DNAT 例外规则存在 |
| SVC-004 | SVC-004 | GVM `ip route get` to 172.16.106.x / 10.82.13.x / 10.92.89.8 | adcu_park_v1 | 全部命中 eth1.6；PVM 出向 eth1.6 |
| SVC-005 | SVC-005 | GVM `ip route get` mark 0x10067 + PVM table 107 | ota_route_v1 | NetId(OTA)→eth1.7；PVM table 107 完整 |
| SVC-006 | SVC-006 | GVM `ip route get` mark 0x10064 + PVM table 108 | adas_route_v1 | NetId(ADAS)→eth1.8；PVM table 108 完整 |
| SVC-007 | SVC-007 | PVM `ss -lunp/ -ltnp` + 进程匹配 someipd | someip_listening_v1 | 7 实例均 LISTEN；GVM 不应见这些 IP；进程级建模（G20） |
| SVC-008 | SVC-008 | PVM `eth0.15` link/IP + `ip neigh show` 172.16.115.98 + Camera Server 进程 | rtsp_input_v1 | eth0.15 UP + IP；ADCU 邻居 REACHABLE/PERMANENT；Camera Server pid 存在；端口 553/RTSP 流量可见 |
| SVC-009 | SVC-009 | PVM `eth0.19` + `ss -lunp` + 邻居 | someip_bigdata_v1 | eth0.19 UP；ADCU 172.16.119.98 邻居正常 |
| SVC-010 | SVC-010 | PVM `vmtap0`/`amblightserver` + 中间件进程 | host_guest_mw_v1 | vmtap0 OK + amblightserver `10.10.200.1:55498` LISTEN；中间件进程缺失 → BLOCKED-L1_env / INFO |
| SVC-011 | SVC-011 | DNS probe（见 §12.2.2）+ GVM dumpsys default DNS | dns_chain_v1 | DNS server 非空 + 经 VLAN3 可达；DNS query 成功 |
| SVC-012 | SVC-012 | PVM `ping -I eth1.3 -c3 172.16.103.20`（ICMP probe） | tbox_gateway_v1 | TBOX 网关可达 |

### 6.8 服务/端口（5 项）

| ID | 需求 ID | 数据源 | parser | expect |
|---|---|---|---|---|
| PORT-001 | PORT-001 | PVM `ss -ltnp ; ss -lunp` | ss_listing_v1 | 列出全部 + 对比基线 |
| PORT-002 | PORT-002 | GVM `ss -ltnp ; ss -lunp` | ss_listing_v1 | 同上 + 标记是否经 DNAT 暴露 |
| PORT-003 | PORT-003 | GVM `ss -ltnp` + 服务基线 | bind_address_v1 | DoIP/VLM/gftpd 必须绑 `10.10.104.40`；非此 → FAIL |
| PORT-004 | PORT-004 | 服务基线 `security_sensitive_bind_any` | unexpected_listen_v1 | 列出实测发现的 0.0.0.0 监听；按 prod_action 决定 WARN/INFO |
| PORT-005 | PORT-005 | DNAT 解析 + PVM 服务基线 | pvm_only_no_dnat_v1 | SOME/IP/Camera/VLAN15-19 绝不能出现 DNAT 到 GVM；出现→FAIL |

### 6.9 性能（6 项，重点闭环 PERF-003/004/005/006）

| ID | 需求 ID | 数据源 | parser | expect | 备注 |
|---|---|---|---|---|---|
| PERF-001 | PERF-001 | ICMP probe（含 PMTU，G2） | probe_loss_v1 | 丢包 ≤1% PASS；>1% WARN；>5% FAIL | 各 SHU 配阈值 |
| PERF-002 | PERF-002 | ICMP probe + RttBurstProbe（G3） | probe_rtt_jitter_v1 | RTT P95 + 抖动；阈值按 SHU | — |
| **PERF-003** | **PERF-003**（新闭环） | `cat /proc/net/dev` 两次采样 60s 间隔 | throughput_window_v1 | 计算 RX/TX bytes_per_sec 与 packets_per_sec；超过 baseline 5x 上报 INFO（业务突发监测） | **算法规范见 §6.9.1** |
| **PERF-004** | **PERF-004**（新闭环） | `cat /proc/softirqs` + `/proc/stat` cpu0..N 行 | softirq_v1 | 网络 softirq 占 cpu 时间 >10% WARN，>30% FAIL；ksoftirqd RSS/CPU 异常 → WARN | **算法规范见 §6.9.2** |
| **PERF-005** | **PERF-005**（新闭环） | `ip -d link show` MTU 字段全量比对 | mtu_consistency_v1 | PVM phys/vlan/vmtap + GVM eth/vlan 全部 MTU 跟 baseline 一致 | baseline 已加 mtu 字段 |
| **PERF-006** | **PERF-006**（新闭环） | 短时 tcpdump 5s + 内核 multicast 计数 | broadcast_storm_v1 | ARP/mDNS pps >100 WARN；SOME/IP SD pps >500 WARN | **算法规范见 §6.9.3** |

#### 6.9.1 PERF-003 吞吐计算算法

```
两次采样 t1 / t2 间隔 W = 60s（轻量巡检窗口）
对每个接口 i：
  rx_bps = (rx_bytes[t2] - rx_bytes[t1]) * 8 / W
  tx_bps = (tx_bytes[t2] - tx_bytes[t1]) * 8 / W
  rx_pps = (rx_packets[t2] - rx_packets[t1]) / W
  tx_pps = (tx_packets[t2] - tx_packets[t1]) / W

输出：每接口 max_rx_bps_24h, current_rx_bps；当 current > 5×daily_avg → INFO
```

#### 6.9.2 PERF-004 softirq 监测算法

```
读 /proc/stat 行 "softirq" 每 60s 采样，计算 NET_RX/NET_TX 周期增量
读 /proc/softirqs：CPU 列分布
读 /proc/[pid]/stat for ksoftirqd/N：utime+stime 增量

判定：
  net_softirq_pct = (delta_NET_RX + delta_NET_TX) / total_softirq_delta
  net_softirq_pct > 10% WARN, >30% FAIL
  ksoftirqd[N] CPU% > 50% sustained 60s → WARN
```

#### 6.9.3 PERF-006 广播/组播风暴检测

```
tcpdump 5s on eth1.3,eth1.4,eth1.{10..14}：捕获 broadcast + multicast，统计 pps
ARP pps > 100 / iface 持续 5s → WARN
mDNS (UDP/5353) pps > 50 / iface → WARN
SOME/IP SD (UDP/30490) pps > 500 / iface → WARN
```

> tcpdump 仅在异常被怀疑时主动触发，不做常态巡检（性能预算）。

### 6.10 安全（6 项）

| ID | 需求 ID | 数据源 | parser | expect |
|---|---|---|---|---|
| SEC-001 | SEC-001 | NAT 规则解析 + GVM `ss -ltnp` | gvm_exposure_list_v1 | 列出经 DNAT 可达的 GVM 端口清单 |
| SEC-002 | SEC-002 | PVM `ss -ltnp ; ss -lunp` | pvm_exposure_list_v1 | 列出 0.0.0.0 + 172.16.* 监听清单 |
| SEC-003 | SEC-003 | GVM `ip addr` + DNAT 规则解析 | pvm_only_isolation_v2 | 与 VM-005 互补：检查 PVM-only VLAN 不在 GVM 出现，也不在 DNAT |
| SEC-004 | SEC-004 | DNAT 解析 + PVM `ss -ltnp` | idps_full_check_v1 | TCP/30006 PREROUTING 例外存在；PVM 该端口 LISTEN 有 |
| SEC-005 | SEC-005 | filter 默认策略 | forward_default_drop_v1 | `-P FORWARD ACCEPT` → WARN，建议 DROP+白名单 |
| SEC-006 | SEC-006 | 与上一次扫描的 ss 输出 diff | listen_port_diff_v1 | 新增 + 监听地址扩大 + 进程变更 → WARN |

### 6.11 基线（5 项）

| ID | 需求 ID | 数据源 | parser | expect |
|---|---|---|---|---|
| BASE-001 | BASE-001 | 内置 baseline JSON | baseline_load | 加载 + schema 校验通过 |
| BASE-002 | BASE-002 | 全集 collector 输出 vs baseline | full_diff_v1 | 应用 diff_policy 后输出差异列表 |
| **BASE-003** | **BASE-003**（新闭环） | diff_policy 字段映射 | diff_policy_apply | ignore→不报；warn_if_changed→WARN；fail_if_changed→FAIL；fail_if_missing→FAIL |
| BASE-004 | BASE-004 | 配置元信息 | config_meta | 报告含 baseline_version/config_version/platform/ts_unix |
| BASE-005 | BASE-005 | 与 VM-005 / SEC-003 联合 | pvm_only_strict_isolation | 任一 VLAN 10-14/15/19 在 GVM 可见或被 DNAT → FAIL |

### 6.12 检查项配置完整示例（L4-NAT-001）

```jsonc
{
  "id":              "L4-NAT-001",
  "req_ids":         ["NET-DIAG-NAT-001"],
  "title":           "PVM DNAT 规则完整性 + VLAN 4 IDPS 例外顺序",
  "layer":           "L4",
  "side":            "PVM",
  "enable":          true,
  "severity":        "FAIL",
  "blocked_severity":"L2_anomaly",
  "event_id_on_fail":"0x4E5E0005",
  "shu_impact":      ["SHU_VLAN3_INTERNET","SHU_VLAN4_DOIP","SHU_VLAN6_ADCU_PARK","SHU_VLAN7_OTA","SHU_VLAN8_ADAS"],
  "data_source": {
    "type":     "abstracted",          // G8: 通过 NetfilterCollector 抽象
    "method":   "list_nat_rules",
    "fallback": "list_nft_ruleset",
    "timeout_sec": 5,
    "max_output_kb": 128
  },
  "parser":          "nat_rules_v1",
  "expect": {
    "must_contain": [
      "PREROUTING -d 172.16.103.40/32 -i eth1.3 -j DNAT --to-destination 10.10.103.40",
      "PREROUTING -d 172.16.104.40/32 -i eth1.4 -p tcp -m tcp ! --dport 30006 -j DNAT --to-destination 10.10.104.40",
      "PREROUTING -d 172.16.104.40/32 -i eth1.4 ! -p tcp -j DNAT --to-destination 10.10.104.40",
      "PREROUTING -d 172.16.106.40/32 -i eth1.6 -j DNAT --to-destination 10.10.106.40",
      "PREROUTING -d 172.16.107.40/32 -i eth1.7 -j DNAT --to-destination 10.10.107.40",
      "PREROUTING -d 172.16.108.40/32 -i eth1.8 -j DNAT --to-destination 10.10.108.40"
    ],
    "rule_order": [
      {"chain":"PREROUTING",
       "before":"172.16.104.40/32 -i eth1.4 -p tcp -m tcp ! --dport 30006",
       "after":"172.16.104.40/32 -i eth1.4 ! -p tcp"}
    ]
  },
  "evidence_files":  ["pvm/iptables_nat_S.txt","pvm/iptables_nat_Lnv.txt"],
  "suggestion":      "恢复缺失的 VLAN X DNAT 规则；TCP/30006 例外规则必须在非 TCP 规则之前。",
  "recheck_cmd":     "iptables -t nat -L -nv ; tcpdump -ni eth1.4 -c 50",
  "perf_budget": {
    "cpu_ms_p95": 60,
    "io_kb": 4,
    "skip_when_conntrack_pct_above": 90
  }
}
```

---

## 7. SHU（Service Health Unit）详细设计

### 7.1 SHU 完整定义

下表以 `SHU_VLAN3_INTERNET` 为例，其它 8 个 SHU 用同一 schema。

```jsonc
{
  "id":         "SHU_VLAN3_INTERNET",
  "name":       "默认互联网通道",
  "priority":   "P0",
  "always_on":  true,
  "consumers":  ["com.mega.map","cockpit.qqmusic","all_default_netid_apps","TBOX_uplink"],
  "deps": {
    "checks": [
      "L1-LINK-001","L2-VLAN-001","L2-VLAN-007",
      "L3-IP-001","L3-IP-003","L3-IP-004","L3-ROUTE-001","L3-ROUTE-006",
      "L4-NAT-001","L4-NAT-002","L4-FW-001","L4-FW-003","L4-FW-004",
      "VM-002","VM-003","VM-007",
      "SVC-001","SVC-011","SVC-012",
      "PERF-005"
    ],
    "interfaces": ["eth1","eth1.3","vmtap1.3","GVM:eth1.3"],
    "kernel":     ["ip_forward","conf.eth1.3.forwarding","conf.vmtap1.3.forwarding"],
    "iptables":   ["NAT_VLAN3","FORWARD_VLAN3"],
    "neighbor":   ["172.16.103.20"]
  },
  "probes": [
    {"id":"icmp_tbox","type":"icmp","iface":"eth1.3","target":"172.16.103.20",
     "interval_sec":30, "count":3, "loss_warn_pct":1, "loss_fail_pct":5,
     "rtt_warn_ms":50, "rtt_fail_ms":100, "burst_on_alert":{"interval_sec":1,"count":5}},
    {"id":"icmp_tbox_pmtu","type":"icmp_pmtu","iface":"eth1.3","target":"172.16.103.20",
     "interval_sec":300, "size_bytes":1472, "df":true},
    {"id":"icmp_uplink","type":"icmp","iface":"eth1.3","target":"<sku_uplink_target>",
     "interval_sec":120, "count":3},
    {"id":"dns_uplink","type":"dns","via":"VLAN3","target":"<sku_dns_test_domain>",
     "interval_sec":60, "timeout_sec":3},
    {"id":"icmp_gvm_perspective","type":"icmp_gvm_perspective","iface":"vmtap1.3",
     "src_ip":"10.10.103.40","target":"172.16.103.20","interval_sec":300, "count":3,
     "_note":"G1：模拟 GVM 视角真实路径，发现 PVM 自身 probe 通但 NAT 段不通"}
  ],
  "rtt_burst": {
    "on_alert_only":  true,
    "interval_sec":   1,
    "count":          30,
    "metric":         ["p50","p95","p99","jitter"]
  },
  "intermittent_detection": {
    "enable":      true,
    "window_sec":  600,
    "fail_pct_threshold": 2.0,
    "_note":"G3：60s probe 之间 jitter 抖动持续 600s 内累计丢包 ≥2% 即 WARN"
  },
  "sla": {
    "icmp_loss_warn_pct": 1, "icmp_loss_fail_pct": 5,
    "icmp_rtt_warn_ms": 50, "icmp_rtt_fail_ms": 100,
    "pmtu_size_bytes": 1472,
    "dns_fail_threshold": 3,
    "any_check_fail_means": "FAIL",
    "any_check_warn_means": "WARN",
    "blocked_means": "WARN_with_blocked_hint"
  },
  "watchdog_links": [
    "RTNLGRP_LINK:eth1",
    "RTNLGRP_LINK:eth1.3",
    "RTNLGRP_IPV4_ROUTE:172.16.103.20/default",
    "INOTIFY:/proc/sys/net/ipv4/ip_forward",
    "INOTIFY:/proc/sys/net/ipv4/conf/eth1.3/forwarding"
  ]
}
```

### 7.2 9 个 SHU 总览

| SHU ID | 优先级 | always_on | 关键 probe（30s 触发） | 关键 watchdog |
|---|---|---|---|---|
| `SHU_VLAN3_INTERNET` | P0 | true | TBOX 网关 ICMP 30s + DNS 60s | eth1/.3 link, ip_forward, conf forwarding |
| `SHU_DNS` | P0 | true | DNS query 60s（SHU 独立 probe） | resolv.conf 变化 |
| `SHU_VLAN4_DOIP` | P0 | true（被动） | DoIP 端口可达性（按需） | iptables NAT VLAN4 规则 |
| `SHU_VLAN6_ADCU_PARK` | P0 | post-boot | ADCU 网关 ICMP 60s | eth1.6 + table 106 |
| `SHU_VLAN7_OTA` | P1 | true | OTA 网关 ICMP 60s | eth1.7 + table 107 |
| `SHU_VLAN8_ADAS` | P1 | true | ADAS 网关 ICMP 60s | eth1.8 + table 108 |
| `SHU_HOST_GUEST` | P0 | true | vmtap0 ↔ GVM eth0 ICMP 30s + 协议层 echo（G11） | vmtap0 + qcrosvm |
| `SHU_VLAN15_RTSP` | P0 | post-boot | ADCU 173.16.115.98 ICMP 60s | eth0.15 + Camera Server |
| `SHU_SOMEIP_BUS` | P0 | true | 组播流量计数 60s | someipd 进程 + multicast counters |

### 7.3 SHU 健康聚合规则（修正版）

```
INPUTS:
  check_results: [PASS|INFO|WARN|FAIL|BLOCKED] for each dep check
  probe_status:  rolling window verdict per probe id
  watchdog_signal_state: triggered or not in last trigger_min_gap_sec

VERDICT:
  if any check FAIL OR any probe FAIL OR (P0 watchdog signal triggered): SHU = FAIL
  elif any check WARN OR any probe WARN OR intermittent_detection hit: SHU = WARN
  elif any check BLOCKED with severity=L2_anomaly: SHU = WARN_blocked_hint
  elif any check BLOCKED with severity=L1_env: SHU = PASS (BLOCKED_L1 视为环境性，不降级)
  else: SHU = PASS
```

> 核心原则：BLOCKED-L1（环境性）不降级 SHU；BLOCKED-L2（异常）必须降级。这正是 G15 要求的分级。

---

## 8. 事件与因果聚合设计（修正 review F3 + G7）

### 8.1 事件 ID 段位（占位，待 polaris 团队最终分配）

| 事件 | ID | 严重度 |
|---|---|---|
| `NETDIAG_BASELINE_DRIFT` | `0x4E5E0001` | WARN/FAIL |
| `NETDIAG_LINK_DOWN` | `0x4E5E0002` | FAIL |
| `NETDIAG_LINK_FLAPPING` | `0x4E5E0003` | FAIL |
| `NETDIAG_VLAN_MISSING` | `0x4E5E0004` | FAIL |
| `NETDIAG_NAT_RULE_DRIFT` | `0x4E5E0005` | FAIL |
| `NETDIAG_FORWARD_DISABLED` | `0x4E5E0006` | FAIL |
| `NETDIAG_CONNTRACK_PRESSURE` | `0x4E5E0007` | WARN/FAIL |
| `NETDIAG_GATEWAY_UNREACHABLE` | `0x4E5E0008` | FAIL |
| `NETDIAG_VM_LINK_BROKEN` | `0x4E5E0009` | FAIL |
| `NETDIAG_HYPERVISOR_DOWN` | `0x4E5E000A` | FAIL |
| `NETDIAG_SERVICE_DOWN` | `0x4E5E000B` | FAIL |
| `NETDIAG_EXPOSURE_RISK` | `0x4E5E000C` | WARN |
| `NETDIAG_DNS_FAILURE` | `0x4E5E000D` | FAIL |
| `NETDIAG_PMTU_BLACKHOLE` | `0x4E5E000E` | FAIL |
| `NETDIAG_TIME_SKEW` | `0x4E5E000F` | WARN |
| `NETDIAG_SCAN_REPORT` | `0x4E5E00F0` | INFO |
| `NETDIAG_APP_NETWORK_TROUBLE` | `0x4E5E00F1` | INFO + verdict |
| `NETDIAG_INCIDENT_DERIVED` | `0x4E5E00FE` | 派生事件占位（不上云） |

### 8.2 事件 payload schema（C7 时钟字段 + G7 因果链 + G18 敏感性）

```jsonc
{
  "schema_version":   "1.0",
  "event":            "NETDIAG_GATEWAY_UNREACHABLE",
  "event_id":         "0x4E5E0008",
  "side":             "PVM",
  "layer":            "L3",
  "severity":         "FAIL",
  "shu":              "SHU_VLAN3_INTERNET",
  "vlan":             [3],
  "scenario":         "A-Internet",
  "rule_id":          "NET-DIAG-SVC-012",
  "check_id":         "L3-IP-001",          // 触发本事件的主 check（可空）

  // C7 时钟字段
  "ts_unix":          1747764000,            // wall-clock，云端展示用
  "ts_boot":          18234567,              // CLOCK_BOOTTIME ms，本机排序用
  "boot_id":          "f0b8c3a5-...",        // /proc/sys/kernel/random/boot_id
  "config_version":   "v1.0-2026-05-09",
  "baseline_version": "v1.0-2026-05-09",
  "diag_version":     "1.0.0",

  // G7 因果链
  "incident_id":      "incident_20260509_153012_SHUVLAN3GW",
  "is_root":          true,                  // 是根事件
  "caused_by":        null,                   // 若是派生事件，填 root incident_id
  "derived_events":   [                       // 根事件携带派生事件清单
    {"event":"NETDIAG_BASELINE_DRIFT","when":"+0.1s","brief":"default route disappeared"},
    {"event":"NETDIAG_VM_LINK_BROKEN","when":"+0.3s","shu":"SHU_HOST_GUEST"}
  ],

  // 证据
  "evidence_summary": "PVM ping -I eth1.3 172.16.103.20: 5/5 lost; ARP state FAILED for 180s",
  "incident_dir":     "/log/perf/network_diag/incidents/incident_xxx",

  // G4 数据质量
  "data_quality": {
    "pvm_collect_complete":  true,
    "gvm_collect_complete":  false,
    "gvm_collect_reason":    "vsock_9101_disconnected",
    "dumpsys_state":         "ok | timeout | unparseable | unavailable"
  },

  // G18 敏感性
  "sensitivity_max":      "med",            // low/med/high；云端按权限拉取
  "redacted_fields":      ["mac_last_octets","conntrack_peer_ip"],

  // 应用感知补充（路径④用，其它路径为 null）
  "app_verdict":          null,             // network_layer_healthy/degraded/failed
  "app_root_cause":       null,
  "app_package":          null
}
```

### 8.3 事件因果聚合规则

#### 8.3.1 聚合窗口

```
incident_window_sec = 30  （默认）
```

30s 内同一聚合键触发的所有事件归并为一个 incident，发出根事件 + 派生事件清单（不发派生事件本体）。

#### 8.3.2 聚合键计算

按事件类型分组：

| 根事件 | 聚合键（决定派生事件归属） |
|---|---|
| `NETDIAG_LINK_DOWN(iface=eth1)` | `link_down:eth1` —— 同窗口内所有 `eth1` 子接口/影响 VLAN 事件归此根 |
| `NETDIAG_HYPERVISOR_DOWN` | `hypervisor` —— 30s 内所有 vmtap/Host-Guest/SHU FAIL 归此根（最高优先级根） |
| `NETDIAG_GATEWAY_UNREACHABLE(VLAN3)` | `gateway:VLAN3` —— 同 VLAN 内 SHU/SVC 事件 |
| `NETDIAG_CONNTRACK_PRESSURE` | `conntrack` |
| `NETDIAG_NAT_RULE_DRIFT` | `nat_rules` |
| `NETDIAG_DNS_FAILURE` | `dns` |
| `NETDIAG_VM_LINK_BROKEN(vmtap1.X)` | `vm_link:vmtap1.X` |

#### 8.3.3 派生事件优先级表

```
rank 0 (highest) = HYPERVISOR_DOWN
rank 1           = LINK_DOWN(eth0/eth1)
rank 2           = VLAN_MISSING / VM_LINK_BROKEN(vmtap1)
rank 3           = NAT_RULE_DRIFT / FORWARD_DISABLED
rank 4           = GATEWAY_UNREACHABLE / CONNTRACK_PRESSURE
rank 5           = SERVICE_DOWN / DNS_FAILURE / PMTU_BLACKHOLE
rank 6           = BASELINE_DRIFT / EXPOSURE_RISK
rank 7 (lowest)  = SCAN_REPORT / APP_NETWORK_TROUBLE
```

聚合时：rank 数字越小越是根事件，rank 大的事件如 30s 内已出现 rank 小的且聚合键关联，则降级为派生事件。

#### 8.3.4 IncidentDeduper 状态机

```
EventBus 收到 raw event E:
  key = compute_aggregation_key(E)
  now = CLOCK_BOOTTIME

  if 存在 active incident I 且 I.key == key 且 (now - I.first_seen) < 30s:
    将 E 加入 I.derived_events
    if E.rank < I.root.rank:
      promote I.root 为 derived，E 提升为新 root
    return  # 不发 polaris 事件

  else:
    创建新 incident I'，root = E
    schedule_flush(I', after = min(deadline, 5s))
    return

flush(I):
  组装 root event payload（含 derived_events 列表）
  写 incident_dir
  polaris_report_raw(root.event_id, json_body, incident_dir)

trigger_min_gap_sec=30 单 SHU 内同一根事件 30s 内只发一次
```

#### 8.3.5 聚合示例

```
T+0.0s : eth1 carrier DOWN              → root event NETDIAG_LINK_DOWN(eth1), key=link_down:eth1
T+0.1s : default route deleted          → derived NETDIAG_BASELINE_DRIFT, 同 key
T+0.3s : ping VLAN3 TBOX FAIL           → derived NETDIAG_GATEWAY_UNREACHABLE(VLAN3), 同 key
T+0.5s : ping VLAN6 ADCU FAIL           → derived NETDIAG_GATEWAY_UNREACHABLE(VLAN6), 同 key
T+1.2s : SHU_VLAN3 marked FAIL          → derived
T+5s   : flush incident → polaris commit:
  根事件 = NETDIAG_LINK_DOWN(eth1)
  derived_events = 4 entries

云端最终看到：1 条事件，含 4 条派生事件清单。

polaris 队列占用：1 条。
```

不开聚合时同事件会产生 5+ 条；按容量 500 估算，10 次类似抖动就把 polaris `mOfflineCache` 打爆。

### 8.4 incident_id 格式与去重

```
incident_id = "incident_<YYYYmmdd>_<HHMMSS>_<root_event_short>_<key_hash>"
example      = "incident_20260509_153012_LINKDOWN_a3f"
```

- root_event_short：去掉 NETDIAG_ 前缀（如 `LINKDOWN`）
- key_hash：聚合键的 MurmurHash3 前 12 bit hex

去重保证：同 incident_id 在 PVM 端 retention 期内唯一，云端按 incident_id 关联多次上报。

### 8.5 路径 ④（App 主动报障）的特殊处理

`NETDIAG_APP_NETWORK_TROUBLE` 收到时：

1. 立即查找该 App `via_netid` 对应的 SHU
2. 触发该 SHU 的全量 check + probe burst（5 包/1s）
3. 5s 后聚合结果：
   - SHU 全 PASS → `app_verdict = network_layer_healthy`
   - SHU WARN → `app_verdict = network_layer_degraded`
   - SHU FAIL → `app_verdict = network_layer_failed`，附 root_cause
4. 用 `NETDIAG_APP_NETWORK_TROUBLE` 作为根事件出云（含 verdict + root_cause）
5. 同窗口内若 SHU 已有独立 incident，二者合并：App 事件作为派生，SHU FAIL 作为根

---

## 9. Watchdog 详细设计

### 9.1 PVM Watchdog 信号源（修正 G19 IP 漂移 + G14 sd-journal）

| 信号 ID | 数据源 | 实现 API | 检测延迟（P95） | 触发事件 |
|---|---|---|---|---|
| `WD_PVM_LINK` | netlink `RTNLGRP_LINK` | `socket(AF_NETLINK, NETLINK_ROUTE)` + `bind` group `RTNLGRP_LINK` | 1s | `NETDIAG_LINK_DOWN` / `NETDIAG_LINK_FLAPPING` |
| `WD_PVM_IPADDR` | netlink `RTNLGRP_IPV4_IFADDR`（**G19 新增**） | 同上 + `RTNLGRP_IPV4_IFADDR` | 1s | `NETDIAG_BASELINE_DRIFT(ip)` |
| `WD_PVM_ROUTE` | netlink `RTNLGRP_IPV4_ROUTE` | 同上 + `RTNLGRP_IPV4_ROUTE` | 1s | `NETDIAG_BASELINE_DRIFT(route)` |
| `WD_PVM_NEIGH` | netlink `RTNLGRP_NEIGH` | 同上 + `RTNLGRP_NEIGH`，监听关键网关条目 | 1s | `NETDIAG_GATEWAY_UNREACHABLE` |
| `WD_PVM_VMTAP_OPER` | inotify `/sys/class/net/vmtap1.X/operstate` | `inotify_add_watch` IN_MODIFY | 1s | `NETDIAG_VM_LINK_BROKEN` |
| `WD_PVM_FORWARDING` | inotify `/proc/sys/net/ipv4/ip_forward` + per-iface | `inotify_add_watch` IN_MODIFY | 1s | `NETDIAG_FORWARD_DISABLED` |
| `WD_PVM_CONNTRACK_PCT` | poll `/proc/sys/net/netfilter/nf_conntrack_count` | 10s timer | 10s | `NETDIAG_CONNTRACK_PRESSURE` |
| `WD_PVM_CONNTRACK_FULL` | sd-journal `nf_conntrack: table full`（**G14 不用 dmesg \| grep**） | `sd_journal_open` + `sd_journal_add_match _TRANSPORT=kernel` + match 字符串 | 3s | `NETDIAG_CONNTRACK_PRESSURE(FAIL)` |
| `WD_PVM_HYPERVISOR` | poll `kill(qcrosvm_pid, 0)` | 5s timer | 5s | `NETDIAG_HYPERVISOR_DOWN` |
| `WD_PVM_SERVICE` | sd-bus `org.freedesktop.systemd1.Unit.PropertiesChanged` | dbus signal | 3s | `NETDIAG_SERVICE_DOWN` |
| `WD_PVM_NAT_RULES` | timer 30s（**降到 30s 保 SLA**） | `iptables -S` 哈希对比 / 或 nft monitor | 30s | `NETDIAG_NAT_RULE_DRIFT` |
| `WD_PVM_VMTAP_UNI` | poll `/proc/net/dev` 增量 + 协议层 echo | 20s 窗 + echo 验证（G11） | 20-25s | `NETDIAG_VM_LINK_BROKEN` |

### 9.2 GVM Watchdog 信号源（G9 ConnectivityService callback 实现）

| 信号 ID | 数据源 | 实现 API | 延迟 | 动作 |
|---|---|---|---|---|
| `WD_GVM_LINK` | netlink `RTNLGRP_LINK` | 同 PVM | 1s | push gvm_alert |
| `WD_GVM_IPADDR` | netlink `RTNLGRP_IPV4_IFADDR` | 同上 | 1s | push gvm_alert |
| `WD_GVM_NEIGH` | netlink `RTNLGRP_NEIGH` | 同上 | 1s | push gvm_alert |
| `WD_GVM_CONNECTIVITY` | ConnectivityService callback（见 9.2.1） | 见 9.2.1 | 1-3s 或 60s 降级 | push snapshot brief |
| `WD_GVM_NETD` | poll `kill(netd_pid, 0)` | 5s timer | 5s | push gvm_alert |
| `WD_GVM_RESOLVER` | DNS probe + resolver state | 60s 巡检 | 60s | push gvm_alert |
| `WD_GVM_VIRTIO_STUCK` | `/proc/net/dev` 增量为 0 + carrier=1 | 20s 窗 | 20-25s | push gvm_alert |

#### 9.2.1 ConnectivityService callback 实现路径（G9 决策）

三选项工程评估：

| 方案 | 代价 | 实时性 | 可量产 | 推荐度 |
|---|---|---|---|---|
| (a) PolarisAgent JNI 中转 | PolarisAgent 加 callback 注册接口 + IPC 转发到 native_diag | 1-3s | ✅ | **v1 选** |
| (b) 直 binder 调 IConnectivityManager | sepolicy 复杂、需要 system_server 等同权限 | <1s | ⚠️ user 镜像可能受限 | v2 评估 |
| (c) 60s `dumpsys connectivity` poll | 简单但延迟大 | 60s | ✅ | **fallback 兜底** |

v1 实现：默认 (a)，PolarisAgent 提供 Java API → JNI → native_diag 通过 polaris event 接收。失败降级到 (c)。

```java
// PolarisAgent 侧（伪代码）
class NetworkDiagBridge {
    void registerCallback() {
        ConnectivityManager cm = ...;
        cm.registerDefaultNetworkCallback(new NetworkCallback() {
            public void onAvailable(Network n) {
                pushToDiag(new SnapshotBrief("AVAILABLE", n));
            }
            public void onLost(Network n) {
                pushToDiag(new SnapshotBrief("LOST", n));
            }
            public void onCapabilitiesChanged(Network n, NetworkCapabilities c) { ... }
            public void onLinkPropertiesChanged(Network n, LinkProperties lp) { ... }
        });
    }
    void pushToDiag(SnapshotBrief b) {
        // 走 polaris event 链或 binder 调 native_diag
    }
}
```

### 9.3 信号触发动作矩阵（修正 review §3.3 第 2 条）

| Watchdog 信号 | 立即采集 sections | 触发 probe burst | 抓包 | 取证目录字段 |
|---|---|---|---|---|
| `WD_PVM_LINK(eth1 down)` | `addr,link,route,rule,neigh,carrier_changes` | — | — | `pvm/{ip,sysctl}_*.txt` |
| `WD_PVM_LINK(eth0 down)` | 同上 + `eth0` 业务相关 | — | — | 同上 |
| `WD_PVM_VMTAP_OPER(down)` | `addr,link,proc_net_dev`，PVM 自 ping vmtap0 | — | — | 含 `qcrosvm` 状态 |
| `WD_PVM_FORWARDING(=0)` | `sysctl_net,addr,route` | 当前 SHU 全 burst | — | sysctl 全量 |
| `WD_PVM_CONNTRACK_FULL` | `conntrack_count`,`dmesg_conntrack`,`ss` | — | 5s tcpdump on eth1 | 全量 NF 状态 |
| `WD_PVM_CONNTRACK_PCT(>=80%)` | `conntrack_count`,`iptables_nat_S`（不含 -L -nv） | — | — | 含 `nf_conntrack_max,buckets,timeout` |
| `WD_PVM_NEIGH(GATEWAY FAILED)` | `neigh,addr,route,rule,iptables_nat` | 该 SHU 加紧 5×1s | 30s tcpdump 关注网关 | 含 ARP 历史 |
| `WD_PVM_NAT_RULES(diff)` | `iptables_nat_S,iptables_filter` | — | — | 哈希前后两版 |
| `WD_PVM_HYPERVISOR(qcrosvm gone)` | 全量 PVM 视角 | — | — | 含 qcrosvm 启动参数（如可读） |
| `WD_PVM_SERVICE(xdja_idps fail)` | `ss`,`systemctl status xdja_idps`,`journalctl -u xdja_idps -n 100` | — | — | service log 节选 |
| `WD_PVM_VMTAP_UNI(eth1.3 unidirectional)` | + 协议层 echo 验证（G11） | 该 SHU burst | 5s tcpdump | 增量统计表 |

### 9.4 IP 漂移监测（G19 修正）

`WD_PVM_IPADDR` 监听 `RTNLGRP_IPV4_IFADDR` 事件。

```c
struct nlmsghdr {
    .nlmsg_type = RTM_NEWADDR | RTM_DELADDR
}
struct ifaddrmsg {
    ifa_family, ifa_index, ifa_prefixlen
}
// 解析 IFA_ADDRESS / IFA_LOCAL，与 baseline 对比
```

变化判定：

- 关键 iface（baseline 列出的）IP 删除/新增 → `NETDIAG_BASELINE_DRIFT(ip,iface)`
- placeholder iface（dummy0/ifb*）变化 → 忽略
- vmtap 新增 IP → INFO

---

## 10. Probe 详细设计

### 10.1 ProbeScheduler 架构

```
┌──────────────┐
│ TimerWheel   │ tick=1s, slots=3600
└──────┬───────┘
       │
       ▼
┌──────────────────┐
│ Coalesce 引擎    │ 同 SHU 多 probe 合并，避免 short-window 内连发
└──────┬───────────┘
       │
       ▼
┌──────────────────┐         ┌────────────────────┐
│ Token Bucket     │── pps ──│ probe_max_pps=100  │
│ (per-type)       │         └────────────────────┘
└──────┬───────────┘
       │
       ▼
┌────────────────────────────────────────┐
│ ProbeWorker pool（4 workers）         │
│  - IcmpProbe / DnsProbe / ...          │
│  - 各 probe 独立超时 / cancellation     │
└──────────┬─────────────────────────────┘
           │
           ▼
┌──────────────────┐
│ ProbeRecorder    │ JSONL append-only
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ EvalDecider      │ 命中 SLA → 触发 alert（→ EventBus → IncidentDeduper）
└──────────────────┘
```

### 10.2 Probe 类型详细规范

#### 10.2.1 ICMP Probe（基础）

```c
int IcmpProbe::run(const Target& t) {
    int s = socket(AF_INET, SOCK_DGRAM, IPPROTO_ICMP);  // 优先非 raw socket
    setsockopt(s, SOL_SOCKET, SO_BINDTODEVICE, t.iface);
    setsockopt(s, SOL_SOCKET, SO_RCVTIMEO, &timeout);
    
    for (i = 0; i < count; i++) {
        send icmp_echo, payload size = t.size_bytes (default 64)
        wait recv with timeout
        record rtt
    }
    return loss_pct, rtt_p50/p95/p99
}
```

约束：

- 默认 size=64
- 默认 count=3，间隔 200ms
- 单次预算：`count * (rtt_max + recv_timeout) ≤ 1.5s`
- raw socket fallback：若 SOCK_DGRAM 不允许（perm/ICMP echo group 不在 net.ipv4.ping_group_range），降级 raw socket（要求 CAP_NET_RAW）

#### 10.2.2 ICMP PMTU Probe（G2 新增）

```c
int IcmpPmtuProbe::run(const Target& t) {
    int s = socket(AF_INET, SOCK_DGRAM, IPPROTO_ICMP);
    setsockopt(s, IPPROTO_IP, IP_MTU_DISCOVER, IP_PMTUDISC_DO);  // DF=1
    
    // 发送大包：default size=1472（1500 MTU - 20 IP - 8 ICMP）
    send icmp_echo with payload 1472
    if (recv timeout) → likely PMTU blackhole → 进一步 binary search
    if (recv ICMP "frag needed" but DF set) → PMTU mismatch confirmed
    
    return mtu_observed
}
```

事件：MTU 1472 不通 但 64 通 → `NETDIAG_PMTU_BLACKHOLE`

#### 10.2.3 DNS Probe

```c
int DnsProbe::run(const Target& t) {
    // 不使用系统 resolver，避免 nscd / netd 缓存掩盖问题
    // 直接构造 DNS 报文 send to t.target_dns_server (或经 VLAN 路由查找)
    
    construct DNS query for t.target_domain (random subdomain to avoid cache)
    send UDP/53
    wait response within timeout_sec=3
    
    return (rtt, resolved_ips, status)
}
```

#### 10.2.4 GVM Perspective Probe（G1 新增）

PVM 端模拟 GVM 视角：从 vmtap1.X 内侧发包，源 IP 设为 GVM 的 IP（10.10.X.40），让数据包真实经过 NAT 链路。

```c
int GvmPerspectiveProbe::run(const Target& t) {
    // 构造 raw IP 包，src=10.10.103.40, dst=172.16.103.20
    // 发到 vmtap1.3 内侧，让 PVM 内核协议栈把它当作 GVM 来的包
    // 经过 PREROUTING (no DNAT match), routing (eth1.3), POSTROUTING SNAT (172.16.103.40)
    // 出 eth1.3
    
    // 实现：
    // - raw socket(AF_INET, SOCK_RAW, IPPROTO_ICMP)
    // - bind 到 vmtap1.X
    // - 手动构造 ICMP echo with src/dst
    // - 监听 ICMP echo reply
    
    // 替代方案：用 nfqueue 注入到 vmtap1.X 入口（更复杂）
    
    return rtt or timeout
}
```

如果 PVM 自身 ICMP probe PASS 但 GvmPerspective probe FAIL → 故障在 NAT/forwarding 段，不在物理链路。这是关键的差分诊断。

#### 10.2.5 RTT Burst Probe（G3 间歇故障）

仅在 SHU alert 时触发，不做常态：

```c
int RttBurstProbe::run(const Target& t) {
    for (i = 0; i < 30; i++) {  // 30 包 × 1s = 30s
        send icmp_echo
        record rtt
        sleep 1s
    }
    
    return {p50, p95, p99, jitter, loss_pct}
}
```

输出 `NETDIAG_GATEWAY_UNREACHABLE` 事件 payload 中作为细化证据。

### 10.3 Probe 加紧策略（G10 量化）

```
default state: 按 SHU 配置周期 (60s/300s/etc)

trigger: any single probe failure detected
 → 进入 ALERT_BURST 模式
 → 周期 1s/包，count=5
 → 5 包内 ≥3 包失败 → confirm FAIL
 → 1 包失败 → 再来一轮 5 包
 → 最多 3 轮（共 15s）
 → 仍持续失败 → final FAIL，触发 RTT Burst
 
exit ALERT_BURST: 任一成功 → 回归正常周期；3 轮全失败 → 进入 30s probe 间隔（避免占用资源），同时上报 FAIL
```

### 10.4 Probe 目标按 SKU 配置（G16）

```jsonc
"probes_dynamic_targets": {
  "SHU_VLAN3_INTERNET": {
    "sku_DEFAULT":    {"icmp_uplink":"<project_health_endpoint_ip>","dns_test":"www.example.com"},
    "sku_CN":         {"icmp_uplink":"<cn_health_endpoint>","dns_test":"www.baidu.com"},
    "sku_EU":         {"icmp_uplink":"<eu_health_endpoint>","dns_test":"www.cloudflare.com"}
  }
}
```

启动时按 `sku` 选定，运行时通过 VSOCK 9101 `dynamic_target` RPC 可热切换。

### 10.5 Probe 资源约束总表

| 项 | 限制 | 实现 |
|---|---|---|
| 单 SHU probe 频率 | ≤1 包/秒（含 burst） | TokenBucket per SHU |
| 总 probe pps | ≤100 | TokenBucket 全局 |
| DNS probe | ≤5 次/分钟 | 计数器 |
| ICMP burst | 30 包/30s 仅 SHU FAIL 时 | flag |
| HTTP probe | 关闭（v1 不启用） | flag |
| 抓包 | tcpdump_max_sec=10, max_pkts=2000 | 启动参数 |
| 目标白名单 | 严格校验 IP/host 合法性 + 不允许 cmdline 注入 | parser |

---

## 11. 采集器详细设计

### 11.1 命令并行执行（G + 性能）

```c
class CommandRunner {
    ThreadPool pool{4};
    
    Future<CommandOutput> run_async(const Command& c);
    vector<CommandOutput> run_parallel(vector<Command> cs) {
        vector<Future<...>> futures;
        for (auto& c : cs) futures.push_back(run_async(c));
        wait_all(futures, max_deadline=5s);
        return collect;
    }
};

// incident 触发时：
auto cmds = build_collect_set(incident);  // 通常 8-12 条命令
auto results = runner.run_parallel(cmds);  // 4 worker 并行
// 总时间 = max(单条) ≈ 2-3s，而非 sum ≈ 10-15s
```

### 11.2 BLOCKED 分级实现（G15）

每条命令在 capability probe 阶段标定其 blocked_severity：

```c
struct CommandSpec {
    string name, cmd;
    BlockedSeverity blocked_sev = L1_env;  // 默认环境性
};

// 启动时探测：
if (which("ethtool") fail) {
    spec_ethtool.available = false;
    spec_ethtool.blocked_sev = L1_env;  // 用户镜像本来就可能没有
}
if (test_f("/proc/net/stat/nf_conntrack") fail) {
    spec_proc_stat.available = false;
    spec_proc_stat.blocked_sev = L1_env;
}

// 运行时若曾经 PASS，突然 fail：
if (was_available && now_fail_to_run) {
    blocked_sev = L2_anomaly;  // 这才是真异常
}

// 间歇 fail（命令超时 / EINTR）：
if (timeout_or_eintr) {
    retry_once();
    if (still fail) blocked_sev = L3_intermittent;  // 重试一次再判
}
```

SHU 评分时（参 §7.3）：

- `L1_env`：SHU 不降级
- `L2_anomaly`：SHU = WARN
- `L3_intermittent`：SHU 不降级，但累计 3 次升级 L2

### 11.3 Netfilter 抽象层（G8）

```c
class NetfilterCollector {
public:
    virtual ~NetfilterCollector() = default;
    virtual vector<NatRule>    list_nat_rules() = 0;
    virtual vector<FilterRule> list_filter_rules() = 0;
    virtual NatCounters         get_nat_counters(int sample_seq) = 0;
    virtual string             dump_raw() = 0;  // 用于 incident_dir 留底
};

class IptablesAdapter : public NetfilterCollector { ... };
class NftAdapter      : public NetfilterCollector { ... };

NetfilterCollector* create() {
    if (which("nft") && nft_listing_works()) return new NftAdapter();
    if (which("iptables")) return new IptablesAdapter();
    throw NoNetfilterAvailable();
}
```

`expect.must_contain` 检查在抽象层之上做：用结构化 `NatRule { chain, in_iface, dst_ip, proto, port_match, target, target_to }` 比较而非字符串。

### 11.4 sd-journal 订阅替代 dmesg | grep（G14）

```c
class JournalReactor {
    sd_journal* j;
    
    void start() {
        sd_journal_open(&j, SD_JOURNAL_LOCAL_ONLY);
        sd_journal_add_match(j, "_TRANSPORT=kernel", 0);
        sd_journal_seek_tail(j);
        sd_journal_previous(j);  // 跳过历史
        
        // 启动独立线程
        thread([this]{ run_loop(); });
    }
    
    void run_loop() {
        while (running) {
            int r = sd_journal_wait(j, 1000000 /*1s*/);
            if (r == SD_JOURNAL_APPEND) {
                while (sd_journal_next(j) > 0) {
                    const char* msg;
                    sd_journal_get_data(j, "MESSAGE", &msg, NULL);
                    if (strstr(msg, "nf_conntrack: table full")) {
                        post_event(WD_PVM_CONNTRACK_FULL);
                    }
                    // 其他关键字：netd crash, vmtap reset, etc.
                }
            }
        }
    }
};
```

### 11.5 命令白名单（修正 sys_design §13.1，加并行标记 + perf 字段）

| Section | 命令（PVM） | 超时 | 输出上限 | 并行组 | conntrack≥80% 时 |
|---|---|---|---|---|---|
| addr | `ip -br addr` | 3s | 64 KiB | A | ✓ |
| link | `ip -d link show` | 3s | 64 KiB | A | ✓ |
| route_main | `ip route show` | 3s | 64 KiB | A | ✓ |
| route_all | `ip route show table all` | 5s | 256 KiB | B | ✓ |
| rule | `ip rule` | 3s | 32 KiB | A | ✓ |
| neigh | `ip neigh show` | 3s | 64 KiB | A | ✓ |
| iptables_nat_S | `iptables -t nat -S`（或 NetfilterCollector） | 3s | 128 KiB | B | ✓ |
| iptables_filter_S | `iptables -S` | 3s | 128 KiB | B | ✓ |
| iptables_nat_Lnv | `iptables -t nat -L -nv` | 5s | 128 KiB | C | **跳过** |
| iptables_filter_Lnv | `iptables -L -nv` | 5s | 128 KiB | C | **跳过** |
| ss_listen | `ss -ltnp` | 3s | 128 KiB | A | ✓ |
| ss_udp | `ss -lunp` | 3s | 64 KiB | A | ✓ |
| ss_state | `ss -t state established` | 5s | 256 KiB | C | **跳过** |
| sysctl_net | `sysctl net.ipv4.{ip_forward,conf.all.{forwarding,rp_filter,proxy_arp},conf.eth0.*,...}` | 3s | 8 KiB | A | ✓ |
| conntrack_full | `cat /proc/net/nf_conntrack` | 5s | 512 KiB | C | **跳过** |
| conntrack_count | `cat /proc/sys/net/netfilter/nf_conntrack_count` + `_max` | 1s | 1 KiB | A | ✓ |
| conntrack_buckets_timeouts | `sysctl net.netfilter.nf_conntrack_*` | 1s | 4 KiB | A | ✓ |
| proc_net_dev | `cat /proc/net/dev` | 3s | 64 KiB | A | ✓ |
| proc_softirqs | `cat /proc/softirqs` | 3s | 16 KiB | A | ✓ |
| proc_stat | `cat /proc/stat` | 3s | 16 KiB | A | ✓ |
| carrier_changes | `for i in eth0 eth1 ...; do echo $i:$(cat /sys/class/net/$i/carrier_changes); done` | 3s | 4 KiB | A | ✓ |
| ethtool | `ethtool eth0; ethtool eth1` | 5s | 16 KiB | B | ✓ |

并行组：A = 立即可执行，B = 中等开销（高 conntrack 仍执行），C = 重操作（高压时跳过）。同组并发执行，组间串行。

### 11.6 GVM 命令白名单

| Section | 命令 | 超时 | 输出上限 | 并行 |
|---|---|---|---|---|
| addr | `ip -br addr` | 3s | 64 KiB | A |
| link | `ip -d link show` | 3s | 64 KiB | A |
| route_all | `ip route show table all` | 5s | 256 KiB | B |
| rule | `ip rule` | 3s | 32 KiB | A |
| neigh | `ip neigh show` | 3s | 32 KiB | A |
| ss_listen | `ss -ltnp` | 3s | 128 KiB | A |
| ss_udp | `ss -lunp` | 3s | 64 KiB | A |
| proc_net_dev | `cat /proc/net/dev` | 3s | 64 KiB | A |
| carrier_changes | 同 PVM | 3s | 4 KiB | A |
| dumpsys_brief | `dumpsys connectivity --short` 或 `dumpsys connectivity 2>&1 \| head -200` | 3s | 32 KiB | B |
| dumpsys_full | `dumpsys connectivity` | 5s | 256 KiB | C（仅 fetch_log 时） |
| ndc | `ndc network list` | 3s | 16 KiB | A |
| netd_state | `dumpsys netd` 或简化版 | 3s | 32 KiB | B |

---

## 12. 取证目录详细设计（修正 review F4 + G18）

### 12.1 目录结构

```
/log/perf/network_diag/                          # PVM 端
├── incidents/
│   ├── incident_20260509_153012_LINKDOWN_a3f/
│   │   ├── manifest.json                        # incident 元信息（见 12.2）
│   │   ├── event.json                            # polaris 事件 payload 副本
│   │   ├── baseline_diff.json                    # 与 baseline 比较结果
│   │   ├── pvm/
│   │   │   ├── ip_*.txt
│   │   │   ├── iptables_*.txt
│   │   │   ├── ss_*.txt
│   │   │   ├── sysctl_net.txt
│   │   │   ├── proc_net_*.txt
│   │   │   ├── carrier_changes.txt
│   │   │   ├── dmesg_conntrack.txt
│   │   │   ├── ethtool_eth0.txt / ethtool_eth1.txt
│   │   │   └── tcpdump_*.pcap
│   │   ├── gvm/                                  # 来自 GVM push or fetch_log
│   │   │   ├── ip_*.txt / ss_*.txt / dumpsys_*.txt / ndc_*.txt
│   │   │   └── ...
│   │   ├── probes_window.jsonl                   # 触发前后 SHU probe 历史
│   │   └── derived_events.json                   # G7 派生事件清单
│   └── ...
├── snaps/
│   └── snap_20260509_153012_VLAN3GW/             # GVM push 携带的快照
└── probes/
    ├── SHU_VLAN3_INTERNET.jsonl                   # 24h 滚动
    ├── SHU_DNS.jsonl
    └── ...

/data/local/polaris/network_diag/                 # GVM 端镜像，相同结构
```

### 12.2 manifest.json schema

```jsonc
{
  "schema_version":      "1.0",
  "incident_id":         "incident_20260509_153012_LINKDOWN_a3f",
  "first_seen_ts_unix":  1747764012,
  "first_seen_ts_boot":  18234567,
  "boot_id":             "f0b8...",
  "config_version":      "v1.0-2026-05-09",
  "baseline_version":    "v1.0-2026-05-09",
  "diag_version":        "1.0.0",
  "platform":            "SA8397",

  "root_event":          "NETDIAG_LINK_DOWN",
  "root_event_id":       "0x4E5E0002",
  "severity":            "FAIL",
  "shu":                 ["SHU_VLAN3_INTERNET","SHU_VLAN6_ADCU_PARK","..."],
  "scenarios":           ["A-Internet","D-ADCU"],

  "data_quality":        { "pvm": "complete", "gvm": "partial:vsock_disconnected" },

  "files": [
    {"path":"pvm/ip_addr.txt","size":2048,"sha256":"...","sensitivity":"med"},
    {"path":"pvm/iptables_nat_S.txt","size":4096,"sha256":"...","sensitivity":"low"},
    {"path":"pvm/tcpdump_eth1.pcap","size":1048576,"sha256":"...","sensitivity":"high","payload_stripped":true},
    {"path":"gvm/dumpsys_brief.txt","size":1024,"sha256":"...","sensitivity":"med"}
  ],
  "redacted_fields":     ["mac_last_octets","conntrack_peer_ip"],

  "derived_event_count": 4,
  "captured_dur_sec":    2.3,
  "size_total_kb":       1280
}
```

### 12.3 retention 策略

```
触发条件：
  total_size > incident_max_size_mb (200 MiB)  OR
  count > incident_max_count (50)               OR
  oldest > retention_days (7)

清理顺序（按价值由低到高）：
  1. snapshots/   保留 24h，超期直接删
  2. probes/*.jsonl 仅保留 24h
  3. incidents/ INFO 级 → 24h 清
  4. incidents/ WARN 级 → 3 天清
  5. incidents/ FAIL 级 → 7 天清
  6. 极端：磁盘 < 100 MiB 时强制清掉所有 INFO + WARN 旧数据，保留最近 5 个 FAIL
```

清理操作必须原子：先删除文件，再更新 manifest 索引。

### 12.4 fetch_log 协议详细（review F4 闭环）

见 §4.1.5 已定义。补充一致性约束：

- 发起 `fetch_log` 前，PVM diag 检查 `log_ref` 在自己 retention 内未过期（防止 GVM 拿到的是已删目录）。
- 大文件单次只能拉一份 `incident_dir` 或 `snap_dir`。
- 中断恢复：chunk_seq 已收到的部分缓存到 `/log/perf/network_diag/.fetch_partial/<req_id>/`，超时未完成清理。

### 12.5 敏感性分级（G18）

| 级别 | 字段类型 | 示例 | 上云策略 |
|---|---|---|---|
| `low` | 接口名/VLAN ID/服务名/sysctl 值 | `eth1.3`, `vlan=3` | 默认上云 |
| `med` | 内部 IP/网关 IP/进程名/PID/socket state | `172.16.103.40`, `xdja_idps` | 默认上云 |
| `high` | MAC 地址/外部对端 IP/conntrack peer/tcpdump payload | `02:df:53:00:00:09`, conntrack 表 | **上云需云端权限**；本地脱敏 |

脱敏规则（在 `report/SensitivityRedact` 实现）：

- MAC 后两段：`02:df:53:00:**:**`
- conntrack 表：保留 src/dst 的 VLAN/网段，外部 IP 哈希后 6 字节
- tcpdump payload：仅留 IP/TCP/UDP 头，截断 L4 之上的 payload
- DNS query 的 qname：保留 TLD + suffix，前缀哈希（`*.example.com`）

`fetch_log` 默认 `redact:on`，云端必须显式权限请求 `redact:off` 才能拉原始数据。

---

## 13. 时钟与时序设计（C7 / G6 修正）

### 13.1 三时钟字段约定

| 字段 | 来源 | 用途 |
|---|---|---|
| `ts_unix` | `clock_gettime(CLOCK_REALTIME)` | wall-clock，云端日历展示用 |
| `ts_boot` | `clock_gettime(CLOCK_BOOTTIME)` ms | 单调递增，跨 suspend，本机排序用 |
| `boot_id` | `cat /proc/sys/kernel/random/boot_id` | 启动 epoch 标识，云端识别同一 boot 内事件 |

### 13.2 内部状态机一律使用 BOOTTIME

```c
class IncidentDeduper {
    struct ActiveIncident {
        uint64_t first_seen_boot_ms;  // CLOCK_BOOTTIME
        ...
    };
    
    void on_event(Event e) {
        uint64_t now = boot_ms_now();
        if (now - active.first_seen_boot_ms < incident_window_sec * 1000) {
            // 聚合，不受 NTP 跳变影响
        }
    }
};
```

`trigger_min_gap_sec` / `global_min_interval_sec` / probe 周期 timer / fetch_log 超时 / VSOCK 心跳—全部 BOOTTIME。

### 13.3 时间偏差检测（NET-DIAG-RPT-005 闭环）

PVM 主进程周期性（每 60s）：

```c
// 通过 VSOCK 9101 ping GVM，request 含 PVM 当前 ts_unix + ts_boot
// GVM 响应 response 含 GVM ts_unix + ts_boot
// 计算偏差：
clock_skew_ms = abs(pvm.ts_unix - gvm.ts_unix);  // 减去 RTT/2 估计

// PVM 也读 polarisd 的时钟（如果暴露）以及 PolarisAgent 的时钟（经云端时间）

if (clock_skew_ms > skew_warn_ms (5000)) {
    报 INFO `NETDIAG_TIME_SKEW`
}
if (clock_skew_ms > skew_fail_ms (60000)) {
    WARN：报告中所有事件聚合可能不准确
    incident_dir/manifest.json 标记 "time_skew_warn"
}
```

### 13.4 Boot Warmup 时序（G5 完整化）

```
+-----+ T+0       systemd / init.rc 拉起
|     |
|     | T+10s      Bootstrap Phase 1-3 完成（config + capability + channels）
|     |
|     | T+10s      进入 Boot Warmup（boot_warmup_sec = 120s）
|     |            ┌── 信号源开始采样
|     |            │   - WatchdogReactor 启动，所有信号 "active=true, suppress=true"
|     |            │   - ProbeScheduler 启动，所有 probe "warmup=true"
|     |            │
|     |            ├── 期内：
|     |            │   - 物理 link DOWN  → 立即 FAIL（无视 warmup）
|     |            │   - conntrack table full → 立即 FAIL
|     |            │   - 其他事件 → INFO 级，写本地 boot_warmup.log，不发 polaris
|     |            │
|     |            └── 期内不做：
|     |                - polaris event 发送（除上述硬故障）
|     |                - SHU FAIL 上报
| 130 | T+130s     Boot Warmup 结束
| s   |            - 重新评估所有信号当前状态
|     |            - 真正存在的故障在此刻进入正式上报通道
+-----+ - 触发首次 NETDIAG_SCAN_REPORT（INFO）
        - 进入正常运行模式
```

每个 watchdog/probe 也可单独配置 `warmup_sec`，例如：

```jsonc
"watchdogs": [
  { "id":"WD_PVM_NEIGH", "warmup_sec":180,
    "_note":"网关 ARP 解析需要更长时间，warmup 比全局更长" },
  { "id":"WD_PVM_CONNTRACK_PCT", "warmup_sec":30,
    "_note":"conntrack 计数从 0 起步，30s 即可稳定" }
]
```

---

## 14. PVM 端 GVM 视角 probe（G1 详化）

### 14.1 实现思路

PVM 自己 ping 网关跑的是 PVM 协议栈本地路径；GVM 应用走的是经过 vmtap + NAT 的路径。两者结果不同时，正是 NAT 段故障的明确信号。

PVM 实现"模拟 GVM 视角"有两种技术路径：

#### 路径 A：raw socket + 手动构造 IP 包（推荐 v1）

```c
int s = socket(AF_INET, SOCK_RAW, IPPROTO_ICMP);
setsockopt(s, IPPROTO_IP, IP_HDRINCL, 1);  // 自己构造 IP 头

struct iphdr ip;
ip.saddr = inet_addr("10.10.103.40");  // 伪装 GVM 源 IP
ip.daddr = inet_addr("172.16.103.20"); // 真实目的
ip.protocol = IPPROTO_ICMP;
...

// 发送时不指定 oif（让内核做路由），但因为 src=10.10.103.40 命中
// vmtap1.3 connected route，加上策略路由 iif=vmtap1.3 → table 106 等
// （注意此时 iif 实际是本机，不一定命中策略路由——见 14.2 限制）

sendto(s, packet, len, 0, &dst_sock, sizeof(dst_sock));
recv on raw socket，过滤 src=172.16.103.20 dst=10.10.103.40 的回包
```

#### 路径 B：nfqueue 注入到 vmtap1.X 入口（v2 复杂）

设置 `iptables -t mangle -A PREROUTING -i vmtap1.3 -j NFQUEUE --queue-num=42`，PVM diag 通过 libnetfilter_queue 注入伪造的 ICMP 包，让内核把它当作真的 vmtap1.3 入站包处理（命中所有策略路由 + iif=vmtap1.3 规则）。

v1 用路径 A（接近真实但不完全等价）；v2 评估路径 B 真实度收益。

### 14.2 路径 A 的局限性

- 不会触发 `iif=vmtap1.X` 的策略路由（rule 217/218/219）
- 不会触发 `iptables -i vmtap1.X` 的入向规则匹配
- 但**会触发** POSTROUTING SNAT（最常见的 NAT 故障在这里）
- 因此路径 A 能发现 ~70% 的 NAT 段故障，足以 v1 作为初版

### 14.3 失败差分判定

| PVM 自身 ICMP probe | GVM Perspective probe | 判定 |
|---|---|---|
| PASS | PASS | SHU 健康 |
| PASS | **FAIL** | NAT/forwarding 段异常（**G1 闭环**） |
| FAIL | FAIL | 物理/邻居/上游故障 |
| FAIL | PASS | 罕见（GVM 路径绕过故障点？需具体分析） |

事件 payload 中 `evidence_summary` 加：

```
"PVM self probe 172.16.103.20: PASS (RTT 1.2ms)
GVM perspective probe (src=10.10.103.40): FAIL (no reply within 3s)
→ Suggests: NAT POSTROUTING SNAT or forwarding issue, not L1/L2"
```

---

## 15. 维护模式（G17 完整化）

### 15.1 接口

通过 polaris IAction `netdiag.set_maintenance`（云端可下发）或 PVM diag 内部 API：

```jsonc
{
  "enable":       true | false,
  "scope":        ["VLAN4","SHU_VLAN15_RTSP"],   // 可空 = 全局
  "duration_sec": 600,
  "reason":       "DoIP 标定流程 / OTA 升级 / IDPS 测试",
  "issuer":       "PolarisAgent.User",
  "max_duration_sec_capped": 3600  // 系统强制上限
}
```

### 15.2 行为

- 期内对应 scope 的告警全部降级为 INFO，不发 polaris event
- watchdog 信号仍然采样并写本地（manifest.json 标记 "in_maintenance:true"）
- 维护期超过 `max_duration_sec_capped` 强制结束（防止遗忘）
- 进入/退出维护期都发 `NETDIAG_SCAN_REPORT(INFO)` 标识时间窗

### 15.3 与 incident 聚合的交互

维护期内的事件不进入 IncidentDeduper 主流程；写本地 `/log/perf/network_diag/maintenance_log/` 留底；维护结束后如有未恢复的 FAIL 状态会被重新评估并产生新 incident（避免漏报）。

---

## 16. 部署与协同

### 16.1 PVM systemd unit（修正 F5）

```ini
# /usr/lib/systemd/system/network-diag.service
[Unit]
Description=Network Diagnostic Daemon (PVM)
After=systemd-modules-load.service polarisd.service
Wants=polarisd.service
ConditionPathIsDirectory=/log/perf

[Service]
Type=simple
ExecStartPre=/bin/mkdir -p /log/perf/network_diag/incidents \
    /log/perf/network_diag/snaps /log/perf/network_diag/probes
ExecStart=/usr/bin/network-diag-pvm --config /etc/polaris/network-diag-pvm.json
Restart=always
RestartSec=2s
StartLimitBurst=5
StartLimitIntervalSec=60s

# 软限：相对低权重
CPUWeight=20
IOSchedulingClass=best-effort
IOSchedulingPriority=7
Nice=10

# 硬限：内存
MemoryMax=128M

# 不用 CPUQuota 硬限，避免 incident 模式下被卡死
# 真正的 CPU 保护靠应用层 ResourceGuard

AmbientCapabilities=CAP_NET_RAW CAP_NET_ADMIN
NoNewPrivileges=true
ReadWritePaths=/log/perf/network_diag /run/polaris/network-diag
RuntimeDirectory=polaris/network-diag
RuntimeDirectoryMode=0750
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true

User=root
Group=root

[Install]
WantedBy=multi-user.target
```

### 16.2 GVM init.rc 与 sepolicy（与 §3.2.4 一致）

详见 §3.2.4。

### 16.3 与 polaris-monitor 协同

- 共享 `/log/perf/` 根目录，但各持子目录（`fd_monitor` vs `network_diag`）
- 共享 200 MB 总配额：polaris-wide ResourceGuard（v2 协调，v1 各跑各的，各 ≤ 200 MB）
- 不竞争 polaris event_id 段（fd_monitor 用 `0x4FXX_XXXX`，net_diag 用 `0x4E5E_XXXX`）

---

## 17. 性能预算与影响评估

### 17.1 常态开销（全部 SHU PASS，60s 巡检间隔）

| 操作 | 频率 | CPU (P95) | Memory peak | IO | 网络 pps | 总评估 |
|---|---|---|---|---|---|---|
| netlink reactor | 持续 | <5 ms 累积/min | 4 MiB | 0 | 0 | 极轻 |
| inotify reactor | 持续 | <2 ms/min | 1 MiB | 0 | 0 | 极轻 |
| journal reactor | 持续 | 5-15 ms/min | 8 MiB | journal read | 0 | 轻 |
| ProbeScheduler 60s 巡检 | 1/min | 50 ms（含 ICMP 3 包/SHU × 9 SHU） | 2 MiB | 0 | ~3 pps | 轻 |
| ProbeScheduler 300s | 1/5min | 30 ms | 2 MiB | 0 | ~1 pps | 极轻 |
| 60s 轻量巡检 collect | 1/min | 200 ms（4 worker 并行 6-8 命令） | 16 MiB | 256 KiB read | 0 | 中 |
| 1h 全量巡检 | 1/h | 2 s | 32 MiB | 1 MiB | 0 | 重（但低频） |
| ConntrackPoller | 1/10s | 1 ms | 1 MiB | 1 KiB | 0 | 极轻 |
| ProcessWatcher | 1/5s | 1 ms | 1 MiB | 0 | 0 | 极轻 |
| VSOCK 心跳 | 1/30s | <1 ms | 64 KiB | 0 | 0 | 极轻 |

合计常态 CPU 占用：**~100 ms/min ≈ 0.17%**（单核）。Memory RSS 估计 30-50 MiB。

### 17.2 异常态开销（incident 触发，路径 ②/③）

| 操作 | 单次 | 总耗时 |
|---|---|---|
| WatchdogReactor 触发 | <5 ms | T+0 |
| 立即 collect 启动（4 worker 并行 8 命令） | 命令 P95 = 60-200 ms | T+0.5-1s |
| Probe burst（5 包 × 1s） | 5s | 并行 |
| baseline_diff 计算 | 50-200 ms | T+1.2s |
| 跨 VM RPC（VSOCK 9101 collect GVM） | 100-300 ms 网络 + 1-2s GVM 采集 | T+2-3s |
| analyzer + RootCauseSolver | 100-200 ms | T+3s |
| incident_dir 写盘 | 200-500 ms（取决于文件数） | T+3.5s |
| polaris_report_raw 提交 | <50 ms | T+3.5s |
| **总延迟（本地闭环）** | | **5-10s** |
| **+ VSOCK 9001 上行 + PolarisAgent 转云** | | **+1-2s** |
| **+ 云端 RTT** | | **+1-10s（取决于 TBOX）** |

异常态 CPU 占用峰值：**单 incident ≈ 1-2 秒 × 50% 单核 ≈ 0.5-1 秒-CPU**。

### 17.3 30s SLA 详细分解（§8.2 review 补充）

按修正后能力评估（路径 ②，不含云端 RTT）：

| 阶段 | 优化前 | 优化后 |
|---|---|---|
| GVM watchdog 触发 | 1-3s | 1-3s |
| GVM 采集 5 命令 | 0.5-1s（串行） | **0.3-0.5s（并行）** |
| GVM 写 snap_dir + 序列化 | 0.2-0.5s | 0.2-0.5s |
| VSOCK 9101 push | 0.1-0.3s | 0.1-0.3s |
| PVM 路由到协调器 | 0.1-0.3s | 0.1-0.3s |
| PVM 立即采集 8 命令 | 0.5-1s（串行） | **0.3-0.5s（并行 4 worker）** |
| PVM probe 加紧 5×200ms | 1-1.5s | **0.5-1s（并行 5 SHU）** |
| analyzer 计算 | 0.5-1s | 0.3-0.5s |
| incident_dir 写入 | 0.5-1s | **0.2-0.4s（并行 + tmpfs staging）** |
| polaris commit | 0.1-0.3s | 0.1-0.3s |
| **本地闭环总** | **5-10s** | **3-7s** |

加上 VSOCK 9001 + PolarisAgent + 云端 RTT，整体 30s SLA 在常态可保（P95），在 4G 弱信号下边缘满足（P99）。

### 17.4 关键性能保护机制

| 机制 | 触发条件 | 行为 |
|---|---|---|
| ResourceGuard A | conntrack ≥80% | 跳过 `iptables -L -nv` / `cat /proc/net/nf_conntrack` |
| ResourceGuard B | ksoftirqd CPU >50% 持续 30s | 暂停 60s 巡检（保留 watchdog） |
| ResourceGuard C | 内存占用 >100 MiB | 强制 retention 清理 + 拒绝新 incident |
| ResourceGuard D | tcpdump 进程超时 | SIGKILL + 标记 BLOCKED |
| ResourceGuard E | VSOCK 9101 send queue >1MB | 丢弃 INFO push，仅保留 FAIL |
| ResourceGuard F | polaris commit -EAGAIN 累积 ≥3 | 暂停事件发送 30s，本地缓存 |

### 17.5 性能压力测试用例（验证 SLA）

| TC | 构造 | 预期 |
|---|---|---|
| TC-PERF-001 | conntrack 注入到 95% 后触发 NAT 漂移检测 | iptables 命令仍能正常执行，整体延迟 <30s |
| TC-PERF-002 | 同时触发 5 个 SHU 都 FAIL | EventBus 不丢事件；incident 聚合得到 1 个根+4 派生 |
| TC-PERF-003 | VSOCK 9101 流量峰值（fetch_log 16 MiB） | 不影响 watchdog 实时性，心跳不丢 |
| TC-PERF-004 | 10s 内 100 次 link flap | flapping 检测准确；不灌爆事件 |
| TC-PERF-005 | NTP 跳变 1h | 内部状态机正常（用 BOOTTIME），incident 聚合不混乱 |

---

## 18. 需求追踪矩阵（NET-DIAG-* × 100% 覆盖）

> 全 53 项需求 × 实现组件 × 测试用例。

### 18.1 模式（5 项）

| 需求 ID | Check ID | 实现组件 | 测试 |
|---|---|---|---|
| MODE-001 | — | `ScanScheduler` 60s/1h | TC-NET-001..023 全量 |
| MODE-002 | — | `ScenarioEval` `scope=vlan` filter | 按 VLAN 执行专项测试 |
| MODE-003 | — | `ScenarioEval` `scope=scenario` | 场景 A-L 各跑一次 |
| MODE-004 | — | `WatchdogReactor` | TC-NET-001/004/011/021 |
| MODE-005 | — | `CommandRunner` 白名单 | 审计 readonly_only |

### 18.2 基线（5 项）

| 需求 ID | Check ID | 实现 |
|---|---|---|
| BASE-001 | BASE-001 | `Config::baseline` 加载 + schema 校验 |
| BASE-002 | BASE-002 | `BaselineDiff` |
| BASE-003 | BASE-003 | `diff_policy` 应用（review F2 闭环） |
| BASE-004 | BASE-004 | `EventComposer` 元信息 |
| BASE-005 | BASE-005 | `pvm_only_strict_isolation`（VM-005 + SEC-003 联合） |

### 18.3 物理链路（6 项）

| 需求 ID | Check ID |
|---|---|
| LINK-001 | L1-LINK-001 |
| LINK-002 | L1-LINK-002 |
| LINK-003 | L1-LINK-003 |
| LINK-004 | L1-LINK-004（巡检模式） |
| LINK-005 | L1-LINK-005（capability gated） |
| LINK-006 | L1-LINK-006 |

### 18.4 VLAN（7 项）

`VLAN-001..007 → L2-VLAN-001..007`

### 18.5 IP/路由（11 项）

| 需求 ID | Check ID | 备注 |
|---|---|---|
| IP-001 | L3-IP-001 | |
| IP-002 | L3-IP-002 | |
| IP-003 | L3-IP-003 | |
| IP-004 | L3-IP-004 | per-iface 全采集 |
| **IP-005** | **L3-IP-005** | **review F2 闭环：proxy_arp 全采集** |
| ROUTE-001..006 | L3-ROUTE-001..006 | |

### 18.6 NAT/防火墙（9 项）

| 需求 ID | Check ID |
|---|---|
| NAT-001..004 | L4-NAT-001..004 |
| FW-001..004 | L4-FW-001..004 |
| **FW-005** | **L4-FW-005**（review F2 闭环：buckets/timeouts） |

### 18.7 虚拟化（7 项）

`VM-001..007 → VM-001..007`

### 18.8 业务（12 项）+ 端口（5 项）

| 需求 ID | Check ID |
|---|---|
| SVC-001..012 | SVC-001..012 |
| PORT-001..005 | PORT-001..005 |

### 18.9 性能（6 项）

| 需求 ID | Check ID | 备注 |
|---|---|---|
| PERF-001 | PERF-001 |
| PERF-002 | PERF-002 |
| **PERF-003** | **PERF-003** | review F2 闭环：吞吐计算窗口 + 算法 |
| **PERF-004** | **PERF-004** | review F2 闭环：softirq 数据源 + 阈值 |
| **PERF-005** | **PERF-005** | review F2 闭环：MTU 基线字段 |
| **PERF-006** | **PERF-006** | review F2 闭环：广播风暴检测模型 |

### 18.10 安全（6 项）

`SEC-001..006 → SEC-001..006`

### 18.11 报告（5 项）

| 需求 ID | 实现 | 备注 |
|---|---|---|
| RPT-001 | **不实现端侧 Markdown** | 用户决定，云端渲染 |
| RPT-002 | `JsonReport` | event payload + report.json |
| RPT-003 | `EventComposer` severity 字段 | 5 级 |
| RPT-004 | `IncidentDirWriter` | 原始命令输出归档 |
| **RPT-005** | **review F2 闭环** | 时间偏差检测见 §13.3 |

---

## 19. 测试用例详细化

### 19.1 23 个验收用例（NET-DIAG-TC-001 ~ 023）

照搬需求 §13 + 加 SLA 验证：

| TC | 构造 | 30s 内识别？ | 备注 |
|---|---|---|---|
| TC-NET-001 | PVM `eth1` carrier down | ✅ <1s | netlink RTNLGRP_LINK |
| TC-NET-002 | GVM `eth1.4` 缺失 | ✅ ≤60s（GVM 巡检） | GVM watchdog 后改 ≤30s |
| TC-NET-003 | DNAT 缺失 | ✅ ≤30s | NAT 哈希对比 30s |
| TC-NET-004 | TCP/30006 被 DNAT 错 | ✅ ≤30s | 同上 |
| TC-NET-005 | table 106 缺失 | ✅ <1s | netlink RTNLGRP_IPV4_ROUTE |
| TC-NET-006 | NetId 错 | ⚠️ 60s（GVM 巡检） | 改 ConnectivityCallback 后 ≤3s |
| TC-NET-007 | someipd 未监听 | ✅ ≤5s | sd-bus PropertiesChanged |
| TC-NET-008 | RTSP 流断 | ⚠️ 60s | 业务侧 |
| TC-NET-009 | PVM 0.0.0.0:5555 暴露 | ✅ ≤60s | 巡检 |
| TC-NET-010 | RX error 持续增长 | ✅ ≤60s | 巡检 + 增量 |
| TC-NET-011 | 网关 ARP FAILED | ✅ <1s | netlink RTNLGRP_NEIGH |
| TC-NET-012 | PVM `eth0` 断 | ✅ <1s | |
| TC-NET-013 | Host-Guest 异常 | ✅ ≤30s | vmtap 协议层 echo |
| TC-NET-014 | DNAT 顺序错 | ✅ ≤30s | NAT 哈希对比 |
| TC-NET-015 | MTU 不一致 | ✅ ≤60s | 巡检 |
| TC-NET-016 | trunk 父接口 DOWN | ✅ <1s | netlink |
| TC-NET-017 | DNS 失败 | ✅ ≤60s（DNS probe）改 30s 后 ≤30s | review F1 修正 |
| TC-NET-018 | rp_filter=1 NAT 路径 | ✅ <1s | inotify 配 sysctl 后；否则 60s |
| TC-NET-019 | PVM MAC 异常 | ✅ <1s | 通过 RTNLGRP_LINK + 启动检查 |
| TC-NET-020 | TBOX 网关不可达 | ✅ ≤30s | ICMP probe 30s 已修正 |
| TC-NET-021 | conntrack table full | ✅ <3s | sd-journal |
| TC-NET-022 | per-iface forwarding=0 | ✅ <1s | inotify |
| TC-NET-023 | TBOX 上游不通（网关可达） | ✅ ≤120s | uplink ICMP 120s |

### 19.2 故障注入接口（仅 userdebug 启用）

```c
// 编译开关：DEBUG_FAULT_INJECTION
#ifdef DEBUG_FAULT_INJECTION
class FaultInjector {
    // 经 IAction "netdiag.test_fault" 触发
    void inject(string fault_type, json args) {
        if (fault_type == "vsock_block") { simulate_vsock_disconnect(); }
        if (fault_type == "high_conntrack") { fake_conntrack_count_pct(args.pct); }
        if (fault_type == "nat_rule_drift") { ... };
    }
};
#endif
```

允许测试用例在 userdebug 下注入，user 镜像编译时整段排除。

### 19.3 性能压力测试（见 §17.5）

5 个 TC 含 conntrack 高压、5 SHU 同时 FAIL、VSOCK 流量峰值、link flap 风暴、NTP 跳变。

---

## 20. 风险与降级策略

### 20.1 综合降级表（与 sys_design §19 合并 + 补充）

| 风险 | 降级 | BLOCKED 等级 | 报告标记 |
|---|---|---|---|
| GVM ethtool 不存在 | 跳过 L1-LINK-005 | L1_env | BLOCKED-L1 |
| `/proc/net/stat/nf_conntrack` 不存在 | 仅看 dmesg + count/max | L1_env | BLOCKED-L1 + degraded_evidence |
| `dumpsys connectivity` 权限受限 | 降级 ip rule/route | L1_env | BLOCKED-L1 + 替代 PASS/FAIL |
| `dumpsys` 突然超时（之前 OK） | 重试 + 标 L3 | L3_intermittent | BLOCKED-L3 |
| GVM placeholder 接口 | 过滤 | INFO | INFO（不参与检查） |
| polaris commit -EAGAIN | 本地保留 + 重试 | — | 内部日志 |
| polarisd 不可达 | 仅本地 incident_dir，不上云 | — | service_degraded |
| VSOCK 9101 不可用持续 60s | GVM fallback polaris event 链 | — | service_degraded |
| VSOCK 9101 可用但 hello 协商失败 | 关闭并退避 | — | service_degraded |
| VSOCK 9001 不可用（polaris VSOCK） | 报告本地缓存 | — | service_degraded（兜底于 polarisd 自身） |
| 命令执行超时 | 重试一次，仍失败 BLOCKED | L3_intermittent | BLOCKED-L3 |
| tcpdump 无权限/不存在 | 跳过抓包子项 | L1_env | BLOCKED-L1 |
| 探测器自身异常 | 标 BLOCKED-L2 | L2_anomaly | BLOCKED-L2 |
| NTP 大跳变 | manifest 标 time_skew_warn，事件用 BOOTTIME | — | INFO `NETDIAG_TIME_SKEW` |
| 维护模式期内 | 降级 INFO，不触发 incident | — | INFO |

### 20.2 灾难恢复

| 灾难 | 行为 |
|---|---|
| network-diag-pvm 崩溃 | systemd 2s 后重启；最多 5 次/分钟 |
| network-diag-gvm 崩溃 | init.rc 重启；onrestart 同样限频 |
| polarisd 长时间不可用 | 持续本地 incident，不上报；polarisd 恢复后下次 incident 触发时附带补报最近 10 个 |
| `/log/perf` 满 | 强制清理 + 拒绝新 incident（保留事件记忆 1h） |
| qcrosvm 崩溃 | 触发 `NETDIAG_HYPERVISOR_DOWN`（最高优先级根事件）；本地落盘；GVM 不可达时 PVM 单独上报 |

---

## 21. polaris 团队对齐清单（最终版）

| 项 | 工作量 | 优先级 | 说明 |
|---|---|---|---|
| PVM polarisd 新增 `NetdiagBridgeAction` IAction | ~100 行 | P0 | 通过 UDS 转发云命令 |
| polaris client SDK 扩展 `polaris_command_listener_register` | ~150 行 | P0 | 见 §4.3.3，让 diag 能接收命令；含 transport 双工改造 + libpolaris 头文件升级 |
| 申请 event_id 段位 `0x4E5E_xxxx` | — | P0 | 18 个事件 ID（见 §8.1） |
| polarisd Dispatcher 配合 NetdiagEventPolicy | ~50 行 | P1 | 路径 ④ 的 enrichment 触发；可后置 |
| GVM sepolicy `network_diag.te` | ~30 条规则 | P0 | VSOCK 出向 + /proc/net + /log/perf |
| PVM systemd 部署清单 | 1 unit | P0 | 与 polarisd 同包发布 |
| 配额协调 | 文档 | P1 | polaris-monitor + network-diag 共享 200 MB 总量 |

---

## 22. 设计决策与已舍弃方案

> 所有 v1.0 + v1.1 关键决策一表汇总。

### 22.1 通信与架构

| 决策 | 备选 | 选择理由 |
|---|---|---|
| 专用 VSOCK 9101（NDGA） | 复用 polaris 命令通道 | 命令通道单 worker 串行 + 5s timeout 不够用；专用通道真双工 |
| 事件统一从 PVM 出口 | 两端各报各 | 云端关联简单，事件聚合天然合并 |
| PVM diag → polarisd 单向 report event | 双向 RPC | F15 收敛：避免引入 SDK 扩展；维护模式走 NDGA |
| baseline 拆独立附件 + sha256 互校 | 内联在主配置 | G1 + review F8：完整展开 + 双端一致性 |
| netfilter 抽象层（iptables/nft）| 直接 iptables | nftables 切换迁移成本预防（G8） |
| 端侧不出 Markdown 报告 | 端侧出 Markdown | 云端渲染统一 UI；端侧仅产生结构化事件（JSON）|
| 端侧不做脱敏（v1）| 写盘时脱敏 | 用户决定 |

### 22.2 时钟、事件、状态机

| 决策 | 备选 | 选择理由 |
|---|---|---|
| 时钟用 BOOTTIME 内部 + REALTIME 上报 | 全用 REALTIME | NTP 跳变下状态机不混乱（G6） |
| PVM boot_id 作全局 epoch（GVM hello 同步）| 双端各用自己 boot_id | B1：双端 fault_id 才能算出一致 |
| Boot warmup 120s | 启动即采 | 避免开机假阳性海啸（G5） |
| 事件因果聚合（30s 窗口）| 各报各 | 不灌爆 polaris 队列（G7） |
| 事件 payload ≤726 字节紧凑格式 | 大 schema 全字段 | PolarisAgent 上云硬约束 |

### 22.3 Fault 模型（B 系列）

| 决策 | 备选 | 选择理由 |
|---|---|---|
| **B1** R1 确定性 hash 算 fault_id | R2 PVM 主分配 / R3 云端模糊匹配 | 双端独立可算；跨 boot 复发统计可做；不依赖运行时协商 |
| **B2.③a** GVM 启动后立即对 ACTIVE fault 补归因（first_pass + 必要时 refine） | ① PVM 终态不补 / ② 全补包括 RECOVERED | 仅持续 fault 有归因价值；first_pass 延迟 3-5s 可接受 |
| **B3.②** side event 条件发送（NDGA online 时不发，离线 + 8s timer 兜底） | ① 全发 / ③ 端侧智能切换 | 稳态 polaris 事件 -33%；保留兜底防漏报 |
| **B4.③** fault_id 锁定 + manifest evolution[] + 派生 fault 用 `cb` 字段 | ① 严格不变不记演化 / ② 重大演化拆分 fault_id | fault_id 端到端稳定；演化轨迹可追溯；因果链直观 |

### 22.4 检测与采集

| 决策 | 备选 | 选择理由 |
|---|---|---|
| 命令并行执行（4 worker）| 串行 for 循环 | 30s SLA 要求（review §8.2 量化） |
| BLOCKED 分级（L1_env / L2_anomaly / L3_intermittent）| 一刀切 | 避免环境性 BLOCKED 误判异常（G15） |
| Probe 加紧策略量化（1s × 5 包 × 3 轮 = 15s）| 文档"加紧打 N 轮" | 工程实现可复现（G10） |
| 上下行差分检测靠内核 netfilter 状态 | App 主动报障 / 端到端 ICMP | conntrack UNREPLIED 是核心指纹，不依赖 App |
| MTU baseline 字段 | 不配 | PERF-005 闭环（review F2） |
| 维护模式（set_maintenance）| 无 | 避免 IDPS/ADAS 标定误报（G17） |

### 22.5 已舍弃方案（不做）

| 方案 | 不做的原因 |
|---|---|
| `polaris_command_listener_register` SDK 扩展 | F15 收敛通道 C 单向后不需要 |
| `NetdiagBridgeAction` IAction | 同上 |
| 端侧 Markdown 报告 | 云端渲染 |
| 取证脱敏（v1）| 用户决定，简化 |
| 同步反向命令通道（PVM→GVM RPC）| polaris 现有 VSOCK 是单向命令；用 NDGA 替代 |
| 跨 VM 同时读写同一文件 | 用户约束（A3）：PVM 写完才通知 GVM 读 |

---

## 23. 文档版本与未决项

### 23.1 版本历史

| 版本 | 日期 | 变更摘要 |
|---|---|---|
| 1.0 | 2026-05-09 | 初版（吸收需求 + sys_design + review F1-F5 + 补充评审 G1-G20）。架构方案 E、通道 A/B/C、PVM/GVM 进程分工、74 检查项 registry、9 SHU、PVM 9 个 watchdog 信号、ICMP/PMTU/DNS/GVMPerspective probe、Boot warmup、事件聚合、命令并行采集 |
| 1.1 | 2026-05-11 | v1.1 增量见 §23.2，详细章节 §24-§28 |

### 23.2 v1.0 → v1.1 完整变更清单

#### 23.2.1 新增检测能力

| ID | 内容 | 落点 |
|---|---|---|
| v1.1-A1 | "上行通下行不通"故障检测（不依赖 App）| §24 |
| v1.1-A2 | conntrack UNREPLIED 状态比例监测 | §24.3.1 / §11.5 |
| v1.1-A3 | PVM/GVM TCP SYN_SENT 累积监测 | §24.3.2 / §24.3.4 |
| v1.1-A4 | NAT 入向 vs 出向计数对称性 | §24.3.3 |
| v1.1-A5 | 新增 fault_class `DOWNSTREAM_PACKET_LOSS`（字典 27→28 项）| §24.1 |
| v1.1-A6 | 新增事件 `NETDIAG_DOWNSTREAM_LOSS = 0x4E5E0010` | §24.2 |

#### 23.2.2 Fault 模型（B 系列）

| ID | 内容 | 落点 |
|---|---|---|
| v1.1-B1 | fault_id / correlation_id 确定性 hash 公式 | §25.1 |
| v1.1-B2 | NDGA hello 同步 `pvm_boot_id_short`（PVM 作为全局 epoch）| §25.2 |
| v1.1-B3 | `/log/perf/network_diag/state/active_faults.json` 持久化 schema | §25.3 |
| v1.1-B4 | 事件 cls 三态（side/root/recov）+ fp/refined/dq 辅助字段 | §25.4 |
| v1.1-B5 | B2.③a：GVM 启动后立即补归因 + Boot Warmup 后必要时 refine | §25.5 |
| v1.1-B6 | manifest.json 跨端字段层级隔离写入规则 | §25.6 |
| v1.1-B7 | B3.②：side event 条件发送 + 8s fallback timer | §26 |
| v1.1-B8 | 4 个事件流场景对照（boot 早期 / 稳态 / 假在线 / NDGA 断开）| §26.4 |
| v1.1-B9 | B4.③：fault_id 锁定 + manifest evolution[] 段 | §27.1-3 |
| v1.1-B10 | 派生 fault 因果链（事件 payload `cb` + `fault_causation_graph.json`）| §27.4 |

#### 23.2.3 共享配置文件附件

| 文件 | 路径 | 内容 |
|---|---|---|
| `baseline-pvm.json` | git: `work/baseline-pvm.json` → 部署 PVM `/etc/polaris/baseline-pvm.json` | PVM 拓扑全展开（接口/IP/NAT/服务）|
| `baseline-gvm.json` | git: `work/baseline-gvm.json` → 部署 GVM `/system/etc/polaris/baseline-gvm.json` | GVM 拓扑全展开 |
| `fault_class_dict.json` | 双端共享 `/etc/polaris/fault_class_dict.json` + GVM `/system/etc/polaris/fault_class_dict.json` | 35 项 fault_class + 1 兜底 = 36 项；含 target_key 抽取规则 + 聚合优先级 + hash 算法定义。**已生成附件** `work/fault_class_dict.json`（453 行） |
| `fault_causation_graph.json` | 双端共享 | 15 条因果边（upstream → downstream）+ infer_caused_by() 实现注意事项。**已生成附件** `work/fault_causation_graph.json`（242 行） |
| `scenario-registry.json` | 双端共享 | 12 个业务场景 A-L + VLAN scope filter（MODE-002）+ watchdog 信号触发表（MODE-004）。**已生成附件** `work/scenario-registry.json`（652 行） |

#### 23.2.4 协议字段扩展

| 字段 | 用途 | 落点 |
|---|---|---|
| NDGA hello `pvm_boot_id_short` | GVM 同步获取 PVM boot_id 作为 fault_id epoch | §25.2 |
| NDGA hello `pvm_active_faults_count` | 提示 GVM 是否扫描历史 fault | §25.2 |
| NDGA push `fault_alert` | PVM/GVM 双向通知对端"有 fault" | §26.5 |
| NDGA push `root_emitted` | GVM 通知 PVM "已发 root cause"，取消 fallback timer | §26.3 |
| 事件 payload `cls` | 三态：side/root/recov | §25.4 |
| 事件 payload `cb` | 派生 fault 的 caused_by 上游 fault_id（可选） | §27.4 |
| manifest.json `evolution[]` | fault 演化轨迹 | §27.3 |
| manifest.json `data_quality.pvm/gvm` | 数据质量分层标记 | §25.5 |

#### 23.2.5 Polaris 团队对齐清单收敛

| 项 | v1.0 | v1.1 |
|---|---|---|
| 申请 event_id 段位 `0x4E5E_xxxx` | ✅ ~15 个 | ✅ ~19 个（含 NETDIAG_DOWNSTREAM_LOSS）|
| GVM sepolicy `network_diag.te` | ✅ | ✅ 含 `/mnt/vendor/log` 只读 |
| ~~`polaris_command_listener_register` SDK 扩展~~ | 必需 | **已撤销**（F15 通道 C 改单向后不需要）|
| ~~`NetdiagBridgeAction` IAction~~ | 必需 | **已撤销** |
| polarisd `mOfflineCache` 容量评估 | 未列 | P1（boot 早期短时大量 side event 评估）|

### 23.3 未决项（v2 候选）

| ID | 内容 | 评审依据 |
|---|---|---|
| V2-001 | HTTP probe 全 VLAN 覆盖 | sys_design review §7.2 |
| V2-002 | softirq/ksoftirqd 轻量采样阈值优化 | sys_design review §7.2 |
| V2-003 | 配置热重载 + PVM/GVM 双端版本协同 | sys_design review §4.2 + G19 |
| V2-004 | virtio queue 卡顿统计学阈值 | sys_design §11.1 注 |
| V2-005 | ARP probe（强制邻居解析） | sys_design §12.1 |
| V2-006 | 自适应 probe 频率 | sys_design §10 v2 |
| V2-007 | 反向命令通道（PVM→GVM 同步 RPC）| 需 polaris 团队评估 |
| V2-008 | nfqueue 注入式 GVM perspective probe（路径 B）| §14.2 |
| V2-009 | mmhab 跨域接口（与 Camera 团队）| G19 |
| V2-010 | 间歇故障 long-running probe 全 SHU 覆盖 | G3 |
| V2-011 | conntrack 解析周期 60s→15-20s 以保 30s SLA | §24.6 注 |
| V2-012 | 取证脱敏机制（on-write redaction）| 用户暂不考虑 |
| V2-013 | conntrack INVALID 状态细分采集 | §24 |
| V2-014 | fault_causation_graph 云端反推扩展 | §27.4.4 |

### 23.4 v1.1 启动实施前提（M7a 阻塞）

启动详细代码实现前必须完成：

1. **Polaris 团队**：分配 event_id 段位 `0x4E5E_0000..0x4E5E_00FF`（19 个事件）
2. **Polaris 团队**：评估 polarisd `mOfflineCache` 在 boot 早期短时大量 side event 场景下的容量
3. **平台/网络团队**：确认 `/mnt/vendor/log → PVM /log` 共享挂载在量产镜像上的可靠性 + SELinux label
4. **平台团队**：分配 NDGA VSOCK 9101 端口（与 polaris 9001 隔离）
5. **GVM SELinux 团队**：审核 `network_diag.te` sepolicy（含 VSOCK + /proc/net + 共享挂载读）

---

## 24. 下行回包丢失检测能力（不依赖 App）

> **背景**：v1.0 设计存在盲区，对"上行数据通路通、下行回包丢失"类故障（如 conntrack UNREPLIED 累积、PMTU 黑洞反向、NAT 反向规则失效、virtio RX 方向卡）**无法可靠定位根因**。常规 ICMP probe 是双向往返，失败时无法区分上行 vs 下行；vmtap 单向检测依赖应用持续重试，App 放弃后失效。
>
> **目标**：v1.1 必加 — 三类检测信号 + 1 个 fault_class + 1 个新事件 ID + 4 个采集 section + 2 个测试用例，**完全在 PVM/GVM 内核与 netfilter 层观测，不依赖 App 集成 `reportNetworkTrouble`**。

### 24.1 新增 fault_class

| fault_class | target_key | 严重度 | 修复动作 |
|---|---|---|---|
| `DOWNSTREAM_PACKET_LOSS` | VLAN 角色（`VLAN3_TBOX` / `VLAN6_ADCU` / ...）或 `"global"` | FAIL | 检查反向路径：conntrack timeout、iptables 反向规则、PHY RX 链路、virtio RX 队列 |

字典版本号同步 bump：`fault_class_dict v1.0 → v1.1`。

### 24.2 新增事件 ID

补入 §8.1 事件 ID 表（占位，待 polaris 团队分配）：

| 事件名 | 建议 ID | 严重度 |
|---|---|---|
| `NETDIAG_DOWNSTREAM_LOSS` | `0x4E5E0010` | FAIL |

### 24.3 新增检查项（3 项加入 §6 Check Registry）

#### 24.3.1 `L4-FW-006`：conntrack UNREPLIED 状态比例（PVM 视角）

```jsonc
{
  "id":              "L4-FW-006",
  "req_ids":         ["NET-DIAG-FW-003"],
  "title":           "PVM conntrack UNREPLIED 状态比例（下行回包丢失指纹）",
  "layer":           "L4",
  "side":            "PVM",
  "severity":        "FAIL",
  "blocked_severity":"L1_env",
  "event_id_on_fail":"0x4E5E0010",
  "shu_impact":      ["SHU_VLAN3_INTERNET","SHU_VLAN4_DOIP","SHU_VLAN6_ADCU_PARK","SHU_VLAN7_OTA","SHU_VLAN8_ADAS"],
  "data_source": {
    "type":    "command_pipe_internal",
    "command": "conntrack_state_stats",   // 见 §24.6 采集器实现
    "timeout_sec": 5,
    "max_output_kb": 16
  },
  "parser":          "conntrack_state_v1",
  "expect": {
    "unreplied_pct_warn":  5,
    "unreplied_pct_fail":  20,
    "invalid_pct_warn":    1,
    "invalid_pct_fail":    5,
    "min_total_entries":   100,             // 总条目少于 100 不触发（避免 boot 早期假阳性）
    "group_by_vlan":       true             // 按 dst_ip 反推 VLAN，分别统计
  },
  "evidence_files":  ["pvm/conntrack_state_breakdown.txt","pvm/conntrack_unreplied_sample.txt"],
  "suggestion":      "下行回包到达 PVM 但未匹配到 conntrack 出向状态。可能原因：① conntrack timeout 过短导致 entry 被淘汰；② iptables 反向规则缺失；③ PHY RX 端丢包；④ virtio RX 队列卡死。",
  "recheck_cmd":     "cat /proc/net/nf_conntrack | awk '/UNREPLIED/{u++}END{print u}'; ss -t state syn-sent",
  "perf_budget": {
    "cpu_ms_p95":              250,        // 解析 nf_conntrack 文本，500 条目约 150ms
    "io_kb":                   512,         // 单次读 /proc/net/nf_conntrack ≤ 512 KiB
    "network_packets":         0,
    "skip_when_conntrack_pct_above": 95     // 表已满时不解析，避免雪上加霜
  }
}
```

**为什么 conntrack UNREPLIED 是核心指纹**：

- conntrack 创建表项时初始状态包含 `[UNREPLIED]` 标记
- 收到反向回包后，内核清除 `[UNREPLIED]` 标记，进入正常 ESTABLISHED 状态
- **如果上行包出去了但下行没回来，conntrack 表项会持续保持 `[UNREPLIED]` 标记直到 timeout**
- 这是"上行通下行不通"在内核 netfilter 层的**唯一精确指纹**，不依赖 App

#### 24.3.2 `L4-FW-007`：TCP `SYN_SENT` 累积（PVM 视角）

```jsonc
{
  "id":              "L4-FW-007",
  "req_ids":         ["NET-DIAG-FW-003"],
  "title":           "PVM TCP SYN_SENT 状态堆积（建联收不到 SYN-ACK）",
  "layer":           "L4",
  "side":            "PVM",
  "severity":        "WARN",                // 单凭这个不足以判 FAIL，跟其他证据合并
  "blocked_severity":"L1_env",
  "event_id_on_fail":"0x4E5E0010",
  "shu_impact":      ["SHU_VLAN3_INTERNET","SHU_VLAN4_DOIP"],
  "data_source": {
    "type":    "command",
    "command": "ss -tn state syn-sent",
    "timeout_sec": 3,
    "max_output_kb": 64
  },
  "parser":          "ss_syn_sent_v1",
  "expect": {
    "syn_sent_count_warn":  10,
    "syn_sent_count_fail":  30,
    "syn_sent_age_warn_sec": 5,             // 单连接 SYN_SENT 持续 >5s
    "syn_sent_age_fail_sec": 15
  },
  "evidence_files":  ["pvm/ss_syn_sent.txt"],
  "suggestion":      "PVM 侧出现大量 TCP 建联挂起。结合 L4-FW-006 UNREPLIED 比例判断是否为下行回包丢失。",
  "recheck_cmd":     "ss -tn state syn-sent",
  "perf_budget": {
    "cpu_ms_p95":  30,
    "io_kb":        16,
    "network_packets": 0
  }
}
```

#### 24.3.3 `L4-NAT-005`：NAT 入向 vs 出向计数对称性

```jsonc
{
  "id":              "L4-NAT-005",
  "req_ids":         ["NET-DIAG-NAT-004"],
  "title":           "PVM NAT 入向 DNAT 与出向 SNAT 计数对称性",
  "layer":           "L4",
  "side":            "PVM",
  "severity":        "WARN",                // 长期不对称才有信号意义
  "blocked_severity":"L1_env",
  "event_id_on_fail":"0x4E5E0010",
  "shu_impact":      ["SHU_VLAN3_INTERNET","SHU_VLAN4_DOIP","SHU_VLAN6_ADCU_PARK","SHU_VLAN7_OTA","SHU_VLAN8_ADAS"],
  "data_source": {
    "type":    "abstracted",
    "method":  "list_nat_counters",
    "fallback":"list_nft_counters",
    "timeout_sec": 5,
    "max_output_kb": 128
  },
  "parser":          "nat_symmetry_v1",
  "expect": {
    "compare": [
      {"vlan":3, "outbound_rule":"SNAT eth1.3", "inbound_rule":"DNAT eth1.3 to 10.10.103.40",
       "symmetry_min_pps": 1,                  // 至少 1 包/秒才比对，避免静默时除零
       "asymmetry_ratio_warn": 0.5,            // 入向/出向 < 0.5 → WARN
       "asymmetry_ratio_fail": 0.1,            // < 0.1 → FAIL（出去 100 包回来 ≤10 包）
       "window_sec": 60                        // 60s 滑动窗
      }
      // VLAN 4/6/7/8 同样格式
    ]
  },
  "evidence_files":  ["pvm/iptables_nat_Lnv.txt","pvm/nat_symmetry_history.jsonl"],
  "suggestion":      "出向 SNAT 计数远大于入向 DNAT 计数。说明上行包正常发出，下行回包未到达或未被 NAT 反向转换。检查 iptables PREROUTING DNAT 规则、conntrack 状态、PHY RX。",
  "recheck_cmd":     "iptables -t nat -L PREROUTING -nv; iptables -t nat -L POSTROUTING -nv",
  "perf_budget": {
    "cpu_ms_p95":   200,
    "io_kb":         32,
    "skip_when_conntrack_pct_above": 80     // G13 保护：conntrack 高压时 iptables -L -nv 慢，跳过
  }
}
```

> **G13 保护下的兜底**：当 conntrack ≥80% 跳过 `iptables -L -nv` 时，L4-NAT-005 标 BLOCKED-L3_intermittent。conntrack 压力本身已通过 L4-FW-003 / L4-FW-006 上报，不会漏故障。

#### 24.3.4 `L5-PORT-006`：GVM TCP `SYN_SENT` 累积（GVM 视角）

```jsonc
{
  "id":              "L5-PORT-006",
  "req_ids":         ["NET-DIAG-FW-003"],
  "title":           "GVM TCP SYN_SENT 状态堆积（应用建联失败用户感知）",
  "layer":           "L5",
  "side":            "GVM",
  "severity":        "WARN",
  "blocked_severity":"L1_env",
  "event_id_on_fail":"0x4E5E0010",
  "shu_impact":      ["SHU_VLAN3_INTERNET","SHU_DNS"],
  "data_source": {
    "type":    "command",
    "command": "ss -tn state syn-sent",
    "timeout_sec": 3,
    "max_output_kb": 32
  },
  "parser":          "ss_syn_sent_v1",
  "expect": {
    "syn_sent_count_warn":  5,
    "syn_sent_count_fail":  15,
    "syn_sent_age_warn_sec": 5,
    "syn_sent_age_fail_sec": 10
  },
  "evidence_files":  ["gvm/ss_syn_sent.txt"],
  "suggestion":      "GVM 侧应用建联未收到 SYN-ACK，与 PVM 端 conntrack UNREPLIED / NAT 不对称证据合并判定。",
  "perf_budget": {
    "cpu_ms_p95": 30, "io_kb": 8, "network_packets": 0
  }
}
```

### 24.4 新增 Watchdog 信号（加入 §9）

#### PVM 侧（§9.1 表追加 3 行）

| 信号 ID | 数据源 | 检测方式 | 延迟 P95 | 触发事件 |
|---|---|---|---|---|
| `WD_PVM_CONNTRACK_UNREPLIED` | `cat /proc/net/nf_conntrack` 解析 | 60s timer：统计 `[UNREPLIED]` 标记行数 / 总行数；超阈值触发 | 60s | `NETDIAG_DOWNSTREAM_LOSS` |
| `WD_PVM_NAT_ASYMMETRY` | `iptables -t nat -L -nv` PREROUTING/POSTROUTING 计数 | 60s timer：维护滚动窗 deltas；不对称比例超阈值触发 | 60s | `NETDIAG_DOWNSTREAM_LOSS` |
| `WD_PVM_TCP_SYN_STUCK` | `ss -tn state syn-sent` | 30s timer：SYN_SENT 计数 + 最大 age | 30s | `NETDIAG_DOWNSTREAM_LOSS`（WARN，需合并） |

#### GVM 侧（§9.2 表追加 1 行）

| 信号 ID | 数据源 | 检测方式 | 延迟 P95 | 触发动作 |
|---|---|---|---|---|
| `WD_GVM_TCP_SYN_STUCK` | `ss -tn state syn-sent` | 30s timer | 30s | NDGA push `gvm_alert{type:tcp_syn_stuck}` 给 PVM |

#### 信号合并规则

单一信号不直接 FAIL，需要**至少 2 个信号同时命中**才升级 FAIL：

```
DOWNSTREAM_PACKET_LOSS = FAIL  当且仅当 60s 窗口内同时满足：
  ① L4-FW-006 UNREPLIED >= 20%  OR  >= 5% 且持续 3 次连续采样
  ② 任一：
     a) L4-NAT-005 入/出比例 < 0.1
     b) L4-FW-007 PVM SYN_SENT >= 30 且 age >= 15s
     c) L5-PORT-006 GVM SYN_SENT >= 15 且 age >= 10s

DOWNSTREAM_PACKET_LOSS = WARN  当且仅当：
  ① UNREPLIED >= 5%  OR
  ② NAT 入/出比例 < 0.5  OR
  ③ PVM SYN_SENT >= 10
```

#### §9.3 触发动作矩阵新增行

| Watchdog 信号 | 立即采集 sections | 触发 probe burst | 抓包 |
|---|---|---|---|
| `WD_PVM_CONNTRACK_UNREPLIED` | `conntrack_state_stats, ss_syn_sent, iptables_nat_Lnv(若 conntrack<80%)` | 该 VLAN SHU 加紧 5×1s | 30s tcpdump on `eth1.X`（仅 conntrack <90% 时启用） |
| `WD_PVM_NAT_ASYMMETRY` | 同上 + `nat_symmetry_history.jsonl` 滚动窗 | 同上 | 同上 |
| `WD_PVM_TCP_SYN_STUCK` | `ss_syn_sent, conntrack_state_stats` | — | — |
| `WD_GVM_TCP_SYN_STUCK` | GVM `ss_syn_sent, ip_route, dumpsys_brief` + NDGA push 触发 PVM 上述采集 | — | — |

### 24.5 新增/修改采集器 sections

#### §11.5 PVM 命令白名单追加

| Section | 命令实现 | 超时 | 输出上限 | 并行组 | 高压跳过 |
|---|---|---|---|---|---|
| `conntrack_state_stats` | 自实现 (见下) | 3s | 16 KiB | B | 跳过 `conntrack ≥95%` |
| `conntrack_unreplied_sample` | 自实现：抽样 20 条 UNREPLIED 详情 | 3s | 16 KiB | B | 同上 |
| `ss_syn_sent` | `ss -tn state syn-sent` | 3s | 64 KiB | A | ✓ 始终执行 |
| `nat_symmetry_history` | 内部状态（无外部命令） | — | 4 KiB（每周期 append 一行）| — | — |

##### `conntrack_state_stats` 实现伪码

```cpp
// 不调用 conntrack 工具（PVM busybox 无），直接读 /proc/net/nf_conntrack
ConntrackStateStats CollectStats() {
    ConntrackStateStats s{};
    FILE* f = fopen("/proc/net/nf_conntrack", "r");
    char line[1024];
    while (fgets(line, sizeof line, f)) {
        s.total++;
        if (strstr(line, "[UNREPLIED]"))  s.unreplied++;
        if (strstr(line, "[INVALID]"))    s.invalid++;
        if (strstr(line, "ESTABLISHED"))  s.established++;
        if (strstr(line, "SYN_SENT"))     s.syn_sent++;

        // 按 dst_ip 反推 VLAN（取出 dst=172.16.X.40 提 X，映射 VLAN）
        UpdateVlanBucket(line, s);

        // 容量保护：解析行数超过 5000 立即 break，写入 truncated=true
        if (s.total >= 5000) { s.truncated = true; break; }
    }
    fclose(f);
    return s;
}
```

输出 JSON 格式：

```jsonc
{
  "ts_boot_ms": 18234567,
  "total":      856,
  "unreplied":  142,
  "invalid":    8,
  "established":650,
  "syn_sent":   12,
  "unreplied_pct": 16.6,
  "by_vlan": {
    "VLAN3": {"total":300,"unreplied":80,"unreplied_pct":26.7},
    "VLAN4": {"total":50, "unreplied":2, "unreplied_pct":4.0},
    "VLAN6": {"total":120,"unreplied":40,"unreplied_pct":33.3},
    "VLAN7": {"total":80, "unreplied":15,"unreplied_pct":18.8},
    "VLAN8": {"total":306,"unreplied":5, "unreplied_pct":1.6}
  },
  "truncated": false
}
```

##### `nat_symmetry_history` 滚动窗内部状态

`/log/perf/network_diag/state/nat_symmetry.jsonl`，60s 一行 append：

```jsonc
{"ts_boot_ms":18234567,
 "VLAN3":{"snat_out":15234,"dnat_in":15102,"delta_out":120,"delta_in":118,"ratio":0.98},
 "VLAN4":{"snat_out":234,  "dnat_in":230,  "delta_out":5,  "delta_in":5,  "ratio":1.0},
 "VLAN6":{"snat_out":12000,"dnat_in":3000, "delta_out":400,"delta_in":15, "ratio":0.04} ← 告警}
```

文件大小：每行 ~500 字节 × 24h × 60 = 720 KiB/天，retention 跟 probes 一样 24h。

#### §11.6 GVM 命令白名单追加

| Section | 命令 | 超时 | 输出上限 | 并行组 |
|---|---|---|---|---|
| `ss_syn_sent` | `ss -tn state syn-sent` | 3s | 32 KiB | A |
| `conntrack_state_stats` | 自实现读 GVM `/proc/net/nf_conntrack`（GVM 有 stats 文件，但本检查不依赖它） | 3s | 16 KiB | B |

> GVM `conntrack_state_stats` 仅辅助证据，不作为 GVM 端单独的 FAIL 来源——GVM 内核的 conntrack 跟 PVM NAT 内核是两个 netfilter 实例，主证据在 PVM。

### 24.6 性能预算（追加 §17）

| 操作 | 频率 | CPU P95 | IO | 备注 |
|---|---|---|---|---|
| `conntrack_state_stats` 60s | 1/min | 150 ms | 256-512 KiB read | 5000 entries 上限保护 |
| `WD_PVM_NAT_ASYMMETRY` (iptables -L -nv) 60s | 1/min | 200 ms | 32 KiB | G13 在高 conntrack 时自动跳过 |
| `WD_PVM_TCP_SYN_STUCK` (ss) 30s | 2/min | 30 ms | 8 KiB | 极轻 |
| `WD_GVM_TCP_SYN_STUCK` (ss) 30s | 2/min | 30 ms | 8 KiB | 极轻 |
| `nat_symmetry_history` jsonl 写 | 1/min | <5 ms | 0.5 KiB write | tmpfs |

**常态新增 CPU 占用**：约 400 ms/min ≈ 0.7%（单核），可接受。  
**异常态新增 CPU**：watchdog 触发后单次 collect 增加 200-400 ms，仍在 §17.2 异常态预算内。

### 24.7 新增测试用例

加入 §19.1：

| TC | 构造条件 | 预期结果 | 30s 内识别？ |
|---|---|---|---|
| **TC-NET-024** | 故障注入：删除 PVM iptables PREROUTING DNAT for VLAN3 中的一条规则（保留 SNAT），App 发起 HTTPS 请求 | 60s 内触发 `DOWNSTREAM_PACKET_LOSS(VLAN3)`：UNREPLIED 比例 ≥20% + NAT 入/出比例 <0.1 双信号合并 → FAIL；root cause 准确指向"下行 NAT 反向规则缺失" | ⚠️ 60s 边缘（conntrack 解析周期）|
| **TC-NET-025** | 故障注入：手动 `conntrack -F` 清空所有 NAT 表项后立即让 App 发起 HTTPS 请求（模拟 conntrack timeout 触发的下行回包丢失） | 30-60s 内触发 WARN→FAIL，UNREPLIED 比例急速上升；GVM SYN_SENT 累积 | ⚠️ 60s 边缘 |

故障注入接口仅 userdebug 启用（已设计）：

```jsonc
{"action":"netdiag.test_fault",
 "args":{"fault_type":"downstream_loss",
         "vlan":3,
         "method":"delete_dnat_rule",
         "duration_sec":120}}
```

### 24.8 不依赖 App 的保证（关键设计原则）

| 信号 | 数据采集层 | 依赖 App 集成？ |
|---|---|---|
| L4-FW-006 conntrack UNREPLIED | 内核 netfilter（`/proc/net/nf_conntrack`）| ❌ 完全不依赖 |
| L4-NAT-005 NAT 计数对称性 | 内核 netfilter（`iptables -L -nv`）| ❌ 完全不依赖 |
| L4-FW-007 PVM TCP SYN_SENT | 内核 sock 表（`ss`）| ❌ 完全不依赖 |
| L5-PORT-006 GVM TCP SYN_SENT | 内核 sock 表 | ❌ 完全不依赖 |

**关键论证**：上述四类信号都是**内核态被动观测**，由 PVM/GVM diag 进程周期采集，不需要任何应用层 SDK 集成。即便业务 App（地图、媒体、第三方）从未调用 `Polaris.reportNetworkTrouble()`，只要业务 App **有上行流量**（即便没有重试），就会在 conntrack / iptables 计数器 / TCP 状态表里留下指纹，被 watchdog 抓到。

**唯一前提**：业务 App 至少发出过几个上行包（建立连接、发送请求）。这是"App 用过网络"的最弱前提，正常车机场景必然满足。

### 24.9 受影响章节小结（v1.1 跨章节修订点）

| 原章节 | v1.1 修订内容 |
|---|---|
| §6.5 L4 NAT/防火墙 | 新增 L4-FW-006/007, L4-NAT-005 |
| §6.7 L5 服务/端口 | 新增 L5-PORT-006 |
| §8.1 事件 ID | 新增 `NETDIAG_DOWNSTREAM_LOSS` |
| §8.3 事件聚合 | `NETDIAG_DOWNSTREAM_LOSS` 优先级 rank 4（与 GATEWAY_UNREACHABLE 同级，可单独成根）|
| §9.1 PVM Watchdog | 新增 3 信号 |
| §9.2 GVM Watchdog | 新增 1 信号 |
| §9.3 信号→动作矩阵 | 新增 4 行 |
| §11.5/§11.6 命令白名单 | 新增 4 sections |
| §17 性能预算 | 新增条目 |
| §19 测试用例 | 新增 TC-NET-024/025 |
| §22 设计决策 | 新增"上下行差分检测靠内核 netfilter 状态" |
| §23 版本历史 | 1.0 → 1.1 |
| fault_class 字典 | 27 → 28 项，含 `DOWNSTREAM_PACKET_LOSS` |

---

## 25. Fault ID 体系与 Boot 早期补归因（B1 + B2.③a）

> **背景**：v1.0 没有定义 PVM 与 GVM 跨端事件关联机制；B2 讨论后确定方向 **③a**：PVM 在 GVM 起来前可独立上报；GVM 启动后**立即**对仍 ACTIVE 的 fault 补根因归因，Boot Warmup 结束后视需要 refine。
>
> 本节定义具体协议字段、状态文件格式、跨端时序、跨章节修订点。

### 25.1 fault_id / correlation_id 生成规则

```
correlation_id = murmur3_64( fault_class || ":" || target_key )[0..8 hex]
fault_id       = murmur3_64( pvm_boot_id_short || ":" || correlation_id )[0..16 hex]

其中:
  pvm_boot_id_short = first 16 hex of /proc/sys/kernel/random/boot_id (PVM 内核)
  fault_class       = 见 fault_class 字典 (28 项 + UNKNOWN)
  target_key        = 字典中每个 class 配套的 key 抽取规则
```

**关键点**：

- **使用 PVM 的 boot_id 作为全局 epoch**，由 GVM 通过 NDGA hello 同步获取
- `correlation_id` 不含 boot_id，用于云端跨 boot 复发统计
- `fault_id` 含 boot_id，每次重启同类故障算出不同 fault_id（同一物理 boot 内则相同）
- 两端独立可算（前提：双端共享 fault_class 字典 + pvm_boot_id 已同步）

### 25.2 pvm_boot_id 同步协议（NDGA hello 扩展）

NDGA hello 帧扩展（修订 §4.1.2）：

```jsonc
// GVM → PVM (client 发起)
{"msg":"hello","version":1,"role":"gvm",
 "gvm_diag_version":"1.1.0",
 "gvm_boot_id":"9e8f7a6b5c4d3e2f1",
 "gvm_config_sha256":"...","gvm_dict_sha256":"..."}

// PVM → GVM (server 应答)
{"msg":"hello","version":1,"role":"pvm",
 "pvm_diag_version":"1.1.0",
 "pvm_boot_id_short":"f0b8c3a5e1d27a89",   // ★ 16 hex (64-bit)
 "pvm_boot_ts_unix": 1747787985,            // PVM 启动绝对时间
 "pvm_config_sha256":"...","pvm_dict_sha256":"...",
 "pvm_active_faults_count": 1}              // 提示 GVM 是否需要扫 active_faults.json
```

GVM 收到 hello response 后：

1. 缓存 `pvm_boot_id_short` 到内存（不持久化，每次启动重新拿）
2. 校验 `config_sha256` / `dict_sha256` 一致；不一致打 FAIL 告警并降级（仅使用本地配置）
3. 若 `pvm_active_faults_count > 0`，**触发补归因扫描**（见 §25.5）

### 25.3 active_faults.json 持久化（D3 落地 + B2 共享）

文件路径：`/log/perf/network_diag/state/active_faults.json`  
所有者：PVM diag 进程；GVM diag 只读访问（通过 `/mnt/vendor/log/perf/...`）。

```jsonc
{
  "schema_version":      "1.1",
  "pvm_boot_id_short":   "f0b8c3a5e1d27a89",
  "pvm_boot_ts_unix":    1747787985,
  "updated_ts_boot_ms":  15300,
  "faults": [
    {
      "fault_id":         "a1b2c3d4e5f60718",
      "correlation_id":   "d4e5f607",
      "fault_class":      "LINK_DOWN",
      "target_key":       "eth1",
      "state":            "ACTIVE_NEW" | "ACTIVE_ONGOING" | "RECOVERED",
      "severity":         "FAIL",
      "first_seen_ts_boot_ms":  15200,
      "first_seen_ts_unix":     1747788015,
      "last_update_ts_boot_ms": 15200,
      "evidence_count":         1,
      "flap_count":             0,
      "manifest_path_short":    "i/20260511/a1b2",
      "side_event_emitted":     true,
      "gvm_root_cause_emitted": false,        // ★ GVM 是否已补 root cause
      "recovered_ts_boot_ms":   null,         // 若 RECOVERED，填恢复时间
      "duration_ms":            null
    }
  ]
}
```

**写入策略**：

- 状态变化时才写盘（ACTIVE_NEW / RECOVERED / severity 变 / evidence_count 变）
- 写入用 `rename(2)` 原子提交（写 `.tmp` → rename）
- GVM 永不写此文件，只读取
- retention：与 incident_dir 一致，进程退出/重启时**保留**

### 25.4 事件 payload `cls` 字段三态语义

| cls 值 | 含义 | 发起方 | 触发时机 |
|---|---|---|---|
| `side` | 单端观测事实，未跨端归因 | PVM / GVM | watchdog 触发立即发出；boot 早期 PVM 独立场景；fallback 场景 |
| `root` | 跨端归因结论 | **GVM**（唯一） | 正常路径：GVM 收到 PVM side event 后汇总；Boot 补归因路径：GVM 启动后扫 active_faults.json 补 |
| `recov` | 故障恢复 | 探测到 RECOVERED 的那一端（通常 PVM 物理层先看到）| 恢复后 debounce 5s |

辅助字段：

| 字段 | 含义 |
|---|---|
| `fp:1` | first_pass —— GVM 在 Boot Warmup 期内的 root cause incident，证据偏弱 |
| `fp:0` | full —— 跨端证据完整 |
| `refined:1` | 跟一个 first_pass 的 incident 关联，发了 refined 版本 |
| `dq` | data_quality 速记：`"p1g1"` (pvm/gvm 都 complete=1)、`"p1g0"` (gvm 缺)、`"p1gf"` (gvm first_pass) |

### 25.5 GVM 启动补归因流程（B2.③a 时序）

```
T+0       GVM net_diagd 启动
T+0-2s    Bootstrap (config + capability)
T+2-5s    NDGA connect + hello 退避重试
T+5s      hello 成功，获取 pvm_boot_id_short + pvm_active_faults_count

T+5.5s    if pvm_active_faults_count > 0:
              扫 /mnt/vendor/log/perf/network_diag/state/active_faults.json
              过滤 state IN ("ACTIVE_NEW","ACTIVE_ONGOING") 的条目
              for each fault f:
                  本地 GVM active_faults_map[f.fault_id] = {
                      fault_class, target_key, severity,
                      first_seen_ts_boot_ms_pvm: f.first_seen_ts_boot_ms,
                      awaiting_root_cause: true,
                      first_pass_emitted: false
                  }

T+6s      并行启动两件事：
          (A) 立即对 awaiting fault 做轻量补归因（不等 Boot Warmup）：
              - 采 GVM 静态：ip_addr / ip_route_all / ip_rule / ip_neigh /
                            ss_listen / dumpsys_brief / proc_net_dev /
                            carrier_changes
              - NDGA request PVM: fetch manifest summary (不重新触发 PVM 取证)
              - 把 GVM 证据写入同一 incident_dir 的 gvm/ 子目录
              - 更新 manifest.json: data_quality.gvm = "first_pass"
                                    + gvm_observations 段
                                    + root_cause_consolidated 段
              - 发 polaris event:
                {v:1, src:"and", cls:"root", st:"fail",
                 fid:f.fault_id, cid:f.correlation_id,
                 chk:..., rc:f.fault_class, tk:f.target_key,
                 sev:3, tsb:6500, dur:0,
                 mp:f.manifest_path_short,
                 fp:1,  dq:"p1gf"}
              - first_pass_emitted = true
          (B) 进入 GVM 自身 Boot Warmup (120s)
              expected end: T+126s
              期内不停止补归因；Warmup 不影响补归因（补归因优先级高）

T+126s    Boot Warmup 结束
          遍历 awaiting_root_cause = true 的 fault，逐个 refine 判定：
              if PVM 已发 recovery event for fault_id:
                  awaiting_root_cause = false
                  跳过 (无需 refine)
              elif severity / target / impact_set 跟首次 first_pass 时一样:
                  跳过 (无新证据)
              else:
                  跑 SHU probe burst
                  采 GVM 完整证据 (复用 §11.6 GVM 全集)
                  NDGA request PVM 最新 manifest
                  更新 incident_dir + manifest.json
                  发 polaris event:
                    {... fp:0, refined:1, dq:"p1g1"}
                  awaiting_root_cause = false
```

### 25.6 manifest.json 跨端更新规则

避免读写竞态（A3 约束）：

| 时刻 | 写入方 | 写入字段 |
|---|---|---|
| T_PVM 触发 fault | PVM | 完整 manifest.json（PVM 视角），写 `data_quality.gvm = "unavailable:gvm_not_ready"` |
| GVM 启动后补归因 | GVM | **追加** `gvm_observations` + `root_cause_consolidated` + `evidence_index` 中的 gvm/ 条目；更新 `data_quality.gvm` |
| PVM 检测恢复 | PVM | **追加** `recovery` 段（recovered_ts_boot_ms / duration_ms） |

**约束**：

- 双端**不同时写**同一文件（A3 用户已确认）
- 每次写都是先写 `.tmp` → rename 原子提交
- 字段层级隔离：PVM 不动 gvm_* 字段，GVM 不动 pvm 视角字段（PVM 视角段 + recovery 段属 PVM 写）
- 极小重叠区 `data_quality`：约定 PVM 仅写 `pvm` 子字段，GVM 仅写 `gvm` 子字段，互不覆盖
- GVM 修改完成后通过 NDGA push `manifest_updated{fault_id}` 通知 PVM（PVM 不主动读，仅做记录）

### 25.7 边界情况处理

| 边界 | 处理 |
|---|---|
| GVM 启动时 fault 已 RECOVERED | 不补归因；云端凭 PVM side event + recovery 闭环 |
| GVM 启动时 PVM 已经 crash 重启过（pvm_boot_id 已变化）| `active_faults.json` 中的 pvm_boot_id_short 与 hello 返回不一致 → 整个文件视为陈旧，全部跳过 |
| 读 active_faults.json 失败 / 文件损坏 | log WARN，进入"无遗留 fault"模式 |
| 共享挂载 `/mnt/vendor/log` 不可访问 | GVM 进入降级：只用自己未来感知到的 fault 走正常 F16 路径；无法补归因 |
| GVM 补归因期间 PVM 又上报了 delta（severity 升级）| GVM 把 delta 也合并进 first_pass 的 root cause（重新算 root_cause_consolidated）|
| 补归因 NDGA RPC 超时 | first_pass 仅用 GVM 视角 + active_faults.json 中静态信息出 root cause；标 `dq:"p1?gf"`（PVM 部分不确定）|
| Boot Warmup 期内 fault 演化为另一个 fault_id | 旧 fault refine 跳过；新 fault 走正常 F16 |

### 25.8 跨章节修订总览

| 章节 | v1.1 修订 |
|---|---|
| §4.1.2 NDGA hello 帧 | 新增 `pvm_boot_id_short` / `pvm_boot_ts_unix` / `pvm_active_faults_count` / config & dict sha256 |
| §8.1 事件 payload schema | `cls` 字段三态枚举；新增 `fp` / `refined` / `dq` 字段 |
| §8.3 事件因果聚合 | 聚合键扩展：同 fault_id 下 side + root + recov 自动归一组 |
| §11.5/§11.6 命令白名单 | 增加 `active_faults_state`（read-only mount path）|
| §13 时钟与时序 | pvm_boot_id 作为全局 epoch；GVM 计算 fault_id 时使用同步过来的 pvm_boot_id_short |
| §17 性能预算 | 补归因新增开销：GVM 启动后单次约 200-500 ms（同时采 GVM 静态 + NDGA RPC）|
| §22 设计决策 | 新增 "B2.③a：补归因即时进行 + Boot Warmup 后视情况 refine" |

### 25.9 性能影响

| 操作 | 频率 | CPU P95 | 备注 |
|---|---|---|---|
| GVM 启动期补归因（首次） | 每个 ACTIVE fault 一次 | 200-500 ms | 包含 GVM 静态采集 + NDGA RPC + manifest 更新 |
| Boot Warmup 后 refine | 仅必要时（fault 仍 ACTIVE + 有新证据） | 500-1500 ms（含 probe burst） | 通常一个 boot 周期 0-1 次 |
| active_faults.json 写盘 | 状态变化时 | <10 ms | < 1 次/分钟 |
| NDGA hello 扩展字段 | 启动一次 | <5 ms | 增加帧大小 ~80 字节 |

补归因不在常态运行路径上，**对 steady-state CPU 占用零影响**。

---

## 26. Polaris 事件上云策略（B3.②）

> **背景**：B2.③a 决策下每个 fault 会产生 side / root / recov 三类事件，全发到云端造成 polaris 事件预算冗余。B3 讨论后确定方向 **②**：**条件性发 side** —— GVM 在线时不发 side（直接发 root），仅在 GVM 离线/Boot 早期/NDGA 断开时由 PVM 兜底发 side 保证不漏报。
>
> 目标：稳态下 polaris 事件数 3→2（节省 33%）；异常态保持完整覆盖。

### 26.1 事件发送决策矩阵

| 检测方 | GVM 在线 + NDGA 通畅 | GVM 离线 / Boot 早期 / NDGA 断开 ≥ 60s |
|---|---|---|
| **PVM watchdog 检测 fault** | PVM 通过 NDGA push `fault_alert` 给 GVM；**PVM 不直接发 polaris side event**；GVM 在 ≤3s 内发 `cls:root` | **PVM 发 polaris side event 兜底**；GVM 起来后按 B2.③a 补 root |
| **GVM watchdog 检测 fault** | GVM 直接发 polaris root event；通过 NDGA pull PVM 视角合并 | GVM 走 fallback：发 polaris side event（经 polaris 事件链兜底）|
| **App 主动报障** | GVM 收到 → 跑 SHU 检查 → 发 root | (Boot 早期 App 不会上线，不存在此场景) |
| **故障恢复** | 检测方直接发 `cls:recov` | 同左 |

**决策原则**：

- root event 是云端期望的主事件（含跨端归因）
- side event 仅作为"GVM 不可达时 PVM 兜底"，避免 polaris 漏报
- 同一 fault_id 下，云端最多看到 1 条 side + 1 条 root + 1 条 recov，且通常 root 替代 side

### 26.2 NDGA online 状态判定（PVM 侧）

```c
class NdgaChannelState {
    bool connected;              // tcp/vsock 层 connect 成功
    bool hello_completed;        // peer 已发 hello + 校验通过
    uint64_t last_heartbeat_recv_boot_ms;  // 最近一次收到 peer 心跳
    
    bool is_online() {
        return connected
            && hello_completed
            && (boot_ms_now() - last_heartbeat_recv_boot_ms) < 10000;  // 10s 内有心跳
    }
};
```

PVM 在 watchdog 触发 fault 时**实时查询** `is_online()` 决定发送路径：

```c
void on_fault_detected(Fault f) {
    if (channel_state.is_online()) {
        // GVM 在线：通过 NDGA push 通知，等 GVM 发 root
        ndga_push("fault_alert", f);
        schedule_side_fallback_timer(f, kSideFallbackTimeoutMs);  // 见 26.3
    } else {
        // GVM 离线/未就绪：PVM 兜底发 side
        emit_polaris_event(f, /*cls=*/"side");
    }
    // active_faults.json 写盘（两种路径都做）
    persist_active_fault(f);
}
```

### 26.3 防漏报兜底：PVM 侧 fallback timer

GVM 在线时 PVM 不发 side，但万一 GVM 收不到 push（NDGA 心跳延迟、PVM 假判 online）会丢事件。需要兜底：

```c
static const int kSideFallbackTimeoutMs = 8000;  // 8 秒

void schedule_side_fallback_timer(Fault f, int timeout_ms) {
    // 8 秒后检查 GVM 是否已发 root
    timer_after(timeout_ms, [f]() {
        if (!gvm_root_event_acked_for(f.fault_id)) {
            LOGW("GVM root cause not received in 8s for fault_id=%s, "
                 "emitting PVM side as fallback", f.fault_id);
            emit_polaris_event(f, /*cls=*/"side");
        }
    });
}
```

GVM 发出 root event 后通过 NDGA push `root_emitted{fault_id}` 通知 PVM，PVM 取消对应 fallback timer。

**8s 超时的依据**：B2 时序中 GVM 补归因典型耗时 200-500 ms，加 NDGA 往返 100-300 ms，正常 1s 内能完成。8s 给足容错；超时则推测 GVM 不可用，兜底发 side。

### 26.4 事件流场景对照

#### 场景 A：Boot 早期 fault（GVM 还没起来）

```
T+15.0s   PVM detect link DOWN
T+15.0s   PVM check NDGA online → false (GVM 未启动)
T+15.2s   PVM 直接 emit polaris side event → mOfflineCache
T+55s     GVM polarisd flush cache → Cloud receives side event
T+62s     GVM 补归因 emit root event → Cloud receives root event
T+200.7s  PVM detect recovery → emit recov event → Cloud

Cloud 视角：fault_id=a1b2 收到 [side, root(fp:1), recov] 3 条事件
```

#### 场景 B：稳态 fault（GVM 在线）

```
T+1000.0s  PVM detect link DOWN
T+1000.0s  PVM check NDGA online → true
T+1000.1s  PVM NDGA push fault_alert{fault_id=b3c4...} → GVM
T+1000.1s  PVM schedule fallback timer (8s)
T+1000.4s  GVM 收到 push，采集 GVM 视角 + NDGA pull PVM manifest
T+1002.0s  GVM emit root event → Cloud receives root
T+1002.0s  GVM NDGA push root_emitted{fault_id=b3c4} → PVM
T+1002.1s  PVM cancel fallback timer
T+1100.0s  PVM detect recovery → emit recov event → Cloud

Cloud 视角：fault_id=b3c4 收到 [root(fp:0), recov] 2 条事件（省 1 条）
```

#### 场景 C：GVM 假在线（NDGA 心跳延迟）

```
T+2000.0s  PVM detect fault
T+2000.0s  PVM check NDGA online → true (心跳 9.8s 前刚收到，刚好低于 10s)
T+2000.1s  PVM NDGA push → 实际 GVM 已 hang，push 阻塞 / drop
T+2000.1s  PVM schedule fallback timer (8s)
T+2008.1s  Timer 触发，gvm_root_event_acked == false
T+2008.2s  PVM 兜底 emit polaris side event → Cloud
T+2008.3s  PVM 标记 NDGA online = false（heartbeat 已超 10s）
T+...      GVM 恢复后按 B2.③a 补 root（即使延迟）

Cloud 视角：fault_id=... 收到 [side(delay 8s), root(later), recov] —— 仍完整
```

#### 场景 D：NDGA 持续断开

```
T+3000.0s  NDGA disconnect (heartbeat 超 10s)
T+3000.0s  PVM 标记 NDGA online = false
T+3050.0s  PVM detect fault
T+3050.0s  PVM check NDGA online → false
T+3050.1s  PVM 直接 emit side event → Cloud
T+3200.0s  PVM detect recovery → emit recov event → Cloud
T+...      NDGA 重连后，GVM 按 B2.③a 补归因（如果 fault 还 ACTIVE）

Cloud 视角：fault_id=... 收到 [side, recov] 2 条（fault 已恢复，GVM 不补 root）
```

### 26.5 GVM 侧补充规则

#### 26.5.1 GVM 收到 NDGA `fault_alert` push 后

```c
void on_ndga_fault_alert(FaultAlertPayload p) {
    // 1. 本地 active_faults_map[p.fault_id] = ACTIVE_NEW，标 awaiting_root_cause
    // 2. 并行：
    //    (a) 启动 GVM 视角采集
    //    (b) NDGA pull PVM manifest summary
    // 3. 完成后合并 → emit polaris root event
    // 4. NDGA push root_emitted{p.fault_id} 给 PVM (取消 fallback timer)
}
```

#### 26.5.2 GVM 自己 watchdog 触发 fault（不来自 PVM）

```c
void on_gvm_watchdog_fault(Fault f) {
    // 算 fault_id (使用缓存的 pvm_boot_id_short)
    // 查本地 active_faults_map，如果已在（PVM 也感知到）→ 续期
    // 如果不在 → 这是 GVM 独立发现的 fault
    //   - NDGA push fault_alert_from_gvm{fault_id} 给 PVM
    //   - PVM 跑 PVM 视角采集，回 NDGA response
    //   - GVM 合并 → emit polaris root event
}
```

PVM 端被动响应（接受 GVM 反向 push）：

```c
void on_ndga_fault_alert_from_gvm(FaultAlertPayload p) {
    // PVM 采集自己视角，写 manifest，回 response
    // 不主动发 polaris side event（GVM 会出 root）
    // 但仍写 active_faults.json，方便 PVM 自己后续判断
}
```

### 26.6 跨章节修订总览

| 章节 | v1.1 修订（B3.② 落地） |
|---|---|
| §4.1.3 NDGA RPC method | 新增 `fault_alert` push 类型（PVM→GVM、GVM→PVM 双向）+ `root_emitted` ack push |
| §8.3 IncidentDeduper | 增加"NDGA online check" 分支：在线时不直接发 side |
| §17 性能预算 | 稳态 polaris 事件数估算下调（每 fault 平均 2 条而非 3 条）|
| §20 风险与降级 | 增加"GVM 假在线导致 side 漏发"风险 → 8s fallback timer 兜底 |
| §22 设计决策 | 新增 "B3.②：side 条件发出（NDGA online 时不发）" |

### 26.7 性能影响

| 维度 | B3.①（全发） | B3.②（改良） | 增量 |
|---|---|---|---|
| 稳态每 fault 事件数 | 3 | 2 | **-33%** |
| 异常/boot 每 fault 事件数 | 3 | 3 | 0 |
| 端侧 polaris 事件 buffer 占用 | 100% | 67% | **节省 33%** |
| PVM 端额外逻辑 | 0 | NDGA online check + fallback timer | 微 |
| GVM 端额外逻辑 | 0 | root_emitted ack push | 微 |

### 26.8 风险与缓解

| 风险 | 缓解 |
|---|---|
| GVM 假在线（NDGA 心跳延迟）导致 side 漏发 | 8s fallback timer 兜底 + heartbeat 10s 超时严格 |
| Fallback timer 误触发（GVM 正在采集但还没发 root）| timer 8s 足够 GVM 完成补归因（典型 1-2s）|
| 同一 fault 既有 side（fallback）又有 root | 云端按 fault_id 折叠（side 自动归到 root 下）|
| PVM 触发兜底 side 后 GVM 又发出 root | cls=root 优先，cls=side 折叠展示 |
| NDGA online 状态读取竞态 | 实现用 atomic load；查询和发送之间间隔 < 100ms |

---

## 27. Fault 演化轨迹与因果链（B4.③）

> **背景**：同一 fault 的 severity 升级、影响 SHU 集合扩大、或派生出下游 fault 时，如何在事件流和 manifest 中体现？B4 讨论后确定方向 **③**：**fault_id 由 hash 锁定永不变**，演化轨迹记录在 manifest `evolution[]`，派生 fault 通过事件 payload `cb`（caused_by）字段引用上游。

### 27.1 Fault ID 锁定规则

| 触发 | 是否新 fault_id？ | 是否发新事件？ |
|---|---|---|
| 同 fault_class + 同 target_key，severity / impacts / root check_id 演化 | ❌ **fault_id 不变** | 仅在"显著演化"时发 delta event；同 fault 事件 ≤ 2 次（D4） |
| 同 fault_class，target_key 不同 | ✅ 新 fault_id | 走正常流程 |
| 不同 fault_class | ✅ 新 fault_id | 走正常流程 |
| 因果上下游派生 fault | ✅ 新 fault_id | 事件 payload 带 `cb` 字段指向上游 fault_id |

### 27.2 "显著演化"判定（复用 D4 + 细化）

`evolution[]` 数组每次写入但不一定 emit polaris event。**只有满足以下任一**才 emit `cls:root, refined:1` 事件（受 D4 max=2 约束）：

1. severity 升级（WARN → FAIL）
2. 影响 SHU 集合**新增** > 1 个（已影响 1 个，又多出 1 个不算；多出 2 个及以上才算）
3. root_cause check_id 改变（如从 `L1-LK001` 演化为 `L1-LK001+L4-FW-006`）
4. 持续时长跨过显著阈值（>5 分钟、>30 分钟、>2 小时）—— 仅作 INFO 级 ongoing log，**不**算入 D4 max 计数

**不算显著演化**（仅写 manifest.evolution[]，不发 polaris event）：

- 单 SHU 内 RTT / loss 数值变化
- 派生事件清单微调
- 影响 SHU 仅新增 1 个

### 27.3 manifest.json `evolution[]` schema

```jsonc
"evolution": [
  {
    "ts_boot_ms":     0,
    "severity":       "WARN",
    "rule":           "slope_loss_2pct",        // 触发判定的具体 check rule
    "impacts":        ["SHU_VLAN3_INTERNET"],   // 当前影响 SHU 集合（完整）
    "impacts_added":  ["SHU_VLAN3_INTERNET"],   // 此次新增
    "delta_event_emitted": true,                // ACTIVE_NEW 首发，必发
    "evidence_count_at_this_point": 1
  },
  {
    "ts_boot_ms":     30000,
    "severity":       "FAIL",                   // ★ 升级
    "rule":           "slope_loss_30pct",
    "impacts":        ["SHU_VLAN3_INTERNET","SHU_DNS"],
    "impacts_added":  ["SHU_DNS"],
    "delta_event_emitted": true,                // 显著演化 emit 第二条
    "evidence_count_at_this_point": 2,
    "trigger_reason": "severity_escalation"
  },
  {
    "ts_boot_ms":     75000,
    "severity":       "FAIL",
    "impacts":        ["SHU_VLAN3_INTERNET","SHU_DNS","SHU_VLAN6_ADCU_PARK"],
    "impacts_added":  ["SHU_VLAN6_ADCU_PARK"],
    "delta_event_emitted": false,               // 仅 1 个新增 + severity 未变 → 不发
    "evidence_count_at_this_point": 2           // 跟 D4 max=2 一致，不再 emit
  },
  {
    "ts_boot_ms":     180000,
    "severity":       "FAIL",
    "impacts":        ["SHU_VLAN3_INTERNET","SHU_DNS","SHU_VLAN6_ADCU_PARK"],
    "impacts_added":  [],
    "delta_event_emitted": false,
    "duration_milestone": "5min",              // 跨过 5 分钟阈值 → ongoing log
    "ongoing_log_emitted": true
  }
]
```

### 27.4 派生 fault 的因果链（`cb` 字段）

#### 27.4.1 事件 payload 新增字段

```json
{"v":1,"src":"pvm","cls":"side","st":"fail",
 "fid":"z9z0...","cid":"...","chk":"...","rc":"SERVICE_DOWN","tk":"xdja_idps",
 "sev":2,"tsb":60000,"dur":0,"mp":"i/.../z9z0",
 "cb":"a1b2c3d4e5f60718"}   // ★ caused_by: upstream fault_id
```

`cb` 字段：

- 类型：16 hex 字符（与 fault_id 同长）
- 长度成本：约 21 字节（field name + value），仍在 726 字节预算内
- 可选：仅当端侧能确认因果关系时才附；否则不附

#### 27.4.2 因果关系判定方式

端侧维护 `fault_causation_graph`（共享配置 + 字典同步），定义已知的因果依赖：

```jsonc
// /etc/polaris/fault_causation_graph.json
{
  "schema_version": "1.0",
  "edges": [
    {
      "upstream":   {"class":"LINK_DOWN", "iface_match":"eth1"},
      "downstream": [
        {"class":"GATEWAY_UNREACHABLE", "vlan":[3,4,6,7,8,10,11,12,13,14],
         "max_lag_sec":30},
        {"class":"VM_LINK_BROKEN", "iface_match":"vmtap1.*",
         "max_lag_sec":10},
        {"class":"SERVICE_DOWN", "comm_in":["someipd"],
         "max_lag_sec":60,
         "_note":"网络断后 someipd 心跳超时退出"}
      ]
    },
    {
      "upstream":   {"class":"LINK_DOWN", "iface_match":"eth0"},
      "downstream": [
        {"class":"SERVICE_DOWN", "comm_in":["camera_server"],
         "max_lag_sec":30}
      ]
    },
    {
      "upstream":   {"class":"HYPERVISOR_DOWN"},
      "downstream": [
        {"class":"VM_LINK_BROKEN", "iface_match":"vmtap*",
         "max_lag_sec":5,
         "_note":"qcrosvm 死 → 所有 vmtap 进入异常"}
      ]
    },
    {
      "upstream":   {"class":"FORWARDING_DISABLED"},
      "downstream": [
        {"class":"GATEWAY_UNREACHABLE", "vlan":"any",
         "max_lag_sec":30},
        {"class":"DOWNSTREAM_PACKET_LOSS", "max_lag_sec":30}
      ]
    },
    {
      "upstream":   {"class":"CONNTRACK_PRESSURE"},
      "downstream": [
        {"class":"DOWNSTREAM_PACKET_LOSS", "max_lag_sec":60}
      ]
    }
    // ... 其余拓扑依赖按需扩展
  ]
}
```

#### 27.4.3 端侧识别逻辑

```c
optional<fault_id_t> infer_caused_by(Fault new_fault) {
    // 1. 在 active_faults_map 中查找近期 (max_lag_sec) 内的活跃 fault
    // 2. 遍历 fault_causation_graph.edges：
    //    - 若 new_fault 命中某条 edge 的 downstream
    //    - 且 active_faults 中存在该 edge 的 upstream fault
    //    - 且时间差 < max_lag_sec
    //    → 返回 upstream fault_id
    // 3. 找不到 → 返回 nullopt
    // 注意：因果识别是"最佳猜测"，错配也不致命（云端可二次验证）
}
```

调用点：

- PVM watchdog 检测到新 fault → 触发 `infer_caused_by()`
- GVM 收到 NDGA `fault_alert` → 在本地也查一次（GVM 视角可能补充因果）
- 事件 payload 组装时若 `cb` 非空则附上

#### 27.4.4 因果图配置文件治理

- 双端共享 `/etc/polaris/fault_causation_graph.json`（PVM）+ `/system/etc/polaris/fault_causation_graph.json`（GVM）
- 启动时双端 sha256 互校（同 scenario-registry.json 机制）
- 版本号跟 `fault_class_dict.json` 联动（dict 改时 graph 可能要改）

### 27.5 因果链上云后云端的展示

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Incident Causal Tree                                                    │
├─────────────────────────────────────────────────────────────────────────┤
│ [Root] fault_id=a1b2  LINK_DOWN(eth1)            T+15s   FAIL          │
│    │                                                                    │
│    ├─ [Derived] fault_id=e5f6  GATEWAY_UNREACHABLE(VLAN3_TBOX)         │
│    │              cb=a1b2                          T+15.5s FAIL         │
│    │                                                                    │
│    ├─ [Derived] fault_id=h7i8  VM_LINK_BROKEN(vmtap1.3)                │
│    │              cb=a1b2                          T+15.7s FAIL         │
│    │                                                                    │
│    └─ [Derived] fault_id=z9z0  SERVICE_DOWN(xdja_idps)                 │
│                   cb=a1b2                          T+60s   FAIL         │
└─────────────────────────────────────────────────────────────────────────┘
```

云端按 `cb` 构建 DAG，运维一眼看出根因 + 派生影响范围。如果运维点击根 fault，可看到完整 incident_dir 证据。

### 27.6 跨章节修订总览

| 章节 | v1.1 修订（B4.③ 落地） |
|---|---|
| §8.2 事件 payload schema | 新增可选字段 `cb`（caused_by）|
| §8.3 事件因果聚合 | 区分 "30s 窗口内聚合"（rank 优先级）与 "跨窗口因果链"（`cb`）；前者合并到根事件，后者用独立 fault_id + cb 引用 |
| §10/§12 取证 manifest | manifest.json 新增 `evolution[]` 段；retention 与原 manifest 一致 |
| §11 采集器 | 新增 `fault_causation_graph` 配置加载与 sha256 校验 |
| §17 性能预算 | `infer_caused_by()` 查询开销：每次 fault 检测时遍历活跃 fault（典型 < 5 条），<5 ms |
| §22 设计决策 | 新增 "B4.③：fault_id 锁定 + manifest evolution[] + cb 因果链" |

### 27.7 性能影响

| 操作 | 频率 | CPU P95 | 备注 |
|---|---|---|---|
| `infer_caused_by()` 查询 | 每个新 fault 一次 | < 5 ms | 内存表查询，活跃 fault 通常 < 5 条 |
| manifest.evolution[] append | 状态变化时 | < 10 ms | 原子 rename 写盘 |
| fault_causation_graph 加载 | 启动一次 | < 50 ms | 配置 < 8 KiB |

整体新增 CPU < 0.1%（单核），可忽略。

---

## 28. 决策汇总与 polaris 团队对齐清单

| 决策点 | 选择 | 落地章节 | 关键效果 |
|---|---|---|---|
| **B1** fault_id / correlation_id 生成 | R1 确定性 hash + PVM boot_id 全局 epoch | §25.1-2 | 双端独立可算；跨 boot 复发统计可用 |
| **B2** PVM 早于 GVM 上报 + GVM 起来后归因 | ③a 立即补归因，仅 ACTIVE，Boot Warmup 后视情况 refine | §25.3-7 | boot 早期 fault 也有完整 root cause |
| **B3** side / root / recov 上云策略 | ② 条件发 side（NDGA online 时不发，离线兜底）| §26 | 稳态 polaris 事件预算 -33% |
| **B4** fault 演化与因果链 | ③ fault_id 锁定 + manifest evolution[] + cb 因果链 | §27 | fault_id 端到端稳定；演化可追溯；因果链直观 |

**B 系列累计新增**：

- 2 个共享配置文件：`fault_class_dict.json` + `fault_causation_graph.json`
- 1 个 PVM 端持久化文件：`/log/perf/network_diag/state/active_faults.json`
- 4 个事件 payload 字段：`cls` / `fid` / `cid` / `cb`（+ 辅助 `fp`/`refined`/`dq`）
- 2 类 NDGA push 消息：`fault_alert` / `root_emitted` ack
- manifest.json 新增 4 段：`gvm_observations` / `root_cause_consolidated` / `evolution[]` / `data_quality`

**Polaris 团队对齐清单更新**（合并 B 系列）：

| 项 | 工作量 | 优先级 |
|---|---|---|
| 申请 event_id 段位 `0x4E5E_xxxx`（含 `NETDIAG_DOWNSTREAM_LOSS=0x4E5E0010`，共 ~19 个）| — | P0 |
| GVM sepolicy `network_diag.te`（VSOCK 9101 + /proc/net + `/mnt/vendor/log` 只读）| ~30 条 | P0 |
| ~~`polaris_command_listener_register` SDK 扩展~~ | — | **已撤销**（F1 确认通道 C 单向）|
| ~~`NetdiagBridgeAction` IAction~~ | — | **已撤销** |
| polarisd `mOfflineCache` 容量 500 是否足够（boot 早期短时大量 side event）| 评估 | P1 |

---

**文档结束**



