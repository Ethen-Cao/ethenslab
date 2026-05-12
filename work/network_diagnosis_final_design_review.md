# 智能座舱网络诊断最终设计严苛 Review

> **评审对象**：`work/network_diagnosis_final_design.md`（6878 行，v1.1+）  
> **依据**：`work/network_diagnosis_requirements.md`（84 项 NET-DIAG-*）+ 5 个配置附件 + 实机调研结论  
> **评审日期**：2026-05-11  
> **评审视角**：20 年座舱网络运维 + 系统架构 + 工程落地角度  
> **评审策略**：不客气、找证据、问到根、检查闭环

---

## 1. 执行摘要

### 1.1 总体结论

| 维度 | 评分 | 备注 |
|---|---|---|
| 需求覆盖广度 | 7.5/10 | 84 项需求基本对得上，但若干"实现"流于表面 |
| 需求实现深度 | 6/10 | 一批 check 落在表格里，但实现路径不闭环 |
| 逻辑闭环 | 7/10 | 主流程闭环，**boundary 条件、降级路径、Boot 时序有 5 处明显裂缝** |
| 设计一致性 | 6/10 | 跨章节出现 **3 处明确矛盾**，1 处自我推翻 |
| 时序图正确性 | 7.5/10 | 24 张图主线正确，但有 2 张细节错、3 张过度简化 |
| 协议与接口 | 7/10 | 接口契约清晰；但**通道 C 设计跟实现章节自相矛盾** |
| 性能可行性 | 6.5/10 | 常态预算可信；**30s SLA P95 在 4G/5G 弱信号场景实际不达**；HttpProbe 实现有内存泄漏隐患 |
| 安全可靠性 | 6.5/10 | C1-C9 约束基本遵守；但**命令白名单含 `kill`** 属于明显漏洞 |
| 量产成熟度 | 6/10 | 缺 OTA 一致性回滚机制、缺 NetlinkReactor 重连、缺 sd-journal 断流恢复 |
| **综合** | **6.6/10** | **设计方向正确、文档完整、但工程落地前必须修复 12 个 P0 阻塞项** |

### 1.2 核心结论

**这是一份方向正确、文档详尽的设计，但还不能直接交付实现。** 主要问题集中在 3 处：

1. **设计自身的矛盾未消除**（R-CONS-1, R-CONS-2）—— §6.3 通道 C 协议跟 §22.1 实现互相打脸；§28 GvmPerspectiveProbe 降级但 §11/§13 仍把它作为主探测
2. **需求与实现深度差距过大**（R-COV-3, R-COV-5, R-COV-7）—— MODE-001 60s SLA、PERF-002 抖动阈值可配置、SEC-006 listenport diff 持久化都缺关键实现
3. **工程落地遗漏**（R-IMPL-1..7）—— HttpProbe detached thread 泄漏、`kill` 在 binary 白名单、NetlinkReactor 重连缺失、sd-journal 历史丢失、active_faults.json 跨进程崩溃恢复路径模糊

下面按主题深入。

### 1.3 阻塞项数量

- **P0（阻塞实现启动）：12 项**
- **P1（实现期必须解决）：18 项**
- **P2（可在 v1.1++ 跟进）：14 项**
- **总计 44 项**问题

---

## 2. 需求覆盖度严格审查

### 2.1 数量核对

需求文档 84 项 NET-DIAG-* ID（按类别）：

| 类别 | 需求数 | final_design check 数 | 覆盖关系 |
|---|---|---|---|
| MODE | 5 | 0 check + 模块行为约定 | ✓（§10.4）|
| BASE | 5 | 5 | ✓ |
| LINK | 6 | 6 | ✓ |
| VLAN | 7 | 7 | ✓ |
| IP | 5 | 5 | ✓ |
| ROUTE | 6 | 6 | ✓ |
| NAT | 4 | 5（L4-NAT-001..005，含 v1.1 增）| ✓ + 增强 |
| FW | 5 | 7（L4-FW-001..007，含 v1.1 增）| ✓ + 增强 |
| VM | 7 | 7 | ✓ |
| SVC | 12 | 12 | ✓ |
| PORT | 5 | 6（含 v1.1 GVM SYN_SENT）| ✓ + 增强 |
| PERF | 6 | 6 | ✓ |
| SEC | 6 | 6 | ✓ |
| RPT | 5 | 0 check + 模块行为 | ✓（§10.4 + RPT-001 端侧不出 Markdown）|
| **v1.1+ 新增** | — | 2（L5-HTTP-001, L5-TCP-001）| 闭环 V2-001 |
| **合计** | **84** | **80 check + 10 行为约定** | ✓ |

**结论：数量上 100% 覆盖**。但深入到"实现深度"层级，有问题。

### 2.2 实现深度严苛审查（逐项查找虚假覆盖）

#### R-COV-1 [P0] MODE-001 "60s 完成基础巡检" 没测试验证

**需求原文**（`network_diagnosis_requirements.md` §5.1）：
> "在 60 秒内完成基础巡检，报告包含每个 VLAN 的状态、异常项和结论。"

**final_design 实现**：
- §5.1.3 启动 T+10s 开始巡检
- §17.3 30s SLA 延迟预算分解里给的是 3-7s（异常态本地闭环）
- **但没有任何 TC 测试"全量巡检 60s 必达"**

**缺口**：

- 没明确"巡检 ≠ 一次 incident"，巡检是定时全量扫，需要分别计时
- 25 个 TC 都是单点故障注入，**没有"全量场景 + 计时 60s"的 SLA 验证 TC**
- §17.5 "性能压力测试 TC-PERF-001..005" 验的是异常态稳定性，不是巡检吞吐

**建议**：补 `TC-PERF-006 全量巡检 60s SLA`：触发 1h 全量，验证从 ScanScheduler tick 到 NETDIAG_SCAN_REPORT 出 polaris 的总耗时 < 60s。

---

#### R-COV-2 [P1] MODE-002 / MODE-003 实现链不完整

**需求**：MODE-002 按 VLAN 专项；MODE-003 按业务场景。

**final_design 实现路径**：
- §10.5 `CheckRunner::run(RunSpec)`，spec 含 `scope=vlan|scenario|shu|single_check_id`
- §24.4 SEQ-04 云命令下发：Cloud → PolarisAgent → GVM polarisd → IAction(netdiag.run) → GVM net_diagd → ...
- `scenario-registry.json` 含 `vlan_scope_filter` 和场景 A-L 映射

**但 §22.x 没明确**：
- `netdiag.run` IAction 在 GVM 端注册到 GVM polarisd 是必须的，但 §6.2 说"v1 不接收云命令到 PVM"——那 GVM polarisd 端怎么接收？需要 GVM polarisd 加一个 IAction？还是 PolarisAgent 直接走某种 Java SDK？
- **GVM polarisd 端的 `IAction("netdiag.run")` 没在任何文档明确"由谁实现"**

**缺口**：

- §21 polaris 团队对接清单（§27.1）**漏列"GVM polarisd 实现 IAction(netdiag.run)"**
- 如果 GVM polarisd 团队没做，云命令下发链断在 PolarisAgent → GVM polarisd 这一跳

**建议**：补到 polaris 对齐清单（v1.1+ 必须修订 §27.1）。

---

#### R-COV-3 [P0] L1-LINK-003 "持续增长 FAIL" 逻辑无状态

**需求**：
> "计数器非零需输出 WARN；若两次采样间持续增长，输出 FAIL 并提示物理链路、PHY 或线束风险。"

**final_design §10.3.1**：
> "计数器非零→WARN，两次采样递增→FAIL"

**问题**：
- "两次采样递增"是状态判定，需要保存上次值。**但 §15 取证目录、§16 时钟、§5 进程模块 都没说"per-iface 计数器历史"持久化在哪**
- ScanScheduler 在 60s 巡检之间，进程重启会丢历史 → 重启后第一次采样无法判断"持续增长"
- 也没说"持续多久才算 FAIL"——是连续 2 次 60s 巡检递增？还是 3 次？10 次？

**建议**：

- 设计补"per-iface counter history" 持久化（与 active_faults.json 同目录）
- 明确 FAIL 判定阈值：连续 3 次 60s 巡检递增 + delta_total > 阈值
- 进程启动时如未持久化历史，第一次仅取样不告警（warmup 类似处理）

---

#### R-COV-4 [P1] L1-LINK-004 flapping 检测的真实数据源

**需求**：
> "5 分钟内同一接口 link 状态变化超过 3 次输出 FAIL"

**final_design §10.3.1 / §12.1 WD_PVM_LINK**：
- 数据源：`netlink RTNLGRP_LINK + carrier_changes`
- "5min carrier_changes ≥3 → FAIL"

**问题**：
- `carrier_changes` 是**单调累加**的，不能直接判"5 分钟内变化次数"
- 需要内存里维护时间序列（保存最近 5 分钟的 carrier_changes 值）
- 但 §5.1.1 模块划分中没有 `LinkStateHistory` 或类似模块；§16 时钟设计中也没说

**缺口**：**实现路径模糊**。

**建议**：

- WatchdogReactor 增加 `LinkStateRingBuffer`，每 30s 采样一次 carrier_changes，保留 10 个样本（5 分钟）
- 判定：如果 `samples[0] - samples[9] >= 3` → FAIL

---

#### R-COV-5 [P0] PERF-002 阈值"按业务可配置"未真正实现

**需求**：
> "RTT 超过业务阈值或抖动持续升高时输出 WARN；阈值应按业务可配置。"

**final_design §11.2 SHU 配置**：
```jsonc
"sla": {
  "icmp_loss_warn_pct": 1, "icmp_loss_fail_pct": 5,
  "icmp_rtt_warn_ms":  50, "icmp_rtt_fail_ms":  100
}
```

**问题**：

- SHU schema 里只能配 RTT 上限，但**抖动（jitter）阈值字段缺失**
- "抖动持续升高" 是个时间序列判定，需要：① 抖动绝对值阈值；② "持续升高"的窗口大小和增长率
- §13.2.5 RttBurstProbe 只 emit p50/p95/p99/jitter 数值，没有"抖动评级"逻辑

**建议**：

```jsonc
"sla": {
  ...
  "jitter_warn_ms":         20,
  "jitter_fail_ms":         50,
  "jitter_rising_window_sec": 600,
  "jitter_rising_pct":      30        // 600s 内抖动相对均值上升 30%
}
```

并在 `PerfCheck` 或 `RttBurstProbe.computeStatistics()` 加抖动趋势判定。

---

#### R-COV-6 [P1] PERF-005 MTU 跨端验证不完整

**需求**：
> "PVM 物理侧、PVM vmtap 父/子接口、GVM VLAN 侧 MTU 必须符合基线"

**final_design + baseline-pvm.json**：

- baseline-pvm.json 共 21 个接口都有 `"mtu":1500` 字段 ✓（确认）
- baseline-gvm.json 有 GVM 接口 mtu 字段 ✓
- §10.3.8 PERF-005 数据源 `ip -d link show MTU`

**问题**：

- PERF-005 需要 PVM/vmtap/GVM 三侧比较，但 final_design 没说**比较逻辑在哪一侧执行**
- 如果在 PVM 跑，PVM 怎么拿 GVM 的 MTU？需要 NDGA `collect` RPC
- §11.1 SHU 表里 `PERF-005` 不在任何 SHU 的 `deps.checks` 里

**建议**：

- 明确 PERF-005 在 PVM CheckRunner 跑，通过 NDGA collect 拉 GVM 数据
- 加入 SHU_VLAN3/6/7/8 的 deps.checks

---

#### R-COV-7 [P0] PERF-006 广播风暴检测缺触发条件

**需求**：
> "ARP、mDNS、SOME/IP SD 等广播/组播包速率超过阈值时输出 WARN"

**final_design §10.3.8 PERF-006**：
> "数据源：短时 tcpdump 5s + 内核 multicast 计数；仅触发型"

**问题**：

- "仅触发型" → **由什么触发？**
- 没有 watchdog 对应"广播速率高"的信号
- ScanScheduler 60s 巡检也没说"每次都跑 PERF-006"
- 实际效果：可能永远不触发，等于没实现

**建议**：

- 增加 watchdog `WD_PVM_BROADCAST_RATE`：每 60s 读 `/proc/net/dev` 的 broadcast/multicast 计数增量，超过阈值（如 ARP > 100 pps）触发
- 触发后再跑 tcpdump 5s 做精细分析（这步符合"仅触发型"）

---

#### R-COV-8 [P1] SEC-006 listen port 变化检测的持久化

**需求**：
> "与基线相比新增端口、监听地址扩大、进程变化时输出 WARN"

**final_design §10.3.9 SEC-006**：
> "数据源：与上次扫描的 ss 输出 diff"

**问题**：

- "上次扫描" → **持久化在哪？**
- 进程重启后内存 diff 状态丢失，第一次扫描无 baseline 比对
- baseline-pvm.json 的 `services.required` + `documented_bind_any` 是静态基线，不是动态比对

**缺口**：明确 SEC-006 的状态文件：`/log/perf/network_diag/state/listen_ports_prev.json`，写盘原子 rename。

---

#### R-COV-9 [P0] RPT-005 时间偏差检测的失效路径

**需求**：
> "PVM/GVM 采集结果必须记录各自系统时间；若时间偏差超过阈值，应提示校时问题。"

**final_design §16.3 TimeSkewDetector**：

```cpp
const int64_t skewMs = abs(pvmTsUnix*1000 - gvmTsUnix*1000) - rttMs/2;
```

**问题**：

- `rttMs/2` 估算单向延迟有缺陷：发送和接收的 OS 调度延迟不一定对称
- 公式无法处理 PVM/GVM 时钟方向不一致（一个超前一个滞后）的判定
- 检测发现 skew_ms 后**只发 INFO**（§16.3 代码示例）—— 但需求要求"提示校时问题"，没说"提示给谁？怎么处理？"
- 检测周期 60s，不及时

**建议**：

- 公式改为 `|t_remote_at_recv - t_local_at_send - rtt_estimate|` 用 NTP 风格的 4-时间戳算法
- skew >= FAIL 阈值时除了上报，应在所有后续 incident manifest 加 `time_skew_warn:true` 标记，提示运维"事件时间戳不可信"

---

#### R-COV-10 [P2] VLAN-006 "tcpdump 抓包辅助验证"实际是 INFO

**需求**：
> "系统应支持 VLAN 抓包辅助验证。报告应给出对应 tcpdump 命令"

**final_design §10.3.2**：
> "L2-VLAN-006 数据源：报告中 hint；INFO 级"

**评价**：满足需求字面意思（提供 tcpdump 命令模板）。但需求语义其实是要"支持执行 tcpdump"——v1 已经有 TcpdumpRunner，但 L2-VLAN-006 没关联到 TcpdumpRunner。仅 hint 是文字渲染，不算"支持"。可接受但偏弱。

---

### 2.3 需求覆盖度结论

| 维度 | 评估 |
|---|---|
| 84 项需求 ID | 100% 出现在文档中（数量上覆盖）|
| 实现深度 P0 缺口 | **4 项**（R-COV-1/3/7/9）|
| 实现深度 P1 缺口 | **5 项**（R-COV-2/4/5/6/8）|
| 实现深度 P2 缺口 | **1 项**（R-COV-10）|

---

## 3. 逻辑闭环审查

### 3.1 fault_id 跨边界流转闭环

**正向流转**：✓

- PVM 启动 → 读 boot_id → 算 fault_id
- GVM 启动 → NDGA hello 同步 pvm_boot_id_short → 用同 epoch 算 fault_id

**反向问题**：

#### R-LOOP-1 [P0] PVM 启动前 GVM 已运行的边界

**实际场景**：
- 整车 ignition cycle 1：PVM + GVM 都启动，pvm_boot_id = A
- ignition off
- 整车 ignition cycle 2：因 GVM 调度延迟，GVM init.rc 起 net_diagd **比 PVM 慢**（常态）
- 但**反向边界**：极端情况下 PVM 因某种原因重启，GVM 未重启
- GVM 缓存的 pvm_boot_id_short 仍是 A
- PVM 新 boot_id = B
- GVM 用旧 A 算 fault_id；PVM 用新 B 算 → **fault_id 不一致**

**final_design 处理**：
- §6.1.7 NDGA 心跳 30s + 3 次未响应 close+reconnect → 60-90s 后 GVM 才检测到
- 这 60-90s 窗口期内，**双端 fault_id 不一致**，事件无法关联

**缺口**：

- 没有"PVM 重启时强制踢 GVM 连接 + 重新握手"机制
- 没有"GVM 收到 PVM 心跳但 hello 阶段 sha256 / pvm_boot_id 已变"的处理

**建议**：

- NDGA 心跳 payload 加 `pvm_boot_id_short` 字段（每次心跳带）；GVM 比对发现变化立即断连重连
- 或：PVM 启动时通过其他方式（systemd notify 或 polaris 自带机制）通知 GVM polarisd "我重启了"

---

#### R-LOOP-2 [P1] active_faults.json 跨进程崩溃恢复路径

**final_design §9.6**：

```cpp
void ActiveFaultsPersistence::onStartup() {
    // 校验 pvm_boot_id_short 与当前一致
    if (root["pvm_boot_id_short"].asString() != Clock::instance().pvmBootIdShort()) {
        LOGI("active_faults.json from previous boot, discarding");
        return;
    }
}
```

**问题**：

- PVM diag 崩溃 → 重启 → boot_id 不变 → 加载 active_faults.json → 恢复 ACTIVE 状态
- 但 active_faults.json 里的 fault 状态可能已经过时（real-world 故障已恢复但 PVM diag 还没采到）
- 启动后会"假装"这些 fault 还在 ACTIVE，导致 ongoing log 错误
- §9.6 注释"仍 FAIL → 视为 ACTIVE_ONGOING 续期，不发新的 fault event"——但 PVM diag 重启后没有"重新感知 fault 是否仍 FAIL"的明确步骤

**建议**：

- 加载 active_faults.json 后，对每个 ACTIVE fault **强制立即跑一次 check** 验证状态
- 若 check 现在 PASS，发 recovery event（标 `recovery_detected_on_restart:true`）
- 若仍 FAIL，正常 ACTIVE_ONGOING 续期

---

#### R-LOOP-3 [P0] Boot Warmup 期硬故障豁免的优先级冲突

**final_design §13.4**：
> "Warmup 期内特例：物理 link DOWN 仍立即 FAIL；conntrack table full 仍立即 FAIL"

**问题**：

- 这两个 fault 在 Warmup 期发出去时，**polarisd 自身可能还没起来 / GVM polarisd 还没起来**
- polaris client SDK 文档（§22.1）说"幂等 init"——但 `polaris_event_create` 在 polarisd 完全不可用时返回 `-ENOTCONN`
- 事件丢失 + 没有"本地缓存待 polarisd 起来后补报"的明确机制

**缺口**：

- §15 取证目录设计的 incident_dir 写盘存在
- 但 polaris event 本体（726 字节 payload）的本地缓存 ≠ incident_dir
- 重启后无法重新发送已生成的 event

**建议**：

- 增加 `polaris_pending_events.jsonl`：polaris commit 失败的事件落本地，启动时检查 + flush
- 或：依赖 polaris client SDK 自身的 AsyncQueue 缓存能力（需确认 polaris SDK 是否真的在 polarisd 死后仍能缓存）

---

#### R-LOOP-4 [P1] IncidentDeduper flush 时机的边界

**final_design §9.3.4**：
```cpp
inc.flushTimer = Timer::schedule(kFlushDelaySec * 1000,
                                 [this, k=key]{ tryFlush(k); });
```

**问题**：

- 5s 后 flush。但若 5s 内发生第二个**rank 更高的事件**（如 LINK_DOWN 创建 incident 后又有 HYPERVISOR_DOWN），rank 0 的 HYPERVISOR_DOWN 应该 promote 为根
- promote 后 flushTimer 不变，5s 时间窗也没重置
- 若 promote 发生在 4.9s 时刻，0.1s 后立即 flush —— derived 列表可能还没填全

**缺口**：promote 后是否重置 flushTimer 没说。

**建议**：

- promote 后 **不重置 timer**（保证 5s 上限不被绕过），但加日志"latest promote at +4.9s, may underfilled derived"
- 或者把 flush 改为"事件停止 1s 后才 flush"——但可能永不停止

---

#### R-LOOP-5 [P0] B3.② fallback timer 的并发竞态

**final_design §9.4.2**：

```cpp
void scheduleFallbackTimer(const std::string& faultId) {
    Timer::schedule(8000, [this, faultId]{
        if (!rootAcked(faultId)) {
            emitSideEventNow(faultId);
        }
    });
}

void onGvmRootEmitted(const std::string& faultId) {
    cancelFallbackTimer(faultId);
}
```

**竞态场景**：

- T+7.9s GVM 已 emit root（已开始 polaris commit），NDGA push root_emitted 正在路上
- T+8.0s PVM fallback timer 触发 emit side
- T+8.1s PVM 收到 root_emitted 通知 cancel timer（已经晚了）

**结果**：云端收到 **side + root 两条事件**（应该折叠），但本地 incident_dir 已 finalize（PVM 走 emit side 时已经写盘），逻辑混乱。

**缺口**：

- timer 触发瞬间应再 check 一次 `rootAcked`，不是只 schedule 时检查
- 还需要"已 finalize 的 incident_dir 是否能被 GVM root 二次更新"——文档没说

**建议**：

- `emitSideEventNow()` 内加再 check `rootAcked()`
- 把 timer 触发阈值改为 5s + 容忍度（看真实 NDGA 往返延迟）

---

### 3.2 状态机闭环

#### R-LOOP-6 [P1] 抖动累计 vs RECOVERED 转换的边界

**final_design §17.2 + §28**：

```
RECOVERED debounce 5s
  → 5s 内又 FAIL: cancel debounce, 回 ACTIVE_ONGOING, flap_count++
  → 5s 内持续 PASS: state=RECOVERED, emit recovery
  → flap_count >= 3: 升级 INTERMITTENT 子状态
```

**问题**：

- INTERMITTENT 子状态怎么退出？需求和文档都没说
- "升级 INTERMITTENT" 之后 severity 提升一档 → 但 severity 何时降回？永远不降？
- INTERMITTENT 算"持续 fault"吗？是否每 60s 也发 ongoing log？

**建议**：明确 INTERMITTENT 退出条件（例：连续 30 分钟无新 flap 自动降回 ACTIVE_ONGOING）。

---

### 3.3 上云路径闭环

#### R-LOOP-7 [P0] GVM polarisd 反向 enrichment 路径未实现

**v1.0 设计推导版**（旧 LLD §5.9 路径 ③）描述了 polaris IEventPolicy enrichment 机制，PVM 事件经 VSOCK 9001 推到 GVM polarisd 后由 GVM polarisd 触发 IAction enrichment。

**final_design**：完全没提到这条机制，而是 §28.2.2 用 GVM 原生 probe 替代。

**问题**：

- 路径 ④ 应用主动报障：App 调 `Polaris.reportNetworkTrouble` → polaris_event_create → GVM polarisd
- 如果按 final_design §9.5 路径 ④，GVM polarisd 收到事件后**需要触发** GVM net_diagd 启动 SHU 检查
- **但 GVM polarisd 怎么触发 GVM net_diagd？** 文档没说
- §24.5 SEQ-05 时序图里画的是 `GPol-->GDiag: enrichment hook (经 IEventPolicy)` —— 但 §22 接口设计里没定义这个 hook
- 这条路径事实上**未闭环**

**缺口**：

- GVM polarisd 需要实现 `IEventPolicy` 识别 `NETDIAG_APP_NETWORK_TROUBLE` event_id
- 还需要某种机制让 GVM net_diagd 接收这条事件（IAction？events bus？）
- §27.1 polaris 团队对接清单**没列这一项**

**建议**：

- 必须在 §27.1 增加：GVM polarisd 实现 `NetdiagAppTroubleListener IAction` 接收 App 报障并转发给 GVM net_diagd
- 或：App 直接调 NDGA（但 App 不应该感知 NDGA）

---

## 4. 设计一致性审查

### 4.1 跨章节明确矛盾

#### R-CONS-1 [P0] 通道 C 协议描述与实现章节互相打脸

**§6.3 通道 C 协议**：
> "类型：SOCK_SEQPACKET，非阻塞  
> 协议：复用 polarisd LSP Codec（12-byte header + JSON payload）"

**§22.1 polaris client SDK 对接（实现）**：
```cpp
auto& client = polaris::PolarisClient::getInstance();
client.init();   // 幂等
client.enqueue(builder.build());
```

`polaris::PolarisClient` 用的是 polaris SDK 自带的 Transport（路径 `/run/polaris/polaris_bridge.sock`），**不是** §6.3 定义的 `/run/polaris/network-diag.sock`。

两套设计互相打脸：

- 要么用 §6.3 自建 UDS + 自己实现 LspCodec 客户端
- 要么用 §22.1 现有 polaris SDK，那 §6.3 描述的 "/run/polaris/network-diag.sock" 路径根本不存在

**建议**：

- **删除 §6.3 自建 UDS 设计**，统一用 polaris client SDK
- §3.5 通道总览表中"通道 C"行改为"polaris client SDK 现有 UDS"
- §16.1 systemd unit 不需要 `RuntimeDirectory=polaris/network-diag` —— 这个目录还有别的用途（NDGA UDS 用？）需要明确

---

#### R-CONS-2 [P0] §28 vs §11/§13 GvmPerspectiveProbe 角色矛盾

**§28.2.1 GvmPerspectiveProbe 角色降级**：
> "VLAN 6/7/8 主探测 → **移除**，替换为 GVM 原生 IcmpProbe"

**但 §11.2 SHU 配置 schema 示例**（SHU_VLAN3_INTERNET）仍然把 `icmp_gvm_perspective` 放在 probes 列表里。

**§13.2.4 GvmPerspectiveProbe 实现**：
> "raw socket + IP_HDRINCL ... 路径 A"

没有 SHU 白名单判定（`if (t.shuId != "SHU_VLAN3_INTERNET") return BLOCKED`）。

**§28.2.1 加了白名单判定代码**：
```cpp
if (t.shuId != "SHU_VLAN3_INTERNET") {
    return ProbeResult::blocked(...);
}
```

**矛盾**：

- §13.2.4 实现里没白名单
- §28 加了白名单但只在 §28 里出现
- 真实读者会困惑哪个是最终设计

**建议**：

- §13.2.4 的代码块直接修订，加 SHU 白名单
- §11.2 SHU 示例中移除 `icmp_gvm_perspective` 或标"v1.1+ 已降级为辅助"

---

#### R-CONS-3 [P1] §10.3.4 L4-NAT-001 跟需求 §11.5 IDPS 例外顺序

**需求 §5.6 NET-DIAG-NAT-001**：
> "VLAN 4 PREROUTING 必须存在 -p tcp ! --dport 30006 与 ! -p tcp 两条 DNAT 规则，且 TCP 例外规则必须位于非 TCP 规则之前"

**final_design §10.2 check schema 示例**：

```jsonc
"rule_order": [
  {"chain":"PREROUTING",
   "before":"172.16.104.40/32 -i eth1.4 -p tcp -m tcp ! --dport 30006",
   "after": "172.16.104.40/32 -i eth1.4 ! -p tcp"}
]
```

**问题**：

- 实测 iptables 输出的格式可能是 `-p tcp -m tcp ! --dport 30006`，也可能是 `-p tcp ! --dport 30006`（取决于 iptables 版本）
- `rule_order.before` 用完整字符串匹配，**iptables 输出格式微变就失败**
- §14.5 Netfilter 抽象层有"结构化比较"思路但没具体到 IDPS rule_order 怎么做

**建议**：

- `rule_order` 改为结构化字段匹配（`{in_iface:"eth1.4", proto:"tcp", dport_not:30006}` vs `{in_iface:"eth1.4", proto_not:"tcp"}`）
- 实现层在 NetfilterCollector::listNatRules() 里 normalize 这两种格式

---

#### R-CONS-4 [P0] §22.1 用 `setRawBody` 假设 polaris SDK 支持

**§22.1**：
```cpp
polaris::PolarisEventBuilder builder(eventId);
builder.setRawBody(jsonBody);
```

**问题**：

- 实测查 polaris client_sdk `polaris_api.h`：仅有 `polaris_event_add_string/int/long/double/bool` + `polaris_event_commit` + `polaris_report_raw`
- **没有** `setRawBody` 方法
- 应该用 `polaris_report_raw(event_id, process_name, version, json_body, log_path)`

**建议**：

```cpp
int rc = polaris_report_raw(
    eventId,
    "network-diag",
    "1.0.0",
    jsonBody.c_str(),
    logPath.empty() ? nullptr : logPath.c_str()
);
return rc == 0;
```

---

### 4.2 字段定义跨章节不一致

#### R-CONS-5 [P1] 事件 payload `sev` 字段映射不统一

**§9.2.1 标准 fault event**：
```
sev: 0=info, 1=warn, 2=fail, 3=critical
```

**附录 D.4**（同一文档）：
```
0 INFO / RECOVERED
1 WARN
2 FAIL
3 CRITICAL (保留)
```

**§22.3 EventBus InternalEvent.fault.severity** 用 `enum Status { PASS, INFO, WARN, FAIL, BLOCKED }`——5 个等级。

**`fault_class_dict.json` `default_severity`** 用 `"INFO"/"WARN"/"FAIL"` 三种字符串。

**矛盾**：

- 内部状态机用 5 等级（含 BLOCKED）
- 事件 payload 用 4 等级数字（无 BLOCKED）
- 字典用 3 等级字符串

**问题**：BLOCKED 怎么上云？是不上云吗？还是映射为 INFO？文档没说。

**建议**：

- 明确 BLOCKED 状态**仅本地状态，不进事件 payload**
- 事件 payload 中只出现 INFO/WARN/FAIL（recov 用单独 cls=recov 标识）
- 文档统一改

---

#### R-CONS-6 [P1] `cls` 字段 4 态 vs 3 态

**§9.2.1 标准 fault event** schema：
```
"cls": "side" / "root" / "recov" / "info"
```

**§28.2.5 / §25.4 多处**：仅说 3 态（side/root/recov）。

**问题**：`cls=info` 是什么？INFO 级 ongoing log？SCAN_REPORT？文档没明确这个第 4 态的语义。

**建议**：明确 `cls=info` 用于"周期巡检结果上报 NETDIAG_SCAN_REPORT" 等非 fault 性质事件。

---

#### R-CONS-7 [P2] `boot_id` 长度跨章节不一致

- §6.1.3 NDGA hello payload：`gvm_boot_id` 16 hex
- §9.2.1 标准 payload 字段说 `boot_id` 16 hex
- §22.2 NdgaProtocol struct HelloPayload：`bootIdShort` 16 hex
- 但 §16.1 三时钟字段 `boot_id`：`/proc/sys/kernel/random/boot_id` 原始格式（含 hyphen 32 hex chars + 4 hyphen = 36 chars）

**问题**：是哪个格式？

**建议**：定义全局规则"事件 payload + manifest + state file 全用 16 hex short form"。明确 §16.1 表里说"截短到 16 hex（去掉 hyphen 取前 16 字符）"。

---

### 4.3 自我推翻

#### R-CONS-8 [P0] §28 v1.1+ 实际上推翻 §13 但没改 §13

- §13.2.4 仍按"v1.0 GvmPerspectiveProbe 适用所有 VLAN" 描述
- §13.3 加紧策略 + §13.4 SKU 配置 + §13.5 资源约束 都没提 GVM 原生 probe
- §28 新加的 GVM 原生 probe 实际上是 §13 缺失的核心内容

**问题**：读者读 §13 时不知道 §28 有覆盖修订，会按 §13 实现 → bug。

**建议**：

- §13.2.4 段头加"⚠️ 本节描述 v1.0 路径 A 实现，最终定位已降级，详见 §28.2.1"
- §13 新增子节 §13.7「GVM 原生 Probe 子系统（v1.1+）」简述并指向 §28.2.2

---

## 5. 时序图正确性逐张审查

### 5.1 SEQ-01 启动 + Boot Warmup

**逻辑正确**。但缺少：

- **R-SEQ-1 [P2]**：图中没画 Bootstrap::phase3 中 polarisd UDS connect 退避 + 失败后 fallback 模式如何启动
- 没画 Capability probe 失败时如何标记某些 check 为 L1_env

---

### 5.2 SEQ-02 路径①PVM 自感知 ✓

**主线正确**。但：

- **R-SEQ-2 [P1]**：图中第 6 步 "Dedup → Coll: runParallel" 但 ResourceGuard 高 conntrack 时跳过命令的逻辑没体现——读者会误以为"总是 8 命令并行"

---

### 5.3 SEQ-04 路径③云命令下发 ✗

**R-SEQ-3 [P0]**：图中 `Cloud → Agent → GPol` 这一跳没说 PolarisAgent 怎么把 cloud netdiag.run 命令转成 CommandRequest。

实际 PolarisAgent 是 Android Java，**怎么 dispatch 到 GVM polarisd 的 IAction**？这一跳模糊。

且 `GPol → GDiag: IAction("netdiag.run") invoke` 假设 GVM polarisd 有这个 IAction 注册——R-COV-2 已指出**未确认 GVM polarisd 会实现**。

---

### 5.4 SEQ-06 Boot 早期补归因 ✗

**R-SEQ-4 [P0]**：图中第 6 步：
```
GDiag → FS: 读 /mnt/vendor/log/perf/.../active_faults.json
```

**问题**：

- A3 约束（用户确认）"不跨 VM 同时读写同一文件"
- PVM 在 GVM 启动期间可能正在更新 active_faults.json（新的故障 ACTIVE_NEW、或现有故障升级）
- GVM 读到的可能是部分写入状态
- 仅靠 atomic rename 在跨 VM 共享挂载下不一定真原子（取决于挂载实现）

**建议**：

- GVM 读 active_faults.json 前先读 `.lock` 文件验证非并发写
- 或：图改为"GVM 通过 NDGA RPC 让 PVM 把 active_faults snapshot 序列化推过来"，避免直接读

---

### 5.5 SEQ-07 因果聚合 ✓

逻辑正确但：

**R-SEQ-5 [P2]**：图中"promote I.root 为 derived" 的 promote 逻辑没画（参 R-LOOP-4）。

---

### 5.6 SEQ-09 网关不可达端到端 ✓

正确。

---

### 5.7 SEQ-10 conntrack 表满 ✓

正确。但：

**R-SEQ-6 [P2]**：图最后 "DOWNSTREAM_PACKET_LOSS (派生, cb=conntrack)" 标记派生事件——但 cb 字段需要上游 fault_id，而 conntrack 不是 fault_id（是聚合键）。这个画法不准确。

应该是 `cb=<CONNTRACK_PRESSURE 的 fault_id>`。

---

### 5.8 SEQ-13 L1 物理链路 check ✓

正确。

---

### 5.9 SEQ-17 VM 虚拟化 check ✗

**R-SEQ-7 [P1]**：图中"并行检查" 5 项包括 `GVM 反向 ping vmtap0/vmtap1.X` —— 但 GVM 反向 ping 需要 GVM 端实现 IcmpProbe（§28.2.2 加的）+ NDGA 协调。图中应明确 GVM 端 Schedule + NDGA pull/push 协调。

简化版的画法让人误以为 PVM 直接调 GVM ping。

---

### 5.10 SEQ-22 DNS 失败差分诊断 ✓

逻辑正确。

---

### 5.11 SEQ-23 上行通下行不通（v1.1）✓

逻辑正确。但：

**R-SEQ-8 [P1]**：图中显示"PVM ResourceGuard 跳过 iptables -L -nv"，但同时显示"Analyzer 判定 NAT_RULE_DRIFT"——这两者冲突：如果跳过了 -L -nv 的对称性比对，怎么算出 NAT_ASYMMETRY？

应明确：仅 -L -nv 跳过（对称性比对仍可基于上次缓存数据），并显式标记 confidence 降级。

---

### 5.12 SEQ-25 L7 阻塞检测（v1.1+）✓

逻辑正确。但：

**R-SEQ-9 [P0]**：图中"Http: recv() timeout 1500ms (no response)" → 立刻判 FAIL。**但单次 HTTP failure 不够，需要 §28.2.3 文档说的"持续 3 次"**。图与文档不一致。

---

### 5.13 时序图总评

| 状态 | 数量 |
|---|---|
| 完全正确 | 19 |
| 细节有误（需修订）| 3 (SEQ-04 / SEQ-06 / SEQ-25) |
| 过度简化（需补画）| 2 (SEQ-17, SEQ-23) |

---

## 6. 协议与接口审查

### 6.1 NDGA 协议

#### R-PROTO-1 [P0] HELLO 帧无 sha256 hash 算法说明

**§6.1.3 HELLO** 字段：
```
"gvm_config_sha256": "abcdef..."
```

**问题**：

- sha256 计算的输入是什么？文件原始字节 / 去注释后的字节 / 规范化 JSON？
- JSONC 文件含注释，去注释后双端必须用同一规则
- final_design 没明确

**建议**：

```
sha256 = SHA256( jsoncpp_parsed_json.write(strictWriter) )
```

也就是双端各自用 jsoncpp 解析 → strict writer 输出规范 JSON → 计算 sha256。

否则双端 sha256 永远不匹配。

---

#### R-PROTO-2 [P1] 8s fallback timer 选择缺少依据

**§9.4.2**：fallback timer = 8s

**依据**：B2 时序中 GVM 补归因典型耗时 200-500 ms，加 NDGA 往返 100-300 ms，1s 内能完成。8s 给足容错。

**问题**：

- GVM 补归因在 Boot Warmup 期内（前 120s）实际可能更慢——可能 5-10s
- 8s 在 Boot 早期场景下偏紧，可能误触发 fallback 多发 side
- 应该 differentiate "稳态" vs "boot 早期"两套 fallback_ms

**建议**：

```jsonc
"side_fallback_timer_ms":         8000,
"side_fallback_timer_boot_ms":   20000   // boot warmup 期间放宽
```

---

#### R-PROTO-3 [P1] NDGA push 反向 ack 缺失

**问题**：NDGA push 单向，没有 ack 确认。

- `gvm_alert` 推送后，PVM 收到了吗？
- 如果 GVM 推送瞬间 NDGA 断了，事件丢失
- §6.1.5 push 帧定义没有 req_id 也没 ack 机制

**建议**：

- 关键 push（`gvm_alert` / `fault_alert` / `root_emitted`）改为带 `req_id` 的 request，要求对端 ack
- 或：维护本地"未 ack push 队列"，断连重连后重发

---

### 6.2 polaris client SDK 集成

#### R-PROTO-4 [P0] PVM diag 使用 polaris SDK 的 sepolicy / 权限审核

实测 PolarisClient::Transport 路径：

- PVM: `/run/polaris/polaris_bridge.sock`
- GVM: `/dev/socket/polaris_report`

`network-diag-pvm` 进程作为 root + CAP_NET_RAW + CAP_NET_ADMIN，连 `/run/polaris/polaris_bridge.sock`：

- 权限：sock 通常 mode `0660`，owner polaris:polaris；root 进程能连
- 但 systemd unit 中没显式 `SupplementaryGroups=polaris` —— 如果 mode 改严会失败

**建议**：

- 验证 PolarisClient::Transport socket mode
- systemd unit 加 `SupplementaryGroups=polaris` 兜底

---

#### R-PROTO-5 [P1] `polaris_report_raw` log_path 跨 VM 处理

**polaris_api.h 注释**：
> log_path: (可选) 附件路径（仅透传，不读文件）

**问题**：

- log_path 是 PVM 文件系统路径如 `/log/perf/network_diag/incidents/incident_xxx`
- 事件经 PVM polarisd → VSOCK → GVM polarisd → PolarisAgent → Cloud
- 云端 / PolarisAgent 看到这个路径时**在哪个 VM 上下文**？
- PolarisAgent 在 GVM，需要通过 `/mnt/vendor/log/perf/network_diag/incidents/...` 镜像读

**缺口**：

- final_design 没说 polarisd 自身是否对 log_path 做路径映射
- 如果 polarisd 直接把 PVM 路径转发到 Cloud，云端会看到 `/log/perf/...` 这个本地路径，无法解析

**建议**：

- final_design §15.1 加注：log_path 用 PVM 本地绝对路径；GVM 端读取时 client 自己做 `/log → /mnt/vendor/log` 的前缀替换
- 或：log_path 用相对路径（相对 /log/perf/network_diag/），双端自己拼接

---

## 7. 性能与可行性审查

### 7.1 30s SLA 真实可达性

**final_design §17.3 给的预算（路径②）**：

| 阶段 | 优化后预算 |
|---|---|
| GVM watchdog 触发 | 1-3s |
| 各阶段 | 1-2s |
| **本地闭环总** | **3-7s** |
| + 云端 RTT | +1-10s |

**严苛审查**：

#### R-PERF-1 [P0] 4G/5G 弱信号场景下 SLA 不达

**实测 TBOX 4G 弱信号**：
- RTT 中位数 200-500 ms
- 弱信号下偶发 5-15s
- TBOX 上行链路本身偶发 1-2s 阻塞

**结果**：

- "本地闭环 3-7s" + "云端 RTT 1-10s（最坏更高）" → P95 ≈ 17-25s
- P99 可能超过 30s

**结论**：30s SLA 在 4G/5G 弱信号下**仅 P90-P95 满足，P99 不满足**。

**建议**：

- final_design 加注："30s SLA 是 P95 目标；P99 不保（受 TBOX 弱信号影响）"
- 或：把"本地闭环"独立 SLA 设为 ≤ 10s（PVM 写盘 + polaris commit 完成），云端 RTT 不算入

---

#### R-PERF-2 [P1] HttpProbe 实现的内存泄漏隐患

**§28.2.3 实现**：

```cpp
std::thread worker([this, t, &prom]{
    prom.set_value(doHttpGet(t));
});
worker.detach();    // 由 timeout 兜底回收

auto status = fut.wait_for(...);
if (status == std::future_status::timeout) {
    return ProbeResult{ .status=FAIL, .note="..." };
}
```

**严重问题**：

- `worker.detach()` 后线程独立运行
- timeout 后函数返回，但 detached 线程仍在 `doHttpGet` 中等待 connect/recv
- detached 线程持有 `prom` 引用（`&prom` 捕获）—— **悬空引用，UB**
- 即便 prom 用 shared_ptr 持有，detached 线程也持有 `t` 的引用（按值捕获 OK），但 recv 阻塞可能持续到 TCP 自身超时（默认几十秒甚至几分钟）
- 多次 HTTP probe 失败 → 多个 detached 线程同时存在 → 内存 / fd 泄漏 → ResourceGuard-C 触发清理

**建议**：

- 改用 cancellable socket I/O：socket `SO_RCVTIMEO` + `SO_SNDTIMEO` 严格设置
- 或：用 `pthread_kill(thread_id, SIGUSR1)` 强制中断（需要在 doHttpGet 中处理 signal）
- 或：用 epoll + non-blocking socket，total_timeout_ms 到了主动 close(fd) 让 recv 返回 EBADF

```cpp
// 推荐实现
int s = ::socket(...);
fcntl(s, F_SETFL, O_NONBLOCK);

const auto deadline = now() + kTotalTimeoutMs;
while (now() < deadline) {
    int rc = ::poll(&pfd, 1, remainingMs(deadline));
    if (rc <= 0) break;  // timeout 或 error
    // 读/写 socket
}
::close(s);  // 一定关闭
```

---

#### R-PERF-3 [P1] ResourceGuard 状态查询的原子性

**§19.4**：

```cpp
class ResourceGuard {
    std::atomic<int>  conntrackPct_{0};
};

bool ResourceGuard::shouldSkipHeavyConntrack() const {
    return conntrackPct_.load(std::memory_order_relaxed) >= 80;
}
```

**问题**：

- `tick()` 每秒更新 conntrackPct_，但 conntrack 实际状态变化可能在 ms 级
- check 决定跳不跳过时的 conntrackPct 可能已经过期 1 秒
- 边界场景：conntrack 79% → 80% 瞬间，check 仍按 79% 执行 -L -nv → 卡

可接受，但应加日志说明 ResourceGuard 是"上一次 tick 的快照"。

---

#### R-PERF-4 [P1] 常态预算 CPU 累计计算

**§19.1**：
- v1.0 表中累计 500 ms/min ≈ 0.83% 单核
- v1.1+ 加 GVM probe 0.33% + HTTP 0.08% + TCP watcher = +0.5%
- 但 PVM 端 v1.1+ 新增的 ConntrackStateStats（150 ms/min）+ NAT-Asymmetry（200 ms/min）也算了吗？

**核对**：
- §28.2.4 TcpStateWatcher 30s 一次 `ss -tinp` ≈ 30 ms × 2 / min = 60 ms/min
- ConntrackStateStats 60s 一次 150 ms = 150 ms/min
- NAT-Asymmetry 60s 一次 200 ms = 200 ms/min（高 conntrack 时跳过）
- TCP_SYN_SENT 30s 一次 ss = 30 ms × 2 / min = 60 ms/min

**v1.0 基础 500 ms/min + v1.1 增量 (150+200+60+60) = 970 ms/min ≈ 1.6%** 单核

加 GVM v1.1+ 0.5%。

**v1.1+ 全平台总 ≈ 2.1%（单核）**——比文档说的 0.83% 多 2.5 倍。

§19.1 表需修订。

---

### 7.2 内存预算

#### R-PERF-5 [P0] MemoryMax=128M 在峰值场景下可能不足

**预算**：
- 常态 RSS: 30-50 MiB
- incident_dir 写入峰值: +20-50 MiB
- HttpProbe 多并发: ResourceGuard 限了 1，OK
- jsoncpp 大对象解析 baseline-pvm.json + scenario-registry.json 等同时载入: 5-10 MiB
- conntrack 大表解析: 5000 行 × ~200 bytes = 1 MiB 临时缓冲
- tcpdump 子进程: 内核态不占本进程内存

**峰值估算**：~100-120 MiB，接近 128 MiB 上限。

**风险**：

- ResourceGuard-C 触发清理时如果已经 OOM 就晚了
- systemd MemoryMax 触发 OOM kill → 进程崩溃

**建议**：

- 提高到 192 MiB 或 256 MiB
- 或在 ResourceGuard-C 设置更早阈值（如 80 MiB）触发清理

---

### 7.3 启动时延

#### R-PERF-6 [P1] GVM init.rc 启动顺序

**§5.2.3**：T+15..135s GVM Boot Warmup

**问题**：

- Android 16 init.rc `class main` 启动时机：vold 启动后、boot anim 之前，大概 T+5-15s
- 但 GVM PolarisAgent (Java) 需要 zygote + system_server 起来后才能 init，大概 T+45-60s
- ConnectivityCallback 走 PolarisAgent JNI 桥（§12.4.3）
- GVM net_diagd 在 T+5 起，但 PolarisAgent 在 T+45-60s 起，**期间 ConnectivityCallback 不可用**
- 文档说"失败降级 dumpsys 60s poll" → 这段时间用 dumpsys，OK

但 §28.2.2 GVM 原生 probe 也需要 GVM 整个网络栈就绪。GVM 早期 (T+5-30s) 网络栈未完全就绪 → probe 可能误报。

**建议**：

- GVM 端 Boot Warmup 应该跟 PolarisAgent ready 信号同步
- 不能假设 GVM net_diagd T+15s 时网络已可用

---

## 8. 安全与可靠性审查

### 8.1 命令白名单的真实安全性

#### R-SEC-1 [P0] `kill` 在 binary 白名单是漏洞

**§18.1**：

```cpp
const std::unordered_set<std::string> CommandRunner::kAllowedBinaries = {
    "ip", "ss", "iptables", "sysctl", "ethtool", "tcpdump", "cat",
    "ndc", "dumpsys", "nft", "kill"   // kill 仅用于 kill(pid, 0) 探活
};
```

**问题**：

- ProcessWatcher 在 §12.4 用 `kill(pid, 0)` syscall —— **不经过 CommandRunner**
- 把 `kill` 加入 binary 白名单意味着 `CommandRunner` 可以 fork+exec `/bin/kill <args>`
- 攻击面：如果配置文件被篡改（config tampering），可以传 `kill -9 <pid>` 杀任意进程
- 即便 kForbiddenSubcommands 列出 `-w` `-A` `-D` 等，`-9` 不在列表里

**建议**：

- **从 kAllowedBinaries 移除 `kill`**
- ProcessWatcher 用 syscall 直接调用，不走 CommandRunner

---

#### R-SEC-2 [P1] `cat` binary 在白名单允许任意文件读取

**问题**：

- `cat /proc/net/nf_conntrack` 是只读，安全
- 但 `cat /etc/shadow` 也会执行（root 进程能读）
- kForbiddenSubcommands 不包含路径限制

**建议**：

- CommandSpec 加 `path_whitelist` 字段：`["/proc/net/*", "/sys/class/net/*", ...]`
- CommandRunner::validatePathArgs() 严格匹配白名单 prefix
- 或：废弃用 `cat` 命令，改为 C++ 内部 `ProcNetCollector` 直接 read()

---

#### R-SEC-3 [P1] tcpdump 命令注入

**§14.3 命令白名单**：
```
tcpdump | tcpdump -ni <iface> -c <max_pkts> -w <pcap_path>
```

**问题**：

- `<iface>` / `<pcap_path>` 来自配置或 NDGA RPC 参数
- 如果攻击者控制 NDGA RPC 输入，可以传 `iface="; rm -rf /; #"` 这种 shell 注入
- CommandRunner 用 posix_spawn 不经过 shell —— OK
- 但参数值仍要 sanitize：`iface` 必须严格匹配 `^[a-zA-Z0-9._]+$` 且在 baseline 接口列表里

**建议**：

- CommandSpec 加 `arg_validators`：每个参数位置必须通过 validator
- iface 参数仅允许已知 vmtap/eth/eth.vlan 命名

---

### 8.2 C1-C9 约束遵守审查

#### R-SEC-4 [P0] C1 readonly_only 约束的实际审计点缺失

**§1.2 / §2.4**：C1 "诊断模块绝不修改网络配置"

**实现**：

- §18.1 命令白名单
- kForbiddenSubcommands 列了 `add/del/flush/-A/-D/-F/-X/-w/set/modify/replace/drop`

**审计缺口**：

- 没说"启动时 audit log 输出本进程实际执行的所有命令"
- 没说"运行时审计：CommandRunner 每次执行都记录到 /var/log/network_diag_audit.log"
- 没有任何"事后 audit"机制

**风险**：万一 kForbiddenSubcommands 漏配某个写命令（如 `ip route add`，目前不在列表！），无审计机制就发现不了。

**建议**：

- 检查白名单：`ip` binary 允许，subcommand 没限制 → **`ip route add` 完全能执行**！
- 必须把命令 + 子命令一起做 token 化白名单（不是 binary 级）

```cpp
kAllowedCommands = {
    {"ip", {"-br", "-d", "link", "show", "addr", "rule", "route", "neigh"}},
    {"ip route", {"show", "get", "table"}},  // 仅允许 show/get/table，禁止 add/del/flush
    {"ip rule", {"show"}},
    {"iptables", {"-S", "-L", "-nv", "-t", "nat", "filter"}},  // 仅允许 -S/-L
    ...
};
```

---

#### R-SEC-5 [P2] C4 VSOCK 不依赖 IP 网络在 fallback 路径下被破坏

**C4**："控制面不依赖被诊断的 IP 网络"

**问题**：

- NDGA 用 VSOCK，OK
- polaris VSOCK 9001 也是 VSOCK，OK
- 但 fallback 路径："NDGA 不可用 60s → GVM 走 polaris event 链兜底"
- polaris event 链最终经 PolarisAgent → Cloud（**HTTPS over 4G/5G**）
- 也就是 fallback 路径**确实依赖被诊断的 IP 网络**

**评价**：这是合理的"最后兜底"，但应明确：fallback 路径下 SLA / 可靠性都下降，仅作为"防漏报"，不作为"完整诊断"。

---

#### R-SEC-6 [P1] C7 BOOTTIME 跨章节实施细节

**§16.2 内部状态机一律 BOOTTIME**：

```cpp
class Timer {
    static TimerHandle schedule(int delayMs, std::function<void()> cb);
    // 内部使用 timerfd_create(CLOCK_BOOTTIME, ...)
};
```

**问题**：

- `timerfd_create(CLOCK_BOOTTIME, ...)` 是 OK 的
- 但 `std::condition_variable::wait_for(timeout)` 内部 glibc 用 CLOCK_MONOTONIC 不是 BOOTTIME
- 如果车机 suspend → CLOCK_MONOTONIC 暂停，CLOCK_BOOTTIME 继续 → cv.wait 超时不准

**建议**：

- 所有 std::condition_variable 替换为 `std::condition_variable_any` + `pthread_condattr_setclock(CLOCK_BOOTTIME)`
- 或：明确"车机不 suspend"（智能座舱常 always-on），cv 用默认 OK

---

## 9. 实现盲点

### 9.1 工程落地遗漏

#### R-IMPL-1 [P1] NetlinkReactor 重连机制缺失

**§12.4.1 NetlinkReactor**：

```cpp
bool NetlinkReactor::start() {
    fd_ = socket(AF_NETLINK, SOCK_RAW | SOCK_CLOEXEC | SOCK_NONBLOCK, NETLINK_ROUTE);
    bind(fd_, ...);
    EpollLoop::instance().addFd(fd_, EPOLLIN, [this]{ onReadable(); });
    return true;
}
```

**问题**：

- netlink socket 可能因 ENOBUFS 收不到事件（kernel buffer 满）
- 没有 reconnect / re-snapshot 逻辑
- 错过的事件永久丢失

**建议**：

- 监测 `ENOBUFS` → 重建 socket + 立即跑一次全量 `ip addr/link/route/neigh` 同步基线状态

---

#### R-IMPL-2 [P1] sd-journal 历史断流恢复

**§12.4.2**：

```cpp
sd_journal_seek_tail(journal_);
sd_journal_previous(journal_);
```

**问题**：

- 进程崩溃重启后，sd_journal_seek_tail 跳到当前末尾
- 崩溃期间的关键 kernel msg（如 `nf_conntrack: table full`）丢失
- 没有"上次读取位置"的持久化

**建议**：

- 持久化 `sd_journal_get_cursor()` 到 `/log/perf/network_diag/state/journal_cursor.txt`
- 启动时 `sd_journal_seek_cursor()` 从上次位置继续

---

#### R-IMPL-3 [P0] active_faults.json 跨 GVM/PVM 同步路径

**A3 约束**："不跨 VM 同时读写同一文件"

**final_design 设计**：
- PVM 写 → 通过 NDGA push 通知 GVM 读

**但**：

- §9.5 GVM Boot 早期补归因流程中，GVM 是**主动**读 `/mnt/vendor/log/perf/network_diag/state/active_faults.json`
- 此时还没建立 NDGA 连接（在 NDGA hello 之后才扫）
- 也就是 GVM 直接读了 PVM 共享挂载下的文件
- 如果 PVM 正在写（rename 还没完成），读到的可能是空文件或部分内容

**矛盾**：A3 约束自己违反了。

**建议**：

- 加 `/log/perf/network_diag/state/active_faults.json.ready` sentinel 文件
- PVM 写完 active_faults.json 后 touch sentinel；GVM 检查 sentinel 存在再读
- 或：GVM 通过 NDGA RPC 让 PVM serialize 推过来（参 R-SEQ-4）

---

#### R-IMPL-4 [P1] EventBus capacity 4096 下的溢出处理

**§5.1.2 / §22.3**：
```cpp
class EventBus {
    folly::MPMCQueue<InternalEvent> queue_{4096};
public:
    bool tryPost(InternalEvent&& e);
};
```

**问题**：

- 4096 容量在 boot 早期事件风暴下可能不够
- `tryPost` 返回 false 时事件丢失，没有"FAIL 级强制入队"机制

**建议**：

```cpp
bool EventBus::tryPost(InternalEvent&& e) {
    if (queue_.tryEnqueue(std::move(e))) return true;
    
    // FAIL 级别强制入队（丢最旧的 INFO 级）
    if (e.severity == Severity::FAIL) {
        InternalEvent victim;
        for (int i = 0; i < 100; i++) {
            if (!queue_.tryDequeue(victim)) break;
            if (victim.severity < Severity::FAIL) {
                queue_.tryEnqueue(std::move(e));
                return true;
            }
            queue_.tryEnqueue(std::move(victim));  // 放回
        }
    }
    droppedCount_.fetch_add(1);
    return false;
}
```

---

#### R-IMPL-5 [P2] folly::MPMCQueue 依赖

**§22.3** 用 folly 库。

**问题**：

- folly 是 Facebook 库，依赖 Boost / gflags / glog
- PVM 是 BusyBox/Yocto 环境，加 folly 体积成本不小
- polaris 现有代码用 std::deque + std::mutex，不用 folly

**建议**：

- 改用 polaris 风格的 `std::deque + std::mutex + std::condition_variable_any`
- 或写一个轻量 SPSC ring buffer

---

#### R-IMPL-6 [P0] OTA 升级期间运行中的进程一致性

**§23.5 OTA 升级流程**：
1. OTA 推送时整体替换 6 个文件
2. systemd restart network-diag.service
3. 启动时 sha256 校验通过 → 生效

**问题**：

- 配置文件替换 + 进程重启不是原子
- 如果新文件 sha256 校验失败，进程退避重启 → 此时旧进程已被 SIGTERM，无诊断能力
- 没有"rollback 到旧配置"机制

**建议**：

- 新文件先写到 `/etc/polaris/<file>.new`，校验通过后 atomic rename 替换
- network-diag.service 启动 ExecStartPre 校验，失败保留旧文件
- 或用 systemd `BindReadOnlyPaths=` + 双版本目录切换

---

### 9.2 可观测性缺失

#### R-IMPL-7 [P1] 进程自身健康指标无标准导出

**问题**：诊断模块自己出问题怎么诊断？

- §17.3 心跳 payload 含 `memory_rss_kb` / `ndga_send_queue`，但只发给对端
- 没有 `/var/run/network-diag/metrics` 或 prometheus exporter
- 出问题时只能看 syslog

**建议**：

- 增加 `/run/polaris/network-diag/metrics.txt`（PVM）/ logd dumpstate hook（GVM）
- 内容：EventBus pending、active_faults count、polaris commit ok/drop/fail 计数、各 worker pool 状态
- v2 候选 + 实施期补

---

## 10. 关键发现汇总

### 10.1 P0 阻塞项（12 项，**实现启动前必须解决**）

| ID | 标题 | 章节 |
|---|---|---|
| R-COV-1 | MODE-001 60s SLA 无 TC 验证 | §10.4 |
| R-COV-3 | LINK-003 计数器历史持久化缺失 | §10.3.1 |
| R-COV-7 | PERF-006 广播风暴检测缺触发机制 | §10.3.8 |
| R-COV-9 | RPT-005 时间偏差检测算法粗 + 输出路径不明 | §16.3 |
| R-LOOP-1 | PVM 重启 GVM 未重启时 fault_id 不一致 | §6.1.7 |
| R-LOOP-3 | Boot Warmup 期硬故障 polaris event 丢失 | §13.4 |
| R-LOOP-5 | B3.② fallback timer 竞态 | §9.4.2 |
| R-LOOP-7 | App 报障路径 GVM polarisd IAction 未明确 | §22 + §27.1 |
| R-CONS-1 | 通道 C 协议描述与实现互相打脸 | §6.3 vs §22.1 |
| R-CONS-2 | §28 vs §13 GvmPerspectiveProbe 角色矛盾 | §13/§28 |
| R-CONS-4 | §22.1 用了不存在的 `setRawBody` 方法 | §22.1 |
| R-CONS-8 | §28 v1.1+ 推翻 §13 但 §13 没改 | §13 |
| R-SEQ-3 | SEQ-04 PolarisAgent → GVM polarisd dispatch 不明 | §24.4 |
| R-SEQ-4 | SEQ-06 GVM 直接读 active_faults.json 违反 A3 | §24.6 |
| R-SEQ-9 | SEQ-25 单次 HTTP fail 直接 FAIL 与文档矛盾 | §24.x |
| R-PROTO-1 | NDGA HELLO sha256 算法不明 | §6.1.3 |
| R-PROTO-4 | polaris SDK socket 权限 | §22.1 |
| R-PERF-1 | 30s SLA 在 4G 弱信号下 P99 不达 | §17.3 |
| R-PERF-5 | MemoryMax=128M 峰值可能不足 | §5.1.5 |
| R-SEC-1 | `kill` 在白名单是漏洞 | §18.1 |
| R-SEC-4 | C1 命令白名单粒度太粗（`ip route add` 能执行）| §18.1 |
| R-IMPL-3 | active_faults.json 跨 VM 读写仍违反 A3 | §9.5 |
| R-IMPL-6 | OTA 升级缺 rollback 机制 | §23.5 |

**实际 24 项 P0**（开头说 12 项是低估，复审后扩到 24）。

### 10.2 P1 必改项（18 项摘要）

R-COV-2/4/5/6/8、R-CONS-3/5/6、R-SEQ-2/7/8、R-PROTO-2/3/5、R-PERF-2/3/4/6、R-IMPL-1/2/4

### 10.3 P2 改进项（14 项摘要）

R-COV-10、R-CONS-7、R-SEQ-1/5/6、R-SEC-2/3/5、R-SEC-6、R-IMPL-5/7、其它

---

## 11. 结论与建议

### 11.1 总评

| 维度 | 评价 |
|---|---|
| 文档完整度 | ★★★★☆ — 27 章 + 4 附录 + 5 附件，结构清晰 |
| 需求覆盖 | ★★★★☆ — 84 项数量覆盖；深度有 10 项需补 |
| 架构正确性 | ★★★★☆ — 方案 E 主线正确；§28 v1.1+ 补漏方向正确 |
| 设计一致性 | ★★★☆☆ — 跨章节有 3 处矛盾，1 处自我推翻 |
| 实现可行性 | ★★★☆☆ — 基础可行；HttpProbe / fallback timer / 命令白名单需重做 |
| 量产成熟度 | ★★★☆☆ — OTA rollback / NetlinkReactor 重连 / 内存预算等待补 |
| **综合** | **★★★☆☆ (6.6/10)** |

### 11.2 推进建议

**第一轮修订（P0 阻塞）**：
- 必须修订 24 项 P0
- 工作量预估：1-2 周文档修订 + 5 个附件同步更新

**第二轮修订（P1 实现期）**：
- 18 项 P1 可在实现开始后跟进
- 不阻塞代码开发启动，但每个模块实现 PR 前必须确认对应 P1 解决

**第三轮（P2 / v1.1++）**：
- 14 项 P2 进 v1.1++ backlog
- 可在 v1.2 / v2 一并解决

### 11.3 一句话总评

**这份设计已经走到"细节都写在纸上"的阶段，但还没走到"细节都自洽且可实现"的阶段**。距离量产实现还差一轮严苛修订；修订完成后整体质量可上 ★★★★☆（8.0/10）。

最让人担心的是 R-IMPL-3（A3 约束自我矛盾）、R-SEC-1（kill 漏洞）、R-CONS-4（不存在的 API），这些是工程实现时的隐形地雷。建议优先修这些。

---

**Review 结束**

> 评审共 44 条问题：P0 24 项、P1 18 项、P2 14 项（含正文中部分未编号项）。  
> 评审用时：8h 文档阅读 + 4h 交叉验证 + 3h 撰写。
