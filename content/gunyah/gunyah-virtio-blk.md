+++
date = '2025-08-04T09:49:58+08:00'
draft = false
title = 'Gunyah virtio-blk 通信机制'
+++

## Block图
![](/ethenslab/images/gunyah-virtio-blk.png)

下面是这张图的解读与要点说明（橙色=控制面，蓝色=数据面）：

### 总览

* **Guest 侧**：Android App 通过文件系统到 `virtio-blk` 前端驱动（VblkFE）。
* **共享内存**：`Guest RAM (shared)` 中包含 **virtqueue(Avail/Used)** 元数据与 **Guest Buffers** 数据缓冲区。
* **Host 侧**：`qcrosvm`（VMM）实现 `virtio-blk` **后端**，通过 **Gunyah Host Driver** 与 **Gunyah Hypervisor** 交互；真实数据落在 **Backing Storage**（镜像文件或块设备）上。
* **分工**：Hypervisor 只做 **陷入与中断路由**，**不搬数据**；数据由 **VMM↔Guest Buffers↔Disk** 在蓝色路径中完成。

### 控制面（橙色）

1. **提交请求**：Guest 的 VblkFE 将 **描述符**（指向 Guest Buffers 的 GPA、长度、方向）写入 **Avail ring**，并对设备寄存器执行 **MMIO QueueNotify**（kick）。
2. **陷入与唤醒**：MMIO 被 Hypervisor 拦截，转交 Host 的 **Gunyah Host Driver**，唤醒 **qcrosvm** 的设备处理线程。
3. **队列处理**：VMM 读取 **Avail ring**，解析描述符；完成 I/O 后更新 **Used ring**。
4. **中断返回**：VMM 请求 Host Driver 触发虚拟中断，Hypervisor 将 **IRQ 注入 Guest**，通知前端有请求完成。

> 关键点：**virtqueue 只承载“元数据与索引”**（哪块缓冲、多大、读写方向、完成状态），**不承载数据本体**。

### 数据面（蓝色）

1. **应用读写**：App 通过 FS 调用 `read()/write()` 到 VblkFE。
2. **后端 I/O**：VMM 根据描述符把 **GPA → VMM 可访问的指针/iovec**，对 **Disk** 执行 `preadv/pwritev`：

   * 读：从 **Disk** 读数据，**直接写入 Guest Buffers**；
   * 写：从 **Guest Buffers** 取数据，**写入 Disk**。
3. **请求完成**：VblkFE 在收到中断后，从 **Used ring** 得知完成与字节数，从 **Guest Buffers** 取/放数据，FS 返回给 App。

### 设计要点 / 常见误区

* **Hypervisor 不搬数据**：仅处理 MMIO 陷入、事件与中断路由；数据由 VMM 直接读写 **Guest Buffers** 与 **Disk**。
* **共享含义**：`Guest RAM (shared)` 表示这片内存页由 Hypervisor 保护并映射给 Guest 与 VMM，二者看到的是 **同一批物理页**（各自视角不同）。
* **一致性**：VMM/Guest 对 ring 的读写需按 virtio 规范配合内存屏障；crosvm 内部已处理。
* **安全与运维**：作为 VM 后端的 **块设备/分区** 不应在 Host 上同时挂载为可写，否则会引发文件系统损坏；需要共享文件时优先用 **文件级共享**（如 virtio-fs）。

### 一句话总结

**控制面** 用 ring 索引 + kick/IRQ 协调请求与完成，**数据面** 则由 VMM 直接在 **Guest Buffers ↔ Disk** 之间搬运数据；virtqueue 从不承载数据本体。
