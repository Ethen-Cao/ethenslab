# Linux Host Client SDK (`libpolaris_client`) 技术需求说明书

**版本**: **v0.2**
**日期**: **2026-02-10**
**模块**: `src/client`
**状态**: **待实现 (To Be Implemented)**
**适用范围**: Linux Host 端业务进程（Cluster/IVI/T-Box 等）→ `polarisd`（UDS IPC）

---

## 订正历史 (Revision History)

| 版本       |             日期 | 订正人 | 订正摘要                                                                                                                                                                                                     |
| -------- | -------------: | --- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| v0.1     |     2026-02-10 | -   | 初版：定义 C API + Builder + 异步队列 + UDS 发送模型                                                                                                                                                                  |
| **v0.2** | **2026-02-10** | -   | **量产化修订**：对齐服务端 LSP 协议（12B Header / LE / msgType / reqId / MAX_PACKET）、明确投递语义（best-effort at-most-once）、补齐错误码与线程模型、完善队列容量/背压/重连退避、强化安全/权限与可观测性、明确 Init/Deinit 幂等与异常边界、修订 params 类型规范（推荐 Object）、补充测试验收要点 |

---

## 1. 概述 (Overview)

`libpolaris_client` 是一个 C/C++ 动态链接库 (`.so`)，供 Linux Host 端业务进程链接使用。其核心职责是将业务产生的事件、日志路径、性能数据通过 IPC 高效、稳定地发送给 `polarisd` 守护进程。

### 1.1 核心设计原则（量产标准）

1. **极低侵入性 (Low Intrusiveness)**
   SDK 的异常（内部错误、线程退出、连接失败、队列满）不得导致宿主进程崩溃或长时间阻塞；不得抛出异常穿透 C API。
2. **业务线程零阻塞 (Non-blocking for callers)**
   业务线程调用 `commit/report` 必须快速返回；不得等待 socket 可写、不得等待重连。
3. **懒加载且线程安全 (Thread-safe Lazy Init)**
   第一次 API 调用触发初始化，且多线程并发只允许初始化一次。
4. **可控资源与可观测 (Bounded & Observable)**
   内存/CPU/FD 使用必须有上限；必须提供 drop/重连等核心指标统计（至少内部计数 + 限频日志）。

### 1.2 投递语义（必须写清，避免误用）

* 默认语义：**Best-effort, at-most-once**

  * 队列满：丢弃（drop）
  * 断线：队列缓存到上限，满则丢弃
  * 不提供“必达/事务/确认”保证（未来如需可基于 `CMD_REQ/CMD_RESP + reqId` 扩展）

---

## 2. 架构设计 (Architecture)

采用 **生产者-消费者** 模型（业务线程生产、后台线程消费），由单例管理全局资源。

### 2.1 核心组件

1. **Facade Layer (C API)**：`polaris_api.h` 对外接口实现层
   * 参数校验、Handle 管理、错误码返回、异常边界保护（catch-all）
2. **ClientManager (Singleton)**：进程内单例
   * Init/Deinit（幂等）
   * 维护队列、后台线程、Transport
   * 维护统计指标（drop、重连、发送失败等）
3. **AsyncQueue（有界队列 + 字节预算）**
   * 建议实现为 **MPSC 队列 + 全局 byte budget**（更易实现变长 payload 的内存上限）
   * 队列满策略：立即丢弃并返回 `-EAGAIN`
4. **WorkerThread**（单线程即可）
   * 从队列取数据 → 通过 Transport 发送
   * 连接失败时执行退避重连
   * 无数据时阻塞等待（CV/eventfd/pipe 任一）
5. **Transport (UDS)**
   * 负责 connect / send（带 MSG_NOSIGNAL）
   * 负责断线检测与重连
   * 负责发送阻塞策略（非阻塞 + poll/timeout）

---

## 3. 功能需求 (Functional Requirements)

### 3.1 句柄与构建器 (Handle & Builder)

* **Opaque Handle**：`PolarisEventHandle` 映射到内部 `PolarisEventBuilder`（C++ 对象）。
* **自动填充**（SDK 内部完成）：
  * `process_name` 为空：读取 `/proc/self/comm`，并 **trim 末尾换行**；注意可能被截断（通常 15/16 字符级别），文档需提示调用方必要时传入更准确的业务进程名。
  * `timestamp_ms`：获取当前时间戳（ms）
  * `pid`：`getpid()`
* **JSON 库选择**：
  * 推荐与服务端一致：`jsoncpp`（减少 schema/序列化差异）
  * 或使用更轻量库（cJSON）但需确保线程安全使用方式（builder 对象私有，无共享全局 state）

> 约束：同一个 handle **不允许**多线程并发修改（builder 常识），但 SDK 对外需明确该约束并提供安全失败策略（见错误码与日志）。

### 3.2 异步发送 (Async Reporting)

* `polaris_event_commit`：
  * 在 commit 阶段完成序列化（形成 LSP Payload 所需 JSON 字符串）
  * 将序列化结果 push 到 `AsyncQueue` 后 **立即返回**
  * commit 后 handle 立即失效（SDK 内部释放）
* **队列满策略（硬约束）**：
  * 立即丢弃并返回 `-EAGAIN`
  * 丢弃必须计数（drop_count++），并限频日志（例如每 1000 次打印一次 warning）

### 3.3 IPC 通信 (Transport) —— **与服务端严格对齐**

#### 3.3.1 Socket
* `AF_UNIX` + `SOCK_STREAM`
* 地址：`/run/polaris/polaris_bridge.sock`（需可配置：环境变量/配置文件/编译宏三选一）
* SDK **不负责** unlink/chmod（避免误删服务端 socket）；权限不足时返回错误码并限频日志。

#### 3.3.2 协议：LSP v1（对齐服务端 `LspCodec`）
* **Header 总长度：12 bytes**
* **字节序：Little Endian**
* Header 结构：

| 字段       | 长度 | 描述                       |
| -------- | -: | ------------------------ |
| totalLen |  4 | 包总长度（含 Header + Payload） |
| msgType  |  2 | 消息类型（见下）                 |
| reserved |  2 | 保留字段，必须为 0               |
| reqId    |  4 | 请求 ID（事件上报为 0）           |

* `msgType`：
  * `EVENT_REPORT = 0x0001`
  * `CMD_REQ = 0x0020`（可选扩展）
  * `CMD_RESP = 0x0021`（可选扩展）
* `MAX_PACKET_SIZE`：**2MB（含 header）**，超出直接拒绝并丢弃该事件（返回 `-E2BIG` 或 `-EINVAL`，二选一但要写死）

#### 3.3.3 发送模型（量产化约束）

* 业务线程不发 socket；仅入队。
* WorkerThread 负责发送：
  * 推荐：socket 设置非阻塞，使用 `poll()` 等待可写，设置写超时（例如 50~200ms）
  * 若遇 `EAGAIN`：进入 poll 等待（不得 busy loop）
  * 若遇 `EPIPE/ECONNRESET/ENOTCONN`：断线 → 进入重连流程
* **SIGPIPE 防御**：所有 send 必须使用 `MSG_NOSIGNAL`

#### 3.3.4 自动重连（退避重试）

* `connect()` 失败或发送断线：进入重连退避
* 推荐参数（写死默认值，可配置）：
  * 初始退避：100ms
  * 指数退避：×2
  * 最大退避：5s
  * 加抖动：±20%（避免多进程同步风暴）
* 重连期间产生事件：按队列容量缓存，满则丢弃（drop）

### 3.4 附件处理 (Log Attachment)

* `log_path` 透传给 `polarisd`
* SDK 不读取、不上传文件内容
* SDK 只做轻量校验（可选）：
  * 为空允许
  * 长度上限（防止异常大字符串）
  * 不做 `access()` 检查（避免额外 I/O 与权限差异）

---

## 4. 非功能需求 (Non-Functional Requirements)

### 4.1 稳定性与安全性（关键）

1. **异常边界**
   * C API 入口必须 `try/catch(...)`，禁止异常穿透到宿主进程。
2. **线程安全声明**
   * Builder（同 handle）线程不安全：由调用方保证
   * `polaris_event_commit` / `polaris_report_raw`：**线程安全**（MPSC 入队）
3. **Init/Deinit 幂等**
   * Init 使用 `std::call_once/pthread_once` 确保只初始化一次
   * `polaris_deinit()` 可重复调用，不崩溃
   * Deinit 与并发上报：上报应安全失败并返回错误码（不 crash、不死锁）
4. **资源上限**
   * 队列必须有上限：`max_pending_bytes`（默认 4MB，可配置）
   * 单条 payload 必须有限制（对齐 `MAX_PACKET_SIZE`）
5. **权限与安全（与服务端策略对齐）**
   * 若服务端采用 SO_PEERCRED 白名单：文档需声明接入方需运行在允许的 UID/GID 下
   * SDK 不主动弱化安全（不 chmod 0666、不 unlink）

### 4.2 性能指标（可量化验收）

1. `commit/report_raw` 平均耗时 < 50us（仅内存拷贝、序列化、入队）
   * 注：序列化成本取决于 params 大小；建议对 payload size 给出推荐上限（如 8KB/16KB）并在超限时拒绝
2. 静态内存开销 < 2MB
3. 队列堆积最大内存 < 4MB（默认）
4. 后台线程空闲时必须阻塞等待（CV/事件驱动），CPU 占用接近 0

---

## 5. 数据结构定义

### 5.1 Event JSON Schema（建议写死）

**推荐格式（params 为 Object，量产更稳）**：

```json
{
  "eventId": 1001,
  "timestamp": 1770312345678,
  "pid": 1234,
  "processName": "hmi_app",
  "processVer": "v1.0",
  "params": { "cpu": 50, "mem": 1024 },
  "logf": "/tmp/crash.log"
}
```

> 兼容说明（可选）：若历史服务端仅支持 params 为字符串，可允许 `params` 为 stringified JSON，但 v0.2 默认推荐 Object，并在联调阶段完成服务端对齐。

---

## 6. 错误码规范（v0.2 新增，量产必须）

所有返回 `int` 的 API 统一使用如下约定：

|       返回值 | 含义                                            |
| --------: | --------------------------------------------- |
|         0 | 成功（已入队）                                       |
|   -EINVAL | 参数非法（NULL、空 key、json_body 非法等）                |
|   -ENOMEM | 内存不足（builder/序列化/入队分配失败）                      |
|   -EAGAIN | 队列满，事件被丢弃（drop）                               |
|    -E2BIG | 单条 payload 超过上限（> MAX_PACKET_SIZE 或 SDK 配置上限） |
| -ENOTCONN | （可选）不允许离线缓存且当前未连接（若采用该策略）                     |

> 说明：`polaris_event_add_*` 仍为 void（保持 v0.1 ABI），但 v0.2 要求内部对错误进行 **计数 + 限频日志**；建议 v0.3 再考虑升级为 `int` 返回。

---

## 7. 可观测性 (Observability)（v0.2 新增）

SDK 内部至少维护以下计数器（原子/无锁）并限频输出日志：

* `enqueue_count`
* `drop_count`（队列满/超限）
* `send_count`
* `send_fail_count`
* `reconnect_count`
* `last_errno`（最近一次 socket 错误）
* `pending_bytes`（当前队列占用字节）

> 可选扩展（不破坏 v0.1 ABI）：新增 `polaris_get_stats()` API 在 v0.2+ 作为增量接口。

---

## 8. 接口实现计划（保持，但补充量产实现约束）

1. `src/client/PolarisClient.h/cpp`

   * 单例、call_once init、队列（MPSC + byte budget）、worker、统计指标
2. `src/client/PolarisEventBuilder.h/cpp`

   * builder 存储字段与 params object、commit 阶段序列化
3. `src/client/Transport.h/cpp`

   * UDS 非阻塞、poll 超时、MSG_NOSIGNAL、指数退避重连
4. `src/client/polaris_api.c`

   * C ABI、参数校验、catch-all、错误码映射、懒加载触发

---

## 9. 对外接口定义（v0.2 保持 v0.1 ABI，补充行为定义）

> 下面接口签名保持不变；v0.2 的变化体现在：**错误码规范、线程语义、协议对齐、资源上限与 drop 统计**。

```cpp
/*
 * Copyright (C) 2024 Voyah Polaris Project
 *
 * Polaris Event Reporting SDK (C API)
 * Thread-safe, Lazy-initialized, Opaque Handle based design.
 *
 * Semantics (v0.2):
 * - Best-effort, at-most-once delivery.
 * - Caller thread MUST NOT block on IPC.
 * - All APIs return 0 on success, negative errno-style value on failure.
 */

#ifndef POLARIS_API_H
#define POLARIS_API_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

// ============================================================================
// 0. 返回值规范 (Return Codes)
// ============================================================================
// 0: success
// <0: failure, errno-style
//
// Recommended common errors:
// -EINVAL   invalid args / invalid handle / invalid state
// -ENOMEM   allocation failure
// -E2BIG    payload too large / key-value too large
// -EAGAIN   queue full -> dropped
// -ECANCELED handle already canceled
// -EALREADY  handle already committed / SDK already deinit
// -ENOTCONN (optional) policy disallows offline caching and not connected
//
// Note: We intentionally do NOT expose internal error strings here.
// Logging is rate-limited inside SDK.

#ifndef POLARIS_OK
#define POLARIS_OK 0
#endif

// ============================================================================
// 1. 类型定义 (Opaque Handle)
// ============================================================================

typedef struct PolarisEventBuilderInternal* PolarisEventHandle;

// ============================================================================
// 2. 事件构建流程 (Builder Pattern)
// ============================================================================

/**
 * [步骤 1] 创建事件构建器
 * - Lazy init: first successful call triggers SDK initialization.
 *
 * @param event_id       事件 ID (必填, >0)
 * @param process_name   逻辑进程名 (可选，NULL 则自动读取 /proc/self/comm)
 * @param process_ver    版本号 (可选，NULL 默认为 "unknown")
 * @param out_handle     [out] 返回 builder handle
 *
 * @return 0 on success; <0 on failure (errno-style)
 */
int polaris_event_create(uint64_t event_id,
                         const char* process_name,
                         const char* process_ver,
                         PolarisEventHandle* out_handle);

/**
 * [步骤 2] 添加 Key-Value 数据
 * - Builder is NOT thread-safe: same handle must not be mutated concurrently.
 * - On error, builder remains valid unless error indicates invalid handle/state.
 *
 * @return 0 on success; <0 on failure
 */
int polaris_event_add_string(PolarisEventHandle handle, const char* key, const char* value);
int polaris_event_add_int(PolarisEventHandle handle, const char* key, int32_t value);
int polaris_event_add_long(PolarisEventHandle handle, const char* key, int64_t value);
int polaris_event_add_double(PolarisEventHandle handle, const char* key, double value);
int polaris_event_add_bool(PolarisEventHandle handle, const char* key, bool value);

/**
 * [步骤 3] 提交发送
 * - Serializes the event and enqueues to AsyncQueue.
 * - After this call (success or failure), SDK will destroy the handle.
 *   Caller must NOT use handle anymore.
 *
 * @param handle    事件句柄
 * @param log_path  (可选) 附件路径（仅透传，不读文件）
 *
 * @return
 *  0        enqueue success
 * -EAGAIN   queue full -> dropped
 * -E2BIG    payload too large -> dropped
 * -EINVAL   invalid handle / invalid state
 * -ENOMEM   allocation failure
 */
int polaris_event_commit(PolarisEventHandle handle, const char* log_path);

/**
 * [可选] 取消发送
 * - Releases the builder without sending.
 *
 * @return
 *  0          success
 * -EINVAL     invalid handle
 * -EALREADY   already committed
 * -ECANCELED  already canceled
 */
int polaris_event_cancel(PolarisEventHandle handle);

// ============================================================================
// 3. 高级接口 (Raw JSON)
// ============================================================================

/**
 * 直接发送原始 JSON
 * - SDK will wrap it into the event schema and enqueue.
 * - Caller thread returns immediately.
 *
 * @param event_id      事件 ID
 * @param process_name  进程名 (可选，NULL 自动)
 * @param process_ver   版本号 (可选)
 * @param json_body     合法 JSON 字符串（UTF-8）
 * @param log_path      (可选) 附件路径
 *
 * @return 0 on success; <0 on failure (see return codes above)
 */
int polaris_report_raw(uint64_t event_id,
                       const char* process_name,
                       const char* process_ver,
                       const char* json_body,
                       const char* log_path);

// ============================================================================
// 4. 生命周期管理 (可选)
// ============================================================================

/**
 * 显式反初始化（幂等）
 *
 * Strategy A (recommended for low-intrusive):
 * - Stop worker thread, drop pending events, return 0.
 *
 * Strategy B (strict):
 * - If pending queue not empty, return -EBUSY unless caller sets "force".
 *
 * v0.2 default: Strategy A.
 *
 * @return 0 on success; <0 on failure
 */
int polaris_deinit(void);

#ifdef __cplusplus
}
#endif

#endif // POLARIS_API_H
```

---

## 10. 验证与验收（v0.2 新增）

### 10.1 功能验收

* 正常连接：持续上报 1h 无崩溃、无死锁、无内存泄漏
* polarisd 重启：SDK 自动重连；重连期间队列按预算堆积，满则 drop
* 队列满：业务线程 commit 不阻塞，返回 -EAGAIN，drop_count 增长正确

### 10.2 协议一致性验收

* 对齐服务端 LSP v1：12B header、小端、msgType=EVENT_REPORT、reqId=0
* payload 超限：SDK 返回 -E2BIG，且不会发出非法包

### 10.3 性能验收

* commit/report_raw 平均 < 50us（按典型 payload：1~4KB）
* 空闲 CPU 占用 ~0（worker 阻塞等待）

---
