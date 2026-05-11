# 智能座舱网络诊断系统设计评审

> 评审对象：`work/network_diagnosis_sys_design.md`
> 对照依据：`work/network_diagnosis_requirements.md`
> 评审日期：2026-05-09
> 评审定位：架构与可落地性评审，不是代码走查

---

## 1. 执行摘要

总体结论：**方向正确，核心架构可落地，但离“可量产、可维护、可在 30s 内稳定感知网络异常”的目标还有几处关键缺口。**

我对当前系统设计的判断如下：

| 维度 | 结论 |
| --- | --- |
| 需求覆盖 | **P0 主链路大体覆盖，P1/P2 以及若干运维型要求存在落空或仅停留在“命名”层** |
| 架构合理性 | **总体合理**。PVM 主诊断、GVM 轻采集、专用 VSOCK 与 polaris 通道分离，这个方向是对的 |
| 扩展性 | **中等偏上**。已有较强配置化思路，但还没有把“允许差异”“场景映射”“大文件取证”“配置热更新/版本协同”做实 |
| 性能开销 | **常态低到中等，异常时中等偏高**。主要热点不在 VSOCK，而在 `dumpsys connectivity`、`/proc/net/nf_conntrack`、`iptables -L -nv`、抓包与取证打包 |
| 30s 感知能力 | **部分满足**。link down、conntrack full、service crash、App 主动报障可以；网关不可达、DNS 失败、NAT 规则漂移当前设计下不能稳定保证 30s |

如果按工程优先级排序，我建议把下面 5 项作为上线前必须补齐的内容：

1. 明确 **30s SLA 的检测路径**，至少补齐网关不可达、DNS、NAT 漂移三类故障的快速检测链路。
2. 补齐 **要求已定义但设计未落地** 的条目：`NET-DIAG-IP-005`、`NET-DIAG-FW-005`、`NET-DIAG-PERF-003/004/006`、`NET-DIAG-RPT-005`、`NET-DIAG-BASE-003`。
3. 明确 **场景 A-L、VLAN 专项、SHU、check registry** 之间的映射关系，否则 `MODE-002/003/004` 实现会很容易漂移。
4. 补齐 **跨通道事件去重/关联** 与 **大文件取证传输协议**，否则同一故障可能产生多条 incident，且 `fetch_log` 在大文件场景下协议不闭环。
5. 收紧 **异常时资源上限策略**，特别是 `CPUQuota=5%`、`dumpsys connectivity` 周期调用、全量 `conntrack` 抽取，否则故障高峰期容易“为了诊断而影响诊断对象”。

---

## 2. 关键发现

### F1. 当前设计不能稳定满足“网络不通 30s 内发现”的目标

这是本次评审最重要的结论。

当前文档中的快速路径主要有：

- PVM netlink/sd-journal watchdog：用于 link down、route 消失、conntrack full、service crash。
- GVM watchdog：用于 link/IP 漂移、DNS 爆发、virtio 卡滞。
- App 主动报障：用于地图、媒体等“业务已感知”的场景。
- SHU + probe：用于业务可用性判定。

问题在于，**不是所有“网络不通”都挂在事件驱动信号源上**。

当前文档明确写出的探测周期是：

- 轻量巡检：60s
- `SHU_VLAN3_INTERNET` 到 `172.16.103.20` 的 ICMP probe：60s
- 到 `8.8.8.8` 的 ICMP probe：300s
- DNS probe：300s
- iptables NAT 规则漂移：60s 哈希比对
- GVM `dumpsys connectivity` 变化：60s 轮询
- vmtap 单向不通：30s 比较窗

这意味着：

- **网关不可达**：当前主要靠 60s ICMP probe，不能保证 30s。
- **DNS 失败**：当前主要靠 60s/300s 检测，不能保证 30s。
- **NAT 规则漂移**：当前 60s 哈希比对，不能保证 30s。
- **vmtap 单向不通**：30s 窗口本身已经吃满预算，再加采样对齐与处理时间，实战上是边缘满足，不是稳态满足。

如果把“地图突然无法上网”作为典型场景：

- **有 App 主动报障接入** 时，可以在约 5-15s 内感知并上报，这是合理的。
- **没有 App 主动报障接入** 时，系统主要依赖 60s/300s 的 probe，不满足 30s。

结论：

- 如果目标只是满足需求文档中的“60s 内完成基础巡检”，当前设计基本可接受。
- 如果目标提升为“网络不通 30s 内发现”，当前设计**必须补强**。

### F2. 多个需求条目在系统设计中只有“检查名”，没有“实现闭环”

系统设计已经把 74 个 check 放进了 registry，这是优点；但有几项要求虽然在表格里出现了 check id，**真正落到配置、采集、比较逻辑、报告字段时是不闭环的**。

重点缺口如下：

| 需求 ID | 现状 | 问题 |
| --- | --- | --- |
| `NET-DIAG-BASE-003` | 仅在 check registry 中出现 | 没有统一的“允许差异”策略模型，只有零散例外说明，例如 GVM MAC、dummy0 fallback、NetId 动态映射 |
| `NET-DIAG-IP-005` | check 名存在 | 采集器未看到 `proxy_arp` 全局与 per-iface 采集；配置 schema 也没有 `proxy_arp` 基线字段 |
| `NET-DIAG-FW-005` | check 名存在 | 采集器未定义 `nf_conntrack_buckets`、`nf_conntrack_tcp_timeout_established`、`nf_conntrack_udp_timeout`、`nf_conntrack_udp_timeout_stream` 的采集与比较 |
| `NET-DIAG-PERF-003` | check 名存在 | 没有明确定义吞吐计算窗口、bps/pps 计算算法、轻量/全量采集路径 |
| `NET-DIAG-PERF-004` | check 名存在 | 没有 softirq / `ksoftirqd` 的数据源、阈值和判定逻辑 |
| `NET-DIAG-PERF-005` | check 名和测试用例存在 | 配置 schema 中没有 MTU 基线字段，意味着“比什么”没有定义 |
| `NET-DIAG-PERF-006` | check 名存在 | 没有广播/组播速率的数据来源、采样周期、阈值模型 |
| `NET-DIAG-RPT-005` | 报告要求存在 | 事件 payload 里有 `ts_unix`，但没有 PVM/GVM 时间偏差检测、校时阈值、报告展示和降级逻辑 |

这类问题的危险在于：**表面上看“需求都有对应 check id”，实际上实现阶段会发现没有数据、没有基线、没有阈值、没有聚合逻辑。**

### F3. 架构本身合理，但“同一故障如何只产出一条高质量 incident”还没设计完

当前架构里，同一故障可能同时经过三条路触发：

1. PVM watchdog 直接感知。
2. GVM watchdog 通过 VSOCK 9101 push 给 PVM。
3. App 通过 `NETDIAG_APP_NETWORK_TROUBLE` 主动报障。

这是对的，说明感知没有单点；但文档没有定义：

- incident 去重键是什么。
- 同一窗口内的多路触发如何归并。
- 哪一路是 primary，哪一路只作为 enrichment。
- 如果 PVM 已经产生 incident，后续 GVM push 或 App 事件到来，是更新同一 incident，还是新建 incident。

如果不加这一层，云端会看到：

- 一条 `NETDIAG_GATEWAY_UNREACHABLE`
- 一条 `NETDIAG_APP_NETWORK_TROUBLE`
- 再加一条 GVM fallback event

三条其实都是同一个故障。这会严重影响运维噪声、统计和闭环效率。

### F4. `fetch_log` 只定义了名字，没有定义大文件协议

这是一个很容易在实现阶段被忽视的协议问题。

当前 VSOCK 9101 协议定义了：

- 帧最大 4 MiB
- `fetch_log` 方法存在
- `log_ref` 指向 `snap_dir`

但没有定义：

- 当目录内有 pcap、长 `dumpsys`、大 `conntrack` 输出时，如何分块传输。
- 是否有 chunk 序号、总长度、校验、断点续传。
- 超时与 backpressure 怎么做。
- 如果不走 VSOCK 传，只走路径引用，PVM 如何保证该路径在 GVM 上仍可读取。

这不是文档表述细节，而是**协议闭环缺失**。如果不补，`log_ref` 在小文本场景可用，在大证据场景会失效。

### F5. 资源控制思路正确，但 `CPUQuota=5%` 过于激进

在 PREEMPT_RT 场景下，诊断进程确实不应该抢实时任务，这是对的；但把 PVM 主诊断进程直接限到 `CPUQuota=5%`，在异常高峰时可能过紧。

高峰场景下同时发生：

- `iptables -L -nv`
- `dmesg` 检索
- `cat /proc/net/nf_conntrack`
- `tcpdump`
- 取证目录打包
- 与 GVM 的 `fetch_log`

这时如果 CPU 被硬限到 5%，反而会拖慢告警、拖慢取证，甚至导致“故障已发生，但证据没来得及采全”。

我的建议是：

- 保留 `Nice=10`、`IOSchedulingClass=best-effort` 这些软限制。
- `CPUQuota` 改成更宽松的上限，或者只在 steady-state 生效，在 incident 模式下允许短时 burst。

---

## 3. 需求覆盖评估

## 3.1 覆盖度结论

我给当前设计的需求覆盖度结论是：

- **P0 核心覆盖：较好**
- **P1/P2 工程化覆盖：中等**
- **可维护性/运维性要求覆盖：偏弱**

## 3.2 覆盖较好的部分

以下要求已经有比较完整的设计落点：

| 需求类别 | 评估 |
| --- | --- |
| PVM/GVM 拓扑基线、VLAN、路由、NAT、服务基线 | 基本完整，且配置化程度较高 |
| NAT/防火墙核心要求 | `DNAT/SNAT`、VLAN 4 规则顺序、FORWARD 默认 ACCEPT 风险都有体现 |
| VM 虚拟链路 | `qcrosvm`、`vmtap`、Host-Guest、trunk 父接口、单向不通都有设计 |
| SHU 与业务视角诊断 | `VLAN3_INTERNET`、`DNS`、`DOIP`、`HOST_GUEST` 等业务抽象是对的 |
| 报告与证据目录 | Markdown/JSON 报告 + `incident_dir` + `snaps` + `probes`，结构已经成型 |
| 部署与权限 | PVM systemd、GVM init.rc、sepolicy、VSOCK 通道均已考虑 |

## 3.3 部分覆盖，需要补充设计的部分

### 1. `MODE-002` / `MODE-003`

文档里写了：

- `scope: full | vlan:N | scenario:X | shu:Y`
- `ScenarioEval + SHU filter`

但缺少真正可实现的映射定义：

- `vlan:4` 到底选哪些 checks。
- 场景 A-L 分别对应哪些 SHU、哪些 probes、哪些 evidence files。
- `PVM-only` VLAN 在按 VLAN 执行时如何裁剪 GVM 采集。

当前实现这些功能，**仍然要补一份显式 mapping schema**。

### 2. `MODE-004`

watchdog 事件已经列得比较全，但没有定义“事件触发哪一组 auto-check、哪一组 probe、哪一组取证”的决策表。

例如：

- `NETDIAG_LINK_DOWN(eth1)` 触发后，是跑全量，还是只跑 L1/L2/L3 子集？
- `NETDIAG_CONNTRACK_PRESSURE` 触发后，是否一定抓 `ss`、`nf_conntrack_count/max`、`dmesg`，是否强制触发 `SHU_VLAN3_INTERNET`、`SHU_DNS` 的新建连接探测？

没有这张映射表，`MODE-004` 会在实现时变成“事件来了就临时写 if/else”，后续维护会很难看。

### 3. `BASE-003`

当前设计已经意识到以下差异不是异常：

- GVM MAC 动态变化
- dummy0 fallback 网络
- NetId 动态变化

但这仍然是“零散例外”，不是统一策略。建议补一个统一 schema，例如：

```json
{
  "diff_policy": {
    "ignore_fields": ["gvm.mac", "android.netid.runtime"],
    "warn_if_changed": ["iptables.filter.default_policy"],
    "fail_if_changed": ["pvm.vlan_ifaces.*.ip", "pvm.policy_route"]
  }
}
```

否则 baseline diff 会随着车型、版本增多而越来越难维护。

## 3.4 明显遗漏或未闭环的条目

以下条目我认为需要在系统设计中明确补齐：

| 需求 ID | 当前问题 | 建议 |
| --- | --- | --- |
| `NET-DIAG-IP-005` | 缺少 `proxy_arp` 采集和基线字段 | 在 collector 和 baseline 中补齐 `all/default/per-iface proxy_arp` |
| `NET-DIAG-FW-005` | 缺少 buckets 与 timeout 采集/比较 | 补 `nf_conntrack_buckets`、`tcp_timeout_established`、`udp_timeout`、`udp_timeout_stream` |
| `NET-DIAG-PERF-003` | 没有吞吐计算设计 | 定义基于 `/proc/net/dev` 的窗口、单位、采样周期 |
| `NET-DIAG-PERF-004` | 没有 softirq 数据源 | 补 `/proc/softirqs`、`/proc/stat`、`top -H` 或轻量解析策略 |
| `NET-DIAG-PERF-005` | 无 MTU 基线字段 | 在 `phys_ifaces`、`vlan_ifaces`、`vmtap`、GVM 接口基线加 `mtu` |
| `NET-DIAG-PERF-006` | 没有广播/组播风暴检测模型 | 定义抓包/内核计数器/pps 阈值 |
| `NET-DIAG-RPT-005` | 没有时间偏差检测与报告逻辑 | 增加 PVM/GVM timestamp 对齐检查与 skew 阈值 |

---

## 4. 架构合理性与扩展性评估

## 4.1 架构总体是否合理

我的结论是：**合理，而且主方向是对的。**

原因如下：

1. **PVM 为主诊断节点** 是正确决策。
PVM 持有物理网卡、iptables、route、conntrack、vmtap 后端和大部分真实证据。让 PVM 负责分析和上报，天然减少了跨 VM 取证的不确定性。

2. **GVM 做轻采集 + 主动推送** 是正确的。
GVM 只保留自己真正知道的上下文，例如 `dumpsys connectivity`、App 网络状态、`eth1.x` 视角。这样既保留 Android 侧真相，又不把主逻辑散落到两端。

3. **专用 VSOCK 9101 与 polaris VSOCK 9001 分离** 是合理的。
这样做避免了诊断 RPC 与 polaris 自身控制面混流，也避免把诊断 RPC 绑在被诊断的 IP 网络上。

4. **配置化 baseline/check registry/SHU** 是非常好的思路。
这说明设计已经意识到：网络诊断不是靠“写死 if/else”，而是靠“配置 + parser + comparator + aggregator”。这是走向长期可维护的正确方向。

## 4.2 扩展性如何

当前扩展性结论是：**中等偏上，但还没有达到“加规则只改配置”的程度。**

### 对不同类型变更的改动成本判断

| 变更类型 | 预计改动面 | 评估 |
| --- | --- | --- |
| 调整阈值、调 probe 周期、调整事件频率 | 改 JSON 即可 | 很方便 |
| 新增已知类型的服务端口或进程基线 | 改 baseline/services/check config | 比较方便 |
| 新增已有模式的 VLAN | 需要改 baseline、check 选择、SHU、场景映射、测试用例 | 中等成本 |
| 新增一个全新业务场景 | 需要补 scenario→SHU→check 映射与报告模板 | 中等成本 |
| 新增一种全新检测能力（例如 softirq、广播风暴、BPF 级别采样） | 需要改 collector/parser/comparator/reporter | 需要代码改动 |
| 新增协议类型或更大证据传输能力 | 需要改 VSOCK 协议与两端实现 | 成本较高 |

### 当前最影响扩展性的 4 个点

1. **场景映射未配置化**
场景 A-L 在需求里定义得很完整，但系统设计里没有一张正式的 `scenario registry`。这会导致每新增一个场景，都要改代码逻辑，而不是纯改配置。

2. **allowed variance 未配置化**
随着车型和版本增多，“哪些差异允许、哪些必须 fail”会迅速爆炸。如果现在不抽象出来，后续会变成大量特判。

3. **check registry 有了，但 collector capability 与 parser capability 没抽象完全**
例如：`PERF-004` 需要 softirq 数据源，`PERF-006` 需要广播风暴数据源；当前 registry 中有 check 名，但 collector 没有对应 capability，这会让 registry 失去约束力。

4. **PVM/GVM 双端配置协同与版本对齐机制未定义**
当前文档有 `baseline_version`，但没有描述：

- PVM/GVM 配置版本如何同步。
- 配置更新是否支持热加载。
- 一端升级、一端未升级时如何降级与告警。

这在量产系统里会很快变成运维痛点。

## 4.3 我对“规则变化后改动方便吗”的直接回答

直接回答用户这个问题：

- **普通规则变化**：方便。比如阈值、端口、VLAN/IP 基线、事件 ID、probe 周期，这些基本都能走配置。
- **中等复杂规则变化**：还行，但不是一处改完。比如新增 VLAN、新增 SHU、新增场景，需要同时改 baseline、check registry、SHU 和测试矩阵。
- **新增规则类型**：不够方便。凡是需要新 collector、新 parser、新 evidence 类型的，都要改代码，不是纯配置。

所以我的评价是：

**当前设计已经有“配置驱动”的雏形，但还没有完全抽象到“规则变化主要改配置，少量改代码”。**

---

## 5. 性能开销评估

## 5.1 常态开销

常态下，这套系统的 CPU 和带宽开销并不高。真正昂贵的不是 VSOCK，而是命令执行和取证。

常态 steady-state 主要包含：

- PVM 60s 轻量巡检
- GVM 60s 轻量巡检
- PVM probes（60s / 300s / 600s）
- netlink / sd-journal / inotify 事件监听

这部分开销总体是可接受的，尤其是：

- VSOCK payload 被限制在小尺寸
- probe 总 pps 被限制到 100 pps
- tcpdump 限时限包

## 5.2 真正的性能热点

### 1. `dumpsys connectivity`

当前设计把它放进了 GVM 采集器，并且用于 60s 周期检测 Android connectivity 变化。这个动作在 Android 上明显比 `ip rule`、`ip route`、`ss` 重。

建议：

- 60s 周期里只做轻量摘要或缓存对比。
- 完整 `dumpsys connectivity` 仅在 anomaly/fetch_log/full-scan 时执行。

### 2. `/proc/net/nf_conntrack`

当前设计允许直接抓取原始 conntrack 表。这个动作在连接很多时很重，而且容易遇到：

- 输出大
- 解析成本高
- 512 KiB 截断后证据不完整

建议：

- 常态只采 `count/max` 和必要计数器。
- 只有在 `NETDIAG_CONNTRACK_PRESSURE`、`NETDIAG_APP_NETWORK_TROUBLE` 且怀疑新连接失败时，才抓更完整证据。

### 3. `iptables -L -nv`

规则多时这个命令不轻，而且高峰期可能拖慢异常处理。建议明确：

- `-S` 用于规则存在性和顺序检查。
- `-L -nv` 仅在 full-scan 或相关 anomaly 触发时执行。

### 4. 取证目录的打包与跨 VM 拉取

真正的大头不是“检测”，而是“证据整理”：

- 目录创建
- 文件写入
- GVM `log_ref` 拉取
- pcap 存储
- report 生成

这部分如果没有限流和 chunking，会直接影响故障高峰期稳定性。

## 5.3 对当前资源限制的判断

| 项 | 结论 |
| --- | --- |
| `MemoryMax=64M` | 偏紧但可接受；如果 incident 中包含 pcap + 大文本，内存峰值需要谨慎 |
| `CPUQuota=5%` | 我认为过紧，不建议量产使用硬限制 5% |
| `probe_max_pps=100` | 合理 |
| `tcpdump_max_sec=10 / max_pkts=2000` | 合理 |
| 轻量巡检 60s | 可以接受 |
| 全量巡检 1h | 可以接受 |

## 5.4 我的性能结论

性能总体结论：**常态开销可控，异常期开销需要再收敛。**

如果按风险排序：

1. `dumpsys connectivity` 周期调用
2. `conntrack` 大表读取
3. 异常时取证打包与 log fetch
4. `iptables -L -nv`
5. tcpdump

VSOCK 本身不是瓶颈，真正的瓶颈在系统命令和证据链构建。

---

## 6. 30s 异常检测能力评估

## 6.1 结论先行

**不能笼统地说“能”。**

更准确的说法是：

- **事件驱动类故障**：基本能在 30s 内检测到，很多是 1-10s。
- **依赖 60s/300s probe 或轮询的故障**：当前不能保证 30s。
- **地图突然无法上网这个具体场景**：如果地图接入 `Polaris.reportNetworkTrouble()`，可以；如果没有 App 主动报障，不能稳定保证。

## 6.2 分故障类型判断

| 故障类型 | 当前检测路径 | 预计延迟 | 是否满足 30s |
| --- | --- | --- | --- |
| `eth0/eth1` link down | PVM netlink `RTNLGRP_LINK` | <1s | 是 |
| 关键 route 消失 | PVM netlink `RTNLGRP_IPV4_ROUTE` | <1s | 是 |
| conntrack table full | sd-journal + 10s count/max poll | 3-10s | 是 |
| 关键服务退出 | sd-bus / 5s 轮询 | 3-5s | 是 |
| `qcrosvm` 退出 | 5s 轮询 | <=5s | 是 |
| vmtap operstate down | inotify | <1s | 是 |
| vmtap 单向不通 | `/proc/net/dev` 30s 比较窗 | 约 30s 边缘 | 勉强，风险较高 |
| 网关不可达 | 60s ICMP probe | 约 60s | 否 |
| DNS 失败 | 60s/300s probe + GVM 60s 巡检 | 60-300s | 否 |
| NAT 规则漂移 | 60s 哈希比对 | 约 60s | 否 |
| 地图主动报障 | App event → PVM SHU 检查 | 5-15s | 是 |

## 6.3 对“地图突然无法上网”的明确判断

这个场景分两种：

### 情况 A：地图接入了主动报障 API

则链路为：

- 地图请求失败
- App 调 `Polaris.reportNetworkTrouble(...)`
- PVM 立即做 SHU 关联检查 + probes
- 生成 root cause 与证据

这一条我认为**可以在 30s 内完成**，通常 10-15s 就够。

### 情况 B：地图没有主动报障接入

则系统只能靠：

- PVM `SHU_VLAN3_INTERNET` 的 60s probe
- GVM 60s 侧的 connectivity / DNS 巡检

这一条**不能保证 30s**。

## 6.4 如果要真正满足 30s，我的建议

建议至少补四项：

1. **关键网关邻居状态改成事件驱动**
使用 netlink 邻居事件，而不是仅靠 60s probe。

2. **DNS 从 300s 降到 15-30s 级别的轻量探测**
可以降低探测目标数量，但不能还是 300s。

3. **NAT 漂移检测从 60s 轮询降到 10-30s，或引入更实时的变更通知**
否则 NAT 类问题始终慢半拍。

4. **vmtap 单向不通的比较窗口缩短到 10s 量级**
否则 30s SLA 只是理论上边缘满足。

---

## 7. 最终建议

## 7.1 上线前必须修改

1. 补齐 `BASE-003` 的统一差异策略模型。
2. 补齐 `IP-005`、`FW-005`、`PERF-003/004/005/006`、`RPT-005` 的采集、基线和判定逻辑。
3. 增加 `scenario registry`，把场景 A-L、VLAN scope、SHU、check、probe、evidence files 的映射正式写出来。
4. 设计 incident 去重/归并策略，避免同一故障多条事件上云。
5. 定义 `fetch_log` 的分块/校验/超时协议。
6. 重新评估 `CPUQuota=5%`，建议改成软限制或 incident 模式放宽。
7. 如果 30s 是硬指标，必须把网关、DNS、NAT 漂移检测链路从 60s/300s 降下来。

## 7.2 可以在第二阶段补齐

1. softirq / `ksoftirqd` 轻量采样。
2. 广播/组播风暴检测模型。
3. 配置热重载与 PVM/GVM 双端版本协同。
4. 更细粒度的 rule capability / collector capability 抽象。
5. incident 历史保留与聚合统计。

## 7.3 最终评语

如果从 0 到 10 分打分：

| 维度 | 分数 |
| --- | --- |
| 架构方向 | 8.5/10 |
| 需求覆盖度 | 7.5/10 |
| 可扩展性 | 7/10 |
| 性能设计 | 7/10 |
| 30s 异常检测能力 | 6/10 |

最终评价：

**这份系统设计已经具备进入详细设计/实现阶段的基础，但还不适合直接作为量产实现蓝图。**

它的优点是主架构选型正确，PVM/GVM 分工正确，配置化思路正确；它的不足是若干关键要求只停留在“有 check 名称”，没有真正闭环到“有数据、有基线、有阈值、有聚合、有 incident 归并”。

把上面列出的必改项补齐后，这套方案会从“方向正确”升级为“工程上可靠”。

---

## 8. 补充评审（从智能座舱网络运维视角）

> 基于 §1-§7 已有评审，补充 20 处之前未明确指出、但在量产排障经验中常见的盲点。
> 评审增补日期：2026-05-09

### 8.1 关键补充发现

#### G1. **Probe 全部部署在 PVM 端，会漏掉"PVM 看到通、GVM 实际不通"的故障**

设计文档 §12.2 写"全部在 PVM 端执行 ... GVM 不重复 probe"，理由是节省流量。这个判断在工程上不成立：

- PVM `ping -I eth1.3 172.16.103.20` 走的是 PVM 自己的协议栈：源 IP `172.16.103.40`、不经过 vmtap、不经过 `iptables` POSTROUTING SNAT。
- GVM 应用的真实路径是 `eth1.3 (GVM) → vmtap1.3 (PVM) → POSTROUTING SNAT → eth1.3 (PVM)` 才到 `172.16.103.20`。
- 当 vmtap 段、SNAT 规则、`forwarding`/`rp_filter` 这些环节坏掉时，**PVM 自身的 probe 仍然 PASS，但 GVM 应用其实不通**。
- 这恰好是"地图突然不能上网"最容易踩的盲区——PVM 各项基线全 PASS，dashboard 一片绿，但用户已经报障。

修正建议：

- PVM 端额外加一类"模拟 GVM 视角"的 probe：在 `vmtap1.3` 上用 `SO_BINDTODEVICE` 强制走"GVM 路径"，或用 raw socket 构造源 IP 为 `10.10.103.40` 的 ICMP 让它真的过一次完整 NAT。
- 或者：让 GVM 端做一次低频（5 分钟一次）的真实端到端 probe，跟 PVM probe 结果做差分，差异即"NAT/forwarding 路径异常"。
- 这一项的成本极低（每 5 分钟几个包），但能闭合一类系统性盲区。

#### G2. **ICMP probe 完全没考虑 PMTU 黑洞**

ICMP echo 默认 64 字节，ECN 等扩展也很小。但车载以太网真实业务流量经常踩 MTU 不一致：

- VLAN 子接口 MTU 默认继承父接口，但 vmtap 的 MTU 由 qcrosvm 启动参数决定，**未必等于** GVM `eth1` MTU。
- 实测过一个故障：`ping -s 1400` 通，`ping -s 1500 -M do` 不通，但 SOME/IP 大数据包卡死——典型 PMTU 黑洞。
- 当前设计中 `PERF-005`（MTU 一致性）虽然在 check 列表里，但配置 schema 没定义 MTU 基线字段（已有 review F2 也指出这点）。即使 MTU 配置一致，物理链路的 PMTU discovery 是否正常仍未验证。

修正建议：

- ICMP probe 增加"大包能不能通"的子项：1 个小包（64B）+ 1 个 PMTU 边界包（如 1472B / 8000B for jumbo），DF=1；丢包阈值分别独立报。
- 这能识别一大类 RTSP 视频卡顿、SOME/IP 大数据丢包、DoIP 刷写中断的真实根因。

#### G3. **缺"间歇性故障"探测能力**

车载网络真实故障里，"完全不通"反而少，"每隔 5 分钟丢一次包"、"某条 VLAN 偶尔 100ms 抖动"才是日常。当前设计：

- 每个 SHU 60s 打 3 个 ICMP 包；
- 滚动窗口"最近 20 条"——20 × 60s = 20 分钟数据；
- 用"连续失败 N 次"判定故障。

这种采样率对间歇故障是看不到的：3 包没丢就过了，下一次 60s 后又随机抽 3 包，绝大多数抖动会被滤掉。

修正建议：

- 至少对 P0 SHU（VLAN3/Host-Guest）做一条"长 RTT 时间序列" probe：1s 一个包持续 60s，记录 P50/P95/P99 + 抖动 + 丢包微突发；不计入流量预算的常态值，仅触发后启动 30s 即可。
- 或者复用 GVM ConnectivityService 自带的 NCM (Network Connectivity Monitor) 的 RTT 时间序列，免得自己重造。

#### G4. **GVM 主动报警的"自身配置快照"在故障时本身不可信**

设计文档 §5.3 GVM alert push payload 含 `snapshot_brief`，里面有 `iface_up`、`has_default_route`、`neigh_state`、`default_netid`。这些数据从 `ip` 命令和 `dumpsys connectivity` 解析。

问题：

- 如果是 netd / resolver 死了导致的故障，`dumpsys connectivity` 自己可能就 hang 或返回过时数据。
- 如果是 GVM `system_server` 卡住，`dumpsys` 全部失效。
- 此时 push 上来的 `snapshot_brief` 反而是误导信息。

修正建议：

- `snapshot_brief` 必须分两层：底层（`ip addr/route/rule/neigh` 来自 netlink，永远可用）+ 高层（`dumpsys connectivity` 等可能 hang）。
- 高层数据用独立超时（≤500ms），超时即填 `BLOCKED` 而不是空字符串。
- alert 发出时必须有 `data_quality` 字段说明哪些字段是降级数据。

否则故障的根因（netd 卡死）会被掩盖。

#### G5. **Boot 阶段缺"warmup 期"，开机必爆假阳性**

设计 §3.1.3 写"启动 → 等待 10s → 执行首次全量 baseline diff"。10 秒在车机环境完全不够：

- TBOX 网关 ARP 解析、DHCP（如果有）、ConnectivityService 注册全部网络、GVM 端 dumpsys 数据填齐——这些都需要时间。
- 实测车机第一次 link up 到 `172.16.103.20` ARP 进入 REACHABLE 通常是 10-30s，最坏到 1 分钟（视 VCM 状态）。
- ADAS / OTA / VLAN 6 等业务网络要等到对端 ECU 注册组播组或者发出 SOME/IP `Find Service`，几十秒级别都常见。

如果 10s 后立即开始全量 diff，会爆出 N 条"假阳性"事件：网关 ARP FAILED、DNS probe 失败、vmtap RX/TX 增量为 0、SOME/IP 服务监听不存在……云端工单海啸。

修正建议（参考 fdleak monitor 的成熟做法）：

- 每个 watchdog/probe/check 各自有 `warmup_sec` 字段，期内只采样不告警。
- 全局有 `boot_warmup_sec`（默认 120s），所有诊断信号在这期间只 INFO/不发 polaris 事件。
- `boot_warmup_sec` 内出现的"异常"如果 warmup 结束仍存在再正式上报，避免 transient 噪声。

这一项不做，第一次量产开机第一天就能把 polaris 队列打爆。

#### G6. **时钟管理没设计：wall-clock vs monotonic vs boot_id**

设计文档全程使用 `ts_unix`（wall-clock）做事件时间戳。两个问题：

1. **车机 NTP 同步前后时钟会跳变**：刚开机的几分钟用本地 RTC（精度差且常错几小时甚至几年），同步后跳到正确时间。incident 排序按 `ts_unix` 直接错乱，云端聚合工具会看到"某 incident 发生在 1970 年"。
2. **`trigger_min_gap_sec=30` 用 wall-clock 实现**：NTP 跳变期间这个限流策略可能误放行（时钟回退）或误压制（时钟前跳）。

修正建议：

- 内部状态机（去重、限流、`first_seen` 计时）一律用 `CLOCK_BOOTTIME`（不受 NTP 影响、suspend 仍计数）。
- 事件 payload 同时输出 `ts_unix`（wall-clock）+ `ts_boot`（monotonic since boot）+ `boot_id`（machine-id 或 `/proc/sys/kernel/random/boot_id`）。
- 云端聚合工具用 `(boot_id, ts_boot)` 排序，用 `ts_unix` 做日历展示。
- PVM/GVM 各自的 `ts_unix` 偏差超过阈值（比如 5s）必须告警——这正是已有 review F2 中 RPT-005 的真正含义。

#### G7. **"事件级聚合"未设计，单一物理故障会触发链式事件**

已有 review F3 提了"incident 去重"，但更深入的问题是**事件链聚合**。举例：

PVM `eth1` 物理 link down 一瞬间，会同时触发：

- `NETDIAG_LINK_DOWN(eth1)`
- `NETDIAG_BASELINE_DRIFT`（route default via 172.16.103.20 消失）
- `NETDIAG_GATEWAY_UNREACHABLE(VLAN3 TBOX)`
- `NETDIAG_GATEWAY_UNREACHABLE(VLAN6 ADCU)`
- `NETDIAG_GATEWAY_UNREACHABLE(VLAN7 OTA)`
- `NETDIAG_GATEWAY_UNREACHABLE(VLAN8 ADAS)`
- `NETDIAG_VM_LINK_BROKEN(vmtap1.3,4,6,7,8)`（GVM ping 全失败）
- `NETDIAG_APP_NETWORK_TROUBLE × N`（每个应用都报障）
- `NETDIAG_SERVICE_DOWN`（如果 someipd 因网络丢包退出）

10+ 条 polaris 事件指向同一根因。

修正建议：

- 设计中明确"事件因果模型"：根事件 + 派生事件。
- `NETDIAG_LINK_DOWN(eth1)` 是根事件，3 秒内触发的所有 `NETDIAG_GATEWAY_UNREACHABLE` 等都是派生事件，payload 里带 `caused_by: NETDIAG_LINK_DOWN/incident_xxx`。
- polaris commit 时只发根事件 + 一个汇总的"派生事件 ID 列表"，不是逐条上云。
- 云端 dashboard 看到一条根 incident，展开是派生事件列表。

否则一次 link 抖动就是 50+ 条事件灌爆 polaris 队列；polarisd `mOfflineCache` 容量 500 条很容易被打满。

#### G8. **netfilter 兼容性：iptables vs nftables**

设计完全围绕 `iptables -t nat -S` / `iptables -S`。Linux 6.6 内核默认推 nftables；当前 PVM 实测仍是 iptables（实测确认了），但风险是：

- `iptables` 当前在 6.6 上很多发行版只是 `iptables-nft`（兼容层），输出格式和原生 `nft list` 不同。
- 一旦车机底座升级把 iptables wrapper 换成原生 nft，本设计的所有"规则字面比对" `must_contain` 会全部 FAIL。
- 已有 review 没提这个点，但量产 5 年内大概率会撞上。

修正建议：

- 把"netfilter 规则采集"做成抽象层：`NetfilterCollector` interface，下面可以接 `IptablesAdapter` / `NftAdapter` / `BpfilterAdapter`。
- `must_contain` 的字符串匹配换成"语义化规则比对"——把规则解析成五元组（chain, match, target, params, position），按结构对比，而不是按文本对比。
- 这样 nftables 切换、kernel 升级都能吸收。

#### G9. **GVM ConnectivityService callback 怎么订阅没说**

设计文档 §11.2 GVM Watchdog 列出"Android Connectivity 变化"用 callback，但回调是 Java 层 API。`network-diag-gvm` 是 native 进程，要怎么用？

三个选项各有问题：

- **走 PolarisAgent 中转**：增加耦合 + 多一跳延迟，PolarisAgent 自己卡住时 callback 失效。
- **直接 binder 调 IConnectivityManager.aidl**：要 `system_server` 同等权限，sepolicy 复杂度大，量产 user 镜像未必给。
- **退回 dumpsys 60s 周期 poll**：跟 callback 重复，且 60s 延迟不够 30s SLA。

设计文档没明确选哪个。

修正建议：

- 默认实现走 `dumpsys connectivity` 60s poll（已有，现成可用）。
- 把 callback 列为"可选增强"——通过 PolarisAgent JNI 桥接（Java callback → native via JNI/binder）。
- 明确这条信号源在 user 镜像上的可达性是 BLOCKED 还是降级。

#### G10. **Probe 加紧策略未量化**

设计文档 §4.2 路径②写"PVM 立即跑对应 SHU 的 PVM 检查 + probe 加紧打 N 轮"。N 是多少？多快？多久？跟正常 probe 怎么协调？没说。

工程实际：

- 加紧 probe 一刀切到 1s/包，连续 30 包，就是 30 秒——已经吃满 SLA。
- 跟正常 probe scheduler 怎么交互？要不要禁掉 60s 那一轮避免双发？
- 加紧期间 probe_max_pps=100 还能保证吗？（如果同时 5 个 SHU 都加紧，单 SHU 1 包/秒 × 5 = 5 包/秒，OK）

修正建议（明确数值）：

- 加紧周期：1s/包，连续 5 包，总计 5 秒；
- 5 包内 ≥3 包失败 → FAIL 终判，1 包失败 → 再来一轮 5 包；
- 加紧期间正常 probe 暂停（同 SHU 互斥），其他 SHU 不受影响；
- 加紧最长持续 30s，超时回归正常 60s。

#### G11. **vmtap 单向不通 30s 窗口在采样误差内"边缘满足"**

已有 review 也提了这个，但具体的数值分析未给。展开：

- `/proc/net/dev` 提供累计计数，30s 单向增长判定要求采样间隔 ≥1s（避免 jitter 误判）。
- 实际 30s 窗口内只有 ~30 个采样点；TX 完全为零、RX 持续增长这种边界案例需要严格 30s。
- 但 GVM 端没"实时事件"信号，只能依赖 PVM 端这种统计学判定。
- 如果 30s 内只有 1 个或 0 个 TX 包（小流量场景），统计学误判率 >10%。

修正建议：

- 30s 改 20s，结合"GVM 那边是不是 carrier=1 + 有 ARP 流量"做交叉验证。
- 加一项"协议层握手"测试：周期性让 GVM 主动 ping vmtap0 (10.10.200.1)，PVM 看是不是 1s 内有响应；这是端到端 echo 测试，比统计学判定可靠得多。
- 这条信号对"双向通"是充分的，对"单向不通"也敏感（因为 ICMP echo 必须双向才能完成）。

#### G12. **Boot 阶段 PolarisAgent 比 network-diag 后启动**

设计 §16.1 systemd unit `After=polarisd.service`，但 PolarisAgent 是 Android Java 应用，启动时机由 Android `system_server` 决定。常见时序：

- PVM Linux 启动 → network-diag-pvm 启动（5-15s）。
- qcrosvm 启动 GVM → Android boot → ConnectivityService 注册（~30s 后）→ PolarisAgent 启动（~45s 后）。

这意味着开机后第一波诊断事件可能在 PolarisAgent 还没起来时已经被产生，事件会卡在 polarisd `mOfflineCache`。

修正建议：

- network-diag-pvm 在 boot warmup 期内（120s）只产生本地 incident_dir，不发 polaris 事件，等 PolarisAgent 通路稳定再补报。
- 或者：让 polarisd 在 PolarisAgent 未连上时把事件落本地磁盘队列（`/data/log/perf/polarisd_pending/`），连上后 flush——这是 polarisd 团队该做的，不是 network-diag 该做。

不处理的话：每次开机第一分钟所有事件丢进黑洞。

#### G13. **`iptables -L -nv` 在 conntrack 表大时 CPU 占用极高**

已有 review 指出 `iptables -L -nv` 是性能热点，没量化。补充：

- iptables 每条规则的命中计数器是从 conntrack 遍历汇总的；
- conntrack 50K 条以上时，`iptables -L -nv` 单次执行 100-300ms 是常态；
- 100K 条时 500ms-1s；
- conntrack 表满时（达到 max=262144），单次执行 >2s，期间持锁影响其他 netfilter 操作。

也就是说**`-L -nv` 在最需要它（conntrack 压力高时）的时候性能最差**。

修正建议：

- conntrack 使用率 ≥80% 时，自动跳过 `-L -nv`，改用 `-S` 已经包含的规则集 + 不带计数器；
- 计数器需求只在 SCAN_REPORT（每天一次）时执行，且加 timeout=3s 兜底。

#### G14. **BusyBox `dmesg | grep` 在 PREEMPT_RT 下读 kmsg 缓冲会潜在影响**

设计文档 §13.1 用 `dmesg | grep -i 'nf_conntrack: table full'` 检索关键字。问题：

- BusyBox `dmesg` 默认读完整 kmsg 缓冲；车机 kmsg 持续累积，开机几小时后能到 16-64 MiB；
- `grep` 在大量文本上是 CPU 密集任务（虽然不大但有 spike）；
- PREEMPT_RT 下大文本 grep 可能造成几十毫秒级 latency spike，影响其他实时任务。

修正建议：

- 改用 `journalctl -k --since="2 minutes ago" --no-pager | grep ...` 只读最近时间窗口；
- 或者：watchdog 用 `sd-journal` API 实时订阅（`SD_JOURNAL_LOCAL_ONLY` + matcher `_TRANSPORT=kernel` + grep matcher），永远不读历史，只看新增——这是设计文档已经提到的方案，但 §13.1 命令集里又退回 `dmesg | grep`，自相矛盾。
- 统一收口到 sd-journal subscribe 路径。

#### G15. **某些 check 在量产 user 镜像上根本拿不到数据，但 BLOCKED 没分级**

实测：当前 device 是 userdebug + Permissive。但量产 user 镜像：

- `dumpsys connectivity` 可能受 SELinux 限制，仅 system 进程可调；
- `iptables` 命令可能不存在（vendor 切到 nft）；
- `/proc/net/nf_conntrack` 可能读不到（perm 修改）；
- `ethtool` 在 GVM 上几乎肯定没有；
- `tcpdump` 在量产镜像通常被剥离。

每条 BLOCKED 不应"等同处理"，应该分级：

- **BLOCKED-L1（环境性）**：例如 `dumpsys` 缺少权限——量产用户镜像的预期状态，**正常态**，报告里 INFO；
- **BLOCKED-L2（异常）**：例如 PVM 上 `iptables` 突然不存在——异常，需要告警 FAIL；
- **BLOCKED-L3（间歇）**：命令超时或 EINTR——重试一次再判定。

设计文档现在所有 BLOCKED 一刀切，会让"正常的 user 镜像"被误判为"系统异常"。

修正建议：补 `blocked_severity` 字段，每条 check 配置独立指定缺失时的处理。

### 8.2 30s SLA 的延迟预算分解（补充）

已有 review 给了"路径②约 10s"的判断，但没拆解。按 20 年座舱排障经验估的实际延迟：

| 阶段 | 单跳延迟 | 累积 |
| --- | --- | --- |
| GVM watchdog 触发（netlink/poll） | 1-3s | 3s |
| GVM 采集快照（`ip` 命令 × 5） | 0.5-1s | 4s |
| GVM 写入 snap_dir + serialize | 0.2-0.5s | 4.5s |
| VSOCK 9101 push（含序列化） | 0.1-0.3s | 4.8s |
| PVM 接收 + 路由到对应 SHU 协调器 | 0.1-0.3s | 5.1s |
| PVM 立即采集（并行：ip + iptables + ss + sysctl） | 0.5-1s | 6s |
| PVM probe 加紧（5 包 × 200ms） | 1-1.5s | 7.5s |
| PVM 数据 merge + analyzer 计算 root cause | 0.5-1s | 8.5s |
| incident_dir 写入（含 baseline_diff、report.md） | 0.5-1s | 9.5s |
| `polaris_report_raw` UDS write + polarisd 序列化 | 0.1-0.3s | 9.8s |
| polarisd VSOCK 9001 send 到 GVM polarisd | 0.1-0.3s | 10.1s |
| GVM polarisd 转发 PolarisAgent | 0.1-0.3s | 10.4s |
| PolarisAgent 上云 RTT（依赖 TBOX/4G/5G） | 1-10s | 11.4-20.4s |

最坏估计 20 秒，常态 11-13 秒。仍在 30s SLA 内，**但前提是 probe 加紧并行采集 + PVM 命令并行执行 + 上云 RTT 不超 8s**。

如果上云 RTT 大（比如 4G 网络弱信号 5-10s 是常见的），SLA 会被吃满。所以"30s SLA"的真实瓶颈：

1. 上云 RTT（不可控，看 TBOX）
2. PVM 命令串行执行（可优化：并发执行 ip/iptables/ss/sysctl 4 个命令，少 1.5-2s）
3. probe 加紧 5×200ms（可优化：并发打 5 个 SHU 的 probe，少 1s）
4. incident_dir 写盘（可优化：用 tmpfs `/run/polaris/network-diag/` 作 staging，最后再 mv 到 `/log/perf/`）

修正建议：

- 设计文档明确：30s SLA 不含云端 RTT；本地诊断闭环（从 GVM 触发到 polaris commit）SLA 改为 15s。
- 命令采集器实现要支持 parallel execution（线程池），不能 for 循环串行。

### 8.3 安全维度补充

#### G16. **probe 目标硬编码 `8.8.8.8`/`www.baidu.com` 的合规风险**

车规产品在某些区域：

- `8.8.8.8` 不可达（被运营商屏蔽）；
- `www.baidu.com` 在出口管制场景需要审批；
- DNS 查询特定域名可能触发 DPI 告警。

修正建议：

- probe 目标全部走配置，按区域/SKU 选择。
- 默认目标用"项目自有的健康检查端点"——例如 TBOX 后端提供一个 `/healthz`，比第三方更可控。
- 在分析 probe 失败时区分"目标本身不可达 vs 我方网络不通"——单目标失败默认 INFO，多目标全失败才 FAIL。

#### G17. **测试模式与维护窗口未设计**

车机经常有维护场景：

- 整车诊断仪连入 VLAN 4 主动测试 IDPS（30006），会让 PVM 的 IDPS 监听看起来"流量异常"；
- ADAS 标定流程会临时改 ADCU 视频流参数，VLAN 15 RTSP 包率会偏离基线；
- OTA 升级期间 VLAN 7 流量会暴涨。

如果没"维护模式"开关，这些正常运维操作都会触发 polaris 事件。

修正建议：

- network-diag-pvm 提供一个 PolarisAgent 可调用的 IAction `netdiag.set_maintenance_mode { enable: true, scope: ["VLAN4"], duration_sec: 600 }`；
- 期内对应 SHU 的告警降级 INFO，不发 polaris 事件；
- 维护模式有最大持续时间防止遗忘。

#### G18. **取证文件可能含敏感信息**

`incident_dir` 里的 `dumpsys connectivity`、`ip neigh show` 包含：

- VLAN 网关 MAC（VCM/TBOX 的 MAC 即设备指纹）；
- conntrack 表（包含所有外部连接对端 IP）；
- `ss -ltnp` 含进程名 + 监听端口（暴露内部架构）。

云端上报这些数据有合规风险（个人信息保护、车控数据安全）。

修正建议：

- 取证打包前过一道脱敏（mask MAC 后两段、tcpdump 包仅留 metadata 不留 payload）；
- 字段级敏感性等级标注（manifest.json 加 `sensitivity: low|medium|high`），云端按等级决定是否拉取。

### 8.4 特殊业务路径补充

#### G19. **VLAN 15 RTSP / mmhab 的"网络范围终止边界"模糊**

设计 SHU_VLAN15_RTSP 标了 P0，但 VLAN 15 业务真实链路是：

```
ADCU 172.16.115.98 → eth0.15 RTSP 流入 → Camera Server → mmhab 共享内存 → GVM Camera Client → 渲染
```

mmhab 是非 IP 通道，网络诊断完全看不到。当前设计只验到 RTSP 输入侧（`eth0.15` link/IP/ARP），对"GVM 是不是真的在收帧"没法验证。

但用户感知"视频不行"覆盖了整条链路。

修正建议：

- 明确标注：网络诊断范围终止于 `eth0.15` + Camera Server 进程存活，不包含 mmhab 后段。
- 跟 Camera 团队约定接口：Camera Client 周期性向 polarisd 发 `CAMERA_FRAME_HEALTH` 事件（含帧率、丢帧率），网络诊断把这条事件作为 SHU_VLAN15_RTSP 的依赖，跨域聚合。
- 否则会出现"网络说没事，画面没了，没人能定位"的责任真空。

#### G20. **多实例 someipd 的进程级故障归因**

实测看到 7 个 someipd 实例（PID 不同，分别绑 VLAN 10/11/12/13/14/19）。当前服务基线列了 8 条 `someipd` bind 项，但：

- 没有 (process_name, pid_start_time, bind_addr) 三元组建模；
- 如果 1/7 实例崩溃，其他 6 个还活着，怎么准确告警"VLAN 11 的 someipd 退出"而不是"someipd 全挂"？
- 当前设计倾向于按 bind 端口判定，但 bind 端口跟 PID 没绑定，进程崩溃后 sport reuse 会让"端口仍监听但是新进程"——监听 ≠ 健康。

修正建议：

- 服务基线模型加 `process_match: {comm: "someipd", argv_pattern: "...VLAN10..."}` 区分实例；
- 健康判定加 `pid_stable: true` 检查（PID start_time 跟上次扫描相同才算健康）；
- 单实例失败上报 `service_instance_id`，不要笼统报"someipd down"。

### 8.5 评分与最终意见调整

补充以上 20 项后，我对评分微调：

| 维度 | 原 review | 补充后 | 说明 |
| --- | --- | --- | --- |
| 架构方向 | 8.5/10 | 8.5/10 | 主架构没问题 |
| 需求覆盖度 | 7.5/10 | **6.5/10** | F2 + G2/G3/G18/G19/G20 把"覆盖度"重新评估，缺口比想象多 |
| 可扩展性 | 7/10 | **6/10** | G8（iptables→nft）+ G14（命令抽象）+ G18（敏感性分级）显示抽象层不够 |
| 性能设计 | 7/10 | 7/10 | G13 的量化没改变结论 |
| 30s 异常检测能力 | 6/10 | **5/10** | G1（PVM probe 漏 NAT 路径）+ G3（间歇故障）+ G10（加紧策略未量化）显示真实保障弱于纸面 |
| **可观测性/可运维性**（新增） | — | **5/10** | G7（事件聚合）+ G6（时钟）+ G18（敏感性）这些量产运维必备项缺失 |

### 8.6 补充上线前必改清单（与 §7.1 合并）

| 优先级 | 项目 | 依据 |
| --- | --- | --- |
| **P0** | Boot warmup 期 + 各信号源 warmup_sec 字段 | G5 |
| **P0** | 时钟管理：内部用 BOOTTIME，事件附 boot_id + ts_boot | G6 |
| **P0** | 事件因果模型 + 根/派生事件聚合 | G7 |
| **P0** | snapshot_brief 分层 + data_quality 字段 | G4 |
| **P0** | 命令并行执行（采集器线程池）+ probe 加紧策略量化 | G10 + 8.2 |
| **P1** | PVM probe 模拟 GVM 视角（或 GVM 低频反向 probe） | G1 |
| **P1** | ICMP probe 加 PMTU 边界包测试 | G2 |
| **P1** | netfilter 抽象层（解耦 iptables vs nftables） | G8 |
| **P1** | BLOCKED 分级（环境性 vs 异常 vs 间歇） | G15 |
| **P1** | conntrack 压力大时跳过 `iptables -L -nv` | G13 |
| **P1** | dmesg 检索统一到 sd-journal | G14 |
| **P2** | 维护模式接口 + 测试窗口 | G17 |
| **P2** | 取证脱敏 + 敏感性分级 | G18 |
| **P2** | someipd 进程级建模 | G20 |
| **P2** | mmhab 跨域接口（与 Camera 团队） | G19 |
| **P2** | probe 目标按 SKU/区域配置 | G16 |
| **P2** | 间歇故障"长 RTT 时间序列" probe（v2 也行） | G3 |

### 8.7 总结

加上 §1-§7 已识别的问题，本设计在工程深度上还需要再迭代一轮。关键差距集中在两处：

1. **量产运维成熟度不够**：boot warmup、时钟管理、事件聚合、敏感性分级、维护模式——这些在第一版常被忽略，第二版必加。设计文档现在的状态是"功能正确，运维痛点缺失"。
2. **真正的端到端故障感知有盲区**：PVM probe 漏 NAT 路径、ICMP 漏 PMTU、缺间歇故障检测——这些都是"地图突然不能上网"类故障的真实场景，文档纸面看 SHU 已覆盖，实际还差 10-30% 才能稳态识别。

如果按补充清单修齐，本设计可以从"能上线但运维痛苦"升级为"能上线且运维省事"，后期维护成本下降一个数量级。

最后一句话总结：**当前设计对"系统状态偏离基线"敏感得很；对"系统状态正常但用户感知不爽"还需要再深一层**。这正是座舱网络诊断真正难的地方。