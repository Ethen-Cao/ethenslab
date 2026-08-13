# PVM STR 进入与冷启动问题调查报告

## 1. 调查范围

- 调查日期：2026-08-10
- 目标事件：2026-08-08 10:46:16 至 10:52:49（Asia/Shanghai）
- PVM Linux 日志：`ivi_PVM_log_sub-syslog_1786158274/syslog/`
- MCU 日志：`ivi_mcu_1786158230/`
- GVM 日志包：`ivi_PVM_log_sub-la_gvm_1786158333.tar.gz`
- PVM Linux 源码：`/home/ethen/workspace/voyah/projects/8397/code/linux/apps/apps_proc/`
- MCU 通信组件：`/home/ethen/workspace/voyah/projects/8397/code/linux/apps/apps_proc/voyah-cluster/rpcd/`

重点文件：

- `081_20260808_104442.zip`，内部成员 `081_20260808_104442.log`
- `082_20260808_104842.log`
- `083_20250530_024824.log`
- `ivi_mcu_1786158230/mcu.log`
- GVM 日志包内部成员 `la_gvm/la_gvm.txt._160.20260808-104918`
- GVM 日志包内部成员 `la_gvm/la_gvm.txt`

## 2. 结论摘要

1. PVM 在 10:46:16 收到 MCU 的 STR 请求并开始请求 GVM suspend；后续约 193 秒一直处于 `WAIT_GVM` 阶段。
2. GVM 明确执行了 `PM: suspend entry (deep)`，并停在 `Suspending console(s)`；没有发现对应的 `PM: suspend exit`。
3. MCU 没有等到 STR 倒计时归零：在最后一次记录中仍剩 25 秒，随后先收到 CAN NM 唤醒，再检测到 `Soc is sleepReady`。
4. MCU 的事件顺序为 `CAN NM wakeNmId=1636` -> `ps_entry_user_on` -> `Soc is sleepReady` -> `Open SOC pwr CMD`。这是典型的“正在进入休眠时又发生唤醒”的竞态。
5. `Soc is sleepReady` 到 `Open SOC pwr CMD` 相隔 3.374 秒，与 PVM 源码中拉低 `SLEEP_RDY` 后等待 MCU ACK 最多 3 秒的窗口高度重合。
6. 083 不是正常 STR resume 日志，而是一轮新的 Linux 冷启动：内核 uptime 重新计时，并重新打印 `Booting Linux on physical CPU`；GVM 同样从 bootloader 重新启动。
7. MCU 的连续运行时间从 7,327 秒增长到 7,529 秒，没有归零，因此本事件中 MCU 自身没有重启；发生冷启动的是 SoC/PVM/GVM。
8. 因此，“MCU 等待 STR 倒计时归零后强制重启”与现有日志不符。当前证据更支持：GVM/PVM 的休眠收尾阶段与 CAN NM 唤醒相撞，MCU 转入 `USER_ON` 并进入 SoC 唤醒/上电流程。
9. `Open SOC pwr CMD` 后存在约 194 秒的 MCU 关键日志缺口，SoC 冷启动恰好发生在这个缺口内。日志没有直接保留 MCU 拉低电源、拉 RESET 或执行 power-cycle 的记录，所以不能写成“日志直接证明 MCU 重启了 SoC”。
10. 结合没有发现 SoC 主动软件重启、panic 或 watchdog 证据，以及当前平台在进入 systemd/kernel suspend 后只能由 MCU 冷启动兜底，最可能是 MCU 在缺口内执行了冷启动恢复；这是中高置信度的因果推断，不是直接日志证据。
11. 可以确认 GVM 已进入 suspend；只能确认 MCU 检测到 PVM 的 `SLEEP_RDY`，但缺少 PVM 内核侧 `PM: suspend entry`，因此不能严格证明 PVM 内核已经真正进入 s2idle。

## 3. 时间基准说明

本次日志存在三套时间，必须分开解释。

### 3.1 PVM syslog 时间

PVM 日志格式前两列分别是墙钟和 monotonic uptime，例如：

```text
2026-08-08 10:49:16.566 7312469 ...
```

表示墙钟为 10:49:16.566，PVM uptime 为 7,312,469 ms。

### 3.2 MCU 时间

MCU 日志中的 `[xxxxxx]` 是会回绕的短计数，跨文件对齐应优先使用：

```text
[SYSTEM]:TIME=7314629 ms
```

在 082 第 34156～34157 行存在可靠锚点：

```text
2026-08-08 10:49:16.627 ... MCULOG--[114629][165]
[SYSTEM]:TIME=7314629 ms# >>wait MPU sleep! STB_Tm=89 S
```

因此本事件附近可按下式换算 MCU 缓存日志的墙钟：

```text
墙钟时间 ≈ 10:49:16.627 + (MCU_SYSTEM_TIME - 7314.629 秒)
```

日志传输和落盘会引入几十毫秒误差，所以换算时间用 `约` 标记。

### 3.3 083 启动初期时间不可信

083 第 1 行的 `2025-05-30 02:48:22` 是冷启动初期的错误系统时间。启动后先读取了旧的备份时间：

```text
083:L32653  Update system time to ... Sat Aug 8 10:48:30 2026
```

随后才从 MCU/RTC 得到正确时间：

```text
083:L56965  recv rtc ... 1786157568
083:L56967  Update system time to ... Sat Aug 8 10:52:48 2026
```

所以 083 中启动早期集中出现的 MCU 历史消息，事件顺序应看 MCU 内部时间，而不能看外层的 2025 时间。

## 4. 对齐后的完整时间线

| 墙钟时间（Asia/Shanghai） | PVM uptime | MCU `SYSTEM:TIME` | 事件与日志证据 | 判断 |
|---|---:|---:|---|---|
| 10:46:16.495 | 7,132,398 ms | 约 7,134.6 s | `081:L98624`：`POWER_MODE=1` | PVM 收到第一次 STR 请求 |
| 10:46:16.495 | 7,132,398 ms | — | `081:L98626-L98627`：`ENTER_STR start`、`EVT_STR_E 1` | PVM STR 流程启动 |
| 10:46:16.496 | 7,132,399 ms | — | `081:L98639-L98642`：订阅 GVM suspend 事件，并调用 `vmm_request_gvm_pwr_key(vmid=52)` | 开始等待 GVM suspend ACK |
| 10:46:16.576 | 7,132,479 ms | 约 7,134.6 s | `081:L98885`：`MCU Request Entry STR` | MCU 与 PVM 首次请求互相对应 |
| 10:47:46.556 | 7,222,459 ms | 7,224.625 s | `081:L188845-L188847`：第二次 `POWER_MODE=1`，`enter_str ignored, stage=1` | 约 90 秒后重试；PVM 仍在 `WAIT_GVM` |
| 10:47:46.597 | 7,222,500 ms | 7,224.625 s | `081:L188883`：`retry cnt is 1 ... delay 90 s` | MCU 第一次重新给出 90 秒窗口 |
| 10:49:16.566 | 7,312,469 ms | 7,314.627 s | `082:L34100-L34102`：第三次 `POWER_MODE=1`，再次 `ignored, stage=1` | PVM 仍在等待 GVM |
| 10:49:16.586 | 7,312,489 ms | 7,314.627 s | `082:L34123`：`retry cnt is 2 ... delay 90 s` | MCU 第二次重试，并非最终超时 |
| 10:49:16.627 | 7,312,530 ms | 7,314.629 s | `082:L34156-L34157`：`STB_Tm=89 S` | 建立 MCU 与墙钟的对齐锚点 |
| 10:49:18.594 | 7,314,494 ms | 7,316.629 s | `082:L36212`：`STB_Tm=87 S` | 倒计时仍正常进行 |
| 约 10:49:18 | — | — | GVM `_160` 成员 `L13103`：`PM: suspend entry (deep)` | GVM 明确开始 deep suspend |
| 约 10:49:18 | — | — | GVM `_160` 成员 `L13128`：`Suspending console(s)`，文件随后结束 | GVM 进入 suspend 尾段，没有看到 resume |
| 约 10:49:28.644 | — | 7,326.646 s | `083:L25899-L25900`：`wait MPU sleep! STB_Tm=25 S` | MCU 此时至少还剩 25 秒，未超时 |
| 约 10:49:29.202 | — | 7,327.204 s | `083:L25906-L25911`：`wakeNmId=1636`、`sleep to repeat mode` | CAN NM 唤醒首先发生；1636 十进制为 `0x664` |
| 约 10:49:29.230 | — | 7,327.232 s | `083:L25916-L26167`：`AccOn=0`、`ps_entry_user_on`、`PsCurSts=4` | MCU 状态机转入 USER_ON |
| 约 10:49:29.325 | — | 7,327.327 s | `083:L26404`：`Soc is sleepReady` | CAN NM wake 后 123 ms 才检测到 SOC ready |
| 约 10:49:32.699 | — | 7,330.701 s | `083:L26881-L26884`：SPI disconnect、`Open SOC pwr CMD` | ready 后 3.374 秒执行 SOC 电源动作 |
| 约 10:49:33.229～10:52:47.001 | — | 7,331.231～7,525.003 s | `083:L26884` 后直接跳到 `L27226`，MCU 记录号 `[224]` 跳到 `[250]` | 约 193.772 秒关键记录缺失；可能已发生记录号回绕 |
| 约 10:52:43.279 | 1,036 ms | MCU 仍连续运行 | `083:L1`：`Booting Linux on physical CPU`；依据 `L56967` 的 RTC 校时换算 | PVM 是冷启动，不是正常 resume |
| 约 10:52:47.037 | — | 7,525.039 s | `083:L27348`：`ipc2 spi connected` | MCU uptime 连续，SOC 通信在新启动后恢复 |
| 10:52:48.019 | 5,776 ms | — | `083:L56965-L56967`：从 RTC 校准到准确时间 | 证明 083 前段墙钟错误 |
| 10:52:49.829 | 7,587 ms | — | `083:L68414`：`libvoyahpm_bsp version: 1.2.11` | 新一轮 powermgr 初始化 |
| 约 10:52:51.378 | — | 7,529.380 s | `083:L71573`：`RTC Reboot [0][0]`；`L71866` 随后给出完整时间 7,529.393 s | SoC 新启动后向 MCU 上报启动握手；不是 MCU 自身重启 |

关键间隔：

- 第一次 STR 请求到 `Soc is sleepReady`：约 192.83 秒。
- 第一次请求到 MCU retry 1：约 90.06 秒。
- retry 1 到 retry 2：约 90.01 秒。
- CAN NM wake 到 `Soc is sleepReady`：123 ms。
- `Soc is sleepReady` 到 `Open SOC pwr CMD`：3.374 秒。
- 未发现 `retry cnt is 3`、倒计时归零或 MCU “force reset/reboot SOC” 日志。

## 5. PVM 源码与运行日志对应关系

运行日志打印的源码行号与当前工作区源码一致，且 083 显示运行库版本为 1.2.11；当前 BSP 头文件同样定义为 1.2.11。因此以下源码可用于解释本次状态。

### 5.1 `stage=1` 的含义

文件：`voyah-cluster/powermgr/inc/powmgr_clientStr.h`

```cpp
enum class FlowStage : uint8_t {
    IDLE = 0,
    WAIT_GVM,
    WAIT_PVM,
};
```

所以两次 `enter_str ignored, stage=1` 均表示 PVM powermgr 仍在 `WAIT_GVM`，不是已经进入 PVM suspend。

### 5.2 GVM ACK 等待上限是 270 秒

文件：`voyah-bsp/voyahpm-bsp/src/voyahpm_bsp.c`

- `L97`：`PM_TIMEOUT_270S 270`
- `L1210-L1216`：请求 GVM power key
- `L1223`：等待截止时间增加 270 秒
- `L1234-L1237`：等待 GVM suspend ACK，270 秒后才报 timeout

本次约 193 秒后检测到 `sleepReady`，仍在 270 秒 PVM 侧等待上限以内。

### 5.3 `SLEEP_RDY` 与真正 PVM suspend 之间存在 3 秒窗口

文件：`voyah-cluster/powermgr/src/powmgr_clientStr.cpp`

```cpp
// L456-L457
PM_PIN_SLEEP_RDY: PM_PIN_LOW
pm_bsp_gpio_set(PM_PIN_SLEEP_RDY, PM_PIN_LOW);

// L462
m_stage = FlowStage::WAIT_PVM;

// L464-L470
等待 MCU 0x8005/0x02 ACK，最多 3 秒

// L472-L488
随后才启动 pm_pvm_enter_suspend()
```

ACK 等待常量位于 `powmgr_clientStr.h:L180-L185`：

```cpp
static constexpr int kMcuCheckGpioAckWaitMs = 3000;
```

MCU 从 `Soc is sleepReady` 到 `Open SOC pwr CMD` 实测为 3.374 秒，与此窗口高度重合。当前缺失 PVM 侧最后阶段日志，无法确认这 3 秒内收到 ACK，还是等待超时后继续。

### 5.4 PVM 目标休眠模式是 s2idle

文件：`voyah-bsp/voyahpm-bsp/src/voyahpm_bsp.c`

- `L415-L449`：向 `/sys/power/mem_sleep` 写入 `s2idle`
- `L643-L681`：通过 systemd `SuspendWithFlags` 请求系统 suspend
- `L1020` 起：`pm_pvm_enter_suspend()`

但本次日志中没有找到 PVM 内核的 `PM: suspend entry` 或成功 resume 记录，因此只能说 PVM 已到达 MCU 可见的 sleep-ready 边界，不能把“PVM 内核已经进入 s2idle”作为确定事实。

### 5.5 进入 systemd/kernel suspend 后的取消边界

平台设计约束如下：PVM 一旦进入 systemd 与 kernel suspend，用户态进程会被冻结，Powermgr 无法继续处理打断事件，也无法再执行“取消 PVM suspend”。因此取消窗口只存在于调用 `pm_pvm_enter_suspend()` 之前。

进入该边界后，打断休眠必须由高通 BSP/kernel 在底层实现 suspend abort。当前底层没有提供有效的取消能力，所以若唤醒与 suspend 提交相撞，现有恢复路径只能由 MCU 对 SoC 执行冷启动兜底。该约束解释了“为什么用户态没有取消日志”，但不能代替 MCU 电源/RESET 动作的直接日志证据。

## 6. GVM 确实进入 suspend，但没有正常 resume

GVM 日志包成员 `la_gvm/la_gvm.txt._160.20260808-104918` 结尾为：

```text
[ 7307.471231][T23732] PM: suspend entry (deep)
[ 7307.910962][T23732] Filesystems sync: 0.439 seconds
[ 7307.950595][T23732] Freezing user space processes
[ 7307.960067][T23732] Freezing user space processes completed
[ 7307.963938][T23732] Freezing remaining freezable tasks completed
[ 7307.964108][T23732] printk: Suspending console(s)
```

该成员到此结束，没有出现正常样例中应有的：

```text
Restarting tasks ...
PM: suspend exit
```

同一日志包的后续 `la_gvm/la_gvm.txt` 从 `BDS Entry`、`Loader Build Info` 等 bootloader 信息重新开始，说明 GVM 也经历了新的启动，而不是从原 kernel suspend 上下文恢复。

## 7. MCU 日志为什么出现在 083 中

MCU 将日志发送给 SOC 保存。当 SOC 保存通道停止时，独立 MCU 文件会出现缺口。

`ivi_mcu_1786158230/mcu.log:L12479-L12481`：

```text
08-08 10:49:07.873 ...
08-08 10:49:07.907 ... [1059008-08 10:52:56.361 ...
08-08 10:52:56.394 ...
```

第二行是半条旧记录与重启后的新记录直接拼接，说明 SOC 侧 writer 在写入中途停止，之后才重新打开。这个文件不能覆盖整个掉线窗口。

083 启动后，rpcd 在很短时间内输出 MCU 内部时间从 7,318 s 到 7,331 s 的历史消息；这些消息的外层 host 时间相同或接近，而且当时 PVM 墙钟仍是错误的 2025 时间。这表明 rpcd 正在接收/排出 MCU 保留的积压日志。事件真实先后顺序必须按 MCU 内部时间还原。

rpcd 对 MCU 文本没有解析复位含义，只是原样打印：

```c
PRINT_INFO("MCULOG--%.*s", ...);
```

对应源码：`voyah-cluster/rpcd/src/rpcd_local.c:L605-L610`。

## 8. `RstR=0x16` 不是本次 SOC 重启原因

`RstR=0x16` 在本事件前已经持续出现，例如 `mcu.log:L35`（10:32:45），并非 10:49 后新产生。

在压缩日志 `139_20260808_103243.mcu.log.gz` 内部约 L6817 可以看到它的来源：

```text
08-08 08:30:35.983 [000000][001][Sys]S32K324 ResetReason:0x16
```

随后 MCU 状态周期性打印 `RstR=0x16`。本次 PVM 冷启动前后 MCU 内部时间从约 7,330 s 连续增长到 7,525 s，没有归零，所以 MCU 本身没有在本事件中重启。

因此，`RstR=0x16` 是 MCU/S32K 更早一次复位留下的状态，不能用于证明本次 SOC 因 STR timeout 被复位。

## 9. MCU 是否重启了 SoC：专项判断

### 9.1 可以直接确认的事实

1. **SoC 确实发生了冷启动。** `083:L1` 的内核 uptime 从 1,036 ms 重新开始；GVM 日志也从 `BDS Entry` 和 bootloader 重新开始，而不是从原 suspend 上下文恢复。
2. **MCU 自身没有重启。** MCU 内部时间在事件前为 7,327.327 秒，重启后的 `RTC Reboot` 为 7,529.380 秒，时间连续增长。`RstR=0x16` 是更早的 MCU reset reason，不是本次事件中新产生。
3. **没有 SoC 主动正常重启的完整日志。** PVM 侧没有 `systemctl reboot`、shutdown、kernel panic 或 watchdog bite；新启动时 `083:L23063` 还记录 `Previous reboot was not an abnormal reset`。
4. GVM 新启动的 bootloader 记录为 `la_gvm/la_gvm.txt:L24`：`KeyPress:0, BootReason:0`；Android 启动后的 bootstat 在 `091_20260808_105306.logcat.log.gz:L43255-L43264` 将原因归一化为 `reboot`。两者能证明这是新启动，但都没有给出“由谁触发”的信息。

### 9.2 `Open SOC pwr CMD` 不能单独证明 MCU 执行了复位

当前事件为：

```text
MCU 7,327.327 s  Soc is sleepReady
MCU 7,330.701 s  Open SOC pwr CMD
```

历史日志 `617_20250530_024824.zip` 中可看到同类唤醒/上电路径：

```text
MCU 0.060 s   Soc is sleepReady
MCU 0.401 s   SOC Pwr ON Over
MCU 3.462 s   Open SOC pwr CMD
MCU 12.433 s  RTC Reboot [0][0]
```

历史样例中 `Open SOC pwr CMD` 位于 `SOC Pwr ON Over` 之后，因此它更像唤醒/上电状态机中的动作或门控，而不是一条可直接等价为“拉 RESET”的日志。当前事件从 sleepReady 到 Open 的 3.374 秒，也与历史样例的 3.402 秒几乎一致。

### 9.3 真正决定因果关系的日志恰好缺失

`083:L26884` 最后一条事件日志为：

```text
[131231][224][PWR]Str = 0,RstR = 0x16,WkSrc = 0
```

下一条 MCU 日志已跳到 `083:L27226`：

```text
[325003][250][IPC2_SYS] request vehicle config
```

两者相差 193.772 秒。PVM 约在 MCU 7,521.281 秒时重新从 `Booting Linux` 启动，正好位于缺口内。当前数据中没有保存这一窗口内可能存在的：

- `Close SOC pwr CMD`；
- `SOC Pwr OFF/ON`；
- `SOC_RESET` 拉低/释放；
- MCU 冷启动兜底计时器到期；
- 其他明确的 power-cycle 记录。

因此，**日志可以证明“MCU 活着时 SoC 冷启动了”，但不能直接证明具体是哪条 MCU 指令或哪根 GPIO 触发了冷启动。**

### 9.4 专项结论

- “MCU 自身是否重启”：**否，日志可直接排除。**
- “SoC 是否冷启动”：**是，日志可直接确认。**
- “是否有直接日志证明 MCU 拉电源/RESET 重启 SoC”：**没有，关键窗口缺失。**
- “最可能是否由 MCU 执行冷启动兜底”：**是，中高置信度。**依据是 SoC 没有主动软件重启或异常崩溃证据、MCU 始终运行并已转入 `USER_ON`，而当前平台在 systemd/kernel suspend 提交后没有底层 abort 能力，只能由 MCU 冷启动恢复。

要把中高置信度提升为确定结论，需要 MCU 固件侧导出缺失窗口的电源状态机记录，或者提供 SOC_PWR_EN/SOC_RESET 的同步波形。

## 10. 原因判断与置信度

| 判断 | 置信度 | 依据 |
|---|---|---|
| 083 是 PVM 冷启动，不是正常 STR resume | 高 | `Booting Linux`、uptime 归零、powermgr 重新初始化 |
| GVM 已进入 deep suspend | 高 | GVM 明确打印 `PM: suspend entry (deep)` 和 `Suspending console(s)` |
| GVM 没有在原内核上下文正常 resume | 高 | 无 `suspend exit`，后续从 bootloader 启动 |
| MCU STR 倒计时没有到零 | 高 | 最后仍为 `STB_Tm=25 S`，且随后检测到 ready |
| “MCU 因 STR timeout 强制重启”不成立 | 高 | 无 timeout/retry 3/force-reset 日志，事件顺序相反 |
| CAN NM 唤醒与 STR 完成阶段发生竞态 | 高 | wake -> USER_ON -> sleepReady，间隔仅 123 ms |
| MCU 自身在本事件中重启 | 排除 | MCU 内部时间从约 7,327 秒连续增长到 7,529 秒 |
| `Open SOC pwr CMD` 本身就是复位命令 | 不支持 | 历史样例显示它属于唤醒/上电路径，且位于 `SOC Pwr ON Over` 之后 |
| MCU 最终执行 SoC 冷启动兜底 | 中高 | 与平台恢复设计和外部症状一致，但真正的电源/RESET 动作位于约 194 秒日志缺口内 |
| PVM 内核已真正进入 s2idle | 未证实 | 只有 MCU 检测到 sleepReady，没有 PVM `PM: suspend entry` |

## 11. 最可能的故障路径

```text
MCU 请求 STR
    -> PVM 请求 GVM suspend
    -> PVM 长时间停在 WAIT_GVM，MCU 两次按 90 秒重试
    -> GVM 最终进入 deep suspend
    -> MCU 等待窗口尚未结束时收到 CAN NM 0x664 唤醒
    -> MCU 状态切换到 USER_ON
    -> 123 ms 后 MCU 又检测到 SOC sleepReady
    -> MCU 与 PVM 在约 3 秒握手窗口中分别执行“唤醒/上电”和“继续 suspend”方向的动作
    -> 若 PVM 已进入 systemd/kernel suspend，Powermgr 用户态被冻结，无法再取消
    -> 高通 BSP/kernel 未提供有效 suspend abort，SOC 未从原上下文恢复
    -> 约 194 秒关键 MCU 日志缺失
    -> 最可能由 MCU 冷启动兜底，最终 PVM/GVM 从 bootloader 重新启动
```

这里最关键的问题不是单一 timeout，而是两个状态机方向冲突：PVM/GVM 正在完成休眠，MCU 已经因为 CAN NM wake 转向 USER_ON。

## 12. 建议的后续验证

1. MCU 侧确认 `wakeNmId=1636`（`0x664`）对应的具体 CAN 节点和唤醒条件，判断是否为预期唤醒或异常 NM 报文。
2. MCU 侧提供 `Open SOC pwr CMD`、`Close SOC pwr CMD`、冷启动兜底定时器的固件实现和 SOC_PWR_EN/RESET 实际电平定义，避免只根据英文日志推断硬件动作。
3. 核对 MCU 在检测到 `SLEEP_RDY` 后是否发送了 `0x8005 byte[0]=0x02` ACK，以及 CAN NM wake 后是否发送 cancel/wakeup 通知。
4. 在 PVM 增加持久化关键点：`GVM_DONE`、`SLEEP_RDY LOW`、MCU ACK/timeout、调用 `pm_pvm_enter_suspend()` 前后、取消休眠事件。普通 syslog 在本事件中会丢失最后窗口，建议同时写 pstore/ramoops 或独立持久化 trace。
5. 抓取 MCU `SLEEP_RDY`、SOC_PWR_EN、SOC_RESET、PVM/GVM heartbeat GPIO 波形，并与 MCU 内部时间同步，确认 10:49:29～10:49:33 的真实电源顺序。
6. 单独调查 GVM suspend 为什么从第一次请求到 ready 需要约 193 秒；重点记录 VMM power-key 请求、GVM kernel suspend entry、VMM suspend ACK 三个时刻。
7. 在 PVM 真正调用 `pm_pvm_enter_suspend()` 前再次检查 wake/cancel 状态；若 MCU 已进入 USER_ON，不应仅因 3 秒 ACK 超时而继续 suspend。该检查必须发生在用户态冻结前。
8. 高通 BSP/kernel 侧补充可验证的 suspend abort：记录 wake pending、冻结阶段、device suspend 阶段以及 abort 原因；用户态冻结后不能再依赖 Powermgr 取消。
9. MCU 电源状态机日志应写入 MCU 自身持久化区，至少保留 SOC_PWR_EN、SOC_RESET、兜底计时器启动/到期和复位原因，避免 SoC 掉线时恰好丢失最关键证据。

## 13. 最终结论

本次事件中，GVM 确实进入了 deep suspend；PVM 到达了 MCU 可见的 sleep-ready 边界，但缺少 PVM 内核真正进入 s2idle 的直接证据。MCU 在 STR 倒计时尚余约 25 秒时收到 CAN NM `0x664` 唤醒，并先转入 USER_ON，随后才检测到 SOC sleepReady。约 3.374 秒后 MCU 记录 `Open SOC pwr CMD`，之后约 194 秒的关键 MCU 日志缺失，PVM 和 GVM在缺口内以冷启动方式重新启动。

现有证据不支持“MCU 等待 STR 倒计时归零后强制重启”。日志可以直接确认 MCU 自身未重启、SoC 确实冷启动，但没有直接保存 MCU 拉电源或 RESET 的动作。结合平台进入 systemd/kernel suspend 后 Powermgr 无法取消、底层又没有有效 suspend abort，最符合全部证据的解释是：休眠收尾与 CAN NM 唤醒发生竞态，SoC 未能正常 resume，随后 MCU 在缺失窗口内执行冷启动兜底。该因果判断为中高置信度，最终坐实仍需 MCU 持久化电源日志或 GPIO 波形。

## 14. Android/GVM 进入 suspend 耗时专项分析

### 14.1 总耗时与时间对齐

Android 在上一段 logcat `089_20260808_104617.logcat.log.gz` 的解压行号 L214608 于
10:46:16.506396 收到：

```text
CAR.POWER: Received AP_POWER_STATE_REQ=SHUTDOWN_PREPARE(1) param=2
```

`param=2` 对应可延期的 deep sleep 请求。PVM 的 GVM uptime 同步日志
`082:L34705-L34710` 给出：10:49:17.188 时 GVM uptime 为 7,306.916 秒。
因此，GVM 内核 `PM: suspend entry (deep)` 的 7,307.471231 秒可换算为
约 10:49:17.743；`Suspending console(s)` 的 7,307.964108 秒对应约
10:49:18.236。

从 Android 收到请求到内核开始 deep suspend 共约 **181.237 秒**；到冻结控制台共约
**181.730 秒**。

| 阶段 | 起止时间 | 耗时 | 占“请求到冻结控制台” |
|---|---|---:|---:|
| PRE_SHUTDOWN_PREPARE | 10:46:16.506396 -> 10:46:18.511881 | 2.005 秒 | 1.104% |
| SHUTDOWN_PREPARE / Garage Mode / framework 收尾 | 10:46:18.511881 -> 约 10:49:17.743 | 179.231 秒 | 98.625% |
| kernel suspend entry -> Suspending console(s) | 约 10:49:17.743 -> 10:49:18.236 | 0.493 秒 | 0.271% |

所以主耗时不在 kernel，而在 Android 用户态的 Garage Mode。

### 14.2 PRE_SHUTDOWN_PREPARE 的约 2 秒

唯一未完成 completion listener 是 PID 4088，即
`com.voyah.cockpit.launcher` 的 `ShutdownHelper`：

```text
10:46:16.510883  ShutdownHelper: onStateChanged:11
10:46:16.511223  unfinished ... pid_4088_comp_time_12759
10:46:18.511355  ShutdownHelper: carPowerManager.complete()
10:46:18.511722  CarPowerManagementService: All listeners completed
```

其 callback 到 `complete()` 为 2.000472 秒，基本解释了全部 2.005 秒 PRE 阶段。

### 14.3 约 179 秒关键路径：Garage Mode 等待 idle jobs

10:46:18.515933，`GarageModeController` 进入 Garage Mode，并持有
`SHUTDOWN_PREPARE` completion。CarPowerManagementService 给它的期限是
900,000 ms（15 分钟），不是本事件约 3 分钟处触发的固定 timeout。

`090_20260808_104756.logcat.log` 中共有 50 次 2 秒
`SHUTDOWN_POSTPONE`；进入核心 SHUTDOWN_PREPARE 后的 49 个检查周期，打印的唯一
unfinished listener 都是同一个 `GarageModeController`。

Garage Mode 先等待 10 秒再检查 idle jobs，随后每秒检查一次：

```text
10:46:28.524750  2 jobs are still running
10:47:19.417775  StableUriIdleMaintenanceService completed
10:47:19.587328  1 jobs are still running
10:47:55.631392  1 jobs are still running
10:47:56.540207  unfinished listener: GarageModeController
```

两个长任务为：

1. `StableUriIdleMaintenanceService`（user 10）：约 60.08 秒后完成；
2. `BackgroundDexoptJobService`：10:46:18.671 启动，到日志结束仍在运行，是最后的
   关键阻塞任务。

ART 日志给出了耗时变长的直接原因：

```text
GetBestInfo: ... is kOatBootImageOutOfDate
Image checksum mismatch
Should recompile: targetFilterIsBetter (current: verify, target: speed/speed-profile)
```

也就是现有 OAT/ODEX 与当前 boot image checksum 不匹配，大量包从 `verify` 被重新
编译到 `speed` 或 `speed-profile`。在 `090` 可见窗口内：

- 实际执行 dexopt：32 条，另有 42 条跳过；
- 31 次明确记录 `OatBootImageOutOfDate / Image checksum mismatch`；
- 32 次 `dex2oatWallTimeMillis` 合计 91.939 秒；
- 该值约占 98.096 秒可见 Garage Mode 窗口的 93.7%，且文件结束时仍有下一包正在编译。

可见的主要单包编译耗时：

| 包名 | dex2oat wall time |
|---|---:|
| `com.mega.map` | 12.529 秒 |
| `com.voyah.ai.voice` | 9.623 秒 |
| `com.voyah.cockpit.sodamusic` | 8.842 秒 |
| `com.bytedance.byteautoservice3` | 6.300 秒 |
| `com.voyah.cockpit.alipaymiddleware` | 5.951 秒 |
| `com.voyah.carlinkhmi` | 5.278 秒 |

`StableUriIdleMaintenanceService` 与 dexopt 并行，不能把它的 60.08 秒再次相加到总耗时。

### 14.4 证据缺口

`090` 最后一条日志为 10:47:56.612328，距 GVM `PM: suspend entry` 还约
81.131 秒。这一段没有后续 logcat，因此可以确认最后一个已知 blocker 是
`BackgroundDexoptJobService`，但不能从现有日志直接给出它的精确完成时刻，也不能把
整段 81.131 秒无条件全部记到 dexopt。

结合 Garage Mode 源码只有在 running/pending idle jobs 清空后才完成，以及随后 GVM
确实进入 kernel suspend，最合理的解释是后台编译在缺口内继续运行并最终结束，之后
CarPowerManagementService 完成 VHAL/kernel 的 suspend 收尾。这是强推断；精确拆分
最后 81.131 秒需要补齐 10:47:56～10:49:18 的 Android logcat。

### 14.5 kernel 阶段分布

GVM kernel 从 `PM: suspend entry` 到 `Suspending console(s)` 仅 492.877 ms：

| kernel 子阶段 | 耗时 |
|---|---:|
| Filesystems sync | 439.731 ms |
| sync 完成到开始冻结 userspace | 39.633 ms |
| Freezing user space processes | 9.472 ms |
| Freezing remaining freezable tasks | 3.871 ms |
| 到 Suspending console(s) | 0.170 ms |

最终判断：Android 约 181 秒进入 suspend 的主要原因是 Garage Mode 触发 idle maintenance
后，ART 因 boot image checksum 不匹配对大量应用执行后台 dexopt；kernel suspend 本身
不到 0.5 秒，不是性能瓶颈。

## 15. 是否可以取消 Garage Mode

### 15.1 结论

可以。当前 AAOS 源码已经提供标准的“跳过 Garage Mode、仍然进入 Suspend-to-RAM”
语义，不需要删除 `GarageModeService`：将
`AP_POWER_STATE_REQ/SHUTDOWN_PREPARE` 的参数由 `CAN_SLEEP(2)` 改为
`SLEEP_IMMEDIATELY(4)`。

本项目的 VHAL 当前在
`hardware/interfaces/automotive/vehicle/2.0/default/impl/vhal_v2_0/KeyEvents.cpp:352-357`
生成请求：

```cpp
if (shutdownOnly) {
    shutdownParam = toInt(VehicleApPowerStateShutdownParam::SHUTDOWN_ONLY);
} else {
    shutdownParam = toInt(VehicleApPowerStateShutdownParam::CAN_SLEEP);
}
```

日志中的 `SHUTDOWN_PREPARE(1) param=2` 与这段代码完全对应。

`SLEEP_IMMEDIATELY` 仍被 `PowerHalService.PowerState.canSuspend()` 判定为可
suspend，但 `canPostponeShutdown()` 返回 `false`。CPMS 随后设置：

```text
mGarageModeShouldExitImmediately = true
```

`GarageMode.enterGarageMode()` 检测到该值后直接调用 completion callback，并打印：

```text
GarageMode exits immediately
```

它不会广播 `ACTION_GARAGE_MODE_ON`，不会启动 idle-job checker，也不会等待
`BackgroundDexoptJobService` 或 MediaProvider idle job。因此该改动可以消除本次日志中
约 179 秒的 Garage Mode 等待；`PRE_SHUTDOWN_PREPARE` 等其余阶段仍然保留。

### 15.2 建议的两种实现

1. **由 VHAL 使用 `SLEEP_IMMEDIATELY`（改动最小、协议已有支持）**

   将 `KeyEvents.cpp` 非 `shutdownOnly` 分支的 `CAN_SLEEP` 改为
   `SLEEP_IMMEDIATELY`。适用于产品策略明确要求“每次收到 STR 请求都立即休眠”的场景。

2. **增加 CarService 产品配置，只关闭自动 Garage Mode**

   如果仍需保留 `CAN_SLEEP` 的定时唤醒语义，可增加 overlayable bool，例如
   `config_enableGarageMode`；关闭时让 `GarageModeController` 在收到
   `STATE_SHUTDOWN_PREPARE` 后立即调用
   `completeHandlingPowerStateChange()`，但继续保留服务和其他 CPMS listener。

第二种方案改动略多，但不会触发 `SLEEP_IMMEDIATELY` 的另一个行为：CPMS 在
`CarPowerManagementService.java:1481-1485` 会把 `wakeupSec` 强制设为 0。因此，如果
产品依赖 `mNextWakeupSec` 安排定时唤醒，应优先使用 CarService 配置方案。

### 15.3 不建议的做法

- 仅 overlay `maxGarageModeRunningDurationInSecs=0` 无效。CPMS 对资源值设有
  15 分钟硬下限，小于 900 秒会恢复为 900 秒。
- `android.car.garagemodeduration=0` 仅在 `userdebug/eng` 构建生效，属于调试超时
  覆盖，不是正式关闭开关。
- 不建议直接删除 `GarageModeService`。`ICarImpl`、shell/dump、CarWatchdog 和测试代码
  均假定该服务存在；让 listener 立即完成更安全。
- `SHUTDOWN_CANCELLED/CANCEL_SHUTDOWN` 会取消整个 STR 并回到 `ON`，不能用它表示
  “只跳过 Garage Mode”。

### 15.4 验证方法与影响

源码已提供临时 A/B 验证命令：

```sh
adb shell cmd car_service suspend --real --skip-garagemode
```

正式 VHAL 改动后的正常日志特征应为：

```text
Received AP_POWER_STATE_REQ=SHUTDOWN_PREPARE ... param=4
starting shutdown prepare without Garage Mode
Entering GarageMode
GarageMode exits immediately
```

其中出现 `Entering GarageMode` 不代表真正启动了维护任务；紧随其后的
`GarageMode exits immediately` 才是判据。还应确认不再出现
`ACTION_GARAGE_MODE_ON`、`Garage Mode idle-job checker` 和持续的
`send shutdown postpone`。

关闭 Garage Mode 后，idle-constrained 维护任务不会在本次熄火窗口运行，包括本次
阻塞 suspend 的 ART background dexopt 和 MediaProvider maintenance。它们会被延后到
其他满足条件的窗口；因此 boot image checksum 不匹配的根因仍应单独修复，否则可能
出现应用长期停留在 `verify` 编译级别、后续其他时机重复尝试 dexopt 等问题。

另外，PVM 文档显示等待 GVM suspend 成功的上限约为 270 秒，而当前 CPMS Garage Mode
允许的最短最大时长为 900 秒。两者在最坏情况下天然冲突：即使本次约 181 秒恰好未到
270 秒，任何超过 270 秒的 idle job 都可能先触发上层等待超时。因此若 MCU/PVM 的 STR
握手有硬超时，量产方案必须跳过 Garage Mode、缩短并重构其等待策略，或同步延长整个
PVM/MCU/VMM 超时契约，不能继续依赖默认 15 分钟 Garage Mode。
