# Linux Host IPC 模块技术需求说明书

**版本**: v1.1
**日期**: 2026-02-10
**模块**: `src/transport/ipc`
**状态**: **已冻结 (Ready for Coding)**

---

## 1. 概述 (Overview)

IPC 模块是 `polarisd` 与 Linux 本地业务进程（Client）之间的通信桥梁。它基于 **Unix Domain Socket (SOCK_STREAM)**，采用 **Epoll Reactor** 模型。
v1.1 版本重点增强了 **生产环境适应性**，包括标准路径规范、优雅退出机制、发送流控（Backpressure）以及基础的安全审计能力。

### 核心组件

1. **IpcServer**: 负责 Socket 生命周期、连接监听、事件分发 (`epoll_wait`) 和 线程控制。
2. **ClientSession**: 负责单连接的数据缓冲、LSP 协议编解码、以及 `EAGAIN` 状态下的发送队列管理。

---

## 2. 详细功能需求 (Functional Requirements)

### 2.1 传输层规范 (Transport Layer)

* **Socket 类型**: `AF_UNIX` (Local Socket) / `SOCK_STREAM` (TCP-like)。
* **Socket 路径**: `/run/polaris/polaris_bridge.sock`
  * *理由*: 符合 Linux FHS 标准，`/run` 为 tmpfs (内存文件系统)，重启自动清理，且比 `/tmp` 更安全。

* **权限策略**:
  * **目录权限**: `/run/polaris/` 权限设为 `0755` (Owner: root, Group: root)。
  * **文件权限**: Socket 文件权限设为 `0666` (rw-rw-rw-)，允许任何用户进程连接（后续可通过 PeerCred 过滤）。

* **最大连接数**: 硬限制 **128** (超过此数值 `accept` 后立即关闭)。

### 2.2 生命周期管理 (Lifecycle)

1. **启动清理 (Stale Socket Cleanup)**:
   * 在 `bind()` 之前，**必须**调用 `unlink(SOCKET_PATH)`，防止因上次异常退出遗留文件导致 `EADDRINUSE` 错误。

2. **优雅退出 (Graceful Shutdown)**:
   * 引入 **`eventfd`** 作为唤醒机制。
   * `stop()` 函数向 `eventfd` 写入 uint64_t (1)，立即唤醒阻塞在 `epoll_wait` 的线程。
   * 退出时，需遍历所有活跃 Session，关闭 FD 并释放内存。

### 2.3 协议契约 (Protocol Contract)

* **编解码**: 严格使用 `LspCodec` (Header 12 Bytes, No Magic)。
* **最大帧限制**: 单个 Frame (Header + Payload) 最大 **2MB**。超过此大小视为恶意攻击，强制断开连接。
* **字节序**: Little Endian (Host Order on ARM64/x86).

---

## 3. 关键非功能需求 (Non-Functional Requirements)

### 3.1 健壮性与流控 (Robustness & Flow Control)

1. **发送端流控 (Outbound Handling)**:
   * **非阻塞发送**: Socket 必须设为 `O_NONBLOCK`。
   * **EAGAIN 处理**: `send()` 返回 `EAGAIN` 或 `EWOULDBLOCK` 时，**严禁**阻塞等待或丢弃数据。
   * **发送队列**: `ClientSession` 需维护 `std::deque<std::vector<uint8_t>> mOutboundQueue`。
   * **Epoll 联动**: 当队列非空时，向 Epoll 注册 `EPOLLOUT` 事件；当 Socket 可写时触发回调继续发送。


2. **背压策略 (Backpressure)**:
   * **接收侧**: 当全局 `MainEventQueue` 满（例如 > 2000 个待处理事件）时，IPC 线程应 **丢弃** 新收到的事件，并记录丢包统计（Rate-limited Log），防止 `polarisd` OOM。

3. **Broken Pipe 防御**:
   * 发送数据时必须使用 `send(fd, buf, len, MSG_NOSIGNAL)`，防止客户端突然断开导致 Daemon 收到 `SIGPIPE` 信号崩溃。

### 3.2 安全性 (Security)

1. **身份审计 (Peer Credentials)**:
   * 在 `accept()` 成功后，立即调用 `getsockopt(fd, SOL_SOCKET, SO_PEERCRED, ...)`。
   * 获取并记录客户端的 **PID (Process ID)**, **UID (User ID)**, **GID (Group ID)**。
   * *v1.1 暂不强制踢除非 root 用户，但必须在 Log 中记录连接者的身份。*



### 3.3 性能 (Performance)

* **内存复用**: 接收缓冲区使用 `std::vector` 的 `reserve/resize` 机制，避免频繁 `realloc`。
* **零拷贝**: 尽量减少数据搬运。

---

## 4. 接口设计 (Interface Design)

### 4.1 `ClientSession` 类设计

```cpp
class ClientSession : public std::enable_shared_from_this<ClientSession> {
public:
    ClientSession(int fd, int epollFd); // 注入 epollFd 以便注册 EPOLLOUT
    ~ClientSession();

    // --- 事件回调 ---
    // 返回 false 表示需要关闭连接
    bool onRead();  // 处理 EPOLLIN
    bool onWrite(); // 处理 EPOLLOUT
    
    // --- 业务接口 ---
    // 发送数据 (自动处理 EAGAIN)
    void send(const std::vector<uint8_t>& data);
    
    // --- 状态查询 ---
    int getFd() const;
    pid_t getPeerPid() const;
    uid_t getPeerUid() const;

private:
    // 处理 Outbound Queue
    void enableWriteEvent(bool enable);

private:
    int mFd;
    int mEpollFd;
    
    // 身份信息
    struct ucred mPeerCred; 

    // 缓冲区
    std::vector<uint8_t> mRecvBuffer;
    std::deque<std::vector<uint8_t>> mOutboundQueue;
    
    // 锁 (可选，如果确认 IpcServer 是单线程 Reactor，则不需要锁)
    std::mutex mQueueLock; 
};

```

### 4.2 `IpcServer` 类设计

```cpp
class IpcServer {
public:
    bool start();
    void stop(); // 线程安全，可从主线程调用

private:
    void threadLoop();
    void handleAccept();
    void handleWakeup(); // 处理 eventfd

    // Socket Setup Helper
    int createServerSocket();
    int createEventFd();

private:
    int mListenFd = -1;
    int mEpollFd = -1;
    int mWakeupFd = -1; // 用于优雅退出
    
    std::atomic<bool> mRunning{false};
    std::thread mThread;
    
    std::map<int, std::shared_ptr<ClientSession>> mSessions;
};

```

---

## 5. 数据流向 (Data Flow)

### 5.1 上行流程 (Event Reporting)

1. Client `send()` -> Kernel Buffer.
2. `epoll_wait` 唤醒 -> `IpcServer` 调用 `session->onRead()`.
3. `session` 读取数据 -> 追加到 `mRecvBuffer`.
4. `LspCodec::decodeFrame` 循环解包.
5. `LspCodec::decodeEvent` 反序列化为 `PolarisEvent`.
6. **流控检查**: 若 `EventQueue` 未满 -> `Push`. 若满 -> `Drop`.

### 5.2 下行流程 (Command Response)

1. 业务线程调用 `session->send(data)`.
2. `session` 尝试直接 `write`.
   * **Case A (Write 全部成功)**: 返回。
   * **Case B (Write 部分成功/失败 EAGAIN)**:
3. 将剩余数据 Push 到 `mOutboundQueue`.
4. 调用 `epoll_ctl(MOD)` 开启 `EPOLLOUT` 监听.
3. `epoll_wait` 唤醒 (Socket 可写) -> `IpcServer` 调用 `session->onWrite()`.
4. `session` 继续发送队列中的数据.
5. 若队列清空 -> 关闭 `EPOLLOUT` 监听.

---

## 6. 异常与错误码

| 错误场景 | 处理策略 | 日志级别 |
| --- | --- | --- |
| `accept` 返回 `EMFILE` | 进程 FD 耗尽，忽略本次连接，等待释放 | ERROR |
| `read` 返回 0 | 对端正常关闭 (FIN)，销毁 Session | INFO |
| `read` 返回 `ECONNRESET` | 对端 Crash (RST)，销毁 Session | WARN |
| `read` 返回 `EAGAIN` | 正常现象，退出读循环 | DEBUG |
| `write` 返回 `EPIPE` | Broken Pipe，销毁 Session | WARN |
| Frame Size > 2MB | 协议违规/攻击，立即销毁 Session | ERROR |

---