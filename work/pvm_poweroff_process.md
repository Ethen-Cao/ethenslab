# PVM 系统关机流程实现说明

本文档基于 `voyahpm_bsp.c` 中的代码实现（已脱敏），描述系统关机的触发机制及其与系统底层服务的交互流程。

## 1. 关机机制概述

该模块的关机功能通过 **systemd D-Bus 接口** 实现。它并不直接操作硬件寄存器或内核系统调用，而是作为客户端向 `systemd-logind` 服务发起关机请求，由初始化系统（Init System）负责执行最终的硬件掉电流程。

## 2. 详细执行流程

关机流程主要由内部函数（原 `pm_pvm_systemd_poweroff`）完成，具体逻辑如下：

### 2.1 文件系统同步 (Sync)
在发起任何总线调用之前，代码首先执行 `sync()` 调用。
- **目的**：执行“最佳努力（Best-effort）”的文件系统缓冲区刷新，确保内存中未写入磁盘的数据尽可能同步，降低文件系统损坏风险。

### 2.2 建立 D-Bus 连接
使用 `sd-bus` 库建立与系统总线的连接。
- **调用**：`sd_bus_default_system(&bus)`。
- **作用**：获取指向系统 D-Bus 总线的句柄，用于后续通信。

### 2.3 发起关机请求（首选方案）
代码优先尝试调用 `systemd-logind` 的高级接口。
- **服务名**：`org.freedesktop.login1`
- **对象路径**：`/org/freedesktop/login1`
- **接口名**：`org.freedesktop.login1.Manager`
- **方法名**：`PowerOffWithFlags`
- **标志位**：`SD_LOGIND_ROOT_CHECK_INHIBITORS` (0x01)
- **含义**：该标志指示 `logind` 在关机时检查并遵循根用户的抑制符（Inhibitors）。

### 2.4 回退机制（兼容方案）
如果 `PowerOffWithFlags` 调用失败（通常是因为 target 系统上的 systemd 版本较低），代码将尝试使用传统的 `PowerOff` 方法。
- **方法名**：`PowerOff`
- **输入参数**：`0` (布尔值)
- **含义**：发起非交互式关机请求。

### 2.5 资源清理
无论调用成功还是失败，函数都会执行资源释放。
- 释放 D-Bus 错误对象 (`sd_bus_error_free`)。
- 释放总线引用句柄 (`sd_bus_unref`)。

## 3. 状态返回
- 如果 D-Bus 调用执行成功，返回 `STATUS_OK`。
- 如果在建立连接或调用方法过程中发生错误，将通过日志记录错误原因并返回 `STATUS_ERR_GENERIC` 或相关错误码。

## 4. 总结
该实现符合 Linux 通用标准，通过 `logind` 管理关机序列，确保了在切断电源前，系统服务能够接收到 `SIGTERM` 信号、文件系统能够被安全卸载。
