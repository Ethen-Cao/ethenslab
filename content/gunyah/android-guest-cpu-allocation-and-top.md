+++
date = '2026-03-16T16:50:00+08:00'
draft = false
title = 'SA8397 Gunyah 场景下 Linux Host / Android Guest 的 CPU 分配策略与 Android top 误判原因'
+++

本文记录一次在 SA8397 SoC 上的实际排查结果。当前系统同时运行 Linux host 与 Android guest，Android guest 由 `qcrosvm` 承载。现场现象是：

- Linux host 看到 18 个 CPU
- Android guest 看到 16 个 CPU
- 但无论在 Android 内启动多少个 `yes`，都无法把 `top` 中的 CPU 打满
- `top` 一直显示较高的 `idle`

排查结论是：这不是 `yes`、cpuset 或普通 affinity 设置的问题，而是当前虚拟化栈本身就只给 Android guest 启用了 12 个 CPU；同时 Android `top` 的显示口径又容易让人误以为 16 个 CPU 都应该可用。

## 1. 当前 CPU 分配策略

### 1.1 Linux host 的 CPU 资源

Linux host 上直接看到：

```text
/sys/devices/system/cpu/present = 0-17
/sys/devices/system/cpu/online  = 0-17
```

也就是说 host 侧一共有 18 个 CPU，且全部在线。

### 1.2 Host 侧对 VM 的 CPU 划分

host 使用 systemd slice 对不同 VM 类型做 CPU 资源隔离：

```ini
# /usr/lib/systemd/system/gvm.slice.d/allowed-cpus.conf
[Slice]
AllowedCPUs=6-17

# /usr/lib/systemd/system/pvm.slice.d/allowed-cpus.conf
[Slice]
AllowedCPUs=0-5
```

这意味着：

- `gvm.slice` 只能使用 host CPU `6-17`，一共 12 个 CPU
- `pvm.slice` 只能使用 host CPU `0-5`，一共 6 个 CPU

而 Android guest 对应的 `qcrosvm.service` 正好运行在 `gvm.slice` 下：

```text
/proc/<qcrosvm-pid>/cgroup = 0::/gvm.slice/qcrosvm.service
```

进一步看 `qcrosvm` 进程本身：

```text
Cpus_allowed_list: 6-17
```

所以从 host 视角，Android guest 实际只被分配到了 12 个 host CPU 时间域。

## 2. Android guest 当前看到的 CPU 拓扑

Android guest 内的状态如下：

```text
/sys/devices/system/cpu/possible = 0-15
/sys/devices/system/cpu/present  = 0-15
/sys/devices/system/cpu/online   = 0-11
/sys/devices/system/cpu/offline  = 12-15
```

这说明 guest 内核配置上暴露了 16 个 CPU，但真正 online 的只有 12 个。

这里的“暴露了 16 个 CPU”需要特别说明。

它的意思不是 Android 真的拿到了 16 个可运行的物理核，而是：

- Android guest 的虚拟硬件拓扑里定义了 16 个 vCPU
- 对 guest 内核来说，这 16 个 CPU 节点是存在的
- 因此内核会在 `possible/present` 维度上看到 `0-15`

换句话说，这里的 CPU 是虚拟 CPU，也就是 vCPU，而不是 host 侧的物理 CPU。

可以把几个概念区分开：

- `possible`：理论上这台系统最多可能存在多少个 CPU
- `present`：当前硬件/虚拟硬件描述中实际声明了多少个 CPU
- `online`：当前真正启用、可以被调度器用来运行任务的 CPU

因此当前 guest 的真实含义是：

- 虚拟拓扑声明了 16 个 vCPU
- guest 内核也认得这 16 个 vCPU
- 但运行时真正启用的只有 12 个
- 剩余 `cpu12-15` 虽然“存在于拓扑中”，但没有 online

如果用一个更直观的比喻：

- “摆了 16 张工位” = 虚拟拓扑暴露了 16 个 CPU
- “只有 12 张工位通电可用” = 实际 online 只有 12 个 CPU

从标准接口也能看出这一点：

```text
getconf _NPROCESSORS_CONF = 16
getconf _NPROCESSORS_ONLN = 12
nproc                    = 12
```

含义分别是：

- `_NPROCESSORS_CONF`：系统配置上存在的 CPU 数量
- `_NPROCESSORS_ONLN`：当前在线、可被调度的 CPU 数量
- `nproc`：用户态通常能实际使用到的 CPU 数量

因此，Android guest 的现状不是“16 个核都在线但是跑不满”，而是“只有 12 个核在线”。

## 3. 为什么 Android 只在线 12 个 CPU

排查 `/proc/cmdline` 后可以直接看到：

```text
maxcpus=12
```

这是最关键的证据。`maxcpus=12` 会限制 guest 内核启动时最多只 bring up 12 个 CPU，因此最终结果就是：

- `possible/present = 16`
- `online = 12`
- `offline = 4`

也就是说，Android guest 当前的 CPU 策略实际上是：

1. 虚拟拓扑对 guest 暴露 16 个 CPU
2. 但 guest 内核启动参数 `maxcpus=12` 只启用其中 12 个
3. 同时 host 的 `gvm.slice` 也只给 `qcrosvm` 分配了 12 个 host CPU

这两层约束是彼此一致的。

## 4. 为什么运行很多个 yes 仍然无法“占满 16 核”

我在 Android guest 里启动了 16 个 `yes > /dev/null`，并检查了每个进程的调度状态。

结果显示：

- `yes` 进程的 `Cpus_allowed_list` 是 `0-15`
- shell 所在 cpuset 也是 `0-15`
- 没有发现额外的 cpuset 或 CFS quota 将它们进一步限制到更少 CPU

这说明应用层并没有被单独限死。

但由于 Android 实际只有 `0-11` 这 12 个 CPU 在线，最终总吞吐量上限也只能接近 12 个 CPU，而不可能接近 16 个 CPU。

所以“启动更多 `yes` 也无法占满”的根因是：

- 调度器只会把任务放到 online CPU 上
- `cpu12-15` 本身就是 offline 状态

## 5. 为什么 Android top 看起来像“显示错误”

现场最容易误判的地方在这里。

Android `top` 里会出现类似这样的头部：

```text
1600%cpu ... 376%idle ...
```

看起来像是：

- 系统总共有 16 个 CPU 容量
- 但只用了大约 12 个 CPU
- 还剩下很多 `idle`

这和实测现象完全一致，但它容易让人误以为：

“既然 guest 能看到 16 个 CPU，那这些 idle 应该是 16 个在线 CPU 中空闲出来的。”

实际上并不是。

### 5.1 `top` 的误导点

Android guest 当前同时存在两组数字：

- configured CPU: 16
- online CPU: 12

而 `top` 的显示口径更接近按“configured CPU 总量”归一化，所以它仍然会把总容量显示成接近 `1600%` 的世界观。  
但调度器真正能用的只有 12 个 online CPU，因此跑满后你依然会在 `top` 头部看到较大的 `idle`。

换句话说：

- `top` 不是在说 “12 个在线 CPU 里还有很多没用到”
- 它更像是在说 “相对 16 个配置 CPU 而言，还有 4 个 CPU 容量没有参与运行”

而这 4 个容量实际上对应的正是 `cpu12-15` 这 4 个 offline CPU。

### 5.2 为什么这会被感知成“top 显示错误”

因为对用户来说，最自然的理解是：

1. Android 看到了 16 个 CPU
2. 我起了足够多的 `yes`
3. 那么 `top` 应该接近 1600% busy、0% idle

但真实系统行为是：

1. Android 只是 `present` 了 16 个 CPU
2. 实际 `online` 只有 12 个
3. `top` 仍然以 16 个 configured CPU 的总量去展示
4. 于是形成“明明很多任务在跑，但 idle 还是很高”的观感

因此更准确地说，这不是 `top` 算错了，而是它的展示口径没有把 `possible/present` 和 `online` 的差异直观表达出来，导致观察者很容易误判。

## 6. 本次排查的最终结论

本次场景下 Linux host 与 Android guest 的 CPU 分配策略可以总结为：

- Linux host 共有 18 个 CPU，全部在线
- host 通过 `gvm.slice` 和 `pvm.slice` 做 CPU 划分
- Android guest 所在的 `qcrosvm.service` 运行在 `gvm.slice`
- `gvm.slice` 只允许使用 host CPU `6-17`，共 12 个 CPU
- Android guest 虚拟拓扑暴露了 16 个 CPU
- 但 guest 启动参数 `maxcpus=12` 只启用了其中 12 个
- 因此 Android guest 的 `cpu12-15` 长期处于 offline

而 Android `top` 看起来“显示错误”的根因是：

- 它的展示更接近基于 16 个 configured CPU 的总容量
- 但实际只有 12 个 online CPU 可以运行任务
- 所以当 12 个在线 CPU 已经接近跑满时，`top` 仍然会显示较高的 `idle`

## 7. 建议的后续排查方向

如果后续要继续追查“为什么 guest 被设计成 `maxcpus=12`”，建议沿下面方向继续：

- Android guest boot image / vendor boot / bootconfig 的生成链
- `qcrosvm` 启动链路里是否有针对 Android guest 注入 bootargs
- guest firmware / DT / launch config 中是否存在与 CPU 数量相关的模板配置
- 产品侧是否故意将 `gvm.slice` 固定为 12 个 CPU，以便和其他 VM 做资源隔离

如果目标是让 Android 真正使用 16 个 CPU，则至少需要同时满足：

- guest 内核去掉 `maxcpus=12`
- host 侧给 `gvm.slice` 分配不少于 16 个 host CPU
- `qcrosvm`/虚拟拓扑配置链路与 guest boot 参数保持一致

## 8. 实测验证：Android guest 压测是否会映射到 Linux host

为了确认 Android guest 的 CPU 负载是否真的会反映到 Linux host，我做了一组更干净的对照实验。

实验方法是：

1. 先在 Android guest 里执行 `pkill yes`，清空残留压测进程
2. 采集一组 host 空载窗口：连续读取两次 host `/proc/stat`，间隔 3 秒
3. 在 Android guest 中启动 16 个 `yes > /dev/null`
4. 再采集一组 host 压测窗口：连续读取两次 host `/proc/stat`，间隔 3 秒
5. 对比 host `cpu6-17` 的差分结果

这里之所以只重点看 `cpu6-17`，是因为当前 host 的 CPU 分配策略本来就是：

```ini
[Slice]
AllowedCPUs=6-17
```

也就是说 Android guest 所在的 `gvm.slice` 本来就只会落在 host 的 `6-17` 这 12 个 CPU 上。

### 8.1 Android guest 侧的压测现象

在 Android guest 启动 16 个 `yes` 后，`top` 头部典型现象如下：

```text
1600%cpu   41%user 1124%sys 428%idle ...
```

这说明 guest 内部确实已经进入高负载状态，并接近 12 个 online CPU 的能力上限。

### 8.2 Linux host 侧的 per-CPU 对照结果

对 host `cpu6-17` 做 3 秒窗口差分后，可以得到两组结果。

空载窗口下，`cpu6-17` 合计：

- `busy = 335`
- `total = 3871`
- 利用率约 `8.7%`

Android guest 压测窗口下，`cpu6-17` 合计：

- `busy = 1786`
- `total = 5382`
- 利用率约 `33.2%`

单核上也能看到明显抬升，例如：

- `cpu6`: `5.5% -> 43.6%`
- `cpu7`: `7.0% -> 45.3%`
- `cpu14`: `4.5% -> 45.5%`

这说明 Android guest 的负载确实会在 Linux host 上体现出来，而且主要集中在 `gvm.slice` 绑定的 `cpu6-17`。

### 8.3 为什么在 host 总览里不一定“特别明显”

即使 Android guest 在内部已经接近跑满 12 个 online CPU，host 总体视图里也不一定会显得极端。

主要原因有两个：

- host 整机一共有 18 个 CPU，总盘子更大
- guest 的负载主要集中在 `6-17`，而不是均匀打满 `0-17`

所以如果只看 host 的整体 `top` 头部，变化可能会被摊薄；但只要看 per-CPU，尤其是 `cpu6-17`，映射关系就很清楚。

### 8.4 线程级验证的说明

我也尝试了从 `qcrosvm` 线程级去看 `schedstat` 和 `top -H`，但这一层的证据不如 per-CPU 稳定。

例如：

- `autoghgvm_vcpu0` 这个命名线程并没有表现出明显增长
- `top -H` 也没有直接给出一个非常直观的“guest vCPU 线程热点”

这说明当前平台上，guest 的实际执行路径未必能通过一个简单命名的 `vcpu` 线程直接看出来；也可能存在更复杂的调度或后端执行路径。

但这并不影响更底层的结论：  
从 host `/proc/stat` 的 per-CPU 差分看，Android guest 的 CPU 压测已经明确映射到了 host 的 `cpu6-17` 上。

### 8.5 本节结论

关于“Android guest 消耗的 CPU 是否会体现在 Linux host 上”，本次实测结论是：

- 会体现
- 但主要集中在 `gvm.slice` 绑定的 host `cpu6-17`
- 如果只看 host 整机总览，不一定非常直观
- 看 host per-CPU 差分，比看单纯的 host `top` 头部更可靠
