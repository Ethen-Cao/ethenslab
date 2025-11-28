+++
date = '2025-11-17T09:26:24+08:00'
draft = true
title = 'QNX Hypervisor 配置问题'
+++

这是一个非常核心的 QNX Hypervisor 配置问题。

简单来说，`loc` (location) 指定的是这个虚拟设备（vdev）或透传设备（pass）**在 Guest VM（客户虚拟机）中的物理地址（Guest Physical Address, GPA）**。

Guest OS（比如你这个配置中的 "la" - 可能是 Linux Android）会通过访问这个 `loc` 指定的地址来和该设备进行通信。

-----

### `loc` 是如何确定的？

`loc` 的确定方式取决于它是**虚拟设备 (`vdev`)** 还是**透传设备 (`pass`)**。

#### 1\. `pass` (设备透传)

对于 `pass` 条目，`loc` 通常是**真实的硬件物理地址（Host Physical Address, HPA）**。

  * **来源：** 这些地址由 **SoC 芯片厂商（例如高通）的技术参考手册（TRM）** 定义。
  * **示例：**
      * `pass loc mem:0x0F000000,0x01000000,rwn=0x0F000000`  \# Passthrough TLMM GPIO space
      * `pass loc mem:0x0a600000,0x100000,rwn=0x0a600000` \# USB0 core\_base
  * **原理：** 你告诉 Hypervisor：“请把 Host 上的这个真实硬件地址 `0x0F000000`，直接映射到 Guest VM 的物理地址 `0x0F000000` 上。” 这样 Guest OS 就能像在裸机上一样直接访问这个硬件。

#### 2\. `vdev` (虚拟设备)

对于 `vdev` 条目（例如 `vdev-virtio-*.so`），`loc` 是一个**由平台架构师选择的“虚拟”地址**。

  * **来源：** 这不是一个真实的硬件地址，而是 Hypervisor 为 Guest VM **虚构**出来的一个地址。
  * **关键原则：** 这个地址必须和 **Guest OS 的设备树（Device Tree, DTB）** 中的定义**完全一致**。
  * **示例：**
      * `vdev vdev-virtio-net.so loc 0x1b018000 intr gic:45 ...`
  * **工作流程：**
    1.  **Hypervisor (`vm_config`)**：Hypervisor 在 `0x1b018000` 这个地址上“模拟”出一个 virtio-net 设备。
    2.  **Guest (DTB)**：Guest OS（Linux）的设备树（.dts）文件中必须有一个对应的节点，如下所示：
        ```dts
        virtio_net@1b018000 {
             compatible = "virtio,mmio";
             reg = <0x0 0x1b018000 0x0 0x1000>;  // 地址必须是 0x1b018000
             interrupts = <0 45 4>;             // 中断号必须是 gic:45
             ...
        };
        ```
    3.  **启动：** Guest OS 启动时，会解析 DTB，发现 `0x1b018000` 地址上有一个 "virtio,mmio" 设备，然后加载对应的驱动。
    4.  **通信：** 当 Guest OS 读写 `0x1b018000` 时，Hypervisor 会捕获这个操作，并将其转发给 Host OS (QNX) 上运行的 `vdev-virtio-net.so` 驱动来处理。

-----

### 如何为新的 `vdev` 选择 `loc`？

如果你要添加一个新的虚拟设备（例如，另一个 `vdev-virtio-*.so`），你需要执行以下步骤：

1.  **查找一个空闲的 Guest 物理地址范围。**

      * 你必须仔细检查这个 `vm_config` 文件（以及它可能 `include` 的所有其他文件）。
      * 列出所有 `pass loc mem:` 和 `vdev loc` 使用的地址范围。
      * **确保你的新 `loc` 地址不会与任何现有的地址范围重叠。** 任何重叠都会导致未定义的行为或系统崩溃。
      * 从你的配置文件来看，`0x1b...` 到 `0x1d...` 以及 `0x2D...` 这几个范围似乎是用于虚拟设备的，你可以尝试在这个附近找一个空闲的地址（例如 `0x1D0E0000`，假设它是空闲的）。

2.  **Guest OS 的设备树 (DTB)。**

      * 这是最重要的一步。你不能只在 `vm_config` 里添加。
      * 你必须在你的 Guest OS（LA）的 `.dts` 文件中添加一个新节点。
      * 这个新节点的 `reg` 属性**必须**包含你在第 1 步中选择的 `loc` 地址。
      * 你还需要为它分配一个未使用的虚拟中断号（例如 `intr gic:112`），并同样在 DTS 的 `interrupts` 属性中指定。

