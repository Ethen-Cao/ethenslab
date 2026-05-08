# rpcd 设计与隐患分析

> 基于 HBEZ 仓库源码：`cluster/platforms/rpcd/`
> 关注两个外部接口：**rpcd ↔ MCU（SPI 物理通道）** 与 **rpcd ↔ upgrademcu（rpcif 客户端 IPC 通道）**。

---

## 1. 组件总览

```
┌──────────────┐  rpcif IPC (unix socket)   ┌─────────┐  SPI ioctl   ┌─────┐
│ upgrademcu   │ ─────────────────────────► │  rpcd   │ ───────────► │ MCU │
│ (rpcif client)│ ◄───────────────────────── │ (server)│ ◄─────────── │     │
└──────────────┘   subscribe/notify msg     └─────────┘ 768B/20ms    └─────┘
                                              ▲    ▲
                                              │    │ GPIO: ivi_spi_cs / ivi_spi_crc
                                              ▼    ▼
                                          /dev/spidev21.0 (Linux)
                                          /dev/spi9       (QNX)
```

| 角色 | 进程 | 主要源码 |
|------|------|----------|
| rpcd 服务 | 独立守护进程 | `src/rpcd_local.c` `src/rpcd_dispatch.c` `src/rpcd_mcu_spi.c` `src/rpcd_mcu_com.c` |
| rpcif 客户端 | 链接到业务进程（如 upgrademcu） | `src/rpcif.c` `inc/rpcif.h` `inc/rpcif-common.h` |
| 协议结构 | 共享头文件 | `inc/rpcd_local.h` |
| 帧 ID 白名单 | 编译期静态表 | `src/auto_gen_rx.c` `src/auto_gen_tx.c` |
| CRC16 工具 | CCITT 查表 | `src/rpcd_utils.c` |

---

## 2. rpcd ↔ SPI 交互设计

### 2.1 物理参数

| 项 | 值 | 来源 |
|----|-----|------|
| 设备节点 | `/dev/spidev21.0`（Linux） / `/dev/spi9`（QNX） | rpcd_mcu_spi.c L42, L51 |
| 模式 | Linux: `SPI_MODE_0`（CPOL=0, CPHA=0）；QNX: `SPI_MODE_CSHOLD_HIGH \| (0 << SPI_MODE_DEASSERT_WAIT_SHFT) \| 8`（自定义标志组合，等价 mode 0） | rpcd_mcu_spi.c L45-54 |
| 时钟 | 5 MHz | rpcd_mcu_spi.c L61 |
| 位宽 | 8 bit | rpcd_mcu_spi.c L62 |
| 主从 | SOC = master，MCU = slave | — |
| 双工 | Linux 走 `ioctl(SPI_IOC_MESSAGE(1))`（rpcd_mcu_spi.c L433），QNX 走 `spi_xchange()`（L380）；均单次同步收发 | rpcd_mcu_spi.c L375-444 |
| 节奏 | SPI 线程从消息队列取数发送（`spi_RecvFromMsgQue` 超时 500ms）；主循环 20ms 定时回调 `RPCD_LOCAL_MSG_20MS_INTERVAL` 触发入队（rpcd_local.c L733-738）。运行时强制：相邻发送间隔最小 10ms，最大 45ms | rpcd_mcu_spi.c L65-69, L505 |
| 单帧大小 | **768 字节**（header 3 + socdata 762 + tail 3） | rpcd_local.h L117-143 |

### 2.2 帧格式

```c
// inc/rpcd_local.h L140-143
typedef struct {
    uint8_t startCode;   // 0xA5
    uint8_t type;        // 0xA2 = SOC→MCU, 0xB2 = MCU→SOC
    uint8_t length;      // 固定 0xFA（250）
} SocMcuComHeader_t;

typedef struct {
    uint8_t crc16_low;
    uint8_t crc16_high;
    uint8_t tailCode;    // 0xAD
} SocMcuComTail_t;

typedef struct {
    SocMcuComHeader_t header;
    uint8_t           socdata[762];   // SPI_DATA_LENGTH，固定长度
    SocMcuComTail_t   tail;
} Soc2McuComMsg_t;
```

| 字段 | 字节 | 说明 |
|------|------|------|
| startCode | 1 | 帧头标识 0xA5 |
| type | 1 | 方向（0xA2 / 0xB2），高 4 bit 复用为长度高 4 位 |
| length | 1 | 表面是 1 字节（值固定 0xFA），实际形成 12-bit 长度的低 8 位 |
| socdata | 762 | 业务载荷，里面再封装 N 个 msg block |
| crc16 | 2 | 小端，仅覆盖 socdata 762 字节 |
| tailCode | 1 | 帧尾 0xAD |

> **长度字段双字节编码**（rpcd_local.c L439）：
> ```c
> ((header.type & 0xf0) << 8) | header.length
> ```
> 即长度被拆到 `type[7:4]` 和 `length[7:0]`，理论可表 12 bit。但实际所有帧长度恒为 762，编码逻辑形同虚设。

### 2.3 CRC16 算法

`src/rpcd_utils.c`：

| 项 | 值 |
|----|-----|
| 多项式 | 0x1021（CCITT） |
| 初始值 | 0xFFFF |
| 输出异或 | 0x0000 |
| 输入/输出反射 | 否 |
| 实现 | 256 项查表 |
| 覆盖范围 | **仅 socdata 762 字节，不包含 header 与 tail** |

### 2.4 收发线程模型

- 单线程 `mcuMainThread`（rpcd_mcu_spi.c L505）。
- 线程主循环阻塞在 `spi_RecvFromMsgQue(..., 500ms)`：等待主线程把待发送帧放入队列；20ms 节奏由 rpcd_local.c 主循环的定时回调入队驱动。
- 取到一帧后：
  1. 拉低 CS GPIO（`/dev/gpio/ivi_spi_cs/value`）
  2. 调用 `spi_transfer()`（Linux: `SPI_IOC_MESSAGE`；QNX: `spi_xchange`）同步发出 768B 并接收 768B
  3. 拉高 CS GPIO
  4. 校验返回帧的 startCode/type/length/tailCode/CRC
  5. 通过 `/dev/gpio/ivi_spi_crc/value` 读取 MCU 端 CRC 校验结果
  6. 调用 `spi_senddata2Listener` 把整帧推给主消息队列

### 2.5 GPIO 握手

| GPIO | 路径 | 用途 |
|------|------|------|
| CS | `/dev/gpio/ivi_spi_cs/value` | 每次传输前拉低、传输后拉高 |
| MCU 状态 | `/dev/gpio/ivi_spi_crc/value` | 读取 MCU 端校验结果（1=OK，0=Error） |

收到帧后会以 1ms 间隔最多轮询 10 次 MCU 状态 GPIO（rpcd_mcu_spi.c L609-623）。

### 2.6 SPI 层重试

```c
// rpcd_mcu_spi.c L584-643
xchange_retry = 2;          // 初值 2，最多发起 2 次 spi_transfer
while (xchange_retry > 0) {
    ret = spi_transfer(...);
    if (ret == 0 && 帧字段全部合法 && CRC OK) {
        // 成功路径：MCU 状态 GPIO 内层最多轮询 10×1ms
        // 状态 OK 时置 xchange_retry = 0 退出
    } else {
        usleep(5000); xchange_retry--;           // 帧错或 ioctl 失败
    }
}
```

外层最多发起 **2 次** SPI 传输（1 次原始 + 1 次重试）。MCU 状态 GPIO 的 10×1ms 轮询是单帧内部循环，不增加外层 `spi_transfer` 次数。

### 2.7 rpcd ↔ SPI 隐患

| # | 隐患 | 位置 | 影响 |
|---|------|------|------|
| **S1** | **无帧边界重同步**：每次传输期望恰好读到 768B，丢失任意一字节后续无法对齐；既不扫描 0xA5，也不丢字节后回退 | rpcd_mcu_spi.c L601-623 | 单 bit 翻转或时钟抖动可能导致 SOC/MCU 长期失同步，仅靠下次成功传输自然恢复 |
| **S2** | **CRC 不覆盖 header/tail**：仅校验 762B 载荷；startCode/type/length/tailCode 全部依赖字面比对 | rpcd_mcu_spi.c L246-255 | 头部位翻转无法被 CRC 检出；只能靠静态魔数判断，魔数恰好被破坏成有效值时静默通过 |
| **S3** | **重试耗尽后静默丢帧**：最终仍失败时 `spi_senddata2Listener(NULL, 0)`，仅打印 "spi send data error"，无错误码上报、无统计 | rpcd_mcu_spi.c L649-652 | 上层完全无法感知失败次数，故障难以定位 |
| **S4** | **GPIO 轮询阻塞 SPI 线程**：MCU 状态轮询最长占用 10ms；GPIO 设备挂死会让整线程卡住 | rpcd_mcu_spi.c L609-623 | 单次 GPIO 异常即可错过下一个 20ms 窗口，导致连续丢帧 |
| **S5** | **最小间隔违规直接跳过**：如果两次发送间隔 < 10ms，本次发送被丢弃，无重排队 | rpcd_mcu_spi.c L571-579 | 业务突发流量下数据被悄悄丢失 |
| **S6** | **CS/状态 GPIO 打开仅重试一次**：启动期 GPIO 不可用即长期失效 | rpcd_mcu_spi.c L524-535 | 启动竞态下 SPI 子系统永久不工作，无回退路径 |
| **S7** | **CRC16 强度不足**：未反射、无 final XOR，且只 16 bit。未对车控关键帧加二次校验 | rpcd_utils.c L14 | 多 bit 错误漏检概率 ≈ 1/2¹⁶ |
| **S8** | **payload 长度恒定 762B**：无变长帧，小消息也必须填 762B | rpcd_local.h L63 | 带宽利用率低；小指令延迟受满帧约束 |
| **S9** | **`g_spicomdata` 全局缓冲被复用**：声明为全局变量（L117），每个周期就地 memcpy，没有双缓冲 | rpcd_mcu_spi.c L117, L565 | 若分发回调同步重入，可能读到下一周期数据 |
| **S10** | **SPI 线程喂狗位置单一**：watchdog 注册在 L549，喂狗在 L668（循环末尾），ioctl/GPIO 阻塞期间无法喂狗 | rpcd_mcu_spi.c L549, L668 | 真正死锁时 watchdog 才生效，定位困难 |
| **S11** | **无握手/ACK 协议**：除底层 GPIO `ivi_spi_crc` 外，应用层无 NAK；丢帧依赖下一周期重新整体推送 | rpcd_mcu_spi.c | 单包重要命令（如重启）丢失即彻底丢失 |

---

## 3. rpcd ↔ upgrademcu (rpcif) 交互设计

### 3.1 IPC 通道

| 项 | 值 | 来源 |
|----|-----|------|
| 后端 | `ipc_backend_local`（Linux 抽象 unix domain socket / QNX 原生通道） | rpcif.c L373 |
| 服务名 | `"rpcsever"`（注：拼写为 sever 非 server） | rpcd_local.c L37 |
| 客户端名 | 调用 `rpcif_init`（L322）时传入，例如 `"upgrade"` | rpcif.c L322 |
| 调用模式 | **fire-and-forget async notify**，无请求-响应配对 | rpcif.c L654-679 |

### 3.2 客户端 API

```c
// inc/rpcif.h
int32_t rpcif_init(const uint8_t *pName,
                   Rpcif_CallbackInfo_t *pCbInfo, void *pContext);
int32_t rpcif_exit(void);
int32_t rpcif_subscribe_frames(uint32_t *frameArray, uint32_t frameNum);
int32_t rpcif_unsubscribe_frames(uint32_t *frameArray, uint32_t frameNum);
int32_t rpcif_update_clusterstate(uint32_t bus_id, uint32_t frame_id,
                                  uint32_t frame_dlc, uint8_t *frame_bytes);
```

回调：

```c
// inc/rpcif-common.h
typedef int32_t (*RPCIF_MSG_PROCESS_CB)(uint32_t bus_id, uint32_t frame_id,
        uint32_t frame_dlc, uint8_t *frame_bytes, void *pContext);
typedef int32_t (*RPCIF_WorkStateUpdate_CB)(Rpcif_WrokState_t enType,
        void *pContext);

typedef enum { RPCIF_ST_CONNECT, RPCIF_ST_DISCONNECT, RPCIF_ST_RECONNECT } Rpcif_WrokState_t;
```

WorkState 通过 IPC `connect/disconnect` 事件 + rpcd PID 文件监控（rpcif.c L155-166）触发。

### 3.3 会话表

```c
// inc/rpcd_local.h L210-214
typedef struct tagRPCD_SessionMgrInfo {
    Rpcif_FrameType_t canMsgId;
    uint32_t          unconditionalSend;
    Rpcd_Session_t    session[RPCD_MAX_SESSION_PER_MSG];   // 10
} Rpcd_SessionMgrInfo_t;

// rpcd_dispatch.c L9
static Rpcd_SessionMgrInfo_t g_RpcdSessionMgr[RPCIF_RX_MAX];  // 200
```

- 一个 frame_id 一个槽位，每槽最多 10 个 client。
- 订阅消息一次最多带 200 个 frame_id。
- 客户端断开（`rpcd_on_disconnected`）会按 channel 清理所有会话槽。

### 3.4 msg block 编码

`socdata[762]` 内由若干 msg block 拼接，单条编码（rpcd_local.c L617-737）：

| 偏移 | 字段 | 说明 |
|------|------|------|
| byte0[7:4] | channel | 0x1=业务帧；0x4/0x5=CAN0/1；0x8=LIN |
| byte0[3:0] + byte1 | length | 12-bit（业务） |
| byte1[7]（非业务通道） | 1=扩展帧 | — |
| byte2-3 / byte2-5 | frame_id | 16 或 32 位 |
| 后续 | payload | — |

业务通道 frame_id 范围举例：
- `0x4F01-0x4F0E`（SOC→MCU 升级命令）
- `0x8F01-0x8F0E`（MCU→SOC 升级响应）
- `0x8420 / 0x8421`（升级状态帧，做了**变化检测**才向 client 转发，rpcd_local.c L668-687）
- `0x83F1`（MCU 日志，直接打印不转发）

### 3.5 分发链路

```
SPI 收到 768B
  │
  ▼
rpcd_mcu_spi 校验 → spi_senddata2Listener
  │
  ▼
rpcd_local 主队列 → 按 channel 解析每个 msg block
  │
  ▼
disp_dispatchMessageToRpcif(frame_id, msg)
  │   遍历 g_RpcdSessionMgr 找到匹配槽
  │   遍历 session[10] 中 validFlag=ON 的 client
  ▼
ipcserver_send_notify(channel, msg)
  │
  ▼
[upgrademcu 进程]
ipcif_on_notify_data → rpcdif_message_process_notify
  │   拷贝 frame_bytes 到栈数组
  ▼
g_clientCallbackInfo.msgCb(bus_id, frame_id, dlc, frame_bytes, ctx)
```

### 3.6 update_clusterstate 路径

```c
// rpcif.c L654-679
RPCIF_LOCK();
msg.enMsgType = RPCD_LOCAL_V_MSG_UPDFRAMEDATA;
msg.frameDataInfo = { bus_id, frame_id, frame_dlc, ... };
memcpy(msg.frameDataInfo.frame_bytes, frame_bytes, frame_dlc);
ipcif_send_notify(g_ClientIpchandle, &msg, sizeof(msg));   // 异步
RPCIF_UNLOCK();
```

rpcd 收到后将其打包成 msg block 入下一帧 SPI 载荷。**不返回 MCU 是否实际收到的应答**——MCU 的 `0x8F0x` 响应通过订阅回调到达，跟当次发送在 API 层并无配对。

### 3.7 rpcd ↔ upgrademcu 隐患

| # | 隐患 | 位置 | 影响 |
|---|------|------|------|
| **R1** | **回调使用栈缓冲 → upgrademcu 实际已踩中**：`rpcdif_message_process_notify` 把 `frame_bytes` 拷到栈上局部数组再传给 client；client 若保存指针，函数返回即 use-after-free。upgrademcu 的 `MsgCallback`（upgrade_mcu.cpp L162-163）直接 `Event event{bus_id, franme_id, frame_dlc, frame_bytes}` **保存指针未拷贝**，后续在 `EventQueue.pop` 后 `*((uint8_t*)event.frame_bytes)` 解引用（L281/L327/L403/L463/L517）。当前依赖 IPC 线程到业务线程之间的栈帧未被覆写而表面工作 | rpcif.c L82-90, upgrade_mcu.cpp L162-163 | **典型 use-after-free**：状态字节是否正确完全取决于栈未被复用，存在偶发读取错误数据导致 OTA 误判失败/成功 |
| **R2** | **回调中调用 `rpcif_update_clusterstate` 死锁**：notify 投递回调时由 IPC 线程执行；若回调里再调发送 API，会再次抢 `RPCIF_LOCK`（rpcif.c L46-47, L661） | rpcif.c L46-47, L654 | upgrademcu 用 EventQueue 解耦了，但其它 client 容易踩中 |
| **R3** | **请求无应答**：`update_clusterstate` 是 fire-and-forget；既不知道 rpcd 是否成功打包，也不知道 MCU 是否收到 | rpcif.c L654-679 | 上层只能靠订阅 0x8F0x 响应帧并自己做超时（upgrademcu 用 3000ms / 重试 3 次），但若 rpcd 在打包阶段丢失，本次命令永远等不到响应 |
| **R4** | **session 满 10 后静默失败**：超过 `RPCD_MAX_SESSION_PER_MSG` 的订阅请求仅打印内部错误日志，不向 client 返回错误 | rpcd_dispatch.c L132-135 | 多 client 场景下后来者订阅永远收不到帧，client 侧无返回值告警 |
| **R5** | **订阅消息固定 200 项填充**：客户端要么发完整 200 项数组，要么 padding `CAN_INVALID_MSG_ID`；同时全量订阅会覆盖现有订阅顺序 | rpcif.c L526-552 | 内存浪费；增量订阅语义不明 |
| **R6** | **重连依赖 rpcd PID 文件监控**：rpcd 异常退出但 PID 文件残留时，client 收不到 RECONNECT | rpcif.c L155-166 | 一次脏退出后 client 永久"假连接"，所有发送返回 OK 但实际丢弃 |
| **R7** | **frame_dlc 无上限校验**：rpcd 主路径在解析 msg block 时按 length 字段直接 memcpy 入 `frame_bytes` 缓冲；upgrademcu 的命令侧 `MCU_DATA_FRAME_LENGTH` = 592，超过即缓冲溢出 | rpcd_local.c L688-695, rpcif.c L82-90 | 若 SPI 链路上出现 length 异常但 CRC 仍偶然通过（参 S2），可造成内存破坏 |
| **R8** | **回调串行执行 + 无超时**：IPC 库逐条投递，client 回调阻塞超过 20ms，下一帧的 MCU 数据将堆积在 IPC 队列中，最终触发队列满或丢帧 | rpcif.c L210-236 | upgrademcu 在回调里向 EventQueue.push（耗时极小）所以安全；其它阻塞型 client 直接劣化整链路 |
| **R9** | **session 槽错误清理时机不一致**：`rpcd_sendDataToClient` 失败即把对应槽置 OFF（一次失败永久踢出） | rpcd_dispatch.c L196-201 | 临时网络抖动会永久注销订阅，client 必须等下次重连才能恢复 |
| **R10** | **0x8420/0x8421 变化检测仅按内容比较**：相同状态被持续过滤，即使 MCU 真实周期上报；新订阅的 client 启动后只能等下次变化才有数据 | rpcd_local.c L668-687 | 上电启动期 client 拿不到当前状态快照 |
| **R11** | **服务名拼写错误（`rpcsever`）**：与官方"rpcserver"不一致，运维脚本/抓包工具易混淆 | rpcd_local.c L37 | 维护性问题 |
| **R12** | **rpcif_init 重复调用静默成功**：第二次 `rpcif_init` 返回 OK 但不做任何事 | rpcif.c L322-402 | 库式集成的进程难以重置上下文 |

---

## 4. 与 upgrademcu OTA 流程的耦合点

upgrademcu 通过 rpcif 与 MCU 通信（参见 [H56EZ_OTA_Architecture_Design.md](../../workspace/HBEZ/H56EZ_OTA_Architecture_Design.md) §6）。每个 OTA 命令都遵循：

```
rpcif_update_clusterstate(1, 0x4Fxx, len, payload)   ── async notify
        │                                              │
        ▼                                              ▼
   rpcd 打包 msg block                            EventQueue 等 0x8Fxx
        │                                              ▲
        ▼                                              │
   下一 20ms SPI 周期发出 ─► MCU ─► 0x8Fxx 响应 ──────┘
                                          (3000ms 超时，3 次重试)
```

OTA 链路实际承受了上述所有 SPI 与 IPC 隐患的复合：

| 触发条件 | 表现 |
|----------|------|
| SPI 单 bit 错误（S1/S2） | 当包响应丢失 → upgrademcu 走 3000ms 超时 → 触发 `goto resend` 重发同一数据包 → CRC 累加错误（OTA 文档 §6.2.3 已记录） |
| MCU GPIO 卡顿（S4） | 整 20ms 周期错过 → 数据包延后 20ms 到达 → 只要 < 3000ms 仍能成功 |
| rpcd 进程崩溃 + PID 残留（R6） | upgrademcu 持续 fire-and-forget，CRC 计算继续累加，最终 `send_mcu_flash_check` 失败，返回 -5 |
| 订阅槽溢出（R4） | 极端情况下并发其它 rpcif client 占满 0x8F01 的 10 槽，upgrademcu 收不到响应 → 全部命令超时 |
| 栈缓冲传递（R1） | **upgrademcu 未规避**：`Event` 直接持有 `frame_bytes` 指针，回调返回后栈失效；后续 `event.frame_bytes` 解引用为 use-after-free，状态字节读到的内容取决于栈被覆写的时机，可能误判 OTA 状态 |

---

## 5. 加固建议

### 5.1 SPI 链路

1. **接收侧加 startCode 扫描重同步**：失配时丢弃 1 字节再尝试，恢复对齐窗口。
2. **CRC 覆盖整帧**或为 header 单独追加校验。
3. **SPI 失败/丢帧暴露给上层**：增加错误码与计数器（`/proc` 或 sysmgr 上报）。
4. **GPIO 操作设硬超时**：使用非阻塞 read 或 select 防止线程独占。
5. **变长 payload 编码生效**：让 `length` 字段真正决定有效字节数，缩小小指令延迟。
6. **关键命令加 ACK 协议**：MCU 收到 `0x4F0B`（重启）等不可重放命令必须显式应答。
7. **双缓冲 / 队列化** `g_spicomdata`，避免回调与下一周期的并发访问。

### 5.2 IPC 链路

1. **回调缓冲改为堆分配 + 引用计数**或在文档中显式标注"不得保留指针"。
2. **`rpcif_update_clusterstate` 用递归锁**，或在回调线程上禁止持锁。
3. **session 满返回错误**（替换 `RPCIF_RET_FAILED`），让 client 能上报订阅失败。
4. **重连机制独立于 PID 文件**：心跳或 IPC 内置 keep-alive。
5. **frame_dlc 严格上界检查**（`<= sizeof(frame_bytes)`）。
6. **0x8420/0x8421 等周期帧首次订阅立即推送 last value**。
7. **修正服务名拼写**（`rpcserver`），同时保留兼容别名。

---

## 6. 关键文件索引

| 主题 | 文件 |
|------|------|
| 协议结构体（帧/会话） | [cluster/platforms/rpcd/inc/rpcd_local.h](../../workspace/HBEZ/cluster/platforms/rpcd/inc/rpcd_local.h) |
| rpcif 客户端 API | [cluster/platforms/rpcd/inc/rpcif.h](../../workspace/HBEZ/cluster/platforms/rpcd/inc/rpcif.h) |
| rpcif 公共定义 | [cluster/platforms/rpcd/inc/rpcif-common.h](../../workspace/HBEZ/cluster/platforms/rpcd/inc/rpcif-common.h) |
| SPI 主线程 | [cluster/platforms/rpcd/src/rpcd_mcu_spi.c](../../workspace/HBEZ/cluster/platforms/rpcd/src/rpcd_mcu_spi.c) |
| MCU 通讯抽象 | [cluster/platforms/rpcd/src/rpcd_mcu_com.c](../../workspace/HBEZ/cluster/platforms/rpcd/src/rpcd_mcu_com.c) |
| rpcd 主循环 / IPC 服务端 | [cluster/platforms/rpcd/src/rpcd_local.c](../../workspace/HBEZ/cluster/platforms/rpcd/src/rpcd_local.c) |
| 会话与帧分发 | [cluster/platforms/rpcd/src/rpcd_dispatch.c](../../workspace/HBEZ/cluster/platforms/rpcd/src/rpcd_dispatch.c) |
| rpcif 客户端实现 | [cluster/platforms/rpcd/src/rpcif.c](../../workspace/HBEZ/cluster/platforms/rpcd/src/rpcif.c) |
| 帧 ID 静态表 | [cluster/platforms/rpcd/src/auto_gen_rx.c](../../workspace/HBEZ/cluster/platforms/rpcd/src/auto_gen_rx.c) [cluster/platforms/rpcd/src/auto_gen_tx.c](../../workspace/HBEZ/cluster/platforms/rpcd/src/auto_gen_tx.c) |
| CRC16 实现 | [cluster/platforms/rpcd/src/rpcd_utils.c](../../workspace/HBEZ/cluster/platforms/rpcd/src/rpcd_utils.c) |
