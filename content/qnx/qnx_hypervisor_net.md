+++
date = '2025-11-15T17:17:50+08:00'
draft = false
title = 'QNX-Android IVI 架构中的 virtio-net 通信'
+++

本文基于一张 QNX Host + Android guest + Hypervisor + T-Box 的 virtio-net 架构图整理而成，图中展示了从 Android App 到车外 T-Box 的完整网络路径。

![](/ethenslab/images/virtio-net.drawio.png)

---

## 1. 概述

在典型的 QNX-Android 车机（IVI）架构中：

* **Android guest** 负责 UI、应用、车载 App；
* **QNX Host** 作为宿主 OS，负责底层驱动、网络、网关逻辑等；
* 两者之间通过 **QNX Hypervisor** 实现虚拟化隔离；
* **virtio-net** 提供了一条高性能的“虚拟网线”，把 Android guest 的网络栈接入 QNX Host 的网络栈，再通过物理网卡连到车外 **T-Box / 外部网络**。

理解这条 virtio-net 通道的工作原理，对于分析「Android App 上不了网」「Android 某段时间全断网」「按应用分流到不同 VLAN」这类问题非常重要。

---

## 2. 整体架构总览

按图的布局，从右到左是：

* **Android guest**
* **Hypervisor（在底部，负责虚拟化）**
* **QNX Host（包含 io-pkt / qvm / 驱动等）**
* **T-Box / 外部网络**

自顶向下的数据路径（单向发送）可以概括为：

> Android App
> → Java 网络库
> → libc
> → Linux 网络协议栈
> → virtio-net 驱动
> → virtqueue / shared memory
> → qvm process 中的 vdev-virtio-net
> → QNX Host io-pkt 中的 vdevpeer
> → bridge / route / VLAN
> → 物理网卡驱动
> → T-Box / 外部网络 

下面分模块拆开说明。

---

## 3. 关键组件角色

### 3.1 Android guest 侧

图右侧的 Android guest 中，自上而下是：

1. **Android App**

   * 普通应用，发起 HTTP/HTTPS 请求。

2. **Java 网络库（Java网络库）**

   * 如 OkHttp、HttpURLConnection 等；
   * 负责 HTTP 协议、TLS 握手、证书校验等。

3. **libc（Bionic）**

   * 提供 `socket() / connect() / send() / recv()` 等系统调用封装；
   * Java 层最终会落到这些 syscall 上。

4. **Linux 网络协议栈（linux 网络协议栈）**

   * Android guest 内核中的 TCP/IP 栈；
   * 负责三次握手、重传、路由、拥塞控制等；
   * 根据路由表选择出口网卡（这里是 virtio-net 对应的 `eth0`）。

5. **virtio-net 驱动（virtio-net驱动）**

   * Linux 内核的 virtio 网卡前端驱动 `virtio_net`；
   * 在内核视角，这就是一块网卡；
   * 向下不直接操作真实硬件，而是：

     * 把待发送的数据写入 **virtqueue（环形队列）**；
     * 写 virtio 设备 MMIO 寄存器触发 **kick** 通知。

---

### 3.2 virtqueue / shared memory（virtioqueue）

图中标记为 **“virtioqueue（share memory）”** 的方框是 Android guest 与 vdev-virtio-net 之间共享的数据结构：

* 本质是 **共享内存中的环形队列（ring buffer）**；
* 包含：

  * **desc table**：每个条目描述一块 guest buffer（addr、len、flags、next）；
  * **avail ring**：guest 写入，告诉设备“这些 desc 已经准备好可用了”；
  * **used ring**：设备（vdev）写入，告诉 guest “这些 desc 已经处理完了”。

virtio-net 驱动做两件事：

1. **写数据**：把 skb 对应的 buffer 地址写到 desc table，更新 avail ring；
2. **发事件（kick）**：向 virtio 设备 MMIO 地址写 QueueNotify 寄存器，告知某个队列有新数据。

---

### 3.3 Hypervisor：截获 kick，触发 VM Exit

图底部的 **Hypervisor** 条代表虚拟化层，它并不直接画出太多细节，但有两点非常关键：

1. **虚拟设备 MMIO 区域映射**

   * virtio-net 的寄存器（包括 QueueNotify）映射在某一块 guest 物理地址区（例如 `loc 0x1b018000`，具体取决于配置）；
   * 这块地址在二级页表中被标记为“由 Hypervisor 接管”的设备区域。

2. **截获 kick 事件**

   * 当 guest 对虚拟设备 MMIO 地址做写操作（kick）时，硬件触发 **guest exit（VM exit）**；
   * Hypervisor 收到 exit 事件，可得知：

     * 访问的地址；
     * 写入的值（通常是某个 queue index）；
   * 然后 Hypervisor 让 qvm 的 vCPU 线程从 “run” 系统调用返回，把 exit 信息交给 qvm。

图中有一条从 **virtio-net驱动 → Hypervisor** 的连线标注为 `kick`，以及一个说明框：“Hypervisor 截获 guest 对 loc 等 MMIO 区域的访问：触发 guest exit，携带访问地址/数据”。

---

### 3.4 qvm process 与 vdev-virtio-net

图左中部有一个 **“qvm process”** 方框，内部包含 **“vdev-virtio-net”** 组件：

* **qvm** 是运行在 **QNX Host 上的用户态进程**：

  * 创建/管理 VM；
  * 运行各 vCPU 线程；
  * 加载各种 vdev 插件（包括 virtio-net 对应的 `vdev-virtio-net`）。

* **vdev-virtio-net** 是一个设备后端模块，职责包括：

  * 初始化 virtio-net 设备（配置队列、feature 协商等）；
  * 在 **kick 事件** 到来时处理 virtqueue：

    1. 根据队列号（queue_id）找到对应 TX/RX virtqueue；
    2. 扫描 avail ring 找到新 desc；
    3. 使用与 guest 共享的地址空间访问 buffer（直接访问 guest memory）；
    4. 通过 iov/memcpy 读取或写入以太帧数据；
    5. 将帧转发给下一层（vdevpeer / io-pkt）或从下一层接收帧写入 RX virtqueue。

图中的说明框对 vdev-virtio-net 的处理流程有详细文字注释：

> 1. 根据 queue_id 找到 TX virtqueue
> 2. 扫描 avail ring 找新 desc
> 3. 通过共享地址空间访问 guest buffer
> 4. 用 iov/memcpy 取出以太帧数据
> 5. 交给 vdevpeer / io-pkt

---

### 3.5 QNX Host：io-pkt、vdevpeer、bridge/VLAN、eth driver

图左侧的 **QNX Host** 方框内部又包含一个 **io-pkt** 子框，其内有：

1. **vdevpeer**

   * 一个 QNX 网络驱动模块（例如 `devnp-vdevpeer-net.so`）；
   * 一侧通过 `/dev/vdevpeer/vp_la` 与 vdev-virtio-net peer 相连；
   * 在 io-pkt 中表现为一个虚拟网卡接口（例如 `vp_la`）。

2. **bridge / route / VLAN**

   * io-pkt 中的桥接、路由、VLAN 逻辑；
   * 可以把 `vp_la` 接入：

     * L2 bridge（与物理网卡或 VLAN 接口桥接）；
     * L3 路由/NAT；
     * 不同 VLAN（例如外部交换机的 VLAN10/VLAN20）。

3. **eth driver**

   * QNX 物理网卡驱动（如 `devnp-em.so` 等）；
   * 对应物理 `eth0` / `em0` 接口；
   * 最终把以太帧从真实物理口发出去，连到 **T-Box**。

最左边是一个单独的 **T-Box** 方框，表示车外/远端设备。

---

## 4. 发送路径：Android → QNX → T-Box

结合图，发包路径可以拆解为：

### 4.1 Android guest 内部

1. **App → Java 网络库 → libc**

   * App 发出 HTTP/HTTPS 请求；
   * Java 网络库对接 libc，发起 `socket()`、`connect()`、`send()` 等系统调用。

2. **libc → Linux 网络协议栈**

   * 内核 TCP/IP 栈根据路由判断出口网卡为 virtio-net（如 `eth0`）；
   * 生成 TCP 段、IP 包。

3. **Linux 协议栈 → virtio-net 驱动**

   * 内核把 skb 交给 virtio-net；
   * virtio-net 将数据描述为若干 buffer（可能是一段或 scatter-gather）。

4. **virtio-net → virtqueue / shared memory**

   * 把每个 buffer 的 guest 物理地址写入 **desc table**；
   * 在 **avail ring** 填入对应的 desc index；
   * 然后向 virtio QueueNotify MMIO 寄存器写入队列号，触发 **kick**。

### 4.2 Hypervisor / qvm / vdev-virtio-net

5. **kick → Hypervisor → guest exit**

   * guest 对 `loc` 对应的 virtio MMIO 地址写操作；
   * Hypervisor 捕获该 MMIO 写，触发 guest exit；
   * exit 信息中包含访问地址和写入的队列号。

6. **guest exit → qvm vCPU 线程返回**

   * qvm vCPU 线程原本阻塞在 “run” 系统调用中；
   * 有 guest exit 时返回，带出 exit 信息。

7. **qvm → vdev-virtio-net**

   * qvm 解析 exit 原因，识别这是 virtio-net 的 QueueNotify；
   * 调用 vdev-virtio-net 的处理函数：

     * 找到对应 TX virtqueue；
     * 读取 avail ring 新增的 desc；
     * 通过共享地址空间访问 guest buffer，把帧数据取出来。

### 4.3 vdev-virtio-net → vdevpeer → io-pkt → T-Box

8. **vdev-virtio-net → vdevpeer（/dev/vdevpeer/vp_la）**

   * vdev-virtio-net 将帧写入 vdevpeer；
   * 在 io-pkt 看来，这就是虚拟网卡 `vp_la` 收到了一个以太帧。

9. **vdevpeer → bridge / route / VLAN**

   * 如果配置为 bridge：

     * `vp_la` 加入某个 bridge，与物理网卡或 VLAN 接口桥接；
   * 如果配置为路由/NAT：

     * `vp_la` 属于一个内部网段，由 QNX 做三层转发；
   * 如果配置 VLAN：

     * `vp_la` 对接 `vlan10`/`vlan20` 等接口，接到车内交换机对应的 VLAN。

10. **bridge / VLAN → eth driver → T-Box**

    * 经过 bridge / VLAN 选择，帧被交给对应物理网卡接口（如 `em0`）；
    * 物理驱动发送帧到线缆/PHY；
    * T-Box 或外部网络设备收到该包。

---

## 5. 接收路径：T-Box → QNX → Android（简述）

接收方向与发送方向对称：

1. **T-Box / 外部设备 → 物理网卡 (eth driver)**

   * 物理网卡驱动收到以太帧，交给 io-pkt。

2. **eth driver → bridge / route / VLAN → vdevpeer(vp_la)**

   * 根据 bridge / VLAN / 路由策略把帧转发到 `vp_la`。

3. **vdevpeer → vdev-virtio-net**

   * vdevpeer 把帧交给 vdev-virtio-net；
   * vdev-virtio-net 找到对应的 RX virtqueue：

     * 从 RX 队列取一个 guest 预先提供的 buffer desc；
     * 把帧写入该 buffer；
     * 在 used ring 标记完成。

4. **vdev-virtio-net → virtqueue → virtio-net 驱动**

   * vdev 更新 used ring 并触发虚拟中断；
   * guest 内核的 virtio-net 驱动通过中断/轮询发现 RX 队列有新包；
   * 将该 buffer 封装为 skb，交给 Linux 协议栈。

5. **Linux 协议栈 → libc → Java 网络库 → App**

   * 内核 TCP/IP 处理 ACK、重组等；
   * 上交到 socket 层，libc `recv()` 返回；
   * Java 网络库拿到数据，解析 HTTP/TLS；
   * App 得到响应。

---

## 6. 设备节点与配置示例

图中的设计隐含了一些关键设备节点及其关系：

* **guest 侧 vdev 节点**：

  * `/dev/qvm/la/la_to_host`
  * 由 VM 配置中的 `system la` + `name la_to_host` 决定；
* **host 侧 peer 节点**：

  * `/dev/vdevpeer/vp_la`
  * 由 `devnp-vdevpeer-net.so` 或 `mods-vdevpeer-net` 驱动创建；
* 两者通过 `mount -T io-pkt` 或 `vpctl` 等命令进行绑定，最终在 io-pkt 中形成一个网卡接口 `vp_la`。

典型示意（伪代码）：

```sh
# 在 QNX Host 上加载 vdevpeer-net 驱动并绑定 virtio-net vdev
mount -T io-pkt \
  -o peer=/dev/qvm/la/la_to_host,bind=/dev/vdevpeer/vp_la,mac=02:df:53:00:00:01 \
  /lib/dll/devnp-vdevpeer-net.so

# 之后你就可以看到并配置 vp_la 网卡
ifconfig vp_la up
# 再把 vp_la 加入 bridge / VLAN 等
```

---

## 7. 总结与调试建议

通过这套 virtio-net 通道：

* Android guest 拥有了 **和物理网卡无关**、但性能接近直连的虚拟网卡；
* QNX Host 则掌握了整个网络出口：

  * 可以在 bridge / VLAN 处分流到不同车内网络；
  * 可以做 NAT / 防火墙 / QoS；
  * 也可以根据 `vp_la` 等接口做精细监控。

排查问题时：

* **Android 侧**：看 `ip addr` / `ip route` / `tcpdump -i eth0`（若支持）；
* **QNX Host 侧**：看 `ifconfig vp_la` / `ifconfig bridgeX` / `ifconfig eth0` 的 RX/TX 计数，必要时抓包；
* 若怀疑 virtio/kick 机制异常，可以关注：

  * guest 是否频繁触发 VM exit；
  * vdev-virtio-net 是否正确消费 virtqueue；
  * vdevpeer 与 io-pkt 是否正常工作（包是否到达 `vp_la`）。

这套 virtio-net 架构是 QNX-Android IVI 系统中最关键的“网络桥”，理解本文描述的路径，有助于你在设计 VLAN 分流、应用分网卡（Android 内按 UID 分配 Network）、排查偶发断网等问题时，更有把握地定位到哪一层出了问题。
