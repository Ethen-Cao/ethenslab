# EPA 泊入锁车后上车黑屏分析报告（纠正版）

## 1. 问题概述

- 故障现象：EPA 泊入完成后锁车，再次上车时车机持续黑屏；执行方控重启后恢复。
- 测试反馈时间：2026-08-06 14:45 左右。
- 系统架构：PVM Linux + qcrosvm + GVM Android。
- 分析范围：故障包中的 PVM、GVM、MCU、Sentry 日志，以及当前 PVM Linux / Android QSSI 相关电源管理源码。

## 2. 核心结论

本次故障不是“EPA 功能异常”，也不能按原报告定性为“系统正常进入深度休眠，随后被方控正常唤醒”。更符合证据的结论是：

1. EPA 泊车在 14:40:04 达到 100%，14:40:08 已退出泊车状态。现有日志没有 EPA 进程崩溃或 EPA 直接控制黑屏的证据，EPA 只是本次用车场景的前置条件。
2. 14:43:35 下电后，GVM Android 进入 `ABANDONED(15)` 并正常下发主屏关闭请求；PVM 随后进入 `STANDBY_ALARM`、`STANDBY/GUARDMODE`。
3. 14:44:34 用户返回车辆时，GVM 已收到重新上电条件：UsageMode 切回 Convenient，电源状态由 15 切到 6，主屏 ON 请求下发并收到软件侧确认，随后 ACC ON。说明“上车唤醒事件没有到达 Android”并不成立。
4. GVM 在确认主屏 ON 后约 2.3 秒，于 14:44:37.022 突然停止旧实例日志；PVM 的聚合 `syslog` 虽然只保存到 14:44:22.456，但 PVM 上的 Tuanjie 进程仍在 14:44:38.725 记录 `UsageMode: 3`。因此，14:44:22 不是 PVM 的实际停止时刻；旧 PVM 与旧 GVM 当前可见末条日志只相差约 1.702 秒。
5. 恢复链路的起点是 MCU 复位：MCU 内部计数从 `[000000]` 重新开始并打印 `S32K324 ResetReason:0x16`，随后依次进入 awake/user_on，打印 `after B21 SOC ON` 和 `SOC Pwr ON Over`。这可以确认 MCU 重新执行了 SoC 上电流程。之后 PVM Linux、GVM Linux 均重新执行完整 boot 路径，而不是原 Linux 内核上下文直接从 suspend 继续。
6. 如果确实由 PVM powermgr/qcrosvm/Gunyah 正常走“暂停或停止 GVM”或“PVM 继续进入低功耗”的软件路径，PVM 侧应产生 `msg 0x8005 ... POWER_MODE=1`、STR 工作线程、`vmm_request_gvm_pwr_key`、GVM suspend ACK/失败以及 PVM suspend 等相关日志。保存这些模块日志的 PVM 聚合 `syslog` 在 14:44:22.456 后缺失，因而没有覆盖真正故障窗口。
7. Tuanjie 日志证明 PVM 至少运行到 14:44:38.725，但它不记录 powermgr/qcrosvm 的 STR 事务。因此，“导出包中没有 STR 相关日志”仍然既不能证明软件路径没有执行，也不能反过来支持该路径已经执行；只能说明关键事务日志没有持久化下来。
8. 旧 GVM 与旧 PVM 的可见末条日志在 1.702 秒内先后终止，均无正常 shutdown/suspend 收尾，随后两个 Linux 又完整启动。这一形态较强支持共享 SoC 计算域发生突发停止，但现有证据仍不能区分 MCU/固件主动撤电、PMIC/局部电源异常、SoC 硬复位、PVM/hypervisor 硬卡死后复位，或软件低功耗路径失效。

因此，本次能够确认的是“GVM 已响应 ON 后整套系统突然不可用，随后由 MCU 复位并重新给 SoC 上电恢复”；直接触发源仍未定位。

## 3. 证据可信度分级

| 级别 | 结论 | 依据 |
| --- | --- | --- |
| 已确认 | GVM 在故障前收到 ON，并完成主屏 ON 请求的软件侧确认 | `mPowerState 15 -> 6`、`sendScreenModeRequest mode=1`、`Screen(1) confirmed state: ON` |
| 已确认 | 旧 GVM 日志在 ON 后约 2.3 秒异常中止 | 最后一条旧系统日志为 14:44:37.022，且日志行本身被截断 |
| 已确认 | PVM 在旧 GVM 日志结束后仍短暂运行 | `PlayerLog77.log:360` 为 14:44:38.725，比旧 GVM 末条晚 1.702 秒 |
| 较强支持 | 14:44:37.022～14:44:38.725 附近，PVM/GVM 所在 SoC 计算域发生突发停止 | 两个旧实例的可见末条日志相隔仅 1.702 秒，均无正常 shutdown/suspend 收尾，之后两个 Linux 都重新 boot |
| 已确认 | 恢复时 MCU 发生复位并重新给 SoC 上电 | MCU 计数回到 `[000000]`，随后出现 `after B21 SOC ON`、`SOC Pwr ON Over` |
| 已确认 | 恢复时 PVM、GVM 均重新执行完整 boot 路径 | 两个 Linux 内核均从 `Booting Linux...` 开始重新打印启动序列 |
| 已确认 | 没有足够证据证明故障前完成了正常 STR | 缺少 CPMS/内核完整 suspend 标志，详见第 6 节 |
| 待验证机制假设 | Guard/待休眠与返车唤醒发生竞态，STR/关机动作未被正确取消 | 当前源码存在可疑窗口，但故障车部署版本与当前源码不一致，且故障窗口 PVM 日志缺失 |
| 无法确定 | 突发停止是物理掉电、主动撤电、硬复位还是 PVM/hypervisor 卡死 | 这些机制可产生相同的日志截断和后续完整启动形态，当前缺少独立电源轨/复位源证据 |
| 无法确定 | `WakeSrc=32` 的具体物理来源、`ResetReason=0x16` 的枚举含义 | 故障包和当前源码中未找到可靠枚举映射 |
| 无法确定 | 故障期间物理背光是否短暂点亮 | `Screen confirmed ON` 是软件请求确认，不等价于面板光学反馈 |

## 4. 时间基准说明

本故障包包含多个时钟域，不能直接把所有日志左侧时间拼成一条绝对时间线：

- GVM logcat 在故障窗口内时间连续，可用于故障前事件排序。
- PVM 聚合 `syslog/787_20260806_144057.log` 只到 14:44:22.456，最后一行还被截断。此前 `780`～`786` 均约为配置上限 50 MiB，而 `787` 只有 42,491,904 字节，说明该 `syslog` 活动文件未正常收尾；它不能代表 PVM 的实际停止时刻。
- PVM 独立应用日志 `tuanjie/LogFiles/PlayerLog77.log` 在 14:44:30.388 仍有心跳，14:44:34.725 收到 `NORMALMODE`，最后于 14:44:38.725 记录 `UsageMode: 3`。下一份 `PlayerLog78.log` 从 14:46:51.069 的 `VoyahStart Inited` 开始，属于重启后的新进程。
- GVM 在 14:44:34.700 收到 `VehicleUsageMode Convenient(0)`，PVM Tuanjie 在 14:44:34.725/726 记录 `NORMALMODE` 和 `UsageMode: 0`，两域同一状态变化只差约 25 ms，说明故障前两侧墙钟基本对齐。由此计算，旧 PVM 与旧 GVM 当前可见末条日志相差约 1.702 秒，不是 14.566 秒。
- 当前 vlogmanager 配置的文件上限为 50 MiB、缓存为 256 KiB，默认刷新周期为 15,000 ms。这可以解释聚合 `syslog` 尾部为何可能丢失，但没有证据证明恰好丢失了一个刷新周期，不能据此推定停止时刻或根因。
- 新 PVM 文件 `syslog/788_20250530_024825.log` 启动时 RTC 错误，先显示 2025-05-30；启动约 5.38 秒后又从备份文件恢复到 14:44:30，随后在启动约 6.58 秒时校正到 14:46:51。按单调时钟反推，本轮 PVM 启动约发生在 14:46:44.4。
- `mcu.log` 和新 PVM 中的 `MCULOG--[...]` 包含 MCU 内部时间，但 MCU 日志可能被缓冲后由 PVM/rpcd 批量接收。新 PVM 已启动约 18.7 秒后，rpcd 才收到从 MCU 内部 `[000000]` 开始的复位日志块。因此物理因果顺序应按“MCU 复位并给 SoC 上电 -> PVM 启动 -> GVM 启动”理解；14:47:04 左侧主机时间主要是收到/落盘时间，不宜用于颠倒该因果顺序。

因此，本报告优先使用同一日志域内的先后顺序，并仅在时钟连续且可校准时进行跨域对齐。

## 5. 故障时间线

> 下表“行数”指原始日志中的行号；`.logcat.log.gz` 的行数按解压后的文本计算，即 `zcat <file> | nl -ba` 所显示的行号。

| 时间 | 域 | 事件 | 判断 | 日志文件名+行数：原始日志 |
| --- | --- | --- | --- | --- |
| 14:38:37 | GVM | APA/EPA 泊车流程开始 | 场景起点 | `203_20260806_144008.logcat.log.gz（解压后）:187315`：`08-06 14:38:37.338128  5397  6823 I adas_app:release_7.0.260728.c2026edb: [FUNC_APA_MODE,APA_FunctionSts,APA状态机信号,1612713985][Callback][0,2(Integer)]` |
| 14:40:04.344 | GVM | 泊车进度达到 100% | 泊车完成 | `203_20260806_144008.logcat.log.gz（解压后）:243758`：`08-06 14:40:04.344927  5397  6823 I adas_app:release_7.0.260728.c2026edb: [FUNC_APA_PROCESS_BAR,APARPAFuncInfo/APAProcessBar,泊车进度条,1612714014][Callback][0,100(Integer)]` |
| 14:40:08.897 | GVM | 泊车模式退出 | 未见 EPA 异常 | `203_20260806_144008.logcat.log.gz（解压后）:251103`：`08-06 14:40:08.897226  5397  6823 I adas_app:release_7.0.260728.c2026edb: [FUNC_APA_MODE,APA_FunctionSts,APA状态机信号,1612713985][Callback][0,0(Integer)]` |
| 14:43:35.392 | GVM | `VehicleUsageModeInitHandler handlePower:0` | 开始下电策略 | `204_20260806_144725.logcat.log.gz（解压后）:138513`：`08-06 14:43:35.392105  3447 17931 I Crystal-Android:: VehicleUsageModeInitHandler handlePower:0 onSuccess!` |
| 14:43:35.456 | GVM | `ACC Off`，`mAccState 1 -> 0` | ACC 下电 | `204_20260806_144725.logcat.log.gz（解压后）:138703`：`08-06 14:43:35.456342  2886  3316 I powermanager-voyah: [VoyahPolicy]:onAccChange: accState=0-ACC Off`<br>`204_20260806_144725.logcat.log.gz（解压后）:138705`：`08-06 14:43:35.456361  2886  3316 I powermanager-voyah: [PowerManagerStateCenter]:mAccState changed from 1 to 0` |
| 14:43:35.491～.501 | GVM | UsageMode=Abandoned，`mPowerState 6 -> 15`，下发主屏 OFF | Android 下电策略正常执行 | `204_20260806_144725.logcat.log.gz（解压后）:138927`：`08-06 14:43:35.491870  2886  3316 I powermanager-voyah: [VoyahPolicy]:onVehicleUsageMode: mode=4-VehicleUsageMode Abandoned`<br>`204_20260806_144725.logcat.log.gz（解压后）:139003`：`08-06 14:43:35.493835  2886  3189 I powermanager-voyah: [PowerManagerStateCenter]:mPowerState changed from 6 to 15`<br>`204_20260806_144725.logcat.log.gz（解压后）:139545`：`08-06 14:43:35.501476  2886  3204 I ScreenModePowerPolicy: sendScreenModeRequest value {"type":1,"mode":0,"priority":5,"reason":"power_state"}` |
| 14:43:35.586 | GVM | `Screen(1) confirmed state: OFF` | 软件侧屏幕关闭确认 | `204_20260806_144725.logcat.log.gz（解压后）:141218`：`08-06 14:43:35.586606  2886  3316 I ScreenModePowerPolicy: Screen(1) confirmed state: OFF, removed from pending` |
| 14:43:35.512 | PVM | EFSM 发布 `STANDBY_ALARM` | PVM 进入下电状态 | `787_20260806_144057.log:268051`：`2026-08-06 14:43:35.512 2230885 I 5552(powermgr): <powermgr> [powmgr_clientVipc.cpp:241] <5552>CClient_Vipc::send_power_mode topic=Power/EFSM/mode payload={"extension":null,"relative":false,"time":1785998615507,"valid":true,"value":{"mode":"STANDBY_ALARM"}}` |
| 14:44:03.333 | PVM | `Outside lock: 2`、`DoorlockNotify: lockStatus=0` | 可确认发生外部锁相关事件；数值语义需枚举表 | `787_20260806_144057.log:301692`：`2026-08-06 14:44:03.333 2258706 I 4630(coreservice): <CLS> [fds_VehicleAccessService.cpp:1016] <5325>Outside lock: 2`<br>`787_20260806_144057.log:301693`：`2026-08-06 14:44:03.333 2258706 I 4630(coreservice): <CLS> [fds_LockCtrlService.cpp:291] <5330>DoorlockNotify: lockStatus=0` |
| 14:44:03.633 | PVM | `Outside lock: 0` | 外部锁信号回落 | `787_20260806_144057.log:302044`：`2026-08-06 14:44:03.633 2259006 I 4630(coreservice): <CLS> [fds_VehicleAccessService.cpp:1016] <5325>Outside lock: 0` |
| 14:44:05.511 | PVM | EFSM 发布 `STANDBY`，随后 `GUARDMODE` | 进入 Guard/待休眠路径 | `787_20260806_144057.log:303333`：`2026-08-06 14:44:05.511 2260884 I 5552(powermgr): <powermgr> [powmgr_clientVipc.cpp:241] <5552>CClient_Vipc::send_power_mode topic=Power/EFSM/mode payload={"extension":null,"relative":false,"time":1785998645510,"valid":true,"value":{"mode":"STANDBY"}}`<br>`787_20260806_144057.log:303336`：`2026-08-06 14:44:05.511 2260884 I 5552(powermgr): <powermgr> [powmgr_clientVipc.cpp:241] <5552>CClient_Vipc::send_power_mode topic=Power/EFSM/mode payload={"extension":null,"relative":false,"time":1785998645511,"valid":true,"value":{"mode":"GUARDMODE"}}` |
| 14:44:22.456 | PVM | 聚合 `syslog` 活动文件最后一行被截断 | 只表示 powermgr/rpcd 等聚合日志在此后未持久化；不能当作 PVM 实际停止时间 | `ivi_PVM_log_1785998893/syslog/787_20260806_144057.log:312390`：`2026-08-06 14:44:22.456 2277829 I 2843(rpcd_main): <rpcd> [rpcd_local.c:609] MCULOG--[479880][154][PWR]S`（行尾被 NUL 截断） |
| 14:44:30.388 | PVM | Tuanjie 心跳仍在输出 | 直接证明 PVM 在聚合 `syslog` 截断约 8 秒后仍在运行 | `ivi_PVM_log_1785998893/tuanjie/LogFiles/PlayerLog77.log:346`：`[Info]BuildInfoPlaceholder 2026-08-06 14:44:30.388 : 68280 : [DashboardEntry] HeartBeat: 2026-08-06 14:44:30:388` |
| 14:44:30.235～.736 | GVM/MCU | Sentry disable/stop；MCU 仍有连续日志 | 只能证明哨兵业务停止，不能证明系统已 suspend | `204_20260806_144725.logcat.log.gz（解压后）:158736`：`08-06 14:44:30.235976  4669  6318 I Arc Sentry Sentry: disable sentry`<br>`204_20260806_144725.logcat.log.gz（解压后）:159162`：`08-06 14:44:30.736561  4669  7332 I Arc Sentry Sentry: stop sentry`<br>`mcu.log:66425`：`08-06 14:44:30.523 \t487561][077][PWR]accon:0, nmMode:3, nmState = 4, Vol = 1340` |
| 14:44:33.380 | MCU | 周期状态仍打印 `Str = 0` | 说明此时 MCU 原始状态值仍为 0；具体枚举语义仍需 MCU 定义确认，不能单独证明或排除后续 STR | `mcu.log:66486`：`08-06 14:44:33.380 \t490121][138][PWR]Str = 0,RstR = 0x16,WkSrc = 0` |
| 14:44:34.601 | GVM | `handlePower:1 onSuccess` | 用户返车/上电事件到达 Android | `204_20260806_144725.logcat.log.gz（解压后）:160327`：`08-06 14:44:34.601820  3447 18098 I Crystal-Android:: VehicleUsageModeInitHandler handlePower:1 onSuccess!` |
| 14:44:34.700 | GVM | UsageMode=Convenient，`mAvnState 15 -> 6`，`mPowerState 15 -> 6` | Android 切回 ON 状态 | `204_20260806_144725.logcat.log.gz（解压后）:160660`：`08-06 14:44:34.700430  2886  3316 I powermanager-voyah: [VoyahPolicy]:onVehicleUsageMode: mode=0-VehicleUsageMode Convenient`<br>`204_20260806_144725.logcat.log.gz（解压后）:160668`：`08-06 14:44:34.700752  2886  3190 I powermanager-voyah: [PowerManagerStateCenter]:mAvnState changed from 15 to 6`<br>`204_20260806_144725.logcat.log.gz（解压后）:160674`：`08-06 14:44:34.700841  2886  3189 I powermanager-voyah: [PowerManagerStateCenter]:mPowerState changed from 15 to 6` |
| 14:44:34.705 | GVM | `Received RESUME power cycle`；下发主屏 ON 请求 | 软件唤醒流程已执行 | `204_20260806_144725.logcat.log.gz（解压后）:161024`：`08-06 14:44:34.705145   643   678 I carwatchdogd: Received RESUME power cycle`<br>`204_20260806_144725.logcat.log.gz（解压后）:161083`：`08-06 14:44:34.705733  2886  3204 I ScreenModePowerPolicy: sendScreenModeRequest value {"type":1,"mode":1,"priority":5,"reason":"power_state"}` |
| 14:44:34.717 | GVM | `Screen(1) confirmed state: ON` | dmpolicy 请求得到确认 | `204_20260806_144725.logcat.log.gz（解压后）:161981`：`08-06 14:44:34.717021  2886  3316 I ScreenModePowerPolicy: Screen(1) confirmed state: ON, removed from pending` |
| 14:44:34.725～.726 | PVM | Tuanjie 收到 `NORMALMODE`、`UsageMode: 0` | 与 GVM 的 Convenient(0) 只差约 25 ms，证明 PVM 已收到返车/正常模式，且两侧墙钟基本对齐 | `ivi_PVM_log_1785998893/tuanjie/LogFiles/PlayerLog77.log:348`：`[Info]BuildInfoPlaceholder 2026-08-06 14:44:34.725 : 68410 : [PowerStateTopicProcessor] Topic : Power/EFSM/mode : Data : {"extension":null,"relative":false,"time":1785998674713,"valid":true,"value":{"mode":"NORMALMODE"}}`<br>`ivi_PVM_log_1785998893/tuanjie/LogFiles/PlayerLog77.log:354`：`[Info]BuildInfoPlaceholder 2026-08-06 14:44:34.726 : 68410 : [SignalDataManager] UsageMode: 0 valid: True` |
| 14:44:34.748 | GVM | `ACC On`，`mAccState 0 -> 1` | ACC 恢复 | `204_20260806_144725.logcat.log.gz（解压后）:162779`：`08-06 14:44:34.748442  2886  3316 I powermanager-voyah: [VoyahPolicy]:onAccChange: accState=1-ACC ON`<br>`204_20260806_144725.logcat.log.gz（解压后）:162780`：`08-06 14:44:34.748453  2886  3316 I powermanager-voyah: [PowerManagerStateCenter]:mAccState changed from 0 to 1` |
| 14:44:35.424 | MCU | `Hacc=1` | MCU 侧也观察到 ACC/唤醒条件，不是“进入休眠”的证据 | `mcu.log:66524`：`08-06 14:44:35.424 \t492241][176][PWR]Hacc=1` |
| 14:44:36.823 | MCU | 故障前最后一条连续 MCU 日志 | 此后无日志，不能单凭空白判定 suspend | `mcu.log:66559`：`08-06 14:44:36.823 \t492626][211][IPC]:CanSig set Id=0x310, StartBit=16, Val=1` |
| 14:44:37.022 | GVM | 最后一条旧 GVM SystemUI 日志被截断 | 只能确定旧 GVM/logcat 在此终止；PVM 此后仍至少运行 1.702 秒 | `204_20260806_144725.logcat.log.gz（解压后）:167705`：`08-06 14:44:37.022890  3171  3171 I [SystemUI 13.2.0.20260728152601.46f24f710] StatusBarStyleAnimManager: showOrHideBlurState: isShow=fal--------- beginning of main` |
| 14:44:38.725 | PVM | 旧 PVM 可见的最后一条应用日志：`UsageMode: 3` | 这是当前故障包中旧 PVM 的真正末条墙钟日志；其后未见正常 shutdown/suspend 收尾。`3` 的具体枚举语义需信号定义确认 | `ivi_PVM_log_1785998893/tuanjie/LogFiles/PlayerLog77.log:360`：`[Info]BuildInfoPlaceholder 2026-08-06 14:44:38.725 : 68530 : [SignalDataManager] UsageMode: 3 valid: True` |
| MCU 内部 0～647 ms（主机落盘为 14:47:04.661～05.300） | MCU | `ResetReason:0x16`，随后 awake/user_on、`after B21 SOC ON`、`SOC Pwr ON Over` | MCU 复位并重新给 SoC 上电；`0x16` 的具体复位原因仍需枚举表 | `mcu.log:66560`：`08-06 14:44:36.808-06 14:47:04.661 \t000000][001][Sys]S32K324 ResetReason:0x16`<br>`mcu.log:66565`：`08-06 14:47:04.862 \t000002][006][PWR]ps_entry_awake`<br>`mcu.log:66567`：`08-06 14:47:04.950 \t000005][008][PWR]ps_entry_user_on`<br>`mcu.log:66575`：`08-06 14:47:05.257 \t000251][016][Hook]after B21 SOC ON`<br>`mcu.log:66576`：`08-06 14:47:05.300 \t000647][017][PWR]SOC Pwr ON Over` |
| 约 14:46:44.4 | PVM | 新 PVM Linux 开始启动 | 由校准后的墙上时间减去单调时钟 6577 ms 反推；与测试执行强制重启相符 | `ivi_PVM_log_1785998893/syslog/788_20250530_024825.log:1`：`2025-05-30 02:48:22.247 1072 I 0(<unknown>): Booting Linux on physical CPU 0x0000000000 [0x515f0014]`<br>`ivi_PVM_log_1785998893/syslog/788_20250530_024825.log:54630`：`2026-08-06 14:46:51.000 6577 D 1109(glink_service_l): Gink Core os_qnx_isr: before vfio_interrupt_wait - 6` |
| 14:46:50.819 | GVM | 新 GVM Linux 内核 `Booting Linux...` | 证明 GVM 重新执行完整 Linux boot；不能据此判断底层物理启动原因 | `204_20260806_144725.logcat.log.gz（解压后）:167726`：`08-06 14:46:50.819881     0     0 I         : Booting Linux on physical CPU 0x0000000000 [0x515f0014]` |
| 14:46:52.778 | PVM | powermgr 打印 BSP 版本 1.2.8 | 确认故障车部署版本不是当前源码的 1.2.11；当前源码只能用于机制参考 | `ivi_PVM_log_1785998893/syslog/788_20250530_024825.log:68259`：`2026-08-06 14:46:52.778 8356 I 5554(powermgr): <powermgr> [powmgr_clientStr.cpp:127] <5554>[STR] libvoyahpm_bsp version: 1.2.8` |

### 5.1 返车唤醒关键日志

```text
08-06 14:44:34.601820 ... VehicleUsageModeInitHandler handlePower:1 onSuccess!
08-06 14:44:34.700752 ... mAvnState changed from 15 to 6
08-06 14:44:34.700841 ... mPowerState changed from 15 to 6
08-06 14:44:34.705145 ... carwatchdogd: Received RESUME power cycle
08-06 14:44:34.705733 ... sendScreenModeRequest ... "mode":1 ... "power_state"
08-06 14:44:34.717021 ... Screen(1) confirmed state: ON, removed from pending
```

这组日志说明 Android 上层并非一直停留在 OFF。需要继续追查的是：为何 ON 已被接受后，旧 GVM 在约 2.3 秒内停止日志，而 PVM 又在约 1.7 秒后停止可见日志。

### 5.2 MCU 重启 SoC 及 PVM/GVM 完整启动

```text
# MCU 复位及 SoC 重新上电（该日志块由主机延后接收）
000000][001][Sys]S32K324 ResetReason:0x16
000002][006][PWR]ps_entry_awake
000005][008][PWR]ps_entry_user_on
000251][016][Hook]after B21 SOC ON
000647][017][PWR]SOC Pwr ON Over

# PVM 新启动
Booting Linux on physical CPU ...
Linux version 6.6.110-rt61-perf ...
Machine model: ... SA8797P ... Voyah Platform ...

# GVM 新启动
08-06 14:46:50.819881 ... Booting Linux on physical CPU ...
08-06 14:46:50.819881 ... Linux version 6.12.38-android16 ...
08-06 14:46:50.819881 ... Machine model: ... Gunyah VM Voyah ...
```

原始文件中的复位值经字节核对是 `0x16`，不是 `0x1`。`ResetReason` 和 MCU 内部计数归零可以确认 MCU 本身发生了复位；后续两条 SoC ON 日志可以确认 MCU 又重新给 SoC 上电。尚不能确定的只是 `0x16` 对应 watchdog、外部复位还是其他具体原因。

hypervisor 没有把底层物理启动原因透传给 PVM/GVM，因此新启动后的 `Canonical boot reason`、`Previous reboot was not an abnormal reset` 等字段没有根因判别价值，不能用于区分异常掉电、MCU 主动断电、软件重启或其他底层原因。本报告只使用两个 Linux 重新执行完整 boot 序列这一事实，不使用其启动原因字段。

### 5.3 旧 PVM、旧 GVM 的真正末条日志

`787_20260806_144057.log` 的最后一行只是 PVM **聚合 syslog** 的末条持久化记录，不是 PVM 的实际末条运行日志：

```text
# mcu.log 中的完整原文
08-06 14:44:22.451 [479880][154][PWR]Str = 0,RstR = 0x16,WkSrc = 0

# PVM 聚合 syslog 中的同一条记录
2026-08-06 14:44:22.456 ... MCULOG--[479880][154][PWR]S<NUL...>
```

两条记录的 MCU 单调计数 `[479880][154]` 完全一致，说明聚合 syslog 只保存了同一消息的第一个字符，随后以 NUL 填满文件尾块。但 PVM 上还有独立的 Tuanjie 日志，它直接证明旧 PVM 在此后继续运行：

```text
# PVM 在聚合 syslog 截断后的心跳
PlayerLog77.log:346  2026-08-06 14:44:30.388 ... [DashboardEntry] HeartBeat

# 返车后 PVM 收到正常模式
PlayerLog77.log:348  2026-08-06 14:44:34.725 ... "mode":"NORMALMODE"
PlayerLog77.log:354  2026-08-06 14:44:34.726 ... UsageMode: 0 valid: True

# 旧 PVM 当前可见末条日志
PlayerLog77.log:360  2026-08-06 14:44:38.725 ... UsageMode: 3 valid: True
```

旧 GVM 的末条日志仍是：

```text
204_20260806_144725.logcat.log:167705
08-06 14:44:37.022890 ... StatusBarStyleAnimManager: showOrHideBlurState: isShow=fal--------- beginning of main
```

GVM 在 14:44:34.700 收到 `VehicleUsageMode Convenient(0)`，PVM 在 14:44:34.725/726 收到对应的 `NORMALMODE`、`UsageMode: 0`，同一状态变化仅差约 25 ms，说明两侧故障前墙钟基本对齐。因此，旧 PVM 与旧 GVM 当前可见末条日志的实际差值约为 **1.702 秒**；不能再用聚合 syslog 的 14:44:22.456 计算二者停止时间差。

两侧末条时间已很接近，且都没有正常 shutdown/suspend 收尾；GVM 末行还在 `false` 中间被截断，并直接与新实例的 `beginning of main` 拼接。结合之后 PVM、GVM 都重新执行完整 boot，这一形态与共享 SoC 计算域突然掉电或硬复位相符。需要保留的机制包括：

- MCU/固件主动撤掉 B21/SoC 电源使能；
- PMIC 或 SoC 局部电源轨异常掉电；
- PVM/hypervisor 硬卡死，使 GVM 和相关日志链路冻结，随后被复位；
- SoC 被硬复位但没有立即重新启动。

但 1.702 秒并不等于“严格同时”：它既可能表示旧 GVM/其 logcat 链路先停止、PVM 随后停止，也可能只是 GVM 最后约 1.7 秒日志尚未落盘。故而可以较高置信度定性为 **14:44:37.022～14:44:38.725 附近共享 SoC 计算域突发停止**，但不能把停止点写死在 14:44:37.022，也不能仅凭现有文件进一步定性为“整个 IVI（包括 MCU 和整车 12 V 供电）物理掉电”。

## 6. 为什么不能判定为正常深度休眠

按当前架构，PVM 触发 GVM STR 后，GVM 正常进入 suspend 应当能观察到至少部分下列标志：

- PVM 接收入口：`msg 0x8005 ... POWER_MODE=1`；
- PVM STR 工作线程及 BSP：`[STR]`、`vmm_request_gvm_pwr_key`、GVM suspend ACK/失败；
- PVM 继续休眠时的 PVM suspend 调用、返回值或持久化同步记录；
- CarPowerManagementService/KeyEvents 的电源状态请求；
- `SHUTDOWN_PREPARE`；
- `SUSPEND_ENTER`；
- `POST_SUSPEND_ENTER`；
- 内核 `PM: suspend entry` / `Entering Suspend-to-RAM`；
- 返车发生在进入阶段时，应出现对应的 `SHUTDOWN_CANCELLED` 或 PVM `CANCEL_STR` 处理证据。

故障前的旧 GVM 日志中未找到上述进入/取消序列；旧 GVM 内核日志中也未找到 `PM: suspend entry`、panic、Oops、watchdog lockup 或正常关机标志。PVM 聚合 syslog 截至 14:44:22.456 也没有 powermgr 的 `msg 0x8005 ... POWER_MODE=1`、`[STR]`、GVM suspend 或 PVM suspend 记录。此前只能看到 `STANDBY_ALARM`、`STANDBY/GUARDMODE`，它们不等于已经发起 STR。

这里必须同时保留日志完整性限制：Android 返车 ON 发生在 14:44:34.601，旧 GVM 停止在 14:44:37.022，旧 PVM Tuanjie 又运行到 14:44:38.725；但是负责记录 powermgr/qcrosvm 事务的 PVM 聚合 syslog 提前约 12 秒结束。因此，真正可以验证“PVM 是否发起 GVM/PVM suspend”的窗口没有被对应模块日志覆盖。Tuanjie 能证明 PVM 仍在运行，却不能回答 STR 是否执行。

故障车新一轮 PVM 启动时明确打印 `libvoyahpm_bsp version: 1.2.8`；当前源码头文件则是 1.2.11。故障车 `powmgr_clientStr.cpp` 的运行时行号也与当前源码不一致，例如部署日志的版本打印在第 127 行，而当前源码在第 167 行。因此，当前源码只能用于解释可能机制，不能替代故障版本的运行证据。

`mcu.log` 在 14:44:36.823 后空白，以及复位后的 `NM_Sleep_o`、`Soc is sleepReady`，都不能单独证明此前完成过 PVM/GVM 深度休眠。这里应区分两个结论：MCU 复位并重启 SoC 是已确认事实；复位之前是否完成过正常 STR 则没有足够证据。

- 日志空白也可能由 MCU/PVM 挂死、日志链路中断、掉电或被错误拉入低功耗造成；
- `Soc is sleepReady` 后紧接 `Soc is not sleepDone`，并非“已成功完成 sleep”的确认；
- 这些 MCU 日志在新 PVM 启动后被批量接收，左侧时间不能直接表示 MCU 状态发生的物理时刻。

更准确的表述是：现有日志既没有证明系统完成正常 STR，也没有证明 PVM/qcrosvm/Gunyah 软件路径曾经被调用。软件低功耗/取消竞态只能作为待验证分支。

## 7. 根因边界与待验证分支

### 7.1 已证实的故障链

```text
锁车 / ACC OFF
  -> PVM: STANDBY_ALARM -> STANDBY/GUARDMODE
  -> Sentry 在 14:44:30 停止
  -> 约 4 秒后用户返车，UsageMode/ACC 恢复 ON
  -> GVM 接受 ON，并确认主屏 ON 请求
  -> PVM Tuanjie 同步收到 NORMALMODE/UsageMode 0；但 PVM 电源事务日志没有保存下来
  -> 旧 GVM 日志于 14:44:37.022 截断
  -> 旧 PVM Tuanjie 于 14:44:38.725 打印 UsageMode 3 后终止可见日志
  -> 共享 SoC 计算域突发停止，车机保持黑屏不可用
  -> 方控操作后 MCU 复位并重新给 SoC 上电
  -> PVM + GVM 完整启动后恢复
```

这里的关键不是“屏幕 ON 请求没有发出”，而是 ON 已被 Android 和 PVM 应用侧接受后，两个旧实例在 1.702 秒内先后停止可见日志。现有证据仍没有跨过 PVM 电源事务日志缺口，无法把箭头补写成“旧 STR 继续执行”，也无法仅凭日志截断把它写成某一种确定的掉电原因。

### 7.2 PVM/qcrosvm/Gunyah 软件低功耗路径：待验证机制假设

当前目录源码可以说明一种可能机制，但已确认不是故障车的精确部署版本：故障车 BSP 为 1.2.8，当前源码为 1.2.11；powermgr 运行时行号也不匹配。

1. `powmgr_convMsg.cpp` 中，收到 MCU 帧 `0x8005` 且 `POWER_MODE=1` 时直接调用 `post_enter_str()`。
2. `post_enter_str()` 只是把 `ENTER_STR` 放入工作队列。
3. `CClient_str` 处理 `ENTER_STR` 时，只检查当前 `m_stage == IDLE`，随后就启动 GVM suspend；这里没有在执行前重新校验最新 UsageMode、ACC/KL15、解锁/唤醒状态或 EFSM 状态。
4. 当前源码中，`post_cancel_str()` 的触发来自 BSP 的 `PM_EVT_WAKEUP_IRQ` 回调。UsageMode 切回 Convenient、ACC ON 或解锁事件本身没有在该 STR 类中形成一个独立的强制取消条件。
5. 同一个 BSP 回调中，如果 `m_shutdowning == true`，方控/电源键唤醒事件会调用 `pm_reboot_soc()`，说明设计上此状态应走 reboot 而不是正常 resume。故障日志进一步表明，车辆上的实际恢复链还包含 MCU 复位和 MCU 重新给 SoC 上电；方控事件如何落到 MCU 复位，需要结合故障版本及 MCU 枚举/接口继续确认，不能只靠当前 PVM 源码替代实车链路。

相关位置：

- `voyah-cluster/powermgr/src/powmgr_convMsg.cpp:456`：处理 MCU `0x8005`；
- `voyah-cluster/powermgr/src/powmgr_clientStr.cpp:345`：处理 `ENTER_STR`；
- `voyah-cluster/powermgr/src/powmgr_clientStr.cpp:41`：由 `PM_EVT_WAKEUP_IRQ` 分流到 reboot/resume/cancel；
- `voyah-cluster/powermgr/src/powmgr_clientStr.cpp:272`：`CANCEL_STR` 处理；
- `voyah-bsp/voyahpm-bsp/src/voyahpm_bsp.c:796`：可中止 GVM suspend 的物理按键/唤醒检测。

因此可以设计如下竞态用于复现验证：

```text
T0: MCU 生成/排队 POWER_MODE=1
T1: 用户返车，Android 先收到 Convenient / ACC ON
T2: GVM 主屏策略执行 ON 并收到确认
T3: PVM 工作线程随后消费旧 ENTER_STR
T4: 若 PM_EVT_WAKEUP_IRQ 未到达、到达过早或只被消费一次，旧 STR 继续推进
T5: 系统进入错误低功耗状态或卡在取消/虚机切换阶段
```

该路径在时序上能够解释“先看到 ON 确认，约 2.3 秒后日志消失”，但本次包内没有 PVM 入口、执行或返回日志支持它。它只能列为候选复现模型，不能定为高概率根因。

### 7.3 与软件 STR 并列的待验证分支

- PVM 内核、qcrosvm/vmm server 或 Gunyah 卡死，使旧 GVM/其日志链路先停止，随后 PVM 或整个 SoC 被复位；
- SoC 本地电源域/PMIC/B21 使能突然丢失或被撤销，使 PVM、GVM 在约 1.702 秒的可见日志窗口内停止。该分支与两侧日志截断的形态相符，但当前日志无法区分“电源硬件异常掉电”和“MCU/固件主动撤电”；
- 故障前 MCU 周期记录的整车电压约为 13.39～13.40 V，因此没有持续性整车低压证据；这不能排除毫秒级跌落或 SoC 局部电源轨异常；
- 固件、电源域或跨核通信异常，使 PVM/GVM 在很短时间内先后失去运行或持久化日志能力；
- PVM 聚合 syslog 可能在 flush/fsync 前丢失了 14:44:22 后的 powermgr/qcrosvm 日志；该分支只能解释“为什么看不到电源事务”，不能解释“为什么黑屏”；
- 单独的 GVM 异常可以解释 14:44:37.022 的首个截断，但不能单独解释 PVM Tuanjie 随后也结束、MCU 复位并重新给 SoC 上电以及两个 Linux 完整重启，仍需 PVM/hypervisor/电源域证据闭环。

### 7.4 暂不支持的故障方向

- EPA/APA 应用崩溃：未见证据；泊车流程已提前结束。
- Sentry 自身导致系统休眠：Sentry stop 只是时间标记，不能证明它触发或完成 STR。
- 单纯 SurfaceFlinger/HWC/背光失败：软件侧主屏 ON 已确认，且最终需要 MCU 重新给 SoC 上电、PVM/GVM 完整启动；问题范围明显大于单一显示应用，但仍建议保留物理背光测量以排除显示支路的并发问题。
- Android 正常 suspend 后原内核上下文直接 resume：缺少 STR 标志，恢复时又重新执行完整 Linux boot，与该结论冲突。

## 8. 整改建议

### P0：PVM/MCU 电源状态协同

1. 在真正调用 GVM suspend 前增加最后一道原子门禁，至少重新检查：
   - UsageMode 仍为 Abandoned/允许休眠；
   - ACC/KL15 仍为 OFF；
   - 无解锁、上车或其他 wake pending；
   - EFSM 仍处于允许 STR 的状态；
   - 当前请求 generation/token 仍然有效。
2. MCU `0x8005/POWER_MODE=1` 请求携带或由 PVM 附加 generation；一旦收到 Convenient、ACC ON、解锁或 wake，立即使旧 generation 失效，避免队列中的旧 `ENTER_STR` 在唤醒后执行。
3. 将 Convenient、ACC ON、解锁等策略唤醒直接纳入 `CANCEL_STR`，不要只依赖物理 `PM_EVT_WAKEUP_IRQ` 的单一路径。
4. 对 `PM_EVT_WAKEUP_IRQ` 增加不可丢失的计数/序号，不要只用单个布尔量表达一次唤醒；记录事件到达时的 `m_stage`、generation、UsageMode、ACC 和 EFSM。
5. 若 GVM suspend/cancel/resume 在超时内不能收敛，明确进入受控恢复，并持久化失败阶段，不要留下黑屏且无诊断信息的中间状态。

### P0：补齐持久化日志

1. PVM 在以下节点写入独立、可跨重启保留的电源事务日志：
   - 收到 MCU `0x8005` 的原始字节和 MCU 序号；
   - `post_enter_str` 入队/出队时间；
   - `m_stage`、generation 和所有门禁条件；
   - `PM_EVT_WAKEUP_IRQ`、`CANCEL_STR`、GVM/PVM suspend/resume 返回值；
   - `pm_reboot_soc()` 的调用方和原因。
2. 打开/导出 PVM pstore/ramoops、GVM pstore、qcrosvm 状态，以及由 hypervisor/平台固件自身持久化的 power/reset 事件；不要使用未透传底层原因的 PVM/GVM `boot reason` 代替。本次包中没有足够的崩溃持久化证据。
3. MCU 日志同时保存“MCU 内部单调时间、MCU boot counter、主机接收时间”，避免再次把缓冲日志的接收时间当成实际复位时间。

### P1：GVM 电源链路观测

1. 连续记录 CPMS 状态：`SHUTDOWN_PREPARE`、`SUSPEND_ENTER`、`POST_SUSPEND_ENTER`、`SHUTDOWN_CANCELLED`、`SUSPEND_EXIT`。
2. 记录虚拟电源键注入、KeyEvents 处理及 `/sys/power` suspend 进入/退出结果。
3. dmpolicy 除请求 ACK 外，补充物理背光 GPIO/亮度、DRM commit 和 panel 状态，区分“软件确认 ON”和“面板实际点亮”。

### P1：复现策略

围绕本次边界做循环测试，而不是只重复完整 EPA 流程：

1. EPA 完成 -> ACC OFF -> 锁车 -> Guard；
2. 以 Sentry stop 为基准，在 -5、0、+1、+2、+4、+6、+10 秒解锁/上车；
3. 每个时间点循环至少 100 次，并对返车动作增加 0～500 ms 抖动；
4. 同时抓取 MCU boot counter、PVM STR transaction、qcrosvm、GVM CPMS、物理背光；
5. 判定标准不仅是“是否黑屏”，还包括最终 PVM/GVM 状态是否一致、是否消费过期 `ENTER_STR`、是否出现 cancel 丢失。

## 9. 建议责任域

| 优先级 | 责任域 | 理由 |
| --- | --- | --- |
| P0 | PVM PowerMgr + MCU 电源状态机 | 掌握 STR 请求、取消和整机重启控制链；需先补齐 14:44:22 后的电源事务持久化证据，Tuanjie 末条日志不能替代该证据 |
| P0 | qcrosvm/GVM suspend 集成 | 需要确认缺失窗口内是否收到过 PVM 发起/取消请求，以及虚机实际阶段 |
| P1 | Android CarPower/屏幕策略 | 已完成 ON 请求，但需验证取消事件和实际面板状态 |
| P2 | EPA、Sentry 业务 | 当前无直接故障证据，主要用于构造触发时序 |

## 10. 最终定性

建议缺陷暂定性为：

> EPA 泊车后的锁车下电场景中，用户返车后 GVM 已响应上电并确认主屏 ON，PVM Tuanjie 也收到 NORMALMODE；旧 GVM 于 14:44:37.022 截断，旧 PVM 最后可见日志为 14:44:38.725，二者仅差约 1.702 秒，随后车机持续黑屏不可用。方控操作后 MCU 复位并重新给 SoC 上电，PVM、GVM 完整启动后恢复。该形态较强支持共享 SoC 计算域突发停止，但 PVM 电源事务日志在 14:44:22 后缺失，现阶段仍无法区分物理掉电、主动撤电、硬复位、PVM/hypervisor 卡死或 STR/关机路径异常。

建议缺陷标题调整为：

> EPA 泊入锁车后返车，GVM 响应 ON 后整机黑屏，方控重启恢复

当前证据既不足以写成“正常 suspend 后正常唤醒”，也不足以写成“旧 STR 未取消导致黑屏”。`ResetReason:0x16` 足以确认 MCU 发生复位，但不足以确定 `0x16` 的具体复位原因；`WakeSrc=32` 和 `ColdStart=0` 也仍缺少可靠枚举语义。
