+++
date = '2026-04-08T21:00:00+08:00'
draft = false
title = 'SA8797 / Gunyah 下 Android Guest 的 vCPU 拓扑、Linux Host 观测口径与实际 CPU 分配'
+++

本文基于一次在 SA8797 车机上的实际排查，回答三个经常被混在一起的问题：

1. Android guest 明明只跑了 `12` 个 `yes`，为什么 `top` 头部还能看到 `1600%cpu` 和较高的 `idle`。
2. Android guest 内部已经接近满载，为什么 Linux host 侧看到的总 `steal` 只有约 `30%` 出头。
3. 当前平台上，Android guest 的 vCPU 数量、亲和性、优先级和时间片到底由哪一层决定。

这三个问题分别对应：

- guest 内部的 vCPU 拓扑与 `top` 展示口径
- hypervisor 实际给 guest 的 wall-clock CPU 时间
- Gunyah / Resource Manager 的静态配置与运行时调度属性

本文只保留已经通过源码和实机确认过的内容，不再使用旧现场里的过期假设。

## 一、结论摘要

当前车机环境下，可以先记住下面 8 个结论：

- Linux host 当前可见 `18` 个 CPU，`0-17` 全部 online。
- Android guest 当前 `possible=0-15`、`present=0-15`，但 `online=0-11`，也就是只启用了 `12` 个 vCPU。
- `maxcpus=12` 来自 Android guest 的启动参数，因此 `16` 个 vCPU 节点里只有前 `12` 个在线。
- 当前 `gvm.slice` 的生效 CPU 集合是 `0-17`；Linux cgroup 没有表现出把 guest 固定在 `12` 个 host CPU 上的行为。
- `gvm.slice/cpu.max = max 100000`，`cpu.stat` 中 `nr_throttled = 0`，因此 Linux cgroup 没有 CPU quota throttle。
- Android guest 的 vCPU 调度属性来自 `autoghgvm` 镜像里的 VM 配置：`affinity="pinned"`、`sched-priority=0`、`sched-timeslice=5000us`。
- upstream Gunyah RM 的调度模型里，guest 的 `sched-priority` 是相对 owner VM 的偏移量。当前配置下，可以确定 Android guest 使用 `5ms` 时间片，且其有效优先级与 owner VM 相同；结合 HLOS/root VM 的默认优先级 `32`，当前场景下可将 guest 的有效优先级理解为 `32`。
- 纯 CPU 压测时，guest 实际拿到的物理 CPU 时间主要体现在 Linux host 的 `cpu6-17` 上，`steal` 约 `33.31%`，折算为约 `6` 个 host-core 的 wall-clock。

换句话说，现场现象不是一个问题，而是两个问题叠加：

- Android `top` 的总量口径更接近 `16` 个 configured vCPU
- hypervisor 实际给 Android guest 的物理 CPU 时间只有大约 `6` 个 host-core 当量

## 二、运行时 VM 视图

### 2.1 Linux host 侧可见的 GVM 列表

当前 Linux host 上，`vmm_service` 管理的 GVM 配置来自 `/etc/vm_config.xml`。实机内容如下：

```xml
<vm_config NUM_VMS="1">
  <vm>
    <vm_name>autoghgvm</vm_name>
    <vmid>52</vmid>
    <systemd_service>qcrosvm.service</systemd_service>
  </vm>
</vm_config>
```

这和 `vendor/qcom/proprietary/vmm-service-noship/vmm-lib/vmm-utils/vm_config.c` 以及 `vendor/qcom/proprietary/vmm-service-noship/vmm-drv/src/vmm_drv.c` 的实现一致：

- `vm_config_get_num_vm()` / `vm_config_get_vmid()` 只从 XML 读取配置
- `vmm_service` 启动时按 XML 逐个创建 `gvm_ctx`

因此，Linux host 用户态服务这条链路当前只显式管理一个 GVM：

- `autoghgvm`
- `vmid = 52`

### 2.2 HLOS / Root VM 的运行时标识

在 host 运行时 device tree 中，还能看到 hypervisor 暴露的 HLOS VM 标识节点：

```text
/sys/firmware/devicetree/base/hypervisor/qcom,gunyah-vm
compatible = "qcom,gunyah-vm-id-1.0", "qcom,gunyah-vm-id"
qcom,vmid = 3
```

这和两处代码能对上：

- Linux 驱动 `vendor/qcom/opensource/gunyah-drivers/drivers/virt/gunyah/gh_rm_core.c`
  会读取 `qcom,gunyah-vm-id-1.0` 节点中的 `qcom,vmid`
- upstream Gunyah RM `include/rm_types.h` 定义 `VMID_HLOS = 0x3`

因此当前平台可确认的 VM 标识是：

- `VMID 3`：HLOS / root VM
- `VMID 52`：Android guest `autoghgvm`

## 三、CPU 拓扑与 vCPU 架构

### 3.1 Linux host 的 CPU 可见性

实机 Linux host：

```text
/sys/devices/system/cpu/possible = 0-17
/sys/devices/system/cpu/present  = 0-17
/sys/devices/system/cpu/online   = 0-17
```

也就是 host 侧共有 `18` 个在线 CPU。

从 `/sys/devices/system/cpu/cpu*/uevent` 可以看到 host 的 DT CPU 节点分成三组：

- `cpu0-5`   -> `/cpus/cpu@0` 到 `/cpus/cpu@500`
- `cpu6-11`  -> `/cpus/cpu@10000` 到 `/cpus/cpu@10500`
- `cpu12-17` -> `/cpus/cpu@20000` 到 `/cpus/cpu@20500`

这说明平台底层 CPU index 不是简单的 `0-17` 连续编号，而是更接近：

- `0-5`
- `8-13`
- `16-21`

### 3.2 Android guest 的 vCPU 可见性

实机 Android guest：

```text
/sys/devices/system/cpu/possible = 0-15
/sys/devices/system/cpu/present  = 0-15
/sys/devices/system/cpu/online   = 0-11
/proc/cmdline                    ... maxcpus=12 ...
```

这说明 guest 内部是：

- 定义了 `16` 个 vCPU 节点
- 但启动时只 bring up 了 `12` 个

因此要把三个概念分开：

- `possible/present = 16`：虚拟拓扑里存在 `16` 个 vCPU
- `online = 12`：当前真正能跑任务的只有 `12` 个 vCPU
- `maxcpus=12`：限制 online vCPU 数量的直接原因

### 3.3 当前生效的 vCPU 调度属性

从运行中的 Android guest `/proc/device-tree/qcom,vm-config/vcpus` 可以读到：

```text
affinity       = "pinned"
sched-priority = 0
sched-timeslice = 5000
affinity-map   = 13 12 11 10 9 8 21 20 19 18 17 16 5 4 3 2
```

这些字段与 `autoghgvm` 生效 DTB 中的内容一致，也与 upstream Gunyah RM 的解析逻辑一致：

- `include/vm_config_parser.h`
- `src/vm_config/vm_config_parser.c`
- `src/vm_config/vm_config.c`

### 3.4 vCPU 架构图

下面这张图把当前平台上和 CPU 相关的三层关系放在一起。

```text
                         +--------------------------------------+
                         | Gunyah Resource Manager / Hypervisor |
                         +--------------------------------------+
                                      |
                    +-----------------+-----------------+
                    |                                   |
                    v                                   v
         +------------------------+          +------------------------+
         | HLOS / Root VM         |          | Android Guest          |
         | vmid = 3               |          | autoghgvm, vmid = 52   |
         | priority = 32          |          | owner-relative prio    |
         | timeslice = 5 ms       |          | affinity = pinned      |
         +------------------------+          | sched-priority = 0     |
                    |                        | sched-timeslice = 5 ms |
                    |                        +------------------------+
                    |                                   |
                    |                        +----------+-----------+
                    |                        | configured vCPU = 16 |
                    |                        | online vCPU = 12     |
                    |                        +----------+-----------+
                    |                                   |
                    |                +------------------+------------------+
                    |                |                                     |
                    |                v                                     v
                    |      online vcpu0..11                       offline vcpu12..15
                    |      affinity-map front 12                  affinity-map tail 4
                    |      13 12 11 10 9 8 21 20 19 18 17 16     5 4 3 2
                    |                |                                     |
                    +----------------+------------------+------------------+
                                                     |
                                                     v
                             Linux host logical CPUs observed at runtime

                 cpu0-5        <-> platform cpu_index 0-5
                 cpu6-11       <-> platform cpu_index 8-13
                 cpu12-17      <-> platform cpu_index 16-21

                 therefore:
                 guest online vcpu0..11 land on the cpu_index set {8..13, 16..21},
                 which corresponds to Linux host cpu6-17
```

这张图里的两部分是直接证据：

- guest 的 `16` / `12` / `affinity-map`
- host 的 `cpu0-17` 与 DT CPU 节点分组

其中“`cpu_index 8..13 / 16..21` 对应 Linux host `cpu6-17`”来自 host DT 节点编号和运行时 per-CPU `steal` 分布的联合观察。

### 3.5 当前在线 vCPU 与 host CPU 的对应关系

如果把前 `12` 个 online vCPU 按当前 `affinity-map` 展开，可以得到下面的对应关系。

| guest vCPU | affinity index | 对应的 host Linux CPU |
| --- | --- | --- |
| vcpu0  | 13 | cpu11 |
| vcpu1  | 12 | cpu10 |
| vcpu2  | 11 | cpu9  |
| vcpu3  | 10 | cpu8  |
| vcpu4  | 9  | cpu7  |
| vcpu5  | 8  | cpu6  |
| vcpu6  | 21 | cpu17 |
| vcpu7  | 20 | cpu16 |
| vcpu8  | 19 | cpu15 |
| vcpu9  | 18 | cpu14 |
| vcpu10 | 17 | cpu13 |
| vcpu11 | 16 | cpu12 |

后 4 个 vCPU 当前是 offline：

| guest vCPU | affinity index | host Linux CPU | 状态 |
| --- | --- | --- | --- |
| vcpu12 | 5 | cpu5 | offline |
| vcpu13 | 4 | cpu4 | offline |
| vcpu14 | 3 | cpu3 | offline |
| vcpu15 | 2 | cpu2 | offline |

## 四、调度属性来自哪一层

### 4.1 Linux cgroup 不负责这次 vCPU 数量限制

当前实机：

```text
systemctl show gvm.slice -p AllowedCPUs
AllowedCPUs=0-17

/sys/fs/cgroup/gvm.slice/cpuset.cpus.effective = 0-17
/sys/fs/cgroup/gvm.slice/cpu.max               = max 100000
cpu.stat:nr_throttled                          = 0
```

这说明：

- `gvm.slice` 当前允许使用整个 `0-17`
- 也没有设置 CPU quota
- guest 只启用 `12` 个 vCPU 不是 Linux cgroup 造成的

### 4.2 vCPU 数量与属性来自 guest 镜像 / RM 配置

`autoghgvm` 由 host DTS 中的 `gh-secure-vm-loader@0` 加载：

- `qcom,vmid = <52>`
- `qcom,firmware-name = "autoghgvm"`

对应节点在 `vendor/qcom/opensource/base-devicetree/arch/arm64/boot/dts/qcom/sa8797p-vms.dtsi`。

而 upstream Gunyah RM 的 vCPU 配置模型只解析这些调度字段：

- `affinity`
- `sched-priority`
- `sched-timeslice`
- `affinity-map`

对应代码：

- `include/vm_config_parser.h`
- `src/vm_config/vm_config_parser.c`
- `src/vm_config/vm_config.c`

### 4.3 优先级与时间片的实际含义

upstream Gunyah RM 里的关键常量是：

```c
#define ROOTVM_PRIORITY            32
#define SCHEDULER_DEFAULT_TIMESLICE 5000000 ns
```

HLOS/root VM 的 vCPU 创建时直接使用：

- `priority = ROOTVM_PRIORITY = 32`
- `timeslice = 5 ms`

而 Android guest 的优先级不是绝对值，而是：

```c
effective_priority = owner_vm->priority + sched_priority
effective_timeslice = sched_timeslice * 1000
```

当前 guest 的运行时属性是：

- `sched-priority = 0`
- `sched-timeslice = 5000 us`

因此它的当前有效调度基线是：

- `priority = owner_vm->priority + 0`
- `timeslice = 5 ms`

对 SA8797 当前场景，结合 HLOS/root VM 的默认优先级 `32`，这组配置与“guest 与 HLOS/root VM 同级、同时间片”这一结论相符。

### 4.4 当前没有看到明文的 CPU quota / reservation 字段

到目前为止，Linux host 侧和 upstream RM 代码里都没有看到如下字段：

- `quota`
- `reservation`
- `share`
- `cap`

当前能看到的调度输入只有：

- vCPU 是否 `pinned`
- 与 owner 的相对优先级
- vCPU 时间片
- vCPU affinity map

这意味着：

- 现有证据足以解释 vCPU 拓扑和基础调度属性
- 但不足以从 Linux host 这一层直接读出 vendor RM 私有 env payload 中的完整 CPU 策略

## 五、为什么 Android top 与 Linux host top 看起来不一致

### 5.1 先排除 Linux host 自己的上限

在 Linux host 上直接运行 `18` 个 `yes` 时，host 的 `18` 个 CPU 可以全部接近满载。  
这说明 host 自己不存在一个固定的 `30%` 或 `6 core` 上限。

### 5.2 受控实验：guest 内启动 12 个 yes

为了看清 guest 对 host 的映射关系，我做了一个干净的受控实验：

1. 先暂停 Android guest 内原有的 `dd` 压测进程
2. 在 guest 内启动 `12` 个 `yes > /dev/null`
3. 同时在 host 上抓 `mpstat -P ALL 1 1`
4. 实验结束后恢复原来的 `dd`

guest 侧典型输出：

```text
1600%cpu ... 279%idle ...
12 个 yes 进程基本都在 100% 左右
```

host 侧 `mpstat` 结果：

```text
all    %steal = 33.31
cpu0-5  %steal ≈ 0
cpu6-17 %steal ≈ 37% - 46%
```

### 5.3 这组结果说明了什么

它说明了两件不同的事。

第一，Android `top` 的总量口径并不是简单按 `12` 个 online vCPU 展示。  
如果它完全按 `12` 个 online vCPU 展示，那么在 `12` 个 `yes` 全部接近满载时，不应该同时出现：

- `1600%cpu`
- 以及较高的 `idle`

这组现象更接近“总容量仍然按 `16` 个 configured vCPU 计算，但真正参与调度的只有 `12` 个 online vCPU”。

第二，host 侧真实分配给 guest 的 wall-clock CPU 时间只有大约：

```text
18 * 33.31% ≈ 5.99 cores
```

也就是约 `6` 个 host-core 当量。

更重要的是，这些时间主要集中在 `cpu6-17`，而不是平均铺在 `cpu0-17` 上。  
这和前面从 `affinity-map` 推导出的“在线 guest vCPU 实际落在 host `cpu6-17`”完全一致。

### 5.4 这不是 cgroup throttle

这次实验同时也排除了一个常见误判：

- 不是 `gvm.slice` 只允许 guest 跑在 `12` 个 host CPU 上
- 也不是 `cpu.max` 把 guest throttle 到了约 `30%`

因为当前实机已经确认：

- `AllowedCPUs = 0-17`
- `cpuset.cpus.effective = 0-17`
- `cpu.max = max 100000`
- `nr_throttled = 0`

因此，host 只看到约 `6` 个 core 的 guest wall-clock，不能归因到 Linux cgroup。

## 六、当前能确认的边界

### 6.1 已确认

- Android guest 当前有 `16` 个 configured vCPU，其中 `12` 个 online。
- `maxcpus=12` 是 `12` 个 online vCPU 的直接原因。
- guest 的 vCPU 调度属性是 `pinned + priority offset 0 + 5 ms timeslice`。
- HLOS/root VM 的默认优先级也是 `32`，默认时间片也是 `5 ms`。
- 在纯 CPU 压测下，guest 的 wall-clock CPU 时间主要体现为 host `cpu6-17` 上的 `steal`。
- 当前观测到的 guest 实际物理 CPU 时间约为 `6` 个 host-core，而不是 `12` 个。

### 6.2 尚未直接读出的内容

- vendor RM 私有 env payload 中的 `usable_cores`
- vendor RM 私有 env payload 中的 `boot_core`
- hypervisor 内部针对各 VM 的精确 wall-clock 账本
- vendor RM 是否存在更下层的专有调度权重逻辑

upstream RM 代码已经证明这些字段在设计上存在：

- `usable_cores`
- `boot_core`

但当前车机运行环境没有把这份 env payload 直接暴露到 Linux host 可读路径上。

从 host CPU index 分组与 guest `affinity-map` 的组合关系看，当前平台的 usable core set 与 `{0-5, 8-13, 16-21}` 这一集合相符；但这一步仍然属于运行时推导，不是直接从 vendor RM env payload 读出的明文结果。

## 七、如何配置 Android guest vCPU

这一节不讨论观测口径，而只回答一个工程问题：如果需要修改 Android guest 的 vCPU 数量、启动时 online 数量、亲和性、优先级和时间片，应该改哪里。

先给出源码视角下的配置链路：

```text
host DTS
  sa8797p-vms.dtsi
    gh-secure-vm-loader@0
      qcom,firmware-name = "autoghgvm"
                 |
                 v
autoghgvm boot image
  包含 guest DTB / VM config
                 |
                 v
guest DTB
  /cpus
  /qcom,vm-config/vcpus
  /chosen/bootargs
                 |
                 v
Gunyah RM
  parse_vcpus()
  handle_vcpu()
                 |
                 v
runtime vCPU
  configured vCPU count
  online vCPU count
  affinity / priority / timeslice
```

这里最重要的结论是：当前源码里看不到通过 `qcrosvm` 命令行直接配置 vCPU 数量的路径。真正生效的入口是 guest 镜像里的 DTB / VM config，RM 在创建 VM 时解析并下发这些属性。

### 7.1 配置入口在哪里

host 侧只负责选择要加载哪一个 guest 镜像。当前平台在：

```dts
auto_vm_0: gh-secure-vm-loader@0 {
    compatible = "qcom,gh-secure-vm-loader";
    qcom,pas-id = <44>;
    qcom,vmid = <52>;
    qcom,firmware-name = "autoghgvm";
    qcom,firmware-index = <0>;
};
```

也就是说，host DTS 这一层决定的是：

- 加载哪个 VM image
- 这个 image 对应哪个 `vmid`

而 guest 的 vCPU 数量和调度属性，不是在这里展开定义，而是在 `autoghgvm` 这份镜像内部的 DTB / VM config 中定义，再由 Gunyah RM 读取。

### 7.2 vCPU 数量是怎么配置的

upstream Gunyah RM 的 `parse_vcpus()` 会先读取 `/qcom,vm-config/vcpus` 节点；如果这个节点没有显式给 `config`，它默认去看 `/cpus`：

```c
const char *config =
    fdt_stringlist_get(fdt, node_ofs, "config", 0, NULL);
if (config == NULL) {
    config = "/cpus";
}
```

随后它会遍历这个路径下所有 `device_type = "cpu"` 的子节点，并把每个 CPU 节点压入 `vd->vcpus`。因此，从源码看：

- `configured vCPU` 的数量，直接由 guest DT 里 CPU 节点的数量决定
- 默认来源是 `/cpus`
- 不是由 `qcrosvm` 命令行直接指定

当前 `autoghgvm` 的生效 DTB 里有 `16` 个 CPU 节点，所以 guest 运行时表现为：

- `possible=0-15`
- `present=0-15`

如果要把 guest 的总 vCPU 数量从 `16` 改成 `12`，源码视角下应当改的是：

- guest DTB 中 `/cpus` 下的 CPU 节点数量
- 或者 `/qcom,vm-config/vcpus` 的 `config` 指向的 CPU 配置路径

### 7.3 启动时哪些 vCPU 会 online

RM 在解析 CPU 节点时，还会读取每个节点的 `status`，并据此决定它是不是 boot 时就启用的 vCPU：

- `status = "okay"`：boot 时启用
- `status = "disabled"`：boot 时不启用
- `status` 缺失：第一个 CPU 视为 boot CPU，其余 CPU 默认不视为 boot-enabled

对于不是 boot CPU 的次级 vCPU，源码还要求它必须有合法的 `enable-method`：

- `psci`
- `qcom,gunyah-hvc`

因此，从源码定义看：

- `/cpus` 决定 guest 一共定义了多少个 vCPU
- `status` 和 `enable-method` 决定这些 vCPU 是否允许在 boot / secondary bring-up 过程中被启用

但当前车机现场还有第二个限制来源：`/chosen/bootargs` 里的 `maxcpus=12`。

从 upstream RM 的 `vm_creation.c` 也能看到这条链路：它会先读取 base DTB `/chosen/bootargs`，再把 `vm->cfgcpio_cmdline` 追加进去，最后把合并后的 `bootargs` 写回生成中的 DTO。也就是说，启动参数这一层本身也是 VM 创建流程的一部分，而不是 Android guest 启动后才临时决定的。

我已经在当前生效的 `autoghgvm` DTB 和 guest 运行时 `/proc/cmdline` 中都确认了 `maxcpus=12`。这意味着当前平台的实际行为是：

- guest DT 定义了 `16` 个 vCPU
- 启动参数又把 online 数量限制到了 `12`

所以如果工程目标是“让 guest 启动时直接 online 16 个 vCPU”，只改 `/cpus` 不够，还需要同时处理 `bootargs` 里的 `maxcpus`。

### 7.4 亲和性、优先级和时间片怎么配置

`parse_vcpus()` 直接解析下面这几个字段：

- `affinity`
- `sched-priority`
- `sched-timeslice`
- `affinity-map`

其中 `affinity` 支持的模式，源码里明确有：

- `sticky`
- `pinned`
- `static`
- `proxy`

真正创建 vCPU 时，`handle_vcpu()` 会按解析结果逐个调用：

- `gunyah_hyp_vcpu_set_affinity()`
- `gunyah_hyp_vcpu_set_priority()`
- `gunyah_hyp_vcpu_set_timeslice()`

也就是说，这几个字段不是“文档说明”，而是直接映射到 hypervisor vCPU 创建接口的输入。

它们的当前含义可以按源码理解为：

- `affinity-map`
  每个 vCPU 对应一个 platform `cpu_index`
- `sched-priority`
  不是绝对优先级，而是相对 owner VM 的偏移量
- `sched-timeslice`
  DT 里按微秒配置，创建时会乘 `1000` 转成纳秒

当前 `autoghgvm` 的运行时配置就是：

- `affinity = "pinned"`
- `sched-priority = 0`
- `sched-timeslice = 5000`
- `affinity-map = 13 12 11 10 9 8 21 20 19 18 17 16 5 4 3 2`

### 7.5 修改时需要联动哪些字段

从源码约束看，下面几组字段不能孤立修改。

第一组是 vCPU 数量和 affinity 数量：

- 非 `proxy` 模式下，`cpu_count` 必须与 `affinity-map` 的元素个数一致
- 否则 `parse_vcpus()` 会直接报错：`cpu and affinity count don't match`

第二组是次级 vCPU 的启动属性：

- 如果某个 vCPU 不是 boot CPU，就必须有合法 `enable-method`
- 当前常见的是 `psci`

第三组是 online 数量与 bootargs：

- `/cpus` 里可以定义 `16` 个 vCPU
- 但 `bootargs` 里的 `maxcpus=12` 仍然会把 online 数量限制到 `12`

第四组是调度属性与 owner VM 约束：

- `sched-priority` 最终会和 owner VM 的优先级相加
- `sched-timeslice` 会做范围检查
- 非受信配置还会额外经过优先级合法性约束

所以，工程上要避免一种常见误区：只改一个数字，然后期待运行时自动收敛。  
对这套 RM 配置来说，vCPU 是一个组合配置，至少要联动检查：

- `/cpus` 下 CPU 节点个数
- 每个 CPU 节点的 `status`
- 次级 CPU 的 `enable-method`
- `/qcom,vm-config/vcpus` 里的 `affinity-map`
- `/chosen/bootargs` 里的 `maxcpus`
- `sched-priority` 与 `sched-timeslice`

### 7.6 用当前 autoghgvm 配置举例

当前实机这组 `16 configured / 12 online`，正好可以反过来当成一个配置示例：

- `/cpus` 下有 `16` 个 CPU 节点
- `/qcom,vm-config/vcpus` 里有 `16` 个 `affinity-map` 条目
- `/chosen/bootargs` 里有 `maxcpus=12`

所以运行时结果是：

- guest 能看到 `16` 个 configured vCPU
- 但只有前 `12` 个 online

如果你的目标分别是下面几种场景，那么源码导向下的改法也不同。

场景一：保持 `16` 个 configured vCPU，但让 `16` 个都在启动时 online

- 保留 `16` 个 CPU 节点
- 保留 `16` 个 `affinity-map` 条目
- 去掉或提高 `bootargs` 里的 `maxcpus`
- 同时确认 secondary vCPU 的 `enable-method` 和 boot policy

场景二：只需要 `12` 个 configured vCPU

- 把 `/cpus` 下 CPU 节点收敛到 `12` 个
- 把 `affinity-map` 条目同步收敛到 `12` 个
- 再根据实际需要决定是否保留 `maxcpus=12`

场景三：vCPU 数量不变，只调整它们落在哪些物理 CPU index 上

- 不改 `/cpus` 数量
- 只改 `affinity-map`

场景四：vCPU 数量不变，只调整调度积极性

- 调整 `sched-priority`
- 调整 `sched-timeslice`

这里要特别强调一点：从当前源码和现场证据看，Android guest 的 vCPU 配置是“拓扑 + affinity + priority + timeslice”的组合配置；本文还没有发现一个公开明文字段，可以直接写成“给这个 guest 固定 12 个物理核保底”。

## 八、本文回答的问题

回到开头的三个问题，可以给出更精确的回答。

### 7.1 为什么 Android guest 能看到 16 个 CPU，却只跑 12 个

因为当前 guest 的虚拟拓扑定义了 `16` 个 vCPU，但启动参数 `maxcpus=12` 只让其中 `12` 个 online。

### 7.2 为什么 Android top 已经很忙，Linux host 的总 `steal` 却只有约 30%

因为这两个数不是同一个口径：

- Android `top` 反映的是 guest 内部的 vCPU 负载与显示口径
- Linux host 的 `%steal` 反映的是 guest 实际拿到的物理 CPU wall-clock

当前实测下，guest 实际拿到的大约是 `6` 个 host-core 当量。

### 7.3 当前到底是谁在决定 guest 的 CPU 行为

当前已经确认有三层共同参与：

- guest 镜像 / DTB 决定 `16` 个 configured vCPU 与 `maxcpus=12`
- Gunyah RM 决定 `pinned / priority / timeslice / affinity-map`
- 更下层的 vendor RM 私有 env payload 和 hypervisor 运行时状态，决定最终可用 CPU 集与实际 wall-clock 分配

因此，分析 Android guest 的 CPU 问题时，不能只看 Android `top`，也不能只看 Linux cgroup，而需要把下面三类信息放在一起：

- guest 的 configured / online vCPU 拓扑
- RM 的 vCPU affinity / priority / timeslice
- host 上按核分布的 `%steal`
