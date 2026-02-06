+++
date = '2025-12-24T17:17:50+08:00'
draft = true
title = 'Polaris 通信协议规范 (LSP v1)'
+++

# Polaris 通信协议规范 (LSP v1)

## 1. 物理层与连接

* **Socket 路径**: `/dev/socket/polaris_bridge`
* **Socket 类型**: `SOCK_STREAM` (可靠流式传输)
* **权限控制**: 仅允许 `system` 用户 (UID 1000) 读写。
* **字节序**: **Little Endian (小端序)** —— *Java 端必须显式处理转换*。

## 2. 封包结构 (Packet Structure)

所有通过 `polaris_bridge` 传输的数据包都必须遵循以下 **12字节定长包头 + 变长 Payload** 的格式。

```text
  0                   1                   2                   3
  0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
 +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
 |                        Total Length                           |
 +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
 |          Message Type         |            Reserved           |
 +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
 |                         Request ID                            |
 +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
 |                                                               |
 /                       JSON Payload (UTF-8)                    /
 /                   (Length = TotalLen - 12)                    /
 |                                                               |
 +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+

```

### 2.1 字段定义

| 字段名 | 偏移 (Offset) | 类型 (Type) | 长度 (Bytes) | 说明 |
| --- | --- | --- | --- | --- |
| **TotalLen** | 0x00 | `uint32_t` | 4 | **包总长**。等于 `12 + Payload长度`。接收端据此判断包是否完整。 |
| **MsgType** | 0x04 | `uint16_t` | 2 | **消息类型**。决定了 Payload 的 Schema 以及处理路由。 |
| **Reserved** | 0x06 | `uint16_t` | 2 | 保留字段，发送时填 0。用于对齐或未来扩展。 |
| **ReqID** | 0x08 | `uint32_t` | 4 | **请求 ID**。用于异步 Request-Response 匹配。<br>• App 发请求时自增。<br>• Daemon 回复时透传该 ID。<br>• 主动上报事件填 0。 |
| **Payload** | 0x0C | `bytes` | N | 业务数据，统一为 UTF-8 编码的 JSON 字符串。 |


## 3. 消息类型定义 (Message Types)

| Hex Value | Macro Name | 方向 (Direction) | 语义 (Semantics) | 路由逻辑 |
| --- | --- | --- | --- | --- |
| **0x0001** | `EVENT_REPORT` | Daemon -> App | **事件推送** | 包含 Native/Host/System 的所有聚合事件。 |
| **0x0020** | `CMD_REQ_HOST` | App -> Daemon | **Host 命令请求** | Daemon 不解析 Payload，直接封装 PLP 协议转发给 Linux Host。 |
| **0x0021** | `CMD_RESP` | Daemon -> App | **通用命令回执** | 包含 Local 执行结果或 Host 返回结果。通过 `ReqID` 匹配。 |
| **0x0022** | `CMD_REQ_LOCAL` | App -> Daemon | **本地命令请求** | Daemon 解析 Payload，由 `CommandExecutor` 在 Android 本地执行。 |

---

## 4. Payload 定义 (JSON Schema)

### 4.1 事件推送 (`EVENT_REPORT` - 0x0001)

由 `PolarisManager` 聚合后发给 App。

```json
{
  "event_id": 10001,           // 事件 ID (定义在 polaris_event.h)
  "timestamp": 1700000000123,  // 毫秒级时间戳
  "module": "audio_hal",       // (可选) 来源模块
  "payload": {                 // 原始业务数据
      "reason": "init_timeout",
      "retry_count": 3
  },
  // 如果有附件，ProtocolEncoder 会注入此字段
  "__attachment": {
      "type": "file",
      "path": "/data/local/tmp/trace_audio_20260205.pb"
  }
}

```

### 4.2 本地命令请求 (`CMD_REQ_LOCAL` - 0x0022)

App 请求在 Android 本地执行任务。

```json
{
  "action": "perfetto",        // 命令动作 (必须在白名单内)
  "args": {                    // 命令参数
      "duration_ms": 5000,
      "buffer_size_kb": 32768,
      "config": "default"
  },
  "timeout_ms": 10000          // 超时设置
}

```

### 4.3 Host 命令请求 (`CMD_REQ_HOST` - 0x0020)

App 请求转发给 Linux Host。Daemon **不感知** 具体内容，仅做透传。

```json
{
  "sub_system": "kernel",
  "command": "dump_slab",
  "params": { "filter": "kmalloc" }
}

```

### 4.4 通用命令回执 (`CMD_RESP` - 0x0021)

无论是 Local 还是 Host 命令，执行结束后都返回此格式。App 通过 Header 里的 `ReqID` 知道是哪个命令的结果。

```json
{
  "code": 0,                   // 0: 成功, 非0: 错误码/ExitCode
  "msg": "success",            // 可读状态信息
  "data": {                    // 执行产物 (可选)
      "output": "Process started...",
      "result_path": "/data/local/tmp/perfetto_trace.pb"
  }
}

```

## 5. 代码定义参考

### 5.1 C++ Header (`polaris_protocol.h`)

```cpp
#ifndef POLARIS_PROTOCOL_H
#define POLARIS_PROTOCOL_H

#include <stdint.h>

// 基础常量
constexpr uint32_t LSP_HEADER_SIZE = 12;
constexpr uint32_t LSP_MAGIC_RESERVED = 0x0000;

// 消息类型定义
enum LspMsgType : uint16_t {
    // Uplink: Daemon -> App
    EVENT_REPORT    = 0x0001, // 聚合事件
    CMD_RESP        = 0x0021, // 命令回执

    // Downlink: App -> Daemon
    CMD_REQ_HOST    = 0x0020, // 转发 Host
    CMD_REQ_LOCAL   = 0x0022  // 本地执行
};

// 协议头结构体 (Packed, Little Endian)
struct LspHeader {
    uint32_t total_len;  // Header + Payload
    uint16_t msg_type;   // LspMsgType
    uint16_t reserved;   // 0
    uint32_t req_id;     // Request Sequence ID
} __attribute__((packed));

#endif // POLARIS_PROTOCOL_H

```

### 5.2 Java 定义 (`PolarisProtocol.java`)

```java
public class PolarisProtocol {
    // Header Size
    public static final int HEADER_SIZE = 12;

    // Message Types
    public static final int EVENT_REPORT    = 0x0001;
    public static final int CMD_REQ_HOST    = 0x0020;
    public static final int CMD_RESP        = 0x0021;
    public static final int CMD_REQ_LOCAL   = 0x0022;

    // Helper to pack header (Little Endian)
    public static byte[] packHeader(int payloadLen, int msgType, int reqId) {
        ByteBuffer bb = ByteBuffer.allocate(HEADER_SIZE);
        bb.order(ByteOrder.LITTLE_ENDIAN); // 关键！
        bb.putInt(HEADER_SIZE + payloadLen);
        bb.putShort((short) msgType);
        bb.putShort((short) 0); // Reserved
        bb.putInt(reqId);
        return bb.array();
    }
}

```

## 6. 关键注意事项

1. **ReqID 生命周期**:
* App 发起 Request 时，必须生成全局唯一的 `ReqID`（建议使用 `AtomicInteger` 自增）。
* `polarisd` 在处理过程中必须全程携带此 ID。
* 当 `CMD_RESP` 返回时，App 根据 ID 找到对应的 Callback/Future 并结束。


2. **粘包处理 (TCP Stickiness)**:
* `polaris_bridge` 是流式 Socket。发送方发送两个包，接收方可能一次 `read` 读到 1.5 个包。
* **AppBridge** 和 **PolarisAgent** 都必须实现 **Buffer 缓冲机制**：
  1. 先读 buffer，看长度是否够 12 字节。
  2. 解析 Header 中的 `TotalLen`。
  3. 看 buffer 剩余数据是否够 `TotalLen - 12`。
  4. 如果够，切分出一个完整包；如果不够，继续 `read`。


3. **JSON 效率**:
   * 虽然 Payload 是 JSON，但为了性能，C++ 侧在合并附件路径时，应使用字符串拼接而非完整的 DOM 解析。
   * Payload 字符串不需要以 `\0` 结尾，长度由 Header 决定。