## libpolaris_client 设计

### 接口定义

polaris_api.h
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