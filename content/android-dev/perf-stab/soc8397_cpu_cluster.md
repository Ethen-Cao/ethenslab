+++
date = '2026-04-14T11:08:03+08:00'
draft = false
title = 'SA8397 CPU 子系统实机核对'
+++

## 1. 结论摘要

2026-04-14 在台架上分别登录 Linux host 与 Android guest 后，可得到下面的结论：

| 条目 | 实机结论 | 状态 |
| --- | --- | --- |
| `3 clusters x 6 QCC` | 可确认。SoC 总计暴露 `18` 个 CPU，当前被切分为 `Android guest 12 核 + Linux host 6 核`。 | `已确认` |
| L1 cache 为每核私有 | 可确认。`cache/index0` 和 `cache/index1` 的 `shared_cpu_list` 仅包含当前 CPU。 | `已确认` |
| `128K I-cache + 64K D-cache` | 当前 bench 的 `sysfs` / `device tree` 未导出容量字段，无法仅靠运行时接口直接读出。 | `未直读确认` |
| `12 MB L2 per cluster` | “cluster 共享一组 Unified cache”可部分确认，但 `12 MB` 容量值当前无法在运行时接口中直读。 | `部分确认` |

当前最重要的修正点有两个：

1. 不能只看 Android guest。Guest 只能看到 `cpu0-cpu11`，Linux host 才能看到 `cpu12-cpu17`。
2. Android guest 的 cacheinfo 带有虚拟化痕迹，不能直接拿它判断物理 L2 归属。

## 2. 实机环境

- Linux host：`adb -s e66b06ea shell`
- Android guest：`adb -s d7df5883 shell`
- Host `uname -a`：`Linux sa8797 6.6.110-rt61-debug ... aarch64 GNU/Linux`
- Guest `uname -a`：`Linux localhost 6.12.38-android16-5-maybe-dirty-4k ... aarch64 Toybox`

这套台架的软件架构是 `Yocto Linux + qcrosvm + Android guest`，因此 host 视角与 guest 视角必须分开看。

## 3. 原始证据

### 3.1 Linux host 看到整颗 SoC 的 CPU 编号空间

```bash
$ adb -s e66b06ea shell lscpu
CPU(s):                      18
On-line CPU(s) list:         12-17
Off-line CPU(s) list:        0-11
Core(s) per cluster:         6
```

```bash
$ adb -s e66b06ea shell cat /sys/devices/system/cpu/possible
0-17

$ adb -s e66b06ea shell cat /sys/devices/system/cpu/online
12-17

$ adb -s e66b06ea shell cat /sys/devices/system/cpu/offline
0-11
```

这说明：

- 物理 CPU 编号空间是 `0-17`，总计 18 个 CPU。
- 当前 Linux host 只在线 `12-17` 这一组 CPU。

### 3.2 Android guest 只看到前 12 个 CPU

```bash
$ adb -s d7df5883 shell cat /sys/devices/system/cpu/present
0-11

$ adb -s d7df5883 shell cat /sys/devices/system/cpu/online
0-11
```

```bash
$ adb -s d7df5883 shell cat /sys/devices/system/cpu/cpu0/topology/cluster_cpus_list
0-5

$ adb -s d7df5883 shell cat /sys/devices/system/cpu/cpu6/topology/cluster_cpus_list
6-11
```

这说明 Android guest 当前持有两个 6 核 cluster：

- cluster0：`cpu0-cpu5`
- cluster1：`cpu6-cpu11`

### 3.3 Linux host 持有第三个 6 核 cluster

```bash
$ adb -s e66b06ea shell cat /sys/devices/system/cpu/cpu12/topology/cluster_cpus_list
12-17
```

因此把 host 与 guest 两侧数据拼起来后，可得到完整物理拓扑：

- cluster0：`cpu0-cpu5`
- cluster1：`cpu6-cpu11`
- cluster2：`cpu12-cpu17`

也就是 `3 clusters x 6 CPUs = 18 CPUs`。

### 3.4 所有可见 CPU 都是同一类 QCC core

```bash
$ adb -s d7df5883 shell cat /sys/devices/system/cpu/cpu0/regs/identification/midr_el1
0x00000000515f0010

$ adb -s d7df5883 shell cat /sys/devices/system/cpu/cpu6/regs/identification/midr_el1
0x00000000515f0010

$ adb -s e66b06ea shell cat /sys/devices/system/cpu/cpu12/regs/identification/midr_el1
0x00000000515f0010
```

```bash
$ adb -s d7df5883 shell cat /sys/devices/system/cpu/cpu0/cpu_capacity
1024

$ adb -s d7df5883 shell cat /sys/devices/system/cpu/cpu6/cpu_capacity
1024

$ adb -s e66b06ea shell cat /sys/devices/system/cpu/cpu12/cpu_capacity
1024
```

这说明当前运行时导出的三个 cluster 都是同构 CPU，没有暴露 big.LITTLE 异构容量差。

## 4. `/sys/devices/system/cpu` 节点导读

### 4.1 顶层节点

`/sys/devices/system/cpu` 是 CPU 热插拔、拓扑、cache、cpuidle、cpufreq 的主入口。实机上最常用的顶层节点可以按下面理解：

| 节点 | 含义 | 本台架观察 |
| --- | --- | --- |
| `kernel_max` | 内核编译时允许的最大逻辑 CPU 编号上限，不代表当前 SoC 的真实核数。 | Linux host 上为 `255`，只能说明内核支持到 `cpu255`。 |
| `possible` | 当前内核实例理论上可能管理的 CPU 编号范围。 | Host 为 `0-17`，guest 为 `0-11`。 |
| `present` | 对当前内核实例来说“存在”的 CPU 编号范围。 | Host 为 `0-17`，guest 为 `0-11`。 |
| `online` | 当前真正参与调度的 CPU。 | Host 为 `12-17`，guest 为 `0-11`。 |
| `offline` | 当前存在但未上线的 CPU。 | Host 为 `0-11`，guest 为空。 |
| `enabled` | 某些 Android 内核额外导出的 CPU 使能位图。不是所有内核都有。 | Guest 上为 `0-11`；host 上没有该节点。 |
| `isolated` | 被 `isolcpus` 或运行时隔离出去、不参与普通调度的 CPU。 | 当前 host/guest 都为空。 |
| `cpufreq/` | CPU 调频框架入口，频率域对象 `policyX` 位于这里。 | Host 有 `policy0/policy6/policy12`；guest 目录存在但为空。 |
| `cpuidle/` | CPU idle 框架入口，展示 idle driver 和 governor。 | Guest 上可见 `current_driver=psci_idle`、`current_governor=menu`。 |
| `hotplug/states` | CPU hotplug 状态机，展示 CPU 上下线时会经过哪些阶段。 | Guest 上能看到 `topology/cpu-capacity`、`arm64/cpuinfo:online` 等阶段。 |

有两个点需要特别注意：

1. `kernel_max` 很容易误导，它不是“机器实际有多少核”，只是内核支持的逻辑编号上限。
2. `possible/present/online` 必须区分开看，尤其在这类 host/guest 分核场景里，三者很容易不一样。

### 4.2 `cpuX/` 目录

每个逻辑 CPU 都有自己的 `cpuX/` 目录，例如 `cpu0/`、`cpu12/`。这类目录更适合回答“这个 CPU 属于哪个 cluster、共享哪级 cache、频率由谁控制”。

| 节点 | 含义 | 本台架例子 |
| --- | --- | --- |
| `cpuX/online` | 当前逻辑 CPU 是否在线。 | Guest 上 `cpu0/online = 1`。 |
| `cpuX/topology/cluster_id` | 该 CPU 所属 cluster 的编号。 | Guest 上 `cpu0=0`，`cpu6=1`。 |
| `cpuX/topology/cluster_cpus_list` | 与该 CPU 同 cluster 的 CPU 列表。 | `cpu0 -> 0-5`，`cpu6 -> 6-11`，`cpu12 -> 12-17`。 |
| `cpuX/topology/package_cpus_list` | 同 package / 同实例可见包内 CPU 列表。 | Guest 上 `cpu0 -> 0-11`，host 上 `cpu12 -> 12-17`。 |
| `cpuX/cache/index*` | cacheinfo 入口，常看 `level`、`type`、`shared_cpu_list`。 | `index0=Data`、`index1=Instruction`、`index2=Unified`。 |
| `cpuX/cpufreq` | 指向 `cpufreq/policyX` 的符号链接，不是独立对象。 | Host 上 `cpu12/cpufreq -> ../cpufreq/policy12`。 |
| `cpuX/cpuidle/stateN` | 某个 CPU 可进入的 idle state，以及驻留时间、延迟等统计。 | Guest 上 `cpu0/cpuidle` 有 `state0`、`state1`。 |
| `cpuX/regs/identification/midr_el1` | CPU identification register，常用于识别核心型号。 | `cpu0/cpu6/cpu12` 都是 `0x00000000515f0010`。 |

下面两条命令很适合初步判断 cluster 划分：

```bash
$ adb -s d7df5883 shell cat /sys/devices/system/cpu/cpu0/topology/cluster_id
0

$ adb -s d7df5883 shell cat /sys/devices/system/cpu/cpu6/topology/cluster_id
1
```

### 4.3 `cpuidle` 和 `hotplug` 节点怎么看

虽然这篇文档重点是 CPU 拓扑和调频，但 `cpuidle` / `hotplug` 在性能稳定性分析里也经常要看：

```bash
$ adb -s d7df5883 shell cat /sys/devices/system/cpu/cpuidle/current_driver
psci_idle

$ adb -s d7df5883 shell cat /sys/devices/system/cpu/cpuidle/current_governor
menu
```

这表示 Android guest 使用 `psci_idle` 作为 idle driver，使用 `menu` 作为 idle governor。

```bash
$ adb -s d7df5883 shell cat /sys/devices/system/cpu/hotplug/states
...
192: base/cacheinfo:online
198: topology/cpu-capacity
199: arm64/cpuinfo:online
...
237: online
```

这份状态机列表通常不用逐项背，但它能回答一个很实际的问题：CPU 上线/下线过程中，内核会在哪些阶段挂接 `cacheinfo`、`topology`、`cpu_capacity`、`cpuinfo` 等子系统。

## 5. Cache 子系统说明

### 5.1 L1 I-cache / D-cache 为每核私有

Android guest 与 Linux host 都能直接看到这一点：

```bash
$ adb -s d7df5883 shell cat /sys/devices/system/cpu/cpu0/cache/index0/type
Data
$ adb -s d7df5883 shell cat /sys/devices/system/cpu/cpu0/cache/index0/shared_cpu_list
0

$ adb -s d7df5883 shell cat /sys/devices/system/cpu/cpu0/cache/index1/type
Instruction
$ adb -s d7df5883 shell cat /sys/devices/system/cpu/cpu0/cache/index1/shared_cpu_list
0
```

```bash
$ adb -s e66b06ea shell cat /sys/devices/system/cpu/cpu12/cache/index0/type
Data
$ adb -s e66b06ea shell cat /sys/devices/system/cpu/cpu12/cache/index0/shared_cpu_list
12

$ adb -s e66b06ea shell cat /sys/devices/system/cpu/cpu12/cache/index1/type
Instruction
$ adb -s e66b06ea shell cat /sys/devices/system/cpu/cpu12/cache/index1/shared_cpu_list
12
```

因此，原文里“每个 CPU core 有自己专属的 I-cache 和 D-cache”这一条可以保留。

### 5.2 L2 是 Unified cache，但 guest 视角会被虚拟化

Linux host：

```bash
$ adb -s e66b06ea shell cat /sys/devices/system/cpu/cpu12/cache/index2/type
Unified

$ adb -s e66b06ea shell cat /sys/devices/system/cpu/cpu12/cache/index2/shared_cpu_list
12-17
```

Android guest：

```bash
$ adb -s d7df5883 shell cat /sys/devices/system/cpu/cpu0/cache/index2/type
Unified

$ adb -s d7df5883 shell cat /sys/devices/system/cpu/cpu0/cache/index2/shared_cpu_list
0-11
```

这里有一个关键现象：

- 在 host 侧，`cpu12` 的 Unified cache 明确由 `12-17` 共享，符合“一个 6 核 cluster 共享一组 L2”。
- 在 guest 侧，`cpu0` 和 `cpu6` 虽然属于两个不同 cluster，但 `index2/shared_cpu_list` 都是 `0-11`。

这说明 Android guest 的 cache 拓扑已经被虚拟化抽象，不能直接把 guest 的 `cache/index2/shared_cpu_list` 当作物理 L2 拓扑。

因此，对 SA8397 物理 cache 子系统做判断时应采用下面的原则：

- 判断物理 cluster 边界：优先看 `cluster_cpus_list`
- 判断物理 cache 归属：优先看 Linux host
- 判断 Android guest 的运行时 cache 行为：可以看 guest `cacheinfo`，但不要直接映射成物理 L2 拓扑

### 5.3 容量值为什么当前无法直读确认

当前 bench 上的 `cacheinfo` 节点只导出了：

- `level`
- `type`
- `shared_cpu_list`

没有导出常见的：

- `size`
- `number_of_sets`
- `ways_of_associativity`

同时，host 侧 `device tree` 也没有提供可直接读取的 `i-cache-size`、`d-cache-size`、`cache-size` 属性。因此：

- `128K I-cache + 64K D-cache`
- `12 MB L2 per cluster`

这两组“容量数字”当前不能写成“已由实机运行时接口验证”。更严谨的表述应该是：

- L1 私有关系已由实机确认
- L2 cluster 共享关系已由 host 侧实机确认
- 具体容量值需要再结合芯片公开资料、BSP 文档或更低层寄存器读取来确认

## 6. `cpufreq policy` 重点解读

### 6.1 `policyX` 到底是什么

`cpufreq` 里最容易误解的点，是把 `policy12` 看成“cpu12 的频率文件夹”。严格来说这不对。

`policyX` 的本质是“一个硬件调频域对象”：

- 域内所有 CPU 共享同一套频率切换约束
- 常见情况下，共享同一个 PLL / clock / 电压域
- 改变这个 policy 的频率，会同时影响这个 policy 里的全部 CPU
- `X` 一般只是这个 policy 选出来的代表 CPU 编号，常常是域内最小 CPU 编号

因此，`policy0`、`policy6`、`policy12` 实际上正好对应三个 cluster 的调频域，而不是三个单核对象。

### 6.2 本台架上的 `policy` 与 cluster 对应关系

Linux host 侧可以看到三个 cpufreq policy：

```bash
$ adb -s e66b06ea shell ls /sys/devices/system/cpu/cpufreq
policy0  policy6  policy12
```

这与 `0-5`、`6-11`、`12-17` 三个 6 核 cluster 完全对齐，说明频率控制域也是按 cluster 划分的。

同时，`cpuX/cpufreq` 只是指向对应 policy 的符号链接：

```bash
$ adb -s e66b06ea shell ls -l /sys/devices/system/cpu/cpu12/cpufreq
/sys/devices/system/cpu/cpu12/cpufreq -> ../cpufreq/policy12
```

这条链接很重要，因为它证明了：

- 频率控制对象在 `cpufreq/policyX`
- `cpu12/cpufreq` 只是为了按 CPU 路径访问更方便
- 真正的“共享频率域”信息要看 `policyX`

### 6.3 `policy12` 的关键字段怎么读

当前 host 在线的是 `policy12`：

```bash
$ adb -s e66b06ea shell cat /sys/devices/system/cpu/cpufreq/policy12/related_cpus
12 13 14 15 16 17

$ adb -s e66b06ea shell cat /sys/devices/system/cpu/cpufreq/policy12/affected_cpus
12 13 14 15 16 17
```

这里可以这样理解：

- `related_cpus`：理论上属于同一个 policy 的 CPU 集合
- `affected_cpus`：当前真正受这个 policy 影响的 CPU 集合

在当前板子上两者相同，都是 `12-17`，因为这个 cluster 整组在线。

频率上下限相关字段：

```bash
$ adb -s e66b06ea shell cat /sys/devices/system/cpu/cpufreq/policy12/cpuinfo_min_freq
1286400

$ adb -s e66b06ea shell cat /sys/devices/system/cpu/cpufreq/policy12/cpuinfo_max_freq
2707200

$ adb -s e66b06ea shell cat /sys/devices/system/cpu/cpufreq/policy12/scaling_min_freq
1286400

$ adb -s e66b06ea shell cat /sys/devices/system/cpu/cpufreq/policy12/scaling_max_freq
2707200
```

这四个字段不要混淆：

- `cpuinfo_min_freq` / `cpuinfo_max_freq`：硬件或驱动宣告的能力边界
- `scaling_min_freq` / `scaling_max_freq`：当前软件策略允许的边界

如果后续有人做了 thermal clamp、userspace 限频或 power hint 调整，通常先变的是 `scaling_*`，不一定会改 `cpuinfo_*`。

当前频点与 governor：

```bash
$ adb -s e66b06ea shell cat /sys/devices/system/cpu/cpufreq/policy12/cpuinfo_cur_freq
2707200

$ adb -s e66b06ea shell cat /sys/devices/system/cpu/cpufreq/policy12/scaling_cur_freq
2707200

$ adb -s e66b06ea shell cat /sys/devices/system/cpu/cpufreq/policy12/scaling_driver
scmi

$ adb -s e66b06ea shell cat /sys/devices/system/cpu/cpufreq/policy12/scaling_governor
performance
```

这里可以读出三个工程结论：

1. `scmi` 说明 CPU DVFS 是通过 SCMI 通道交给底层固件/平台电源时钟框架处理。
2. `performance` governor 表示当前策略倾向于把频率顶到上限。
3. `cpuinfo_cur_freq` 与 `scaling_cur_freq` 当前同为 `2707200`，与 governor 状态一致。

可选 governor 与 OPP 离散频点：

```bash
$ adb -s e66b06ea shell cat /sys/devices/system/cpu/cpufreq/policy12/scaling_available_governors
ondemand userspace performance schedutil

$ adb -s e66b06ea shell cat /sys/devices/system/cpu/cpufreq/policy12/scaling_available_frequencies
1286400 1555200 1689600 2092800 2227200 2572800 2707200
```

这表示这个 policy 当前不是连续频率调节，而是在若干离散 OPP 上切换。

切频开销与统计：

```bash
$ adb -s e66b06ea shell cat /sys/devices/system/cpu/cpufreq/policy12/cpuinfo_transition_latency
30000

$ adb -s e66b06ea shell cat /sys/devices/system/cpu/cpufreq/policy12/stats/total_trans
0

$ adb -s e66b06ea shell cat /sys/devices/system/cpu/cpufreq/policy12/stats/time_in_state
1286400 0
1555200 0
1689600 0
2092800 0
2227200 0
2572800 0
2707200 352972
```

这里的解读是：

- `cpuinfo_transition_latency=30000` 通常表示切频延迟量级，单位一般是 ns
- `total_trans=0` 表示自统计清零以来没有发生频点切换
- `time_in_state` 全部时间都落在 `2707200`，再次说明该 cluster 一直锁在最高频

### 6.4 为什么 `policy0` / `policy6` 在 host 上还能看到，以及如何读出它们的频点表

即使 host 当前只有 `12-17` 在线，仍然能看到：

- `policy0`
- `policy6`
- `policy12`

这说明 `policy` 反映的是“系统里定义过的调频域”，不是“当前在线 CPU 的临时目录”。

当前去读离线 cluster 的 policy，会看到：

```bash
$ adb -s e66b06ea shell cat /sys/devices/system/cpu/cpufreq/policy0/related_cpus
cat: read error: Device or resource busy
```

这类报错在当前场景下是合理的，含义更接近“这个频率域对象存在，但对应 cluster 当前没有上线到可读状态”，而不是“系统没有这个 policy”。

但这并不代表 `policy0` / `policy6` 的频点表拿不到。当前板子上，读取离线 cluster 频点表的更可靠方法是看 host 的 `debugfs`：

```bash
$ adb -s e66b06ea shell cat /sys/kernel/debug/energy_model/cpu0/cpus
0-5

$ adb -s e66b06ea shell cat /sys/kernel/debug/energy_model/cpu6/cpus
6-11

$ adb -s e66b06ea shell cat /sys/kernel/debug/energy_model/cpu12/cpus
12-17
```

```bash
$ adb -s e66b06ea shell ls -1 /sys/kernel/debug/energy_model/cpu0
cpus
flags
ps:1286400
ps:1555200
ps:1689600
ps:2092800
ps:2227200
ps:2572800
ps:2707200
```

`cpu6` 和 `cpu12` 下的 `ps:*` 集合同样也是：

- `ps:1286400`
- `ps:1555200`
- `ps:1689600`
- `ps:2092800`
- `ps:2227200`
- `ps:2572800`
- `ps:2707200`

这说明三个 cluster 的 performance states 完全一致，也就等价于：

- `policy0` 频点表：`1286400 1555200 1689600 2092800 2227200 2572800 2707200`
- `policy6` 频点表：`1286400 1555200 1689600 2092800 2227200 2572800 2707200`
- `policy12` 频点表：`1286400 1555200 1689600 2092800 2227200 2572800 2707200`

对于在线 cluster，还可以看到 `opp` debugfs 与 `policy12` sysfs 完全对齐：

```bash
$ adb -s e66b06ea shell ls -l /sys/kernel/debug/opp/cpu12
opp:1286400000
opp:1555200000
opp:1689600000
opp:2092800000
opp:2227200000
opp:2572800000
opp:2707200000
```

当前 `opp` debugfs 只给在线的 `cpu12` 建了目录，没有给离线的 `cpu0` / `cpu6` 建对应目录；但 `energy_model/cpu0` 与 `energy_model/cpu6` 已经足够证明这两个离线 cluster 注册的是同一套频点表。

### 6.5 `energy_model` 里的 `power` / `cost` 是什么

除了 `cpufreq` 和 `opp`，Linux host 还导出了 CPU energy model：

```bash
$ adb -s e66b06ea shell ls -1 /sys/kernel/debug/energy_model/cpu0
cpus
flags
ps:1286400
ps:1555200
ps:1689600
ps:2092800
ps:2227200
ps:2572800
ps:2707200
```

这里的 `ps:*` 就是 performance state。每个 state 下常见的字段有：

- `frequency`
- `power`
- `cost`
- `inefficient`

`power` 和 `cost` 的含义不要混淆：

- `power`：这个 performance state 下的活动功耗
- `cost`：调度器做能量估算时使用的归一化代价系数

对 CPU 来说，它们描述的是“单个 CPU 在该 perf state 下的模型值”，不是整个 cluster 的总和。

Linux Energy Model 里 `cost` 的定义是：

```text
cost = power * max_frequency / frequency
```

这意味着：

1. `power` 更接近“这个频点本身有多耗电”
2. `cost` 更接近“为了提供单位性能，需要付出多大能量代价”
3. 在最高频点上，因为 `max_frequency / frequency = 1`，所以 `cost = power`

这也解释了为什么本板子在 `2.7072 GHz` 这一档看到：

```bash
$ adb -s e66b06ea shell cat /sys/kernel/debug/energy_model/cpu0/ps:2707200/power
182032

$ adb -s e66b06ea shell cat /sys/kernel/debug/energy_model/cpu0/ps:2707200/cost
182032
```

而在较低频点，例如 `1.2864 GHz`，`cost` 会大于 `power`，因为调度器要把该状态按最高频进行归一化比较。

还有一个容易误解的点：`power` 的单位不一定是严格的物理瓦数。Linux 允许它是：

- `uW`（微瓦）
- 或平台自定义的抽象标度

所以在没有额外平台文档的前提下，更稳妥的用法是：

- 把 `power` / `cost` 当作“相对比较值”
- 不要直接把它们当成实验室功耗仪表读数

结合当前台架数据，可以得到两个实际结论：

1. 三个 cluster 的 `ps:*` 频点集合完全一致，因此它们的 DVFS 档位一致。
2. 三个 cluster 的 `power` / `cost` 存在小幅差异，因此它们虽然不是 big.LITTLE 异构性能等级，但能耗模型并非逐点完全相同。

例如在最高频点：

```bash
$ adb -s e66b06ea shell cat /sys/kernel/debug/energy_model/cpu0/ps:2707200/power
182032

$ adb -s e66b06ea shell cat /sys/kernel/debug/energy_model/cpu6/ps:2707200/power
176743

$ adb -s e66b06ea shell cat /sys/kernel/debug/energy_model/cpu12/ps:2707200/power
185601
```

因此，针对 SA8397 更准确的理解应当是：

- 不适合按“大小核”来理解
- 更适合按“同构 cluster，但能耗模型略有差异”来理解

### 6.6 为什么 Android guest 看不到 `policyX`

Android guest 上虽然有 `/sys/devices/system/cpu/cpufreq/` 目录，但当前是空的：

```bash
$ adb -s d7df5883 shell ls -l /sys/devices/system/cpu/cpufreq
total 0
```

这意味着 guest 当前没有直接暴露底层 `policyX` 对象。因此：

- 在 guest 里可以看 CPU 拓扑、cache、idle 状态
- 但要看完整 DVFS policy、governor、OPP、time-in-state，必须回到 Linux host

### 6.7 本节结论

对这块板子来说，`cpufreq policy` 可以概括成一句话：

> `policy0`、`policy6`、`policy12` 分别对应 SA8397 的三个 6 核 cluster 调频域；`cpuX/cpufreq` 只是到 `policyX` 的快捷入口；三个 cluster 当前注册的是同一套频点表 `1286400/1555200/1689600/2092800/2227200/2572800/2707200 kHz`；host 在线的 `policy12` 由 `scmi` 驱动、运行在 `performance` governor 下，并且一直停留在 `2707200 kHz`。

## 7. 对性能分析的实际意义

1. 在 Android guest 中抓到的 CPU trace 只覆盖 `cpu0-cpu11`，看不到 host 的 `cpu12-cpu17`。
2. 如果要分析完整 SoC 的 CPU 占用、调频或热问题，必须同时采集 host 与 guest 两侧数据。
3. 不能把 Android guest 的 `cache/index2/shared_cpu_list = 0-11` 直接解释成“12 个 CPU 共享同一组物理 L2”。
4. 看调频问题时，优先盯 `cpufreq/policyX`，不要只看 `cpuX/cpufreq`，因为真正的控制对象是 policy。
5. 当前可以确认的是“3 个 6 核 cluster + L1 私有 + cluster 级 Unified L2 + cluster 级 cpufreq policy”，且三个 cluster 的频点表一致；不能确认的是 L1/L2 的精确容量值。

## 8. 推荐保留的文档表述

如果只保留当前已经被实机验证的内容，建议把 SA8397 CPU 基本信息写成下面这样：

> SA8397 CPU 子系统在当前台架上可观察到 18 个 CPU，物理上由 3 个 cluster 组成，每个 cluster 6 个同构 Qualcomm Compute Cores。L1 I-cache 和 D-cache 为每核私有；Unified L2 以 cluster 为共享单位。当前软件栈下，Android guest 使用 `cpu0-cpu11` 两个 cluster，Linux host 使用 `cpu12-cpu17` 一个 cluster。L1/L2 的精确容量值未能通过当前运行时接口直接读出，需要结合芯片资料进一步确认。
