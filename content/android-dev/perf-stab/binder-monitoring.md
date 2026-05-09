+++
date = '2026-05-09T00:00:00+08:00'
draft = false
title = 'Binder 监控方案 — 基于 AOSP 源码分析'
+++

## 1. Binder 空间耗尽时打印明细

### 现状

内核 binder 驱动在 buffer 满时打印 `cannot allocate buffer: no space left`，但不打印是谁占用了空间。用户态只能通过 `BINDER_GET_EXTENDED_ERROR` ioctl 拿到错误码。

**关键代码位置：**

| 文件 | 行号 | 说明 |
| :--- | :--- | :--- |
| `frameworks/native/libs/binder/IPCThreadState.cpp` | 1789-1805 | `logExtendedError()` 方法，已有错误日志：`Binder transaction failure. id: %d, cmd: %s, error: %d (%s)` |
| `frameworks/native/libs/binder/ProcessState.cpp` | 48 | buffer 大小 `BINDER_VM_SIZE = 1MB - 2*PAGE_SIZE` |

### 建议添加的监控位置

#### 内核侧

`drivers/android/binder_alloc.c` 中 `binder_alloc_new_buf()` 失败时，dump 该进程所有 pending transaction 的来源（`from_proc`/`from_thread`）和大小。可以遍历 `binder_alloc.buffers` 链表输出每个 buffer 的 `data_size`、`offsets_size`、目标 node 信息。

```c
// binder_alloc.c — binder_alloc_new_buf() 失败时新增 dump 逻辑
// 遍历 alloc->buffers 链表，输出每个已分配 buffer 的：
//   - data_size / offsets_size
//   - 目标进程 pid / 目标 node 的 ptr/cookie
//   - is_async 标记（区分同步/异步 buffer）
```

#### 用户态补充

在 `IPCThreadState::logExtendedError()` 中，当错误码为 `-28 (ENOSPC)` 时，额外读取 `/proc/self/fd/<binder_fd>` 或通过 debugfs `/sys/kernel/debug/binder/proc/<pid>` dump buffer 使用明细。

```cpp
// IPCThreadState.cpp — logExtendedError() 中针对 ENOSPC 的增强
if (error == -ENOSPC) {
    // 选项1：读取 /proc/self/fd/<binder_fd> 获取该进程的 binder 统计
    // 选项2：读取 /sys/kernel/debug/binder/proc/<pid>/ 下的 states 文件
    ALOGE("Binder buffer exhausted, dump pending buffers from debugfs");
}
```

---

## 2. Binder 线程耗尽

### AOSP 已有监控

| 机制 | 文件 | 位置 |
| :--- | :--- | :--- |
| 线程饥饿检测 | `IPCThreadState.cpp:747-768` | 当 `mExecutingThreadsCount >= mMaxThreads` 时记录饥饿开始时间，超过 100ms 打印 `ALOGE` |
| Watchdog 监控 | `Watchdog.java:449-458` | `BinderThreadMonitor` 调用 `Binder.blockUntilThreadAvailable()` |
| Native 阻塞等待 | `IPCThreadState.cpp:713-728` | `blockUntilThreadAvailable()` 打印 `Waiting for thread to be free` |

**默认配置：** `ProcessState.cpp:49` — `DEFAULT_MAX_BINDER_THREADS = 15`

### 建议增强

- 现有的 100ms 阈值可能太短（正常负载也会触发），但对长时间阻塞场景够用
- 可以在饥饿日志中额外打印每个 binder 线程当前在处理什么 transaction（interface descriptor + code）

```cpp
// IPCThreadState.cpp:747-768 线程饥饿检测增强
// 当 mExecutingThreadsCount >= mMaxThreads 时，额外遍历线程列表，
// 打印每个线程正在处理的：
//   - target descriptor（如 "android.app.IActivityManager"）
//   - transaction code（如 START_ACTIVITY_TRANSACTION）
//   - 已执行时长
```

---

## 3. Binder 耗时超过 3s 打印日志

### AOSP 已有的耗时统计框架

| 层级 | 机制 | 文件 |
| :--- | :--- | :--- |
| Native | BinderObserver | `BinderObserver.cpp:28-70` — `onBeginTransaction()` / `onEndTransaction()` 记录每次 transaction 的开始和结束时间 |
| Java 服务端 | BinderCallsStats | `BinderCallsStats.java:220-264` — 记录 CPU 时间和 wall time |
| Java 服务端 | BinderLatencyObserver | `BinderLatencyObserver.java:198-228` — 延迟直方图 |
| Java 客户端 | ProxyTransactListener | `BinderProxy.java:576-610` — `onTransactStarted()` / `onTransactEnded()` 回调 |

但这些都不直接打印日志，只是统计上报 statsd。

### 最佳注入点

#### Native 侧（服务端）

`IPCThreadState.cpp` 的 `doTransactBinder()` 方法（line 1719-1731），已有 `BinderObserver` 框架，可在 `onEndTransaction` 中加阈值判断：

```cpp
// IPCThreadState.cpp — doTransactBinder() 增强
BinderObserver::CallInfo callInfo = mProcess->mBinderObserver->onBeginTransaction(...);
status_t error = binder->transact(code, data, reply, flags);
int64_t duration = mProcess->mBinderObserver->onEndTransaction(mBinderStatsQueue, callInfo);
if (duration > 3000) {
    ALOGW("Slow binder transact(%d ms): %s code=%d", duration,
          String8(binder->getInterfaceDescriptor()).string(), code);
}
```

#### Java 侧（客户端）

`BinderProxy.java` 的 `transact()` 方法（line 541-617），在 `transactNative()` 前后加时间戳：

```java
// BinderProxy.java — transact() 增强
long start = SystemClock.uptimeMillis();
transactNative(code, data, reply, flags);  // line 599
long duration = SystemClock.uptimeMillis() - start;
if (duration > 3000) {
    Log.w(TAG, "Slow binder call: " + getInterfaceDescriptor() + " code=" + code
          + " took " + duration + "ms");
}
```

---

## 4. 其他值得监控的 Case

| Case | 说明 | 相关代码 |
| :--- | :--- | :--- |
| BinderProxy 对象泄漏 | 单进程 BinderProxy 超过 25000 个直接 crash | `BinderProxy.java:89` `CRASH_AT_SIZE = 25_000` |
| Oneway Spam | 内核检测到单向调用过多 | `IPCThreadState.cpp:1184-1188` `BR_ONEWAY_SPAM_SUSPECT` |
| DeadObject 频率 | 目标进程死亡导致的 `BR_DEAD_REPLY` 频率突增 | `IPCThreadState.cpp:1197-1199` |
| Frozen 进程通信失败 | 向冻结进程发送 transaction | `IPCThreadState.cpp:1205-1208` `BR_FROZEN_REPLY` |
| 同步 Binder 调用阻塞主线程 | `BinderProxy.mWarnOnBlocking` 机制 | `BinderProxy.java:546-563` 已有，但默认只 warn 一次 |
| Binder 异常传播 | 服务端抛异常但客户端无感知 | `BinderCallsStats.java:384-400` `callThrewException()` |
| 大 Parcel 传输 | 单次 transaction 数据量过大逼近 buffer 上限 | 内核侧可在 `binder_alloc_new_buf()` 中对 `data_size` 加阈值告警 |

### BinderProxy 对象数量监控建议

当前 `CRASH_AT_SIZE = 25_000` 太高，建议降低告警阈值，在 5000 时就开始 warn：

```java
// BinderProxy.java — 新增 warn 阈值
private static final int WARN_AT_SIZE = 5_000;

// 在 sProxyMap 中添加元素时检查
if (sProxyMap.size() >= WARN_AT_SIZE) {
    Log.w(TAG, "BinderProxy count=" + sProxyMap.size() + ", approaching crash limit");
}
```

---

## 5. 总结建议

按优先级排列：

| 优先级 | 监控项 | 实施位置 | 说明 |
| :--- | :--- | :--- | :--- |
| 1 | Binder buffer 满时 dump 占用明细 | 内核 `binder_alloc.c` | 需改内核，定位 buffer 耗尽问题最关键 |
| 2 | 同步 Binder 超时 >3s 打印 | `BinderProxy.transact()` / `doTransactBinder()` | 改动小，快速见效 |
| 3 | 线程饥饿持续时间 | `IPCThreadState.cpp:747-768` | 已有 100ms 阈值，加 3s 级别的更严重告警 |
| 4 | Oneway 积压数量 | 内核侧 | 对单个目标进程的 pending async transaction 数量加上限告警 |
| 5 | BinderProxy 对象数量 | `BinderProxy.java` | 降低告警阈值，5000 时就开始 warn |
