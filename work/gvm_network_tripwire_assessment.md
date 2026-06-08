# GVM 网络异常 —— "举旗"模块评估

> 定位:GVM 侧部署 `android_net_diag`,与 PVM `linux_net_diag` 经专用通道(channel A)**直连**。
> 端侧(双端进程)只做三件事:**异常监控、取证、事件上传** —— **不做归因**。
> 根因 / 业务影响 / 去重全部在云端。本模块不含 check / SHU / 因果图。

---

## 1. GVM 可能的网络异常清单(7 类 ~30 项)

### A. virtio 链路层 (L1/L2)
- A1 virtio-net 主接口 down(eth0)
- A2 VLAN 子接口 down(eth1.3/.4/.6/.7/.8)
- A3 链路 flap(短时间反复 up/down)
- A4 VLAN 子接口未创建 / 丢失
- A5 MTU 异常或与对端不一致
- A6 virtio 队列卡死(carrier 在,但 TX/RX 不过包)
- A7 接口 error/drop 计数器异常增长

### B. IP / 路由 / 邻居 (L3)
- B1 接口丢失 IP 地址(DHCP 续租失败 / 地址被删)
- B2 IP 地址冲突
- B3 默认路由缺失或被改
- B4 策略路由表(VLAN 6/7/8 的 table 106/107/108)缺失或错误
- B5 `ip rule` 缺失 —— VLAN 流量没进对应 table
- B6 网关 ARP 解析失败(邻居 INCOMPLETE / 网关 MAC 不可达)
- B7 邻居表出现 FAILED 条目

### C. DNS / 解析
- C1 DNS 解析失败(Android resolver,按 network 维度配置)
- C2 per-network DNS server 配置为空 / 错误
- C3 Private DNS (DoT) 配置异常
- C4 解析超时 / 间歇失败

### D. Android 框架裁决(ConnectivityService / netd)—— **仅 GVM 可见的核心信号**
- D1 默认网络意外切换
- D2 网络被判 `!VALIDATED`(Android validation / captive-portal 探测失败)
- D3 captive portal 被检出
- D4 完全无默认网络(Android 视角全断)
- D5 NetworkRequest 长期不被满足(App 请求的能力无人满足)
- D6 网络 capability 变化(丢失 INTERNET / 变 metered 等)
- D7 per-UID/App 网络被屏蔽(防火墙 / data saver / doze / restricted / VPN)
- D8 VPN 上线/掉线影响路由
- D9 tethering / 热点状态异常

### E. 进程存活
- E1 netd 崩溃 / 重启
- E2 resolver 异常
- E3 承载 ConnectivityService 的 system_server 异常(大故障)
- E4 vendor 网络守护进程异常

### F. 应用层 / 用户感知
- F1 App 主动报障(reportNetworkTrouble)
- F2 L7 假死:TCP ESTABLISHED 但下行无数据(payload 被 DPI 拦截,四层全 PASS 而用户感知断网)
- F3 单 App / 单 UID 的 socket 全失败而其它 App 正常

### G. 虚拟化 / GVM↔PVM 通路
- G1 GVM↔PVM 控制通路(Host-Guest)异常
- G2 virtio↔vmtap 不一致(GVM 侧看 up,PVM 侧 tap 异常)

---

## 2. 检测源(tripwire 监听什么)

| 检测源 | 覆盖异常 | 说明 |
|---|---|---|
| GVM netlink(LINK/ADDR/ROUTE/RULE/NEIGH) | A1-A7、B1-B7 | 事件驱动,捕捉瞬态;Java 侧可用 `ip monitor` 子进程或薄 JNI |
| `ConnectivityManager` NetworkCallback | C1、D1-D6、D8、D9 | Java/binder API,由 PolarisAgent 注册后转发给 `android_net_diag`(见 §7) |
| 进程存活 poll(5s) | E1-E4 | `kill(0)` / ps;system_server 异常另走高优先级 |
| resolver 状态查询 | C1-C4 | `dumpsys`/`ndc resolver` 取 per-network DNS 配置 |
| App 报障 API | F1 | 既有 reportNetworkTrouble 入口 |
| 被动 socket 启发式(可选) | F2、F3 | ESTABLISHED 多 + 重传涨 + 无 recv → 疑似;**仅举旗,确诊靠 PVM 抓包** |

> tripwire 自带**最小去抖**:同一异常 N 秒内只举一次旗、flap 合并成一次。这是唯一允许的本地逻辑,不算"诊断"。

---

## 3. 检测到异常后 —— Android 侧做什么

触发即采一份**轻量、只读**快照到 GVM 取证目录(秒级、低开销):

| 采集项 | 命令 / 来源 | 对应异常 |
|---|---|---|
| 连接态总览 | `dumpsys connectivity` | D 全类、C1 |
| netd / 防火墙 / per-UID | `dumpsys netd`、`ndc` | D7、E1-E2 |
| 链路+计数器 | `ip -s link`、`/proc/net/dev` | A1-A3、A7 |
| 地址 / 路由 / 规则 / 邻居 | `ip addr`、`ip route show table all`、`ip rule`、`ip neigh` | A4、B1-B7 |
| socket 表 | `ss -tunap` | F2、F3 |
| 解析配置 | resolver dump + 1-2 次测试解析 | C1-C4 |
| 网络属性 | `getprop`(net.* / vendor 网络相关) | 辅证 |
| 崩溃线索 | logcat ring(网络 tag,崩溃栈) | E1-E4 |

产出:`gvm_flag.json`(举的旗:异常分类、ts_boot/ts_unix、boot_id、初步证据指针、给 PVM 的补采清单)+ 上述原始输出文件,全部落在 **GVM incident 目录**。

---

## 4. Android 做不了的 —— 委托 PVM

GVM 无物理网卡、无 NAT、看不到对端,以下交 PVM:

| 委托项 | PVM 侧手段 | 服务于 |
|---|---|---|
| 物理网卡 / VLAN trunk 状态 | `ethtool`、物理 link 探测 | A1-A2、A5、G2 |
| vmtap 计数器(virtio 对端) | PVM netlink + `/proc/net/dev` | A6、G2 |
| NAT / filter / mangle 规则 | iptables/nft(只读) | D7 真因、B 段转发 |
| conntrack 表 + UNREPLIED 统计 | `/proc/net/nf_conntrack` | F2(上行通下行不通) |
| 物理/VLAN 抓包 | tcpdump 限时限包 | F2、A6 确诊 |
| 网关 / ECU 可达性 | PVM 视角 ICMP/路由 | B3、B6、D2/D4 真因 |
| 跨端关联 | PVM 合并双端快照 | 全部 |

委托方式见 §5 —— `android_net_diag` 经 channel A 给 `linux_net_diag` 发一条 flag 消息(incident id + 异常分类 + PVM 补采清单)。
**注意**:GVM 侧深状态由 `android_net_diag` 在 §3 **自采**,PVM 不反向驱动 GVM;`linux_net_diag` 只采自己这侧 + 读 GVM 取证文件。

---

## 5. 触发与回传 —— channel A 直连 + 共享挂载传文件

### 为什么保留 channel A

`linux_net_diag` ↔ PVM `polarisd` **只有单向通道**(diag→polarisd,仅 `report_event`,无反向)。
若没有 channel A,`linux_net_diag` 就**收不到**任何触发(GVM 举旗 / 云命令 / App 报障经 polarisd 都送不进来)。
所以保留 `android_net_diag ↔ linux_net_diag` 的**专用直连通道 channel A**,正是为了绕开 polarisd 单向限制。

### 三条通道职责

| 通道 | 物理 | 走什么 |
|---|---|---|
| **channel A** | VSOCK,`android_net_diag` ↔ `linux_net_diag` 直连 | flag 消息、云命令转发、小控制消息(**VSOCK + 小 JSON,非 NDGA 协议栈**) |
| 共享挂载 | GVM 写 / PVM 读,单向 | 批量取证文件(大文件不走 channel A,省掉分块协议) |
| 通道 C | `linux_net_diag` → PVM `polarisd`,单向 report | 事件 + tarball 上云 |

### 流程

```
GVM android_net_diag 监测到异常(或经 channel A 收到云命令 / App 报障)
  │ 1. 建 GVM incident 目录,自采全部 GVM 侧取证(§3 清单)→ 写共享挂载
  │ 2. 经 channel A 发 flag 消息给 linux_net_diag
  │    (incident id + 异常分类 + 取证路径 + PVM 补采清单)
  │ 3. 另发一条 polaris event 上云(仅"已举旗",report 方向)
  ▼
PVM linux_net_diag
  │ 4. channel A 收到 flag(直连,无 polarisd 单向问题)
  │ 5. 采 PVM 侧取证(NAT / conntrack / 物理链路 / 抓包 / ECU 可达)
  │ 6. 读共享挂载里 GVM 的取证目录
  │ 7. 合并 PVM + GVM 取证为单个 incident tarball + 单 manifest
  │ 8. 经通道 C 发事件 + tarball 上云
  ▼
归因在云端
```

### 要点
- **触发走 channel A** —— 实时、零轮询;`linux_net_diag` 不依赖 polarisd 收任何东西。
- **大文件走共享挂载** —— channel A 只传小消息,因此**不需要分块 / fetch_log 协议**。
- **PVM 不反向驱动 GVM 采集** —— GVM 取证由 `android_net_diag` 自采,channel A 只传 flag/通知。
- 端侧两个进程都只做 **监控 + 取证 + 上传,都不做归因**。最终交付物 = 一个 tarball + 一份 manifest。
- 云端要更多数据 → 下一轮:云命令经 channel A → `android_net_diag` 重新采。不需要任何反向 pull。

---

## 6. 边界 —— 端侧不做什么(不做归因)

| 不做 | 去哪做 |
|---|---|
| 78 项 check / 期望值比对 | 云端拿快照 diff 基线 |
| SHU 业务健康聚合 | 云端 |
| 因果图 / 根因推断 / incident 去重 | 云端 |
| 自研跨 VM 协议栈(NDGA:IDL / 分块 / session) | channel A 仅一个 VSOCK + 小 JSON 消息;大文件走共享挂载 |
| 在 GVM 打包 / 出云 | PVM 统一打 tar、出云 |
| 深度采集常驻 | 按需触发,不常驻深采 |

---

## 7. 落地形态与工作量

`android_net_diag` 是 GVM 上一个**专用进程**,只含四块,无归因相关代码:

| 子部分 | 内容 |
|---|---|
| 监控 | netlink 监听 + 进程 poll + (D 类)ConnectivityService 信号 + 最小 flap 去抖 |
| 取证 | 触发即跑 §3 的只读命令快照,写 GVM incident 目录 |
| 通信 | channel A 客户端(VSOCK,小 JSON);polaris event 上云 |
| 上传 | 取证文件落共享挂载,flag 经 channel A 通知 PVM |

> **D 类信号(ConnectivityService)是 Java/binder API。** native `android_net_diag` 拿不到 Java 层
> `NetworkCallback`,故由 PolarisAgent(常驻 Java 进程)注册回调后转发给它;netlink / 进程 poll /
> 命令快照,native 进程自己直接做。

对比原设计 `android_net_diagd`(自带 Bootstrap/Clock/Config、CommandRunner、AlertBuilder、
SnapshotPackager、NDGA client + fallback,号称 PVM 1/3 体量):**保留**独立进程 + channel A 直连,
**砍掉** NDGA 协议栈、跨端打包、配置体系,以及一切归因代码(check/SHU/因果)。净剩"监控+取证+通信+上传"。

---

## 8. 已知弱点(诚实标注)

- **F2(L7 假死)无法在 GVM 侧自动确诊** —— `android_net_diag` 只能靠 App 报障(F1)或被动 socket 启发式举旗,确诊必须靠 PVM 在物理/VLAN 口抓包看下行有无数据。四层全 PASS 类故障的固有难点。
- **D 类信号依赖 PolarisAgent 中转** —— native `android_net_diag` 拿不到 Java 层 `NetworkCallback`,需 PolarisAgent 注册后转发;多一个进程间跳,但换来 net_diag 不必写成 Java。
- **共享挂载用于大文件回传** —— channel A 只传小消息。若平台无 GVM→PVM 共享挂载,大文件改走 channel A 分块传(此时 channel A 才需一个最小分块封装);触发本身始终走 channel A,不受影响。
