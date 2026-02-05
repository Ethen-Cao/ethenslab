为了实现 **全域统一 (Universal Consistency)**，我们需要定义一个 **“标准数据契约 (Canonical Data Contract)”**。无论是在 Linux Kernel (Host)、Android Native (C++) 还是 Android Framework (Java)，大家都在操作同一个逻辑实体，只是在不同语言下的表现形式不同。

我们需要对之前的 C++ 定义进行升级，使其与 Java 层的定义 **严格对齐**。

---

### 1. 全域统一数据模型 (The Canonical Model)

这是所有层级必须遵守的“宪法”。

| 字段名 | 类型 (逻辑) | 语义说明 | 必填 |
| --- | --- | --- | --- |
| **eventId** | uint64 / long | 事件的唯一标识符 (全系统唯一 ID 表) | Yes |
| **timestamp** | uint64 / long | 事件发生的物理时间 (ms) | Yes |
| **pid** | int32 / int | 产生事件的进程 ID | Yes |
| **processName** | string | 产生事件的进程名/模块名 | Yes |
| **processVer** | string | 产生事件的进程的版本 | Yes |
| **params** | Map / JSON / Bundle | 具体的业务参数 (Key-Value) | No |
| **logf** | string | 关联的文件路径 (如 Trace, Log) | No |

---

### 2. 各层级的具体实现映射

为了达成你的目标，我们需要修改 C++ 层的结构体，使其字段与 Java 完全一一对应。

#### 2.1 C++ 定义 (Native & Daemon)

**修正点**：之前的 `PolarisEvent` 只有 `payload` (JSON)，现在我们将 `pid` 和 `processName` 提出来作为一级成员变量，与 Java 对齐。

```cpp
// include/polaris_event.h

struct PolarisEvent {
    // 1. 身份信息
    uint64_t eventId;
    
    // 2. 上下文信息
    uint64_t timestamp;
    int32_t pid;
    std::string processName;
    
    // 3. 业务数据 (对应 Java 的 Bundle)
    // 即使在 C++ 里，用 JSON String 存储 params 依然是最灵活的
    // 因为 C++ 没有类似 Bundle 的原生通用 KV 容器
    std::string paramsJson; 
    
    // 4. 附件信息
    std::string attachment;

    // 构造函数
    PolarisEvent(uint64_t id, int32_t p, std::string proc, std::string json)
        : eventId(id), pid(p), processName(std::move(proc)), 
          paramsJson(std::move(json)), timestamp(getCurrentTimeMs()) {}
};

```

#### 2.2 JSON 传输协议 (The Wire Format)

这是连接 C++ 和 Java 的桥梁。当 C++ 的 `ProtocolEncoder` 序列化上述结构体时，必须生成 **符合 Java 预期的 JSON 结构**。

**标准传输 JSON 格式**:

```json
{
  "eventId": 10001,
  "timestamp": 1707012345678,
  "pid": 520,
  "processName": "audio_hal",
  "params": {               <-- 对应 Java 的 Bundle
      "reason": "timeout",
      "retry": 3
  },
  "__attachment": "/data/local/tmp/trace.pb"
}

```

#### 2.3 Java 定义 (Android Framework)

保持你之前的定义不变，它现在完美对应了上面的模型。

```java
public class PolarisEvent implements Parcelable {
    public long eventId;        // <-> C++ eventId
    public long timestamp;      // <-> C++ timestamp
    public int pid;             // <-> C++ pid
    public String processName;  // <-> C++ processName
    public Bundle params;       // <-> C++ paramsJson
    public String logFilePath;  // <-> C++ attachment
    // ...
}

```

---

### 3. 数据构造策略 (Data Construction Strategy)

为了保证“全域统一”，不同的源头在生成事件时，必须负责填充这些标准字段。

#### 场景 A: Android Native 进程上报

* **源头**: `libpolaris_client`
* **动作**:
* `eventId`: 用户传入。
* `pid`: 调用 `getpid()` 自动获取。
* `processName`: 调用 `getprogname()` 自动获取。
* `params`: 用户传入的 JSON。
* `timestamp`: `clock_gettime()`。



#### 场景 B: Linux Host 上报

* **源头**: `HostIngestor` (在接收到 Host 数据时构造)
* **动作**:
* `eventId`: 映射 Host 的 ID。
* `pid`: 填 **0** 或 Host 侧的 PID (如 `kernel_pid`)。
* `processName`: 填 **"host_kernel"** 或 **"polaris_hostd"**。
* `params`: Host 传来的 JSON。
* `timestamp`: Host 传来的时间（需注意时钟同步）或收到时间。



#### 场景 C: polarisd 内部产生 (如 ResourceMonitor)

* **源头**: `ResourceMonitor`
* **动作**:
* `eventId`: `EVENT_SYS_RESOURCE`.
* `pid`: `getpid()` (即 polarisd 自己的 PID)。
* `processName`: **"polarisd"**。
* `params`: `{"cpu": 90}`。



---

### 4. 架构调整：序列化层的职责

为了支撑这个统一定义，我们需要更新 `ProtocolEncoder` (C++) 和 `ProtocolParser` (Java) 的逻辑。

#### C++ `ProtocolEncoder::encode` 的职责变更

以前它只是简单的拼接字符串，现在它需要**组装标准 JSON**。

```cpp
// 伪代码
std::string ProtocolEncoder::serializeJson(const PolarisEvent& event) {
    json j;
    j["eventId"] = event.eventId;
    j["timestamp"] = event.timestamp;
    j["pid"] = event.pid;
    j["processName"] = event.processName;
    
    // 解析 paramsJson 字符串并嵌入对象，而不是作为字符串
    // 这样 Java 端收到的是一个嵌套对象，可以直接转 Bundle
    j["params"] = json::parse(event.paramsJson); 
    
    if (!event.attachment.empty()) {
        j["__attachment"] = event.attachment;
    }
    
    return j.dump();
}

```

#### Java `LspProtocolParser` 的职责变更

Java 端解析代码变得更标准、更简单了，不需要再去扁平化遍历了。

```java
private static PolarisEvent parseJsonToEvent(String jsonString) {
    JSONObject root = new JSONObject(jsonString);
    
    PolarisEvent event = new PolarisEvent(root.getLong("eventId"));
    event.timestamp = root.getLong("timestamp");
    event.pid = root.optInt("pid");
    event.processName = root.optString("processName");
    event.logFilePath = root.optString("__attachment");
    
    // 直接提取 params 对象转 Bundle
    JSONObject paramsObj = root.optJSONObject("params");
    if (paramsObj != null) {
        event.params = jsonToBundle(paramsObj);
    }
    
    return event;
}

```

### 总结

通过这种方式，我们实现了真正的 **全域统一**：

1. **Host/Native/Java** 三端都在谈论同一个 `PolarisEvent`。
2. **Schema 强一致**：`pid`, `processName`, `timestamp` 在每一层都是一等公民。
3. **兼容性**：Java 端收到的永远是结构化良好的数据，而不需要去猜测 JSON 里哪些字段是 Metadata，哪些是 Params。