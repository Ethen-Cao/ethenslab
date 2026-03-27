# OTA Watchdog 超时复现工具

在 PREEMPT_RT 内核环境下，通过模拟 OTA 写入场景触发 UFS I/O 风暴，复现 watchdog 超时问题。工具分为**车端数据采集**和**本地 trace 分析**两部分。

## device_collect.sh — 车端数据采集

在目标设备上执行，模拟多种 I/O 写入场景并采集 ftrace、DLT、系统指标等数据。

### 用法

```bash
adb push device_collect.sh /tmp/
adb shell "chmod +x /tmp/device_collect.sh && /tmp/device_collect.sh"
```

### 执行流程

| 阶段 | 说明 |
|------|------|
| 1/5 采集基线 | 采集 10 秒 DLT 日志作为 timeout 消息基线 |
| 2/5 配置 ftrace | 开启 256MB buffer 的 `sched_switch` 事件追踪，记录 UFS IRQ 基线 |
| 3/5 启动监控 | 后台启动 DLT 采集和系统指标（上下文切换、UFS IRQ）采样 |
| 4/5 I/O 风暴 | 依次执行 4 个写入场景（见下方） |
| 5/5 收集数据 | 停止 ftrace，等待 15 秒捕获延迟上报，保存所有数据 |

### I/O 写入场景

- **场景 A**: 256MB buffered write + sync
- **场景 B**: 预填零 256MB + 覆写 256MB（urandom）+ sync
- **场景 C**: 1GB write + sync
- **场景 D**: 4 轮 256MB write + sync（顺序偏移写入）

写入目标为当前启动槽位的**对侧分区**（`la_super_a` / `la_super_b`），脚本会自动检测并拒绝写入已挂载的分区。

### 输出

数据保存在设备 `/log/wd_reproduce_<timestamp>/` 目录下：

| 文件 | 内容 |
|------|------|
| `trace.txt` | ftrace sched_switch 完整记录 |
| `dlt_baseline.txt` | 基线 DLT 日志 |
| `dlt_during_io.txt` | I/O 期间 DLT 日志 |
| `sys_metrics.csv` | 系统指标时序数据（上下文切换数、UFS IRQ 累计） |
| `dd_output.txt` | dd 写入速率输出 |
| `dmesg_tail.txt` | 内核日志末尾 500 行 |
| `pids.txt` | 关键进程 PID 记录 |
| `test_meta.txt` | 测试元数据（耗时、IRQ 增量等） |

---

## local_analyze.sh — 本地 Trace 分析

在开发机上运行，对车端采集的数据进行 ftrace 分析和综合判定。

### 用法

```bash
# 自动从设备 pull 最新数据并分析
./local_analyze.sh

# 分析已 pull 到本地的数据目录
./local_analyze.sh data/
```

若不指定目录，脚本会通过 `adb pull` 自动获取设备上最新的 `wd_reproduce_*` 数据。

### 分析项

| 分析项 | 说明 |
|--------|------|
| 1. DLT 分析 | 对比基线与测试期间的 timeout 消息数量，提取 watchdog/pmonitor 相关日志 |
| 2. UFS IRQ 线程运行时间 | 从 ftrace 计算 UFS IRQ 线程每次切入/切出的运行时长，输出 Top 10 |
| 3. ktimers D 状态分析 | 检测 RT 定时器线程是否因锁阻塞进入 D 状态，计算持续时间 |
| 4. 关键进程调度间隔 | 计算 ivcd/mcd/audiomgr/pmonitor/updatemgr 的最大调度间隔，标记超阈值项 |
| 5. updatemgr 调度时间线 | 列出所有 >600ms 的异常调度间隔 |
| 6. UFS IRQ 线程 D 状态 | 检测 UFS IRQ 线程是否进入 D 状态 |
| 7. 异常区间 CPU 活动 | 定位最大异常间隔对应时段，统计该时段各进程 CPU 切入频次 |

### 综合判定

脚本最终输出 `[FAIL]` / `[WARN]` 标记和结论：

| 判定条件 | 级别 |
|----------|------|
| DLT 捕获到 pmonitor/watchdog timeout | FAIL |
| 测试期间 timeout 消息数 > 基线 | FAIL |
| ktimers 进入 D 状态 | FAIL |
| updatemgr 调度间隔 > 1000ms | FAIL |
| UFS IRQ 运行时间 > 3000ms | FAIL |
| UFS IRQ 运行时间 > 500ms | WARN |

---

## 典型工作流

```bash
# 1. 在车端执行数据采集
adb push device_collect.sh /tmp/
adb shell "chmod +x /tmp/device_collect.sh && /tmp/device_collect.sh"

# 2. 在本地执行分析（自动 pull 数据）
./local_analyze.sh

# 或手动 pull 后分析
adb pull /log/wd_reproduce_20260326_143000/ data/
./local_analyze.sh data/
```
