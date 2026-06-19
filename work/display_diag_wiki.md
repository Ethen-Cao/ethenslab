# display_diag 工作原理

## 概述

`display_diag` 是 PVM 平台上运行在 SOC Linux 侧的显示屏诊断守护进程。它对车载显示屏（中控屏、仪表屏、HUD 等）的硬件链路进行周期性健康检查，通过 I2C 读取桥接芯片（DS90UB983 等）的寄存器状态，将诊断结果通过 vsock 上报到 QNX Host 侧。

- **源码路径**: `layers/meta-voyah-bsp/recipes-products/owfds-misc/files/diag/display_diag/`
- **进程名**: `display_diag`
- **日志 TAG**: `[DISPLAY_DIAG_INFO]` / `[DISPLAY_DIAG_ERROR]`
- **上报通道**: AF_VSOCK → Host (CID=VMADDR_CID_HOST, port=10001)

---

## 架构

```
┌──────────────────────────────────────────────────────────┐
│                 display_diag Main Loop                    │
│                                                          │
│  for displayId in [central, cluster, hud, ...]:          │
│    for diagType in [CABLE, LINK]:                         │
│      if (enabled):                                        │
│        diag_detect_status() ──────────────────────┐       │
│          │                                        │       │
│          ├─ find_panel_cBridgeChipID()            │       │
│          │   parse XML to get bridge chip ID      │       │
│          │                                        │       │
│          ├─ find_bridge_library_name()            │       │
│          │   build .so path:                      │       │
│          │   /usr/lib/lib<chip>.so                 │       │
│          │                                        │       │
│          └─ call_dynamic_diag_func()              │       │
│               ├─ dlopen(libxxx.so)  ◄── dlopen    │       │
│               ├─ dlsym(func_diag)                 │       │
│               ├─ func_diag(diagType) ─────────┐   │       │
│               └─ dlclose()                     │   │       │
│                                                ▼   │       │
│                              ┌─────────────────────┐│       │
│                              │ Bridge .so diag func ││       │
│                              │ (DS90UB983 etc.)     ││       │
│                              │                     ││       │
│                              │  serdes_lock()      ││       │
│                              │  open(I2C bus)      ││       │
│                              │  check_i2c()        ││       │
│                              │  read port lock reg ││       │
│                              │  read vp sync reg   ││       │
│                              │  read CABLE/LINK    ││       │
│                              │  close(I2C)         ││       │
│                              │  serdes_unlock()    ││       │
│                              └─────────────────────┘│       │
│                                        │            │       │
│        display_diag_send_sync() ◄──────┘            │       │
│          └─ vsock_send() ──> QNX Host                │       │
└──────────────────────────────────────────────────────────┘
```

---

## 核心数据结构

### 显示屏枚举

```c
// display_def_type.h
typedef enum {
    DISPLAY_ID_CENTRAL = 0,   // 中控屏
    DISPLAY_ID_PASSAGER,      // 副驾屏
    DISPLAY_ID_CLUSTER,       // 仪表屏
    DISPLAY_ID_CEILING,       // 顶棚屏
    DISPLAY_ID_HUD,           // HUD
    DISPLAY_ID_ARP1,          // AR 屏 1
    DISPLAY_ID_ARP2,          // AR 屏 2
    DISPLAY_ID_DLP,           // DLP 屏
    DISPLAY_ID_MAX,
} DisplayIdType;
```

### 诊断类型枚举

```c
typedef enum {
    DISPLAY_DIAG_TYPE_CABLE = 0,  // 线缆诊断 (SAR ADC 故障检测)
    DISPLAY_DIAG_TYPE_LINK,       // 链路诊断 (FPD-Link 链路有效性)
    DISPLAY_DIAG_TYPE_MAX,
} DisplayDiagType;
```

### 诊断状态枚举

```c
typedef enum {
    DISPLAY_DIAG_STATUS_NORMAL   = 0,  // 正常
    DISPLAY_DIAG_STATUS_ABNORMAL,      // 异常
} DisplayDiagStatus;
```

### 显示屏诊断配置表

```c
// display_diag.c — 静态配置表
struct display_diag_info {
    const char *screen_name;                               // 屏名称
    const char *panel_name;                                // 对应的面板/桥接芯片标识
    const char *suffix;                                    // 诊断函数后缀 (_diag / _diag_sub)
    uint8_t     diag_enable;                               // 总使能开关 (由 XML 配置覆盖)
    uint8_t     diag_type_enable[DISPLAY_DIAG_TYPE_MAX];   // 每种诊断独立开关
    uint8_t     diag_status[DISPLAY_DIAG_TYPE_MAX];        // 当前诊断状态缓存
    uint8_t     diag_messages[DISPLAY_DIAG_TYPE_MAX][16];  // 诊断消息 (vsock 协议)
};

// 默认配置 (运行时可由 XML 覆盖 diag_enable)
struct display_diag_info diag_info_case[DISPLAY_ID_MAX] = {
    {"central",   "DP0_COMMON_MST1_OEM",   "_diag",     0, {CABLE=1, LINK=1}},
    {"passager",  "NULL",                  "_diag",     0, {CABLE=1, LINK=1}},
    {"cluster",   "DP3_COMMON_MST1_OEM",   "_diag",     0, {CABLE=1, LINK=0}},
    {"hud",       "DP3_COMMON_MST1_OEM",   "_diag_sub", 0, {CABLE=0, LINK=0}},
    // ...
};
```

**注意**: `diag_enable` 默认为 0 (DIAG_DISABLE)，运行时由 XML 配置 `Diag_display_<screen_name>` 动态开启。`cluster` 的 LINK 诊断默认关闭。

---

## 主循环：轮询调度

```c
int main(int argc, char **argv)
{
    // 1. 加载 XML 配置 → 覆盖 diag_enable
    display_diag_enable_from_cfg();
    
    // 2. 计算轮询间隔
    uint32_t total_enabled = 0;
    for (每个屏) {
        for (CABLE, LINK) {
            if (使能) total_enabled++;
        }
    }
    uint32_t sleepTimes = 3000 / total_enabled;  // 默认 3000ms 总周期
    if (sleepTimes < 200) sleepTimes = 200;       // 最小 200ms
    
    // 3. 解析 XML 一次，获取当前显示配置
    char *xml_name = find_display_current_xml();
    
    // 4. 主循环：Round-Robin 轮询
    DisplayIdType   displayId = 0;
    DisplayDiagType diagType  = 0;
    
    while (TRUE) {
        // 低功耗挂起检查
        if (diag_suspend_flag) { sleep(1); continue; }
        
        // DP 电源状态检查
        if (DP 未上电 || DP trigger 激活中) { sleep(1); continue; }
        
        // 执行诊断
        if (diag_enable && diag_type_enable) {
            uint8_t value = diag_detect_status(displayId, diagType, xml_name);
            // 更新消息并发送
            diag_messages[diagType][STATUS_OFFSET] = value;
            display_diag_send_sync(displayId, diagType);
        }
        
        // 推进到下一个 (displayId, diagType)
        if (++diagType >= MAX) { diagType = CABLE; displayId++; }
        if (displayId >= MAX)  { displayId = CENTRAL; }
        
        sleepMs(sleepTimes);
    }
}
```

### 轮询间隔计算示例

| 使能配置 | total_enabled | sleepTimes | cluster CABLE 检查间隔 |
|------|:---:|:---:|:---:|
| central(CABLE+LINK) + cluster(CABLE) | 3 | 1000ms | ~3000ms |
| 全部 6 项使能 | 6 | 500ms | ~3000ms |
| 仅 cluster(CABLE+LINK) | 2 | 1500ms | ~3000ms |

**当前运行配置下** `total_enabled=3`，每个屏的 CABLE/LINK 约 3 秒检查一次。但源码中 `sleepTimes = 3000 / total_enabled`（最小 200ms），间隔随使能项数动态变化。且 `sleepMs(sleepTimes)` 只在执行了使能项后才调用——如果某一项被跳过（diag_enable=0 或 type_enable=0），则不 sleep 直接推进到下一项，实际间隔会略小于计算值。

---

## 动态函数加载机制

```c
static int call_dynamic_diag_func(char *libname, char *funcname, DisplayDiagType diagType)
{
    void *handle = dlopen(libname, RTLD_LAZY);   // 动态加载 bridge .so
    diag_func_type diag_func = dlsym(handle, funcname); // 查找诊断函数
    int status = diag_func(diagType);             // 调用
    dlclose(handle);                              // 卸载
    return status;
}
```

### .so 路径和函数名拼接规则

源码：`display/driver/src/display_drv_utils.c:381` `find_bridge_library_name()`

```c
// libname  = "/usr/lib/lib" + cBridgeChipID + ".so"
// funcname = lowercase(cBridgeChipID) + suffix    // suffix = "_diag" 或 "_diag_sub"
strcat(libname, cBridgeChipID);
strcat(libname, ".so");
strcat(funcname, cBridgeChipID);
strLowerCase(funcname);
strcat(funcname, addfix);
```

**没有**再拼接 `_<panel>`。`cBridgeChipID` 本身已包含面板标识符（如 `ds90ub983_mst_clus888_hud47`），来自 XML 解析结果。

示例（cluster 的 CABLE 诊断）：
```
XML:      DP3_COMMON_MST1_OEM → cBridgeChipID = "ds90ub983_mst_clus888_hud47"
libname:  /usr/lib/libds90ub983_mst_clus888_hud47.so
funcname: ds90ub983_mst_clus888_hud47_diag      ← lowercase(cBridgeChipID) + "_diag"
```

---

## DS90UB983 桥接芯片诊断

### I2C 总线

| 参数 | 值 |
|------|-----|
| I2C 总线 | SEL_I2C_BUS（编译期宏定义） |
| SER 地址 | SEL_SERADDR |
| DES 地址 | SEL_DESADDR0 |

### 文件锁保护

```c
// 文件锁路径: /run/lock/ds90ub983_mst_clus888_hud47_i2c.lock
static int serdes_lock(void) {
    int fd = open(LOCK_PATH, O_RDWR | O_CLOEXEC);
    while (1) {
        if (flock(fd, LOCK_EX | LOCK_NB) == 0)  // 非阻塞排他锁
            return fd;
        sleepMs(50);  // 等待 50ms 后重试
    }
}

static void serdes_unlock(int lock_fd) {
    close(lock_fd);  // 关闭 fd 自动释放锁
}
```

诊断操作 (`_diag`) 和配置操作 (`_config`) 共用同一把锁。这确保了 I2C 访问的互斥，防止诊断读取与芯片配置同时操作总线导致状态混乱。

### I2C 通信验证

```c
static I2cStatusType check_i2c(int fd, uint8_t dev_addr) {
    for (int i = 1; i <= 3; i++) {        // 最多重试 3 次
        read_i2c(dev_addr, fd, 0x00, &val); // 读 DEVICE_ID 寄存器 (地址 0x00)
        if ((dev_addr << 1) == val)         // 验证: 读回值应等于 (设备地址 << 1)
            return SUCCESS;
        sleepMs(50);                        // 失败等 50ms 再试
    }
    return FAILED;
}
```

DS90UB983 的 DEVICE_ID 寄存器 (0x00) 在上电后返回 `I2C 地址 << 1`，用于验证 I2C 总线通信正常。

### 诊断函数: `ds90ub983_mst_clus888_hud47_diag()`

```c
uint8_t ds90ub983_mst_clus888_hud47_diag(DisplayDiagType diag_id)
{
    // 1. 获取文件锁
    int lock_fd = serdes_lock();
    
    // 2. 打开 I2C 总线
    int fd = open(SEL_I2C_BUS, O_RDWR);
    
    // 3. 验证 I2C 通信 (读 DEVICE_ID)
    check_i2c(fd, SEL_SERADDR);
    
    // 4. 读取 4 个状态寄存器（用于日志，不影响诊断结果）
    //    port0 lock:  写 0x2D=0x01, 读 0x0C
    //    port1 lock:  写 0x2D=0x12, 读 0x0C
    //    vp0 sync:    写 0x40=0x31, 0x41=0x30, 读 0x42
    //    vp1 sync:    写 0x40=0x31, 0x41=0x70, 读 0x42
    
    // 5. 执行诊断 (switch diag_id)
    switch (diag_id) {
        case DISPLAY_DIAG_TYPE_CABLE:
            // 读 SAR ADC LINE_FAULT0_FINAL 寄存器
            // 写 0x40=0x39 (SAR ADC page), 0x41=0x1D, 读 0x42
            // 判断:
            //   0x22 ~ 0x3D = NORMAL
            //   0x00 ~ 0x0A = 对地短路
            //   0x49 ~ 0x6A = 开路
            //   > 0xA9      = 对电源短路
            
        case DISPLAY_DIAG_TYPE_LINK:
            // 读 FPD-Link 链路状态寄存器
            // 写 0x2D=0x01 (port0), 读 0xC4
            // bit5 = 1 → 链路有效 (NORMAL)
            // bit5 = 0 → 链路无效 (ABNORMAL)
    }
    
    // 6. 关闭 I2C，释放锁
    close(fd);
    serdes_unlock(lock_fd);
    return diag_status;
}
```

### 寄存器详解

#### Port Lock Status (0x0C)

| 寄存器 | Port 选择 | 含义 |
|--------|:---:|------|
| 0x0C | 0x2D=0x01 (Port 0) | FPD-Link Port 0 接收锁定状态 |
| 0x0C | 0x2D=0x12 (Port 1) | FPD-Link Port 1 接收锁定状态 |

值 `0x53` 表示端口已锁定（DES 已与 SER 建立 FPD-Link 连接）。

#### VP Sync Status (0x42)

| 寄存器 | Page/Reg | 含义 |
|--------|:---:|------|
| 0x42 | Page 0x31, Reg 0x30 | Video Processor 0 同步状态 |
| 0x42 | Page 0x31, Reg 0x70 | Video Processor 1 同步状态 |

- `0x1`: VP 已同步到 DP 输入视频流
- `0x3`: VP 未同步

#### SAR ADC LINE_FAULT (CABLE 诊断)

| 寄存器 | Page/Reg | 含义 |
|--------|:---:|------|
| 0x42 | Page 0x39, Reg 0x1D | LINE_FAULT0_FINAL (Port 0 线缆故障检测) |
| 0x42 | Page 0x39, Reg 0x1F | LINE_FAULT2_FINAL (Port 2 线缆故障检测, 用于 HUD) |

SAR ADC 持续采样 FPD-Link 输出线的电压，判断线缆状态：

```
0x00 ───── 0x0A ─── 0x22 ═══════════ 0x3D ═══ 0x49 ───── 0x6A ─── 0xA9 ─────→
 对地短路         正常范围              开路           对电源短路
```

#### FPD-Link Link Status (0xC4, LINK 诊断)

| 寄存器 | Port 选择 | 位 | 含义 |
|--------|:---:|:---:|------|
| 0xC4 | 0x2D=0x01 | bit5 | Port 0 链路有效状态 |
| 0xC4 | 0x2D=0x12 | bit5 | Port 1 链路有效状态 |

---

## vsock 上报协议

### 消息格式

```
+────0────+────1────+────2────+────3────+──4──+──5──+──6──+──7──+──8~11─+──12──+──13~15──+
│  0x00   │  0x80   │  0xFF   │  0xFF   │ DTC │ DTC │ DTC │ DTC │ len=4 │status│ reserved │
└─────────┴─────────┴─────────┴─────────┴─────┴─────┴─────┴─────┴───────┴──────┴──────────┘
  └── fixed magic 0xFFFF8000 ──┘  └── DTC code (4B) ──┘  └ len ┘ └ stat ┘
```

| 偏移 | 大小 | 字段 |
|:---:|:---:|------|
| 0 | 4 | 标识符 `{0x00, 0x80, 0xFF, 0xFF}` (小端, 即 0xFFFF8000) |
| 4 | 4 | DTC 诊断码（每种屏+类型不同） |
| 8 | 4 | 数据长度（固定 4） |
| 12 | 1 | 诊断状态（0=NORMAL, 1=ABNORMAL） |
| 13 | 3 | 保留 |

### Cluster 消息模板

```c
// CABLE: DTC = 0x9F331F
{0x00, 0x80, 0xFF, 0xFF, 0x1F, 0x33, 0x9F, 0x00, 0x04, 0x00, 0x00, 0x00, 0x00, ...}

// LINK:  DTC = 0x9F334C
{0x00, 0x80, 0xFF, 0xFF, 0x4C, 0x33, 0x9F, 0x00, 0x04, 0x00, 0x00, 0x00, 0x00, ...}
```

### 长连接管理

```c
static int g_vsock = -1;  // 全局 vsock fd

static int vsock_send(uint8_t *msg, uint8_t len) {
    if (g_vsock < 0) {
        vsock_reconnect();  // 断线自动重连
    }
    // 循环发送直到全部发送完毕
    while (sent < len) {
        int n = send(g_vsock, msg + sent, len - sent, MSG_NOSIGNAL);
        if (n < 0 && (errno == EPIPE || errno == ECONNRESET)) {
            close(g_vsock); g_vsock = -1;  // 连接断开，下次重连
        }
        sent += n;
    }
}
```

### 日志节流

```c
// 每 3 次成功发送才打印一次日志，减少日志量
if (++p->diag_print_count[diagType] >= 3) {
    p->diag_print_count[diagType] = 0;
    LOGI("send ok: screen_name -> %s, diagType -> %s, value -> %s",
         p->screen_name, "CABLE/LINK", "NORMAL/ABNORMAL");
}
```

---

## 电源管理

```c
static int display_diag_suspend(void *ctx, enum PM_MODE mode) {
    diag_suspend_flag = TRUE;   // 暂停诊断
}
static int display_diag_resume(void *ctx, enum PM_MODE mode) {
    diag_suspend_flag = FALSE;  // 恢复诊断
}
```

通过 LPM (Low Power Manager) 注册 suspend/resume 回调。进入低功耗时暂停诊断（I2C 不可用），唤醒后恢复。

### 额外保护

```c
// DP 电源关闭 → 跳过诊断
if (get_dp_power_mode("/run/display-voyah/TRG_DP3S1/dppwr") != ON)
    skip;

// DP trigger 激活（模式切换中）→ 跳过诊断
if (get_dp_trigger_inactive("/run/display-voyah/TRG_DP3S1/active") != INACTIVE)
    skip;
```

这两种保护确保在显示屏未上电或正在进行模式切换（如分辨率变更）时不发起 I2C 诊断。

---

## 时序

### 诊断调用时序

```
                    3000ms 总周期 (total_enabled=3)
┌──────────────────────────────────────────────┐
│ central  │ cluster  │ central  │ central  │ ...
│  CABLE   │  CABLE   │   LINK   │  CABLE   │ 
│  1000ms  │  1000ms  │  1000ms  │  1000ms  │
└──────────────────────────────────────────────┘

当前运行配置下仅 central CABLE、central LINK、cluster CABLE 使能。
HUD 的 CABLE/LINK 均为 {0,0}，不会进入轮询队列。

### 单次 I2C 诊断耗时（估算）

以下为基于典型 I2C 速率（100kHz/400kHz）的**估算值**，非精确测量：

| 步骤 | I2C 操作 | 估算耗时 |
|------|:---:|:---:|
| dlopen + dlsym | — | ~1ms |
| serdes_lock (正常) | — | ~1ms |
| I2C open | — | ~1ms |
| check_i2c: 读 DEVICE_ID (0x00) | 1 read | ~1ms (成功) / +100ms (重试×2) |
| 读 port0 lock: 写 0x2D=0x01, 读 0x0C | 1 write + 1 read | ~2ms |
| 读 port1 lock: 写 0x2D=0x12, 读 0x0C | 1 write + 1 read | ~2ms |
| 读 vp0 sync: 写 0x40=0x31, 0x41=0x30, 读 0x42 | 2 writes + 1 read | ~3ms |
| 读 vp1 sync: 写 0x40=0x31, 0x41=0x70, 读 0x42 | 2 writes + 1 read | ~3ms |
| CABLE: 写 0x40=0x39, 0x41=0x1D, 读 0x42 | 2 writes + 1 read | ~3ms |
| 或 LINK: 写 0x2D=0x01, 读 0xC4 | 1 write + 1 read | ~2ms |
| dlclose + unlock | — | ~1ms |
| **正常总计** | **6 writes + 4 reads + 1 diag** | **~18ms** |
| **I2C 重试总计** | 同上 + check_i2c 重试 | **~118ms** |

**状态 dump 的 4 个寄存器（port0/port1 lock, vp0/vp1 sync）仅用于日志，总计 6 次 write + 4 次 read，约 10ms。**

---

## 覆盖场景和盲区

### 会触发 DTC/vsock 上报的异常（由 CABLE/LINK 诊断返回值决定）

源码：`DS90UB983_MST_CLUS888_HUD47.c:1039-1079`，`diag_id` 的 switch 分支

| 异常类型 | 诊断类型 | 检测寄存器 | 判定逻辑 | 检测延迟 |
|------|:---:|------|------|:---:|
| FPD-Link 线缆开路 | CABLE | SAR ADC LINE_FAULT0_FINAL (0x1D) | 0x49~0x6A | ~3s |
| FPD-Link 线缆对地短路 | CABLE | SAR ADC LINE_FAULT0_FINAL (0x1D) | 0x00~0x0A | ~3s |
| FPD-Link 线缆对电源短路 | CABLE | SAR ADC LINE_FAULT0_FINAL (0x1D) | >0xA9 | ~3s |
| FPD-Link 链路失效 | LINK | port0 reg 0xC4 bit5 | bit5=0 | ~3s |
| DS90UB983 芯片无响应 | — | check_i2c 失败 | — | ~3s |
| I2C 总线不可用 | — | open/read 失败 | — | ~3s |

### 仅打印日志、不触发 vsock 上报的状态寄存器

源码：`DS90UB983_MST_CLUS888_HUD47.c:1011-1036`，仅 `LOGI()` 打印，不参与返回值判断

| 寄存器 | 读取方式 | 作用 |
|------|------|------|
| port0 lock status (0x0C) | 写 0x2D=0x01, 读 0x0C | 仅日志记录，用于辅助调试 |
| port1 lock status (0x0C) | 写 0x2D=0x12, 读 0x0C | 仅日志记录，用于辅助调试 |
| vp0 sync status (0x42) | 写 0x40=0x31, 0x41=0x30, 读 0x42 | 仅日志记录，用于辅助调试 |
| vp1 sync status (0x42) | 写 0x40=0x31, 0x41=0x70, 读 0x42 | 仅日志记录，用于辅助调试 |

**`port lock status != 0x53` 或 `vp sync status != 0x1` 不会触发 vsock 上报 ALARM，也不影响 CABLE/LINK 的 NORMAL/ABNORMAL 判定。**

### 无法检测的异常

| 异常类型 | 原因 |
|------|------|
| **GPU 渲染黑帧** | 视频时序正常，桥接芯片全部寄存器正常 |
| **Unity HMI 显示空白 UI** | 同上有正常视频信号 |
| **背光故障** | 背光由独立电路控制，不经过桥接芯片 |
| **Panel 内部故障** | 不在 I2C 诊断范围内 |
| **1-2 秒瞬态黑屏** | 间隔 3 秒，大概率落在两次检查之间 |

---

## 配置文件

### XML 配置覆盖

```xml
<!-- 运行时通过 XML 配置开启/关闭诊断 -->
<Diag_display_central>true</Diag_display_central>
<Diag_display_cluster>true</Diag_display_cluster>
```

代码中通过 `find_display_config_value("Diag_display_cluster", &value, "false")` 读取，覆盖 `diag_enable` 字段。

### DP 状态文件

```
/run/display-voyah/TRG_DP0S1/dppwr    → DP0 (中控屏) 电源状态
/run/display-voyah/TRG_DP3S1/dppwr    → DP3 (仪表屏/HUD) 电源状态
/run/display-voyah/TRG_DP0S1/active   → DP0 trigger 状态
/run/display-voyah/TRG_DP3S1/active   → DP3 trigger 状态
```

---

## 提速轮询的风险分析

若将 cluster 诊断从 3s 提速到 500ms，需评估以下风险：

### 1. I2C 写 page/port selector 不是纯读

`ds90ub983_mst_clus888_hud47_diag()` 并非纯读操作。它会写入 `0x2D`（port select）、`0x40`/`0x41`（page/register select）这类索引寄存器，然后再读目标状态寄存器。这些是桥接芯片的间接寻址机制，写入 index 寄存器不会改变视频输出配置或 reset 链路。

### 2. I2C 竞争风险（外部进程）

`_config`、`_display_status`、`_diag` 三个入口都通过 `serdes_lock()` 获取同一把 `/run/lock/ds90ub983_mst_clus888_hud47_i2c.lock`（`flock` 排他锁），本库内部不会交叉踩寄存器。但如果系统中有**外部进程直接访问同一桥片 I2C 地址且不遵守这把 flock**，500ms 频率会提高 I2C 总线上 page/port selector 被互相覆盖的概率——读可能拿到错误寄存器的值，写可能写到错误目标。目前未发现此类外部进程。

### 3. 日志压力（最现实的瓶颈）

源码 `DS90UB983_MST_CLUS888_HUD47.c:1011-1036`：状态 dump 的 4 个 `LOGI()` **没有任何节流**，每次 diag 调用必定打印：

```c
LOGI("port0 lock status:0x%x\n", value);  // 无节流
LOGI("port1 lock status:0x%x\n", value);  // 无节流
LOGI("vp0 sync status:0x%x\n", value);    // 无节流
LOGI("vp1 sync status:0x%x\n", value);    // 无节流
```

对比 DTC vsock 上报有三级节流（`diag_print_count` 每 3 次才 syslog），状态日志完全裸奔：

| 轮询间隔 | cluster 日志量 | 全天估算 |
|:---:|------|:---:|
| 3s（当前） | ~1.3 行/秒 | ~11 万行 |
| 500ms | ~8 行/秒 | **~69 万行** |
| 200ms | ~20 行/秒 | ~173 万行 |

仅 cluster 一个屏。如果 central 也提速，syslog 存储压力和 I/O 抖动会成倍放大。

### 4. 误报风险

I2C 瞬时失败（总线忙、芯片偶发无响应）、DP power/trigger 状态切换边界、锁等待（config 和 diag 同时竞争）都可能导致单次 ABNORMAL。频率越高越容易捕获毛刺。**必须连续 N 次异常才上报 DTC**（建议 N=2~3，对应 1~1.5s 确认窗口）。

### 5. CPU/IO 开销

每次 diag 调用都执行 `dlopen()` → `dlsym()` → `diag_func()` → `dlclose()`，外加 vsock send。单次 ~18ms 中 I2C 占 ~13ms、dlopen/dlclose 占 ~2ms、vsock 占 ~1ms。如果只对 cluster 做 500ms，SoC 开销可忽略；如果全局改为 200ms 对所有屏，每秒额外 ~50+ 次 dlopen/dlclose。

### 6. 收益边界

提速只能在物理链路层更快发现 CABLE 断线/短路和 LINK 失效。仍然检测不到：

- Unity HMI 空白 UI（`UIDefault.prefab` 回退）
- GPU 渲染黑帧
- 背光电路故障
- Panel 内部故障

### 建议的落地策略

1. **cluster-only**：仅对 cluster 做独立快速轮询，不改 `DEFAULT_DIAG_INTERVAL_MS`，不动 central/hud 等其他屏
2. **日志节流**：port/vp status 的 4 行 `LOGI` 改为每 N 次或状态变化才打
3. **连续异常确认**：连续 2~3 次 ABNORMAL 才上报 DTC，避免 I2C 瞬态误报
4. **可观测性**：记录单次诊断耗时、lock wait 次数、I2C retry 次数
5. **24h soak**：上车前覆盖开关屏、DP mode switch、休眠唤醒、倒车/环视高负载场景

---

## 相关源码文件

| 文件 | 说明 |
|------|------|
| `diag/display_diag/src/display_diag.c` | 主程序：轮询调度、动态加载、vsock 上报 |
| `diag/display_diag/inc/display_diag.h` | 头文件：端口、偏移量、开关宏定义 |
| `display/driver/inc/display_def_type.h` | 公共类型定义：枚举、状态码 |
| `display/bridge/DS90UB983_MST_CLUS888_HUD47/src/*.c` | DS90UB983 桥接芯片驱动：I2C 配置、诊断函数 |
| `display/driver/src/display_drv_utils.c` | XML 解析、bridge .so 路径/函数名拼接 (`find_bridge_library_name`) |
| `display/driver/inc/display_drv_i2c.h` | I2C 读写封装 |
| `display/driver/inc/display_drv_utils.h` | 工具函数声明 |
