# 智能座舱网络诊断需求

> 基于《智能座舱网络拓扑系统设计与实现》制定  
> 适用平台：SA8397 智能座舱，PVM Linux + GVM Android + qcrosvm Hypervisor  
> 文档日期：2026-05-09  
> 文档目标：定义一套覆盖物理链路、VLAN、PVM/GVM 虚拟化网络、路由/NAT、防火墙、业务服务、性能与安全风险的网络诊断需求，确保网络问题可发现、可定位、可复现、可闭环。

---

## 1. 背景

智能座舱网络采用 PVM/GVM 双虚拟机架构：PVM Linux 直接占有物理网卡 `eth0`、`eth1`，承担物理 VLAN 接入、三层路由、iptables NAT、防火墙与车控/SOA 中间件承载；GVM Android 通过 virtio-net 接入 PVM 提供的 `vmtap` 后端，运行 HMI、诊断、地图、娱乐和部分工程服务。

系统中同时存在以下网络路径：

| 路径 | 说明 |
| --- | --- |
| PVM 物理链路 | `eth1` 连接 VCM trunk，承载 VLAN 3/4/6/7/8/10-14；`eth0` 连接 ADCU 视频/数据专线，承载 VLAN 15/19 |
| PVM-GVM 虚拟链路 | `vmtap0` 对应 Android `eth0`，作为 Host-Guest 控制通道；`vmtap1` 对应 Android `eth1` trunk，承载 VLAN 3/4/6/7/8 |
| 三层路由与 NAT | PVM 通过 `10.10.X.0/24` 到 `172.16.X.0/24` 的 SNAT/DNAT 映射，使 GVM 服务暴露到车载网络 |
| Android 多网络 | GVM 通过 fwmark、NetId、`ip rule` 和 per-network route table 控制应用选路 |
| PVM 私有业务面 | VLAN 10-14、15、19 的原始 VLAN/IP 仅 PVM 可见，承载 SOME/IP、NTP、RTSP 摄像头、ADCU SOME/IP 大数据等；选定数据可由 PVM 通信中间件经 `vmtap0` 受控转发给 Android |
| 视频旁路 | ADCU RTSP 到 PVM Camera Server，再经 mmhab 共享内存进入 GVM Camera Client，不走 iptables NAT |

网络诊断必须覆盖上述所有路径，避免只验证单一 ping 连通性而遗漏 VLAN、NAT、策略路由、服务端口、吞吐、抖动、安全暴露等问题。

---

## 2. 诊断目标

### 2.1 总体目标

网络诊断系统应实现以下目标：

1. 自动识别座舱当前网络拓扑状态，包括 PVM/GVM 接口、VLAN、IP、路由、iptables、业务端口与关键进程。
2. 对网络问题进行分层诊断，覆盖物理链路、二层 VLAN、三层 IP、四层端口、应用服务、虚拟化链路、NAT、防火墙、性能和安全配置。
3. 在故障发生时输出明确结论，包括故障域、影响 VLAN、可能根因、证据、建议操作和验证命令。
4. 支持主动巡检、故障触发诊断、手动专项诊断和诊断报告导出。
5. 诊断动作应安全可控，不应改变网络配置，不应中断业务服务，不应引入大流量冲击。

### 2.2 非目标

以下能力不属于本需求范围：

1. 自动修改量产网络配置，例如自动增删 iptables、路由、VLAN 子接口。
2. 替代 IDS/IPS 做深度入侵检测。
3. 对第三方 ECU 内部故障进行完整诊断。
4. 对 mmhab 视频帧内容做图像质量分析；本需求仅覆盖视频网络输入链路和 Camera Server/Client 通路状态。

---

## 3. 诊断对象与覆盖范围

### 3.1 PVM 网络对象

| 对象 | 必须诊断的内容 |
| --- | --- |
| 物理接口 `eth0`、`eth1` | link 状态、速率、双工、MAC、carrier、RX/TX 包量、错误包、丢包、CRC、overrun、driver 状态 |
| VLAN 子接口 | `eth1.3/4/6/7/8/10/11/12/13/14`、`eth0.15/19` 是否存在、是否 UP、IP 是否正确、父接口是否正确 |
| vmtap 设备 | `vmtap0`、`vmtap1`、`vmtap1.3/4/6/7/8` 是否存在、是否 UP、IP 是否正确、收发计数是否增长 |
| 路由 | main 表、策略路由表 106/107/108、空表 220、默认路由、connected route、异常重复路由 |
| iptables | nat PREROUTING/POSTROUTING、filter FORWARD、默认策略、规则命中计数、IDPS 30006 例外规则 |
| conntrack | NAT 连接是否建立、连接数是否过高、状态是否异常、是否存在大量 UNREPLIED |
| 服务进程 | `xdja_idps`、`someipd`、`dlt-daemon`、`charon-systemd`、`ivcd_main`、`proftpd`、Camera Server 等 |
| PVM 私有业务面 | VLAN 10-14、15、19 是否误暴露到 GVM，SOME/IP/RTSP/NTP 监听是否符合设计 |

### 3.2 GVM 网络对象

| 对象 | 必须诊断的内容 |
| --- | --- |
| 虚拟接口 | Android `eth0`、`eth1`、`eth1.3/4/6/7/8` 是否存在、是否 UP、IP 是否正确、MAC 是否稳定 |
| Android 路由 | main 表、1100、1400、eth1.3、eth1.6、eth1.7、eth1.8 表是否符合预期 |
| Android 规则 | fwmark、NetId、`ip rule` 优先级、未标记流量默认是否走 VLAN 3 |
| 关键服务 | DoIP `13400`、VLM `5062/5064`、gftpd `58046`、hpp_transfer、Polaris agent、mdnsd、adbd 等 |
| 网络框架 | `dumpsys connectivity` 中 NetworkAgent、LinkProperties、NetworkCapabilities 是否与 VLAN 配置一致 |
| 应用选路 | 指定 NetId 和未指定 NetId 的流量是否按预期 VLAN 出口转发 |

### 3.3 外部网络对象

| 对象 | 必须诊断的内容 |
| --- | --- |
| VCM/TBOX | VLAN 3 默认网关 `172.16.103.20` 可达性、VCM `172.16.103.11` 可达性、网关 ARP 状态 |
| 诊断上位机/OBD | VLAN 4 到 `172.16.104.40` 的 DoIP/VLM/gftpd 可达性，IDPS 30006 是否被 PVM 接收 |
| ADCU | VLAN 6 泊车业务、VLAN 15 RTSP 视频、VLAN 19 SOME/IP 大数据可达性 |
| SOME/IP ECU | VLAN 10-14 组播与单播端口可用性、PVM someipd 监听状态 |
| OTA/远程诊断/ADAS Internet | VLAN 7/8 网关可达性、默认策略路由、DNS/互联网探测结果 |

---

## 4. 诊断分层模型

诊断系统应采用分层模型输出结论，避免直接给出模糊的“网络不通”。

| 层级 | 诊断域 | 典型问题 |
| --- | --- | --- |
| L1 物理链路 | PHY、线束、交换芯片端口、link | link down、速率错误、CRC 错误、carrier 抖动、接口 flapping |
| L2 VLAN/以太网 | VLAN 子接口、802.1Q tag、ARP、MAC/FDB | VLAN 缺失、tag 错误、ARP 失败、MAC 冲突、广播异常 |
| L3 IP/路由 | IP、route、ip rule、网关 | IP 错配、默认路由错误、策略表缺失、跨 VLAN 路由异常 |
| L4 NAT/防火墙 | iptables、conntrack、端口 | DNAT/SNAT 缺失、规则顺序错误、FORWARD 拒绝、conntrack 满 |
| L5 服务 | DoIP、SOME/IP、OTA/远程诊断、RTSP、DNS、NTP | 端口未监听、进程崩溃、服务绑定错误 IP、协议握手失败 |
| 虚拟化链路 | virtio-net、vmtap、qcrosvm | vmtap 不存在、GVM 接口无包、virtio 队列异常、跨 VM 单向不通 |
| 性能质量 | 带宽、时延、抖动、丢包、CPU | 高延迟、吞吐下降、突发丢包、软中断过高 |
| 安全暴露 | 服务暴露面、私有 VLAN、调试端口 | PVM 私有面误转发、GVM 端口全透传、FTP/Telnet/NFS/adbd 暴露 |

---

## 5. 功能需求

### 5.1 诊断模式需求

| ID | 需求 | 优先级 | 验收标准 |
| --- | --- | --- | --- |
| NET-DIAG-MODE-001 | 系统应支持“一键全量巡检”，自动采集 PVM 与 GVM 的接口、路由、iptables、服务端口、关键计数器并生成报告。 | P0 | 在 60 秒内完成基础巡检，报告包含每个 VLAN 的状态、异常项和结论。 |
| NET-DIAG-MODE-002 | 系统应支持按 VLAN 专项诊断，输入 VLAN ID 后仅诊断对应链路、IP、路由、NAT、服务和连通性。 | P0 | 对 VLAN 3/4/6/7/8/10-14/15/19 均可执行；不存在 GVM 暴露面的 VLAN 应明确说明“PVM-only”。 |
| NET-DIAG-MODE-003 | 系统应支持按业务场景诊断，包括互联网、诊断、泊车/ADCU、OTA/远程诊断、ADAS Internet、SOME/IP、RTSP 视频、Host-Guest 控制/中间件转发通道。 | P0 | 选择业务场景后，报告能列出涉及接口、VLAN、地址、服务端口和诊断结论。 |
| NET-DIAG-MODE-004 | 系统应支持故障触发诊断，可由 link down、接口错误计数突增、服务端口消失、路由/NAT 配置漂移、丢包率超阈值触发。 | P1 | 触发后自动保存故障前后关键状态，报告中标记触发原因和时间戳。 |
| NET-DIAG-MODE-005 | 系统应支持只读运行模式，所有诊断命令不得修改网络配置。 | P0 | 命令白名单中不得包含 `ip link add/del`、`ip route add/del`、`iptables -A/-D/-F`、`sysctl -w` 等修改类操作。 |

### 5.2 拓扑与配置基线诊断需求

| ID | 需求 | 优先级 | 验收标准 |
| --- | --- | --- | --- |
| NET-DIAG-BASE-001 | 系统应内置当前网络拓扑基线，包括 PVM 物理接口、VLAN、vmtap、GVM 接口、IP 地址、路由表、NAT 映射和业务用途。 | P0 | 基线至少包含本文档第 11 章列出的 VLAN 与地址映射。 |
| NET-DIAG-BASE-002 | 系统应对运行时配置与基线进行差异检测。 | P0 | 任一接口缺失、IP 不一致、VLAN 父接口错误、路由缺失、NAT 规则缺失均输出 FAIL。 |
| NET-DIAG-BASE-003 | 系统应识别“允许差异”和“异常差异”。 | P1 | 例如 ADB 序列号变化不应判定网络异常；PVM `eth1.6` IP 变化应判定异常。 |
| NET-DIAG-BASE-004 | 系统应支持基线版本号。 | P1 | 报告中显示诊断使用的基线版本、生成时间和适用平台。 |
| NET-DIAG-BASE-005 | 系统应对 PVM-only VLAN 做隔离一致性检查。 | P0 | VLAN 10-14/15/19 若出现在 GVM `ip addr`、GVM route 或 PVM DNAT 规则中，应输出安全告警。 |

### 5.3 物理链路诊断需求

| ID | 需求 | 优先级 | 验收标准 |
| --- | --- | --- | --- |
| NET-DIAG-LINK-001 | 系统应检查 PVM `eth0`、`eth1` 的 link 状态。 | P0 | 任一接口 `state DOWN`、`LOWER_UP` 缺失或 carrier 为 0 时输出 FAIL；`eth1` 异常应标记 VLAN 3/4/6/7/8/10-14 受影响，`eth0` 异常应标记 VLAN 15 RTSP 视频和 VLAN 19 SOME/IP 大数据受影响。 |
| NET-DIAG-LINK-002 | 系统应检查链路速率和双工模式。 | P0 | `eth1` 预期为 1000BASE-T1 trunk；`eth0` 预期为 ADCU 视频/数据专线。速率降级或 half-duplex 输出 WARN/FAIL。 |
| NET-DIAG-LINK-003 | 系统应采集 RX/TX error、dropped、overrun、carrier、CRC 等计数器。 | P0 | 计数器非零需输出 WARN；若两次采样间持续增长，输出 FAIL 并提示物理链路、PHY 或线束风险。 |
| NET-DIAG-LINK-004 | 系统应检测接口 flapping。 | P1 | 5 分钟内同一接口 link 状态变化超过 3 次输出 FAIL；数据源优先级为 `/sys/class/net/<if>/carrier_changes`、`dmesg`/`journalctl`/Android logcat 链路事件、巡检模式周期采样。若一次性诊断无法获得历史数据，应将 flapping 子项标记为 BLOCKED/INFO，不影响当前 link 状态检查。 |
| NET-DIAG-LINK-005 | 系统应支持 ethtool 信息采集。 | P1 | 当平台支持 `ethtool` 时，报告包含 driver、speed、duplex、autoneg、link detected；不支持时输出“不支持”而非 FAIL。 |
| NET-DIAG-LINK-006 | 系统应检查 PVM `eth0`、`eth1` 的 MAC 地址基线。 | P0 | 当前 SA8397 基线中 `eth0` 应为 `02:df:53:00:00:09`、`eth1` 应为 `02:df:53:00:00:04`；若项目允许按车辆烧录不同 MAC，应匹配版本化白名单/OUI/非零非广播规则并保持跨重启稳定。异常输出 FAIL，并提示可能影响 RTL9071/VCM/ADCU 侧 FDB 学习与转发。 |

### 5.4 VLAN 与二层诊断需求

| ID | 需求 | 优先级 | 验收标准 |
| --- | --- | --- | --- |
| NET-DIAG-VLAN-001 | 系统应检查 PVM 物理 VLAN 子接口是否完整。 | P0 | `eth1.3/4/6/7/8/10/11/12/13/14`、`eth0.15/19` 任一缺失输出 FAIL。 |
| NET-DIAG-VLAN-002 | 系统应检查 vmtap VLAN 子接口是否完整。 | P0 | `vmtap1.3/4/6/7/8` 任一缺失输出 FAIL，并判断 GVM 对应 VLAN 无法工作。 |
| NET-DIAG-VLAN-003 | 系统应检查 GVM VLAN 子接口是否完整。 | P0 | Android `eth1.3/4/6/7/8` 任一缺失输出 FAIL。 |
| NET-DIAG-VLAN-004 | 系统应校验 VLAN ID 在 PVM 物理侧、PVM vmtap 侧、GVM 侧一致。 | P0 | 例如 PVM `eth1.6`、`vmtap1.6`、GVM `eth1.6` 必须同时存在并对应 VLAN 6。 |
| NET-DIAG-VLAN-005 | 系统应采集每条 VLAN 的 ARP/邻居表状态。 | P1 | 网关 ARP 长期 INCOMPLETE、FAILED 或 MAC 频繁变化时输出 WARN/FAIL。 |
| NET-DIAG-VLAN-006 | 系统应支持 VLAN 抓包辅助验证。 | P1 | 报告应给出对应 tcpdump 命令，例如 `tcpdump -ni eth1.4` 与 `tcpdump -ni vmtap1.4`，用于对比 NAT 前后流量。 |
| NET-DIAG-VLAN-007 | 系统应检查 VLAN 3/6/7/8 关键网关的 ARP/邻居状态。 | P0 | `172.16.103.20`、`172.16.106.20`、`172.16.107.20`、`172.16.108.20` 在 PVM 对应 VLAN 上应为 REACHABLE 或 STALE；INCOMPLETE/FAILED 输出 FAIL，DELAY/PROBE 应复采，持续异常输出 WARN/FAIL。 |

### 5.5 IP 与路由诊断需求

| ID | 需求 | 优先级 | 验收标准 |
| --- | --- | --- | --- |
| NET-DIAG-IP-001 | 系统应检查 PVM 各 VLAN IP 是否符合基线。 | P0 | 任一 PVM IP 缺失或与基线不一致输出 FAIL。 |
| NET-DIAG-IP-002 | 系统应检查 GVM 各 VLAN IP 是否符合基线。 | P0 | 任一 GVM IP 缺失或与基线不一致输出 FAIL。 |
| NET-DIAG-IP-003 | 系统应检查 PVM `net.ipv4.ip_forward` 是否为 1。 | P0 | 值不为 1 输出 FAIL，判定 GVM 到外部转发不可用。 |
| NET-DIAG-IP-004 | 系统应检查 PVM 转发相关内核参数。 | P0 | `net.ipv4.conf.all.forwarding` 应为 1，且 PVM 转发路径所涉接口的 per-interface `forwarding` 也应为 1，至少包括 `eth1.3/4/6/7/8` 与 `vmtap1.3/4/6/7/8`，缺一项即输出 FAIL。`rp_filter` 应检查 `all/default/eth1.3/4/6/7/8/10/11/12/13/14/eth0.15/eth0.19/vmtap1.3/4/6/7/8/vmtap0`。对 NAT/策略路由路径，`rp_filter=1` strict 模式应输出 FAIL 或高危 WARN，`0` 或 `2` 可接受。 |
| NET-DIAG-IP-005 | 系统应采集 `proxy_arp` 等非强制内核网络参数用于漂移分析。 | P1 | `proxy_arp` 不作为当前 L3 NAT 架构的 P0 前提；若与基线不一致，输出 INFO/WARN，并说明需结合项目网络脚本确认。 |
| NET-DIAG-ROUTE-001 | 系统应检查 PVM main 路由表。 | P0 | 必须存在 `default via 172.16.103.20 dev eth1.3` 及各 connected route。 |
| NET-DIAG-ROUTE-002 | 系统应检查 PVM 策略路由表 106/107/108。 | P0 | `iif vmtap1.6/7/8` 必须分别查表 106/107/108，并指向对应 `172.16.106/107/108.20` 网关。 |
| NET-DIAG-ROUTE-003 | 系统应识别 PVM table 220 为空规则。 | P2 | 报告中标记为“已知待确认项”；若该规则开始影响路由，应输出 WARN。 |
| NET-DIAG-ROUTE-004 | 系统应检查 GVM main 表无默认路由。 | P1 | 若 GVM main 表出现 default route，应输出 WARN，提示可能绕过 Android multinetwork 策略。 |
| NET-DIAG-ROUTE-005 | 系统应检查 GVM fwmark/NetId 路由规则。 | P0 | NetId 100/101/102/103 应分别对应 VLAN 8/6/3/7；未标记流量应默认走 VLAN 3；`dumpsys connectivity` / LinkProperties 应符合 §11.4 Android Network 基线，权限受限时按 BLOCKED 降级并使用 `ip rule`、`ip route` 作为替代证据。 |
| NET-DIAG-ROUTE-006 | 系统应提供 `ip route get` 选路验证。 | P0 | 对 `172.16.106.x`、`172.16.104.x`、`8.8.8.8 mark 0x10066` 等测试目标输出预期接口和网关。 |

### 5.6 NAT 与防火墙诊断需求

| ID | 需求 | 优先级 | 验收标准 |
| --- | --- | --- | --- |
| NET-DIAG-NAT-001 | 系统应检查 PVM DNAT 规则完整性和 VLAN 4 规则顺序。 | P0 | VLAN 3/4/6/7/8 的 `172.16.X.40 -> 10.10.X.40` 映射必须存在；VLAN 4 PREROUTING 必须存在 `-p tcp ! --dport 30006` 与 `! -p tcp` 两条 DNAT 规则，且 TCP 例外规则必须位于非 TCP 规则之前，确保 TCP/30006 留给 PVM IDPS。 |
| NET-DIAG-NAT-002 | 系统应检查 PVM SNAT 规则完整性。 | P0 | GVM 到物理侧的 `10.10.X.0/24 -> 172.16.X.40` SNAT 必须存在。 |
| NET-DIAG-NAT-003 | 系统应检查外到内回程 SNAT 规则。 | P0 | 到 `10.10.X.40` 且出 `vmtap1.X` 的流量应 SNAT 为 `10.10.X.1`。 |
| NET-DIAG-NAT-004 | 系统应检查 NAT 规则命中计数。 | P1 | 在执行专项连通性测试后，对应规则计数应增长；不增长则判定未经过预期路径。 |
| NET-DIAG-FW-001 | 系统应检查 FORWARD 链默认策略和规则。 | P0 | 若默认 ACCEPT，应输出安全 WARN，并列出当前入站新建连接暴露风险。 |
| NET-DIAG-FW-002 | 系统应检测 DNAT 端口全透传风险。 | P0 | VLAN 3/4/6/7/8 若对 GVM 全端口 DNAT，应在安全章节列出暴露面和建议白名单。 |
| NET-DIAG-FW-003 | 系统应检查 conntrack 状态。 | P1 | conntrack 表使用率超过 80%、大量 UNREPLIED 或 INVALID 连接时输出 WARN/FAIL。 |
| NET-DIAG-FW-004 | 系统应检查 conntrack 表满证据。 | P0 | 采集 `dmesg` 中 `nf_conntrack: table full` 记录、`/proc/net/stat/nf_conntrack` 中 `insert_failed`、`drop`、`search_restart` 计数；任一非零或 `dmesg` 出现 table full，输出 FAIL，并提示老连接可用但新连接被丢弃的典型现象。 |
| NET-DIAG-FW-005 | 系统应采集 conntrack 容量与超时配置。 | P1 | 采集 `nf_conntrack_buckets`、`nf_conntrack_tcp_timeout_established`、`nf_conntrack_udp_timeout`、`nf_conntrack_udp_timeout_stream` 等参数；与项目基线偏离时输出 INFO/WARN，便于分析 SOME/IP UDP 表项膨胀风险。 |

### 5.7 PVM-GVM 虚拟化链路诊断需求

| ID | 需求 | 优先级 | 验收标准 |
| --- | --- | --- | --- |
| NET-DIAG-VM-001 | 系统应检查 `qcrosvm` 进程和 virtio-net 后端状态。 | P0 | GVM 正常运行时，PVM 应存在相关 qcrosvm 进程及 vmtap 设备。 |
| NET-DIAG-VM-002 | 系统应验证 Host-Guest 控制通道。 | P0 | PVM `10.10.200.1` 与 GVM `10.10.200.40` 双向可达。 |
| NET-DIAG-VM-003 | 系统应验证每条 GVM VLAN 到 PVM vmtap 网关可达。 | P0 | GVM 到 `10.10.103/104/106/107/108.1` ping 或等价探测成功。 |
| NET-DIAG-VM-004 | 系统应检测跨 VM 单向不通。 | P1 | 当 GVM TX 增长但 PVM vmtap RX 不增长，判定 virtio/vmtap 方向异常；反向同理。 |
| NET-DIAG-VM-005 | 系统应检查 GVM VLAN 是否误接入 PVM-only 网络。 | P0 | Android 侧出现 VLAN 10-14/15/19 输出 FAIL。 |
| NET-DIAG-VM-006 | 系统应检查 Host-Guest 控制通道接口配置基线。 | P0 | PVM `vmtap0` 必须存在、UP、IP 为 `10.10.200.1/24`；GVM `eth0` 必须存在、UP、IP 为 `10.10.200.40/24`，MAC 应稳定或符合允许变化规则；缺失或异常输出 FAIL。 |
| NET-DIAG-VM-007 | 系统应检查 PVM/GVM trunk 父接口状态。 | P0 | PVM `vmtap1` 与 GVM `eth1` 必须存在且 UP；任一缺失或 DOWN 输出 FAIL，并标记 GVM VLAN 3/4/6/7/8 全部受影响。 |

### 5.8 业务连通性诊断需求

| ID | 业务 | 需求 | 优先级 | 验收标准 |
| --- | --- | --- | --- | --- |
| NET-DIAG-SVC-001 | 默认互联网 VLAN 3 | 系统应验证 GVM 未标记流量经 VLAN 3 到 PVM，再经 TBOX 默认网关出站。 | P0 | `ip route get`、NAT 计数、网关可达性均符合预期。 |
| NET-DIAG-SVC-002 | 诊断 VLAN 4 | 系统应验证外部访问 `172.16.104.40:13400` 能 DNAT 到 GVM `10.10.104.40:13400`。 | P0 | PVM eth1.4 与 vmtap1.4 抓包可见地址转换，GVM DoIP 端口监听。 |
| NET-DIAG-SVC-003 | IDPS | 系统应验证 `172.16.104.40:30006` 被 PVM `xdja_idps` 接收，不被 DNAT 到 GVM。 | P0 | DNAT 规则排除 30006，PVM socket 监听存在，GVM 不接收该端口连接。 |
| NET-DIAG-SVC-004 | ADCU 泊车 VLAN 6 | 系统应验证 GVM 到 `172.16.106.0/24`、`10.82.13.0/24`、`10.92.89.8` 的选路正确。 | P0 | 目的地址命中 GVM `eth1.6` 表，PVM 从 `eth1.6` 出口转发。 |
| NET-DIAG-SVC-005 | OTA/远程诊断 VLAN 7 | 系统应验证 OTA/远程诊断通道策略路由与网关可达。 | P1 | GVM NetId=103 或目的 `172.16.107.0/24` 走 `eth1.7`；PVM table 107 正确。 |
| NET-DIAG-SVC-006 | ADAS Internet VLAN 8 | 系统应验证 ADAS Internet 通道策略路由与网关可达。 | P1 | GVM NetId=100 或目的 `172.16.108.0/24` 走 `eth1.8`；PVM table 108 正确。 |
| NET-DIAG-SVC-007 | SOME/IP VLAN 10-14 | 系统应验证 PVM `someipd` 在 172.16.110-114.40 监听单播和组播端口。 | P0 | `ss` 可见预期端口，组播 `239.5.1.2:30490` 状态正常；GVM 不可见。 |
| NET-DIAG-SVC-008 | RTSP 视频 VLAN 15 | 系统应验证 ADCU 到 PVM Camera Server 的 RTSP 输入链路。 | P0 | `eth0.15` link/IP 正常，ADCU `172.16.115.98` 可达，Camera Server 进程存在，RTSP 端口或流量可见。 |
| NET-DIAG-SVC-009 | ADCU A2 SOME/IP 大数据 VLAN 19 | 系统应验证 PVM `eth0.19` 与 `someipd` 大数据监听状态。 | P1 | PVM `172.16.119.41` 存在，ADCU `172.16.119.98` 可达或有 SOME/IP 流量。 |
| NET-DIAG-SVC-010 | Host-Guest 控制/中间件转发通道 | 系统应验证 `10.10.200.0/24` 内部控制链路、`amblightserver` 及 PVM 通信中间件转发状态。 | P1 | GVM 到 PVM `10.10.200.1` 可达，相关控制/转发端口监听存在；PVM-only VLAN 不应以原始 VLAN/IP 出现在 GVM。若 `vmtap0`/GVM `eth0` 正常但中间件进程、端口或协议基线缺失，应输出 BLOCKED 或 WARN，不应误判为底层网络 FAIL。 |
| NET-DIAG-SVC-011 | VLAN 3 DNS 解析 | 系统应验证 GVM 通过 VLAN 3 默认互联网通道的 DNS 解析能力。 | P0 | `dumpsys connectivity` / LinkProperties 中默认网络 DNS server 应非空；DNS server 应经 VLAN 3/NAT 可达；已知域名解析应成功。若 ping 外部 IP 正常但 DNS 失败，应区分 DNS 配置异常、Android `netd`/resolver 异常、PVM NAT/路由异常、TBOX/上游 DNS 不响应。 |
| NET-DIAG-SVC-012 | TBOX 默认网关可达性 | 系统应验证 PVM 到 TBOX `172.16.103.20` 的 L3 默认网关可达性和上游下一跳可用性。 | P0 | PVM `eth1.3` 应能 ARP 解析并通过 ICMP 或等价 L3 探测到达 `172.16.103.20`；若网关不可达，输出 FAIL 并标记 VLAN 3 默认互联网通道不可用。DHCP/DNS 转发能力仅在产品配置确认使用时作为扩展检查。 |

### 5.9 服务与端口诊断需求

| ID | 需求 | 优先级 | 验收标准 |
| --- | --- | --- | --- |
| NET-DIAG-PORT-001 | 系统应采集 PVM TCP/UDP 监听端口。 | P0 | 报告列出监听 IP、端口、协议、进程名、PID，并标记是否属于预期服务。 |
| NET-DIAG-PORT-002 | 系统应采集 GVM TCP/UDP 监听端口。 | P0 | 报告列出监听 IP、端口、协议、进程名、PID，并标记是否通过 PVM DNAT 暴露。 |
| NET-DIAG-PORT-003 | 系统应识别服务绑定地址错误。 | P0 | DoIP/VLM/gftpd 若未绑定 `10.10.104.40` 或监听缺失，输出 FAIL。 |
| NET-DIAG-PORT-004 | 系统应识别非预期调试端口暴露。 | P1 | `adbd:5555`、FTP、Telnet、NFS、SSH、HTTP 若监听 `0.0.0.0`，报告中输出安全 WARN。 |
| NET-DIAG-PORT-005 | 系统应检查 PVM 私有服务未被 DNAT 暴露给 GVM。 | P0 | SOME/IP、Camera Server、VLAN 15/19 服务不得通过 NAT 暴露到 GVM。 |

### 5.10 性能与稳定性诊断需求

| ID | 需求 | 优先级 | 验收标准 |
| --- | --- | --- | --- |
| NET-DIAG-PERF-001 | 系统应支持每 VLAN 丢包率检测。 | P1 | 对网关或指定目标执行短周期探测，丢包率超过 1% 输出 WARN，超过 5% 输出 FAIL。 |
| NET-DIAG-PERF-002 | 系统应支持 RTT 与抖动检测。 | P1 | RTT 超过业务阈值或抖动持续升高时输出 WARN；阈值应按业务可配置。 |
| NET-DIAG-PERF-003 | 系统应采集接口吞吐。 | P1 | 报告中展示每个接口/VLAN 在采样窗口内 RX/TX bps 和 pps。 |
| NET-DIAG-PERF-004 | 系统应检查软中断和 CPU 网络负载。 | P2 | 网络软中断占比异常、ksoftirqd 高负载时输出 WARN。 |
| NET-DIAG-PERF-005 | 系统应检查 MTU 一致性。 | P0 | PVM 物理侧、PVM vmtap 父/子接口、GVM VLAN 侧 MTU 必须符合基线；任一业务链路存在不一致输出 FAIL，并标记可能影响 SOME/IP 大包、DoIP 刷写、RTSP/RTP 视频或中间件转发。 |
| NET-DIAG-PERF-006 | 系统应识别广播/组播风暴风险。 | P2 | ARP、mDNS、SOME/IP SD 等广播/组播包速率超过阈值时输出 WARN。 |

### 5.11 安全诊断需求

| ID | 需求 | 优先级 | 验收标准 |
| --- | --- | --- | --- |
| NET-DIAG-SEC-001 | 系统应输出 GVM 暴露面清单。 | P0 | 对 VLAN 3/4/6/7/8，列出经 DNAT 可达的 GVM 监听端口。 |
| NET-DIAG-SEC-002 | 系统应输出 PVM 车内服务暴露面清单。 | P0 | 列出所有监听在 `0.0.0.0` 或 `172.16.*` 的 PVM 服务。 |
| NET-DIAG-SEC-003 | 系统应检查 PVM-only VLAN 隔离。 | P0 | VLAN 10-14/15/19 不应出现在 GVM，不应存在到 GVM 的 DNAT/SNAT。 |
| NET-DIAG-SEC-004 | 系统应检查 IDPS 旁路配置。 | P0 | TCP/30006 必须由 PVM 接收；若被 DNAT 到 GVM 或端口未监听输出 FAIL。 |
| NET-DIAG-SEC-005 | 系统应识别 FORWARD 默认 ACCEPT 风险。 | P1 | 报告中明确说明当前策略对入站新建连接的影响，并建议默认 DROP + 白名单。 |
| NET-DIAG-SEC-006 | 系统应检测异常监听端口变化。 | P1 | 与基线相比新增端口、监听地址扩大、进程变化时输出 WARN。 |

### 5.12 日志与报告需求

| ID | 需求 | 优先级 | 验收标准 |
| --- | --- | --- | --- |
| NET-DIAG-RPT-001 | 系统应生成 Markdown 格式诊断报告。 | P0 | 报告包含摘要、异常列表、拓扑状态、分层诊断结果、证据、建议。 |
| NET-DIAG-RPT-002 | 系统应支持机器可读 JSON 输出。 | P1 | 每条检查项包含 id、name、status、severity、evidence、suggestion、timestamp。 |
| NET-DIAG-RPT-003 | 系统应给每个问题分配严重级别。 | P0 | 严重级别至少包括 PASS、INFO、WARN、FAIL、BLOCKED。 |
| NET-DIAG-RPT-004 | 系统应保留原始命令输出。 | P1 | 报告目录中保存 `ip addr`、`ip route`、`iptables`、`ss`、`ethtool` 等原始输出，便于复盘。 |
| NET-DIAG-RPT-005 | 系统应支持时间戳对齐。 | P1 | PVM/GVM 采集结果必须记录各自系统时间；若时间偏差超过阈值，应提示校时问题。 |

---

## 6. 诊断场景定义

### 6.1 场景 A：GVM 无法访问互联网

| 项目 | 内容 |
| --- | --- |
| 涉及路径 | GVM App -> Android `eth1.3` -> PVM `vmtap1.3` -> PVM `eth1.3` -> TBOX `172.16.103.20` |
| 必查项 | GVM VLAN 3 IP、GVM fwmark 默认路由、PVM `vmtap1.3`、PVM `eth1.3`、PVM default route、SNAT、TBOX 网关 ARP、DNS |
| 判定逻辑 | 若 GVM 到 `10.10.103.1` 不通，定位为虚拟链路；若 PVM 到 `172.16.103.20` 不通，定位为物理/VCM/TBOX；若 NAT 计数不增长，定位为 NAT/选路 |
| 输出建议 | 提供 `ip route get`、`iptables -t nat -L -nv`、`tcpdump -ni vmtap1.3`、`tcpdump -ni eth1.3` 验证命令 |

### 6.2 场景 B：诊断仪无法连接 DoIP

| 项目 | 内容 |
| --- | --- |
| 涉及路径 | 诊断仪 -> VLAN 4 `172.16.104.40:13400` -> DNAT -> GVM `10.10.104.40:13400` |
| 必查项 | `eth1.4` link/IP、`vmtap1.4`、GVM `eth1.4`、DoIP 端口监听、DNAT 规则、FORWARD、conntrack |
| 判定逻辑 | PVM eth1.4 有包但 vmtap1.4 无包，定位 NAT/FORWARD；vmtap1.4 有包但 GVM 端口无监听，定位 GVM 服务；PVM eth1.4 无包，定位外部诊断链路 |
| 特殊规则 | TCP/30006 应被排除 DNAT，不得影响 13400 |

### 6.3 场景 C：IDPS 无法访问或旁路失效

| 项目 | 内容 |
| --- | --- |
| 涉及路径 | 外部 -> `172.16.104.40:30006` -> PVM `xdja_idps` |
| 必查项 | `xdja_idps` 进程、PVM 30006 监听、DNAT 例外规则、iptables 规则顺序、eth1.4 入包 |
| 判定逻辑 | 若 TCP/30006 被 DNAT 到 `10.10.104.40`，判定规则错误；若 PVM 端口未监听，判定服务异常 |

### 6.4 场景 D：ADCU 泊车网络不可达

| 项目 | 内容 |
| --- | --- |
| 涉及路径 | GVM -> `eth1.6` -> PVM `vmtap1.6` -> PVM `eth1.6` -> ADCU/VCM |
| 必查项 | GVM `eth1.6` 路由、PVM table 106、SNAT、`172.16.106.20` 网关、`10.82.13.0/24` 和 `10.92.89.8` 特殊路由 |
| 判定逻辑 | GVM route 不正确定位 Android multinetwork；PVM route 不正确定位策略路由；eth1.6 无 ARP 定位 VCM/ADCU 链路 |

### 6.5 场景 E：OTA/远程诊断通道异常

| 项目 | 内容 |
| --- | --- |
| 涉及路径 | GVM/PVM -> VLAN 7 -> `172.16.107.20` 网关 |
| 必查项 | GVM NetId=103、PVM table 107、NAT、网关可达、OTA/远程诊断服务进程按需启动状态 |
| 判定逻辑 | OTA/远程诊断服务未启动但网络路径正常，应输出业务服务未启动而非网络故障 |

### 6.6 场景 F：ADAS Internet 异常

| 项目 | 内容 |
| --- | --- |
| 涉及路径 | GVM/PVM -> VLAN 8 -> `172.16.108.20` 网关 |
| 必查项 | GVM NetId=100、PVM table 108、NAT、网关可达、DNS/上行连通性 |
| 判定逻辑 | 网关可达但互联网不可达，定位上游网络；GVM 选路错误则定位 Android fwmark/NetId |

### 6.7 场景 G：SOME/IP 服务异常

| 项目 | 内容 |
| --- | --- |
| 涉及路径 | PVM `eth1.10-14` / `eth0.19` -> SOME/IP ECU |
| 必查项 | PVM VLAN 10-14/19 IP、someipd 进程、组播 `239.5.1.2:30490`、单播端口、路由、组播加入状态 |
| 判定逻辑 | GVM 不应参与该路径；若问题仅在 GVM 侧观察到，应提示业务设计不经 GVM |

### 6.8 场景 H：摄像头视频无画面

| 项目 | 内容 |
| --- | --- |
| 涉及路径 | ADCU `172.16.115.98` -> PVM `eth0.15` -> Camera Server -> mmhab -> GVM Camera Client |
| 必查项 | `eth0` link、`eth0.15` IP、ADCU ARP/连通性、RTSP/RTP 流量、Camera Server 进程、GVM Camera Client 状态、mmhab 通道状态 |
| 判定逻辑 | eth0.15 无包定位 ADCU/物理链路；PVM 有 RTSP 但 GVM 无画面，定位 Camera Server/mmhab/Camera Client；不得误判为 iptables NAT 问题 |

### 6.9 场景 I：PVM 与 GVM 互通异常

| 项目 | 内容 |
| --- | --- |
| 涉及路径 | `vmtap0`/`vmtap1.X` <-> Android `eth0`/`eth1.X` |
| 必查项 | qcrosvm、vmtap、virtio-net、PVM/GVM 接口计数、Host-Guest ping、VLAN 子接口 |
| 判定逻辑 | PVM vmtap 存在但 GVM 接口不存在，定位 Guest 初始化；GVM 发包但 PVM 不收，定位 virtio/qcrosvm；PVM 收包但不转发，定位路由/NAT |

### 6.10 场景 J：DNS 解析失败

| 项目 | 内容 |
| --- | --- |
| 涉及路径 | GVM App -> Android DNS/netd -> VLAN 3 `eth1.3` -> PVM `vmtap1.3` -> PVM `eth1.3` -> TBOX/上游 DNS |
| 必查项 | GVM 默认网络是否为 VLAN 3、Android LinkProperties DNS 配置、`netd`/resolver 状态、PVM VLAN 3 NAT、TBOX `172.16.103.20` 网关 ARP、UDP/TCP 53 抓包、按域名和按 IP 的连通性对比 |
| 判定逻辑 | 若 ping 外部 IP 正常但域名解析失败，定位 DNS 配置、DNS 服务器可达性或上游 DNS；若 GVM 未发出 53 端口请求，定位 Android DNS/netd；若 vmtap1.3 有 DNS 请求但 eth1.3 无请求，定位 PVM NAT/路由；若 eth1.3 有请求无响应，定位 TBOX/上游 DNS |
| 输出建议 | 同时输出 `ip route get <外部IP> mark 0x10066`、`dumpsys connectivity` 中 DNS server、`getprop` DNS 相关属性、`tcpdump -ni vmtap1.3 port 53`、`tcpdump -ni eth1.3 port 53` 的验证建议 |

### 6.11 场景 K：conntrack 表满 / 新连接失败

| 项目 | 内容 |
| --- | --- |
| 涉及路径 | PVM netfilter conntrack 表 + 所有经 NAT/状态防火墙的连接 |
| 必查项 | `nf_conntrack_count` / `nf_conntrack_max` 使用率、`/proc/net/stat/nf_conntrack` 中 `insert_failed`/`drop`/`search_restart`、`dmesg` 中 `nf_conntrack: table full`、UDP/TCP timeout 参数、`nf_conntrack_buckets`、是否对 SOME/IP 高频 UDP 配置 `NOTRACK` |
| 判定逻辑 | 现象：老连接（已 ESTABLISHED）正常，新连接全部失败、`tcpdump` 可见 SYN 出去但无 SYN-ACK；若 `dmesg` 出现 table full 或 `insert_failed > 0`，直接输出 FAIL，根因为 conntrack 满；若使用率 > 80% 且仍在增长，输出 WARN，提示扩容 `nf_conntrack_max` 或缩短 UDP timeout |
| 输出建议 | 同时给出扩容命令、`NOTRACK` 配置示例（VLAN 10-14 SOME/IP UDP），并记录是否存在外部扫描/广播风暴造成连接暴涨 |

### 6.12 场景 L：PVM 默认网关可达但 GVM 上不了公网

| 项目 | 内容 |
| --- | --- |
| 涉及路径 | PVM `eth1.3`(SNAT) <-> TBOX 上游公网；PVM forward path: `vmtap1.3` -> `eth1.3` |
| 必查项 | PVM 自身 `ping -I eth1.3 8.8.8.8` 是否通；`ip_forward`、`conf.all.forwarding`、`conf.eth1.3/vmtap1.3.forwarding`；POSTROUTING SNAT 命中计数；FORWARD 链命中/DROP 计数；conntrack 使用率与 `insert_failed`；GVM `ping 10.10.103.1`、`ping 172.16.103.20`、`ping 8.8.8.8`、`ping www.example.com` 的分级结果 |
| 判定逻辑 | (1) PVM `ping -I eth1.3 8.8.8.8` 不通 → 定位 TBOX 上游/SIM/鉴权，与 IVI 无关；(2) PVM 通但 GVM 不通 → 排查 `forwarding`、SNAT、FORWARD、conntrack；(3) GVM ping 公网 IP 通但域名不通 → 进入场景 J（DNS）；(4) GVM 到 `10.10.103.1` 不通 → 定位 vmtap/virtio |
| 输出建议 | 报告中明确标注每一级 ping 结果，避免笼统判定“GVM 上不了网”；若属于 TBOX 上游问题，应在结论中标注“非座舱网络故障” |

---

## 7. 采集数据要求

### 7.1 PVM 必采集命令

```bash
ip -br addr
ip -br link
ip -d link show
ip route show table all
ip rule
ip neigh show
sysctl net.ipv4.ip_forward
sysctl net.ipv4.conf.all.forwarding
sysctl net.ipv4.conf.all.rp_filter
sysctl net.ipv4.conf.default.rp_filter
sysctl net.ipv4.conf.all.proxy_arp
sysctl net.netfilter.nf_conntrack_max
for i in eth1.3 eth1.4 eth1.6 eth1.7 eth1.8 eth1.10 eth1.11 eth1.12 eth1.13 eth1.14 eth0.15 eth0.19 vmtap0 vmtap1.3 vmtap1.4 vmtap1.6 vmtap1.7 vmtap1.8; do printf "%s rp_filter=" "$i"; cat /proc/sys/net/ipv4/conf/$i/rp_filter 2>/dev/null; printf "%s proxy_arp=" "$i"; cat /proc/sys/net/ipv4/conf/$i/proxy_arp 2>/dev/null; done
iptables -t nat -S
iptables -S
iptables -t nat -L -nv
iptables -L -nv
ss -ltnp
ss -lunp
cat /proc/net/nf_conntrack
cat /proc/net/stat/nf_conntrack
sysctl net.netfilter.nf_conntrack_count
sysctl net.netfilter.nf_conntrack_buckets
sysctl net.netfilter.nf_conntrack_tcp_timeout_established
sysctl net.netfilter.nf_conntrack_udp_timeout
sysctl net.netfilter.nf_conntrack_udp_timeout_stream
dmesg | grep -i nf_conntrack | tail -n 50
for i in eth1.3 eth1.4 eth1.6 eth1.7 eth1.8 vmtap1.3 vmtap1.4 vmtap1.6 vmtap1.7 vmtap1.8; do printf "%s forwarding=" "$i"; cat /proc/sys/net/ipv4/conf/$i/forwarding 2>/dev/null; done
ping -c 3 -I eth1.3 8.8.8.8 || true
cat /proc/net/dev
for i in eth0 eth1 vmtap0 vmtap1; do cat /sys/class/net/$i/carrier_changes 2>/dev/null; done
```

如平台支持，还应采集：

```bash
ethtool eth0
ethtool eth1
ethtool -S eth0
ethtool -S eth1
```

### 7.2 GVM 必采集命令

```bash
ip -br addr
ip -br link
ip -d link show
ip rule
ip route show table all
ip neigh show
ss -ltnp
ss -lunp
dumpsys connectivity
ndc network list
cat /proc/net/dev
for i in eth0 eth1; do cat /sys/class/net/$i/carrier_changes 2>/dev/null; done
```

### 7.3 按需抓包命令

| 业务 | PVM 物理侧 | PVM vmtap 侧 |
| --- | --- | --- |
| VLAN 3 默认通道 | `tcpdump -ni eth1.3` | `tcpdump -ni vmtap1.3` |
| VLAN 4 DoIP | `tcpdump -ni eth1.4 port 13400` | `tcpdump -ni vmtap1.4 port 13400` |
| VLAN 6 ADCU | `tcpdump -ni eth1.6` | `tcpdump -ni vmtap1.6` |
| VLAN 7 OTA/远程诊断 | `tcpdump -ni eth1.7` | `tcpdump -ni vmtap1.7` |
| VLAN 8 ADAS | `tcpdump -ni eth1.8` | `tcpdump -ni vmtap1.8` |
| RTSP 视频 | `tcpdump -ni eth0.15 host 172.16.115.98` | 不适用 |
| SOME/IP | `tcpdump -ni eth1.10 udp port 30490` | 不适用 |

抓包应默认短时运行，例如 5-10 秒，避免影响系统资源和存储。

---

## 8. 诊断结果定义

### 8.1 状态定义

| 状态 | 含义 |
| --- | --- |
| PASS | 检查通过，符合基线或阈值 |
| INFO | 信息项，不代表异常 |
| WARN | 存在风险或非致命偏差，需要关注 |
| FAIL | 明确异常，可能导致业务不可用 |
| BLOCKED | 因权限、命令缺失、设备不在线等原因无法完成检查 |

### 8.2 故障归因要求

每个 FAIL/WARN 结果应包含：

1. 问题标题。
2. 影响业务和 VLAN。
3. 故障层级，例如 L1、L2、L3、NAT、防火墙、服务、虚拟化、性能、安全。
4. 关键证据，例如接口状态、规则缺失、端口未监听、计数器异常。
5. 推荐操作，例如检查线束、恢复 VLAN 子接口、重启服务、核对 iptables 配置。
6. 复核命令。

示例：

```text
[FAIL] VLAN 4 DoIP 不可达
影响：诊断上位机 -> Android doip_server
故障层级：L4 NAT / L5 服务
证据：PVM eth1.4 收到 13400 入包，vmtap1.4 无对应包；iptables nat PREROUTING 缺失 VLAN 4 DNAT 规则
建议：恢复 -d 172.16.104.40 -i eth1.4 ! --dport 30006 DNAT 到 10.10.104.40 的规则
复核：tcpdump -ni eth1.4 port 13400；tcpdump -ni vmtap1.4 port 13400；iptables -t nat -S
```

---

## 9. 阈值要求

| 指标 | 默认阈值 | 说明 |
| --- | --- | --- |
| 接口 link down | 立即 FAIL | 对 `eth0`、`eth1`、关键 VLAN 子接口适用 |
| RX/TX error 增长 | 任意持续增长 WARN，快速增长 FAIL | 需两次采样对比 |
| 丢包率 | >1% WARN，>5% FAIL | 按业务可配置 |
| RTT | >50 ms WARN，>100 ms FAIL | 车内以太网默认阈值，互联网链路可单独配置 |
| 抖动 | >20 ms WARN | 对 RTSP、SOME/IP、OTA/远程诊断可单独配置 |
| conntrack 使用率 | >80% WARN，>95% FAIL | 当前连接数可由 `/proc/net/nf_conntrack` 或 `conntrack -S` 获取；最大值必须采集 `sysctl net.netfilter.nf_conntrack_max` |
| 接口 flapping | 5 分钟内 >3 次 FAIL | 依赖事件日志或周期采样 |
| 新增监听端口 | WARN | 若在 PVM `0.0.0.0` 或车载网 IP 上监听，风险提升 |

---

## 10. 报告模板要求

诊断报告应至少包含以下章节：

```text
# 网络诊断报告

## 1. 摘要
- 总体状态：PASS/WARN/FAIL
- 诊断时间：
- 平台：
- 基线版本：
- 异常数量：

## 2. 关键异常
- [FAIL/WARN] 问题、影响范围、建议

## 3. 拓扑状态
- PVM 物理接口
- PVM MAC 基线
- PVM VLAN
- PVM vmtap
- GVM VLAN
- Android Network / LinkProperties 基线
- PVM-only VLAN 隔离

## 4. 路由与 NAT
- PVM 转发内核参数
- PVM route/rule
- GVM route/rule
- iptables NAT/FORWARD
- conntrack

## 5. 业务诊断
- VLAN 3 默认互联网
- VLAN 3 TBOX 默认网关
- VLAN 3 DNS 解析
- VLAN 4 诊断/IDPS
- VLAN 6 ADCU 泊车
- VLAN 7 OTA/远程诊断
- VLAN 8 ADAS Internet
- VLAN 10-14 SOME/IP
- VLAN 15 RTSP 视频
- VLAN 19 ADCU A2 SOME/IP 大数据

## 6. 性能与稳定性
- 丢包、RTT、吞吐、接口错误、flapping

## 7. 安全暴露面
- GVM 暴露端口
- PVM 暴露端口
- 调试服务
- 全端口 DNAT 风险

## 8. 原始证据索引
- 命令输出文件列表
```

---

## 11. 拓扑基线

### 11.1 VLAN 与地址基线

| VLAN | PVM 接口 | PVM IP | GVM 接口 | GVM IP | 用途 | 暴露关系 |
| --- | --- | --- | --- | --- | --- | --- |
| 3 | `eth1.3` | `172.16.103.40/24` | `eth1.3` | `10.10.103.40/24` | 默认互联网/TBOX | DNAT/SNAT 到 GVM |
| 4 | `eth1.4` | `172.16.104.40/24` | `eth1.4` | `10.10.104.40/24` | 诊断 + IDPS | 除 TCP/30006 外 DNAT 到 GVM |
| 6 | `eth1.6` | `172.16.106.40/24` | `eth1.6` | `10.10.106.40/24` | ADCU 泊车/APA | DNAT/SNAT 到 GVM |
| 7 | `eth1.7` | `172.16.107.40/24` | `eth1.7` | `10.10.107.40/24` | OTA/远程诊断 | DNAT/SNAT 到 GVM |
| 8 | `eth1.8` | `172.16.108.40/24` | `eth1.8` | `10.10.108.40/24` | ADAS Internet | DNAT/SNAT 到 GVM |
| 10 | `eth1.10` | `172.16.110.40/24` | 无 | 无 | SOME/IP | PVM-only |
| 11 | `eth1.11` | `172.16.111.40/24` | 无 | 无 | SOME/IP | PVM-only |
| 12 | `eth1.12` | `172.16.112.40/24` | 无 | 无 | SOME/IP | PVM-only |
| 13 | `eth1.13` | `172.16.113.40/24` | 无 | 无 | SOME/IP | PVM-only |
| 14 | `eth1.14` | `172.16.114.40/24` | 无 | 无 | SOME/IP NTP | PVM-only |
| 15 | `eth0.15` | `172.16.115.41/24` | 无 | 无 | ADCU RTSP 视频 | PVM-only + mmhab 到 GVM |
| 19 | `eth0.19` | `172.16.119.41/24` | 无 | 无 | ADCU A2 SOME/IP 大数据 | PVM-only |
| Host | `vmtap0` | `10.10.200.1/24` | `eth0` | `10.10.200.40/24` | Host-Guest 控制 | 内部通道 |

### 11.2 关键网关基线

| VLAN | 网关 | 说明 |
| --- | --- | --- |
| 3 | `172.16.103.20` | TBOX，PVM 默认网关 |
| 6 | `172.16.106.20` | ADCU/泊车网络出口 |
| 7 | `172.16.107.20` | OTA/远程诊断通道出口 |
| 8 | `172.16.108.20` | ADAS Internet 出口 |

### 11.3 父接口与关键内部通道基线

| 位置 | 父接口 / 通道 | 子接口或对端 | 影响范围 |
| --- | --- | --- | --- |
| PVM 物理侧 | `eth1` | `eth1.3/4/6/7/8/10/11/12/13/14` | VCM trunk，承载默认互联网、诊断、ADCU 泊车、OTA/远程诊断、ADAS Internet、SOME/IP 总线 |
| PVM 物理侧 | `eth0` | `eth0.15/19` | ADCU 专线，承载 RTSP 视频与 SOME/IP 大数据 |
| PVM-GVM virtio | `vmtap1` | `vmtap1.3/4/6/7/8` | Android VLAN 3/4/6/7/8 的 trunk 后端 |
| GVM virtio | `eth1` | `eth1.3/4/6/7/8` | Android 多 VLAN trunk 前端 |
| Host-Guest 控制 | PVM `vmtap0` | GVM `eth0` | `10.10.200.0/24` 内部控制和通信中间件转发通道 |

### 11.4 MAC 与 Android 多网络基线

#### PVM MAC 基线

| 接口 | 期望 MAC | 说明 |
| --- | --- | --- |
| `eth0` | `02:df:53:00:00:09` | ADCU 专线，承载 VLAN 15/19 |
| `eth1` | `02:df:53:00:00:04` | VCM trunk，承载 VLAN 3/4/6/7/8/10-14 |

> 若不同车辆允许按烧录值生成 MAC，应使用车型/软件版本绑定的 MAC 白名单或 OUI 规则替代固定值；诊断报告必须明确当前采用的是“固定 MAC 基线”还是“白名单/OUI 基线”。

#### Android Network 基线

| NetId / fwmark | Android 接口 | 业务 | 期望 LinkProperties |
| --- | --- | --- | --- |
| NetId=100 / `0x10064` | `eth1.8` | ADAS Internet | 包含 `10.10.108.40/24`、`default via 10.10.108.1`、`172.16.108.0/24 via 10.10.108.1` |
| NetId=101 / `0x10065` | `eth1.6` | ADCU 泊车/APA | 包含 `10.10.106.40/24`、`default via 10.10.106.1`、`172.16.106.0/24`、`10.82.13.0/24`、`10.92.89.8` 路由 |
| NetId=102 / `0x10066` | `eth1.3` | 默认互联网/TBOX | 包含 `10.10.103.40/24`、`default via 10.10.103.1`、`172.16.103.0/24 via 10.10.103.1`；默认网络 DNS server 应非空 |
| NetId=103 / `0x10067` | `eth1.7` | OTA/远程诊断 | 包含 `10.10.107.40/24`、`default via 10.10.107.1`、`172.16.107.0/24 via 10.10.107.1` |
| Host-Guest | `eth0` | 控制/中间件转发 | 包含 `10.10.200.40/24`、到 `10.10.200.1` 的链路路由 |

> 若 `dumpsys connectivity`、`ndc network list` 或 LinkProperties 在量产版本中权限受限，应将 Android Network 细项标记为 BLOCKED，并保留 `ip rule`、`ip route show table all`、接口/IP 结果作为降级证据。

### 11.5 关键服务基线

| 系统 | 服务 | 地址/端口 | 预期 |
| --- | --- | --- | --- |
| PVM | `xdja_idps` | `172.16.104.40:30006/tcp` | 必须监听，不被 DNAT |
| GVM | `doip_server` | `10.10.104.40:13400/tcp,udp` | 诊断服务，需经 DNAT 暴露 |
| GVM | `vlm-agent` | `10.10.104.40:5062/tcp`, `10.10.104.40:5064/udp` | 诊断/生命周期管理 |
| GVM | `gftpd` | `10.10.104.40:58046/tcp` | 诊断/刷写文件传输 |
| PVM | `someipd` | `172.16.110-114.40`、`172.16.119.41` 多端口 | PVM-only 服务总线 |
| PVM | Camera Server | `172.16.115.41` RTSP/RTP 输入 | 经 mmhab 提供给 GVM Camera Client |
| PVM | `amblightserver` | `10.10.200.1:55498/udp` | Host-Guest 控制通道服务，仅应在 `10.10.200.0/24` 内部可达 |

---

## 12. 可实现性要求

### 12.1 运行环境

1. 诊断工具应能通过 ADB 同时连接 PVM 与 GVM。
2. 诊断工具应能自动识别 PVM/GVM 身份，不依赖固定 ADB 序列号。
3. PVM/GVM 命令权限不足时，应输出 BLOCKED，并说明缺失权限或命令。
4. 诊断工具应允许配置外部目标地址，例如诊断仪地址、ADCU 地址、SOME/IP ECU 地址、互联网探测地址。

### 12.2 安全约束

1. 默认不执行长时间抓包。
2. 默认不执行大带宽压测。
3. 默认不访问非白名单外部地址。
4. 对生产环境执行端口探测时，应限制频率和目标端口范围。
5. 报告中不得泄露敏感凭据、密钥、token。

### 12.3 可扩展性

1. 新增 VLAN 时，应只需更新拓扑基线，不需要重写诊断逻辑。
2. 新增业务服务时，应可通过服务基线追加端口和进程检查。
3. 阈值应支持按项目、车型、软件版本配置。

---

## 13. 验收用例

| 用例 ID | 用例名称 | 构造条件 | 预期结果 |
| --- | --- | --- | --- |
| TC-NET-001 | PVM `eth1` link down | 断开或模拟 `eth1` carrier down | VLAN 3/4/6/7/8/10-14 全部标记受影响，故障层级 L1 |
| TC-NET-002 | GVM VLAN 4 缺失 | Android `eth1.4` 不存在 | 诊断 VLAN 4 FAIL，指出 DoIP/VLM/gftpd 不可达 |
| TC-NET-003 | PVM DNAT 规则缺失 | 删除 VLAN 4 DNAT 规则 | 诊断仪到 DoIP FAIL，定位 NAT，PVM eth1.4 有包但 vmtap1.4 无包 |
| TC-NET-004 | IDPS 例外规则错误 | TCP/30006 被 DNAT 到 GVM | IDPS 旁路 FAIL，输出安全风险 |
| TC-NET-005 | PVM table 106 缺失 | 删除 table 106 默认路由 | VLAN 6 ADCU 出站 FAIL，定位策略路由 |
| TC-NET-006 | GVM fwmark 映射错误 | NetId=101 不走 eth1.6 | 应用选路 FAIL，定位 Android multinetwork |
| TC-NET-007 | SOME/IP 服务未监听 | 停止 PVM someipd | VLAN 10-14 服务 FAIL，但 GVM 网络不应被误判 |
| TC-NET-008 | RTSP 有流但 GVM 无画面 | Camera Server 正常收包，mmhab 异常 | 网络输入 PASS，视频跨 VM 通道 FAIL |
| TC-NET-009 | 新增 PVM 调试端口 | PVM `0.0.0.0:5555` 监听 | 安全诊断 WARN，列入暴露面 |
| TC-NET-010 | 接口错误计数增长 | 注入 RX error/CRC 递增 | 稳定性诊断 WARN/FAIL，提示物理链路风险 |
| TC-NET-011 | 网关 ARP 失败 | VLAN 3/6/7/8 任一网关邻居状态为 INCOMPLETE/FAILED | 对应业务 FAIL，定位为网关不可达或二层/物理链路异常 |
| TC-NET-012 | PVM `eth0` link down | 断开或模拟 `eth0` carrier down | VLAN 15 RTSP 视频和 VLAN 19 SOME/IP 大数据全部标记受影响，故障层级 L1 |
| TC-NET-013 | Host-Guest `eth0` 配置异常 | Android `eth0` 缺失、DOWN 或 IP 非 `10.10.200.40/24` | Host-Guest 控制/中间件转发通道 FAIL |
| TC-NET-014 | VLAN 4 DNAT 顺序错误 | VLAN 4 `! -p tcp` 规则缺失，或 TCP/30006 例外规则缺失/顺序异常 | IDPS 或 DoIP 诊断路径 FAIL，定位 NAT 规则顺序/完整性 |
| TC-NET-015 | MTU 不一致 | PVM 物理侧、vmtap 侧、GVM VLAN 侧任一 MTU 偏离基线 | MTU 一致性 FAIL，提示 SOME/IP/DoIP/RTSP 静默丢包风险 |
| TC-NET-016 | trunk 父接口 DOWN | PVM `vmtap1` 或 GVM `eth1` DOWN | Android VLAN 3/4/6/7/8 全部 FAIL，定位 virtio trunk 父接口异常 |
| TC-NET-017 | DNS 解析失败 | GVM 经 VLAN 3 ping 外部 IP 正常，但域名解析失败或 DNS 53 端口无响应 | 默认互联网链路不应误判为整体不通，应定位 Android DNS/netd、PVM NAT、TBOX 或上游 DNS |
| TC-NET-018 | `rp_filter` strict 导致丢包 | PVM `vmtap1.6` 或 `eth1.6` 等策略路由路径 `rp_filter=1` | 转发内核参数 FAIL/WARN，提示反向路径过滤可能丢弃 GVM 回程包 |
| TC-NET-019 | PVM MAC 基线异常 | `eth0` 或 `eth1` MAC 与固定基线/白名单不一致 | MAC 基线 FAIL，提示可能影响 RTL9071/VCM/ADCU FDB 学习 |
| TC-NET-020 | TBOX 默认网关不可达 | VLAN 3 网关 ARP 正常但 PVM 无法 ICMP 或等价 L3 探测 `172.16.103.20` | VLAN 3 默认互联网通道 FAIL，定位 TBOX/L3 网关异常 |
| TC-NET-021 | conntrack 表满 | `dmesg` 出现 `nf_conntrack: table full` 或 `insert_failed > 0`，老连接可用但新连接 SYN 无应答 | conntrack 诊断 FAIL，定位为 conntrack 表满，建议扩容 `nf_conntrack_max` 并对 VLAN 10-14 SOME/IP UDP 配置 `NOTRACK` |
| TC-NET-022 | PVM 转发关闭 / per-if forwarding=0 | 任意一项 `ip_forward`、`conf.all.forwarding`、`conf.eth1.3/vmtap1.3.forwarding` 为 0 | GVM 互联网/业务全部 FAIL，PVM 自身仍可 ping 网关，定位 PVM 转发未启用 |
| TC-NET-023 | TBOX 上游公网不可达 | PVM `ping -I eth1.3 8.8.8.8` 不通，但 PVM 到 TBOX `172.16.103.20` 网关可达 | 报告标注“非座舱网络故障”，定位 TBOX 上游/SIM/鉴权 |

---

## 14. 输出结论要求

诊断系统最终输出应避免“可能有问题”这类不可执行结论，应使用以下格式：

```text
结论：VLAN 4 诊断链路在 PVM NAT 层异常。
影响：外部诊断仪无法访问 Android DoIP/VLM/gftpd。
证据：PVM eth1.4 收到 13400 入包；vmtap1.4 无对应包；nat PREROUTING 缺少 VLAN 4 DNAT 规则。
建议：恢复 VLAN 4 DNAT 规则，并复核 TCP/30006 IDPS 例外规则。
复核：再次执行 VLAN 4 专项诊断，确认 DNAT 计数增长且 GVM 13400 有连接。
```

---

## 15. 后续建议

1. 将本需求拆分为诊断工具的检查项配置文件，按 `check_id` 管理，便于自动化实现。
2. 将拓扑基线与软件版本绑定，避免不同车型或分支配置差异造成误报。
3. 对安全风险项建立白名单审批机制，尤其是 PVM `0.0.0.0` 监听服务和 GVM 全端口 DNAT 暴露面。
4. 在工程阶段补充典型故障包和日志样例，形成网络问题知识库。
