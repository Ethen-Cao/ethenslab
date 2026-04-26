+++
date = '2026-04-20T14:00:00+08:00'
draft = false
title = 'Android Guest DMA-buf 内存分配调查 (SA8397)'
tags = ["Android", "DMA-BUF", "Virtualization", "Gunyah", "Qualcomm", "Memory"]
+++

## 1. 背景与结论速览

本文回答一个问题：在 **PVM (Yocto Linux) + GVM (qcrosvm + Android Guest)** 架构的 SA8397 Cockpit 平台上，Android Guest 里的 **audio / video / camera / graphics** 子系统是否都使用 dma-buf，分别"分配了多大"。

结论：

1. 是的，四大子系统在 GVM 内部都走 **dma-buf** 框架，用户态通过 `/dev/dma_heap/*` 申请，跨 VM 传递使用 **HAB** 或 **virtio-mmio** 通道。
2. **大部分堆不是静态预分配**——`qcom,system` / `system` 等 system heap 是按需从内核 page allocator 取，上限就是 Guest 剩余可用内存；只有 **secure / QSEE / CMA** 型的 carveout 才在 device-tree 里有固定大小。
3. 本次取样（设备 `d7df5883`，处于运行中的座舱工况）GVM 内活跃 dma-buf 合计 **≈ 4.40 GB / 5922 个**，主要由 GPU (KGSL/HGSL) 占用。

## 2. GVM 中可用的 DMA Heap

GVM 的 Android 内核只暴露标准 `dma_heap` 接口（**没有** legacy ION，也**没有** `debugfs/dma_heap`）：

```text
$ adb shell ls /dev/dma_heap/
qcom,qseecom
qcom,qseecom-ta
qcom,secure-non-pixel
qcom,secure-pixel
qcom,system
qcom,system-uncached
system
system-secure
```

按来源分类：

| Heap 节点 | 类型 | 后端 | 典型使用者 |
|---|---|---|---|
| `qcom,system`, `qcom,system-uncached`, `system` | 动态 system heap | 内核 page allocator | 几乎所有非安全缓冲（图形、编解码、显示、音频共享页） |
| `qcom,secure-pixel`, `qcom,secure-non-pixel`, `system-secure` | secure heap | Hyp/TZ 划分的 secure carveout | DRM、受保护视频帧 |
| `qcom,qseecom`, `qcom,qseecom-ta` | QSEE carveout | `qseecom_region` / `qseecom_ta_region` | TZ 通信、TA 加载 |

## 3. Reserved-memory 中的静态 carveout

从 `/proc/device-tree/reserved-memory/` 读取 `size` 属性：

| 区域 | 大小 | 备注 |
|---|---|---|
| `linux,cma` | **32 MiB** (`0x02000000`) | 默认 CMA 池，`CmaTotal` 达到 **68 MiB** 说明另有 qseecom 相关 CMA 被合计 |
| `qseecom_region` | **20 MiB** (`0x01400000`) | QSEE 通信 |
| `qseecom_ta_region` | **16 MiB** (`0x01000000`) | TA 代码/数据 |
| `cp_pixel_region` / `cp_nonpixel_region` / `cp_b_pt_region` / `cp_np_pt_region` / `cp_p_pt_region` / `system_secure_region` / `soccp_fe_vm_1` | DT 无 `size` 节点 | 由 bootloader / Gunyah 运行时划分，大小非静态 |
| `buffer@b0xxxxxxx` × **62 项** | 每块起始 16 KiB | GVM ↔ PVM 的 virtio 共享内存窗口（首项地址从 `0xb00000000` 起） |

`/proc/meminfo` 摘录（GVM 总内存 ~34 GB）：

```text
MemTotal:   34705016 kB
MemFree:    16409172 kB
CmaTotal:      69632 kB
CmaFree:       57172 kB
Slab:         580144 kB
```

## 4. 活跃 DMA-buf 快照

数据来源：`/sys/kernel/debug/dma_buf/bufinfo`（29 501 行，804 KB）。

### 4.1 总量

**4398.7 MB** / **5922** 个 buffer。

### 4.2 按 exporter heap 分组

```text
qcom_hgsl             2334.5 MB   (5385 bufs)   ← KGSL/HGSL (GPU)
qcom,system           1307.8 MB   ( 336 bufs)
system                 756.4 MB   ( 196 bufs)
qcom,system-uncached     <1 MB   (   1 bufs)
qcom,qseecom             <1 MB   (   2 bufs)
msm_hab                  <1 MB   (   2 bufs)
```

### 4.3 按挂载设备（IOMMU / DMA master）分组

```text
soc:hgsl-iommu:gfx3d_user_0                        3379.5 MB  (5468 bufs)  ← GPU 渲染上下文
28027000.virtio-mmio                                367.9 MB  (  45 bufs)  ← 跨 VM virtio backend
aaa1000.qcom,vidc:non_secure_bitstream_cb           206.3 MB  (  28 bufs)  ← 视频比特流
soc:qcom,smmu_sde_unsec_cb@ae00000                  188.2 MB  (   6 bufs)  ← DPU/显示 (主屏)
aaa1000.qcom,vidc:non_secure_pixel_cb               152.0 MB  (  71 bufs)  ← 视频像素帧
aaa1000.qcom,vidc:non_secure_cb                      46.8 MB  ( 113 bufs)  ← 视频元数据/辅助
soc:qcom,smmu_sde_unsec_cb@8c00000                   45.8 MB  (  16 bufs)  ← DPU/显示 (副屏)
hab-aud                                              22.5 MB  (   3 bufs)  ← 音频 HAB 通道
hab-ogles                                             0.7 MB  (  56 bufs)  ← OpenGL ES HAB 通道
firmware:qcom_mem_object                              <1 MB   (   2 bufs)
```

### 4.4 Top 单个 buffer

```text
272 MB   system      ← 经 virtio-mmio 流转的超大帧/池
 67 MB   qcom_hgsl   ← GPU 堆
 56 MB   qcom_hgsl
 53 MB   qcom_hgsl × 多个
```

## 5. 按子系统对照

| 子系统 | dma-buf 路径 | 本次活跃占用 |
|---|---|---|
| **Graphics (GPU)** | GVM app → `libgsl`/KGSL → `qcom_hgsl` exporter → `gfx3d_user_0` → HGSL 转发到 PVM 的 Adreno | **3379 MB / 5468 bufs**（远超其它） |
| **Graphics (Display/SDE)** | SurfaceFlinger → DRM/SDE → `smmu_sde_unsec_cb` 双实例（主副屏） | 188 + 46 = 234 MB / 22 bufs |
| **Video (VIDC)** | libcodec2 → `aaa1000.qcom,vidc` 三种 CB（bitstream/pixel/通用） | 206 + 152 + 47 = 405 MB / 212 bufs |
| **Audio** | Audio HAL → `hab-aud`（3 块共享段，每块 ~7.5 MB） | 22.5 MB / 3 bufs |
| **Camera / Display 跨 VM 帧** | `28027000.virtio-mmio`（virtio-camera / virtio-gpu / virtio 音频 backend 的共享帧） | 367 MB / 45 bufs |
| **OpenGL ES 跨 VM 控制** | `hab-ogles` 命令通道 | 0.7 MB / 56 bufs |
| **QSEE / TA** | `qcom,qseecom` heap + `qseecom_region` 20 MB carveout | ~0 活跃 |

几点观察：

- **Camera 的帧数据不经过 Android 原生 camera HAL 的 dma-buf**，而是由 PVM 侧 Sensor 子系统产出后，通过 **virtio-mmio @ 0x28027000** 的共享缓冲导入 GVM，归入 `system` heap；这也是为什么 "camera" 在 `bufinfo` 里没有单独 exporter，需要在 `virtio-mmio` 计数里定位。
- **Audio 走 HAB**（`hab-aud` 3 个段 × ~7.5 MB），不走 virtio。
- **GPU 绝对大头**：HGSL 架构下，Guest 内核的 `qcom_hgsl` 只是影子 exporter，真实物理页来自系统内存；每个渲染上下文、纹理、FBO 都会产生 dma-buf，5000+ 个 buffer 绝大多数是 GL/EGL 对象。
- **没有独立 "camera heap" 或 "video heap"**：所有非安全分配都落到统一的 `qcom,system` / `system`，按需使用系统 RAM。

## 6. 关键澄清

"dma-buf 分配了多大" 这个问题必须分两层回答：

1. **静态容量层**：仅 secure / QSEE / CMA 型 carveout 有固定大小，合计大约 `CMA 32 MB + QSEE 20 MB + QSEE-TA 16 MB + 多个 cp_*_region（运行时划分）`。
2. **动态占用层**：system heap 按需分配，没有上限语义，只有实时用量。本次取样为 **≈ 4.40 GB**，其中：
   - GPU 占 77%（3380 MB）
   - 视频编解码占 9%（405 MB）
   - 跨 VM virtio 通道占 8%（368 MB）
   - 显示占 5%（234 MB）
   - 其它（音频/OpenGL HAB/QSEE）合计 < 1%

因此常见问题 "为什么 Guest 启动就少了几个 G" 的答案不在 dma-buf 预留——而在 GPU 运行时驻留、SurfaceFlinger 合成层、VIDC 解码池、以及 virtio backend 导入的 PVM 帧缓冲。

## 7. 复现命令

```bash
adb root
adb shell mount -t debugfs none /sys/kernel/debug   # GVM 默认未挂载

# dma-buf 实时快照
adb pull /sys/kernel/debug/dma_buf/bufinfo .

# 按 heap 聚合
awk '/^[0-9]/{sz=$1+0;heap=$5;bh[heap]+=sz;ch[heap]++}
     END{for(h in bh)printf "%-25s %9.1f MB  (%d bufs)\n",h,bh[h]/1048576,ch[h]}' bufinfo

# 按挂载设备聚合
awk '/Attached Devices/{in_dev=1;next}
     /^[0-9]+\t/{lastsz=$1+0;in_dev=0}
     in_dev && /^\t[^T]/{dev=$0;sub(/^\t/,"",dev);bydev[dev]+=lastsz;cntdev[dev]++}
     END{for(d in bydev)printf "%-55s %8.1f MB  (%d bufs)\n",d,bydev[d]/1048576,cntdev[d]}' bufinfo \
  | sort -k2 -nr

# Heap 清单
adb shell ls /dev/dma_heap/

# Carveout 尺寸
adb shell 'for n in linux,cma qseecom_region qseecom_ta_region; do
  printf "%-22s " $n
  od -An -tx1 /proc/device-tree/reserved-memory/$n/size | tr -d " \n"; echo
done'

# CMA / 内存水位
adb shell cat /proc/meminfo | grep -iE 'memtotal|memfree|cma|slab'
adb shell cat /sys/kernel/debug/cma/linux,cma/count   # 8192 × 4 KB = 32 MB
```

## 8. 调试技巧：如何监控 DMA-buf 泄漏

泄漏检测的核心思路是 **"快照差值 + 归因"**。本机 GVM 工具链齐全，推荐下面四层组合使用。

### 8.1 宏观：`bufinfo` 快照差值

`/sys/kernel/debug/dma_buf/bufinfo` 是 kernel 层最权威的 dma-buf 清单。在可疑场景前后采两份，对比 heap 维度的字节数和**条数**：

```bash
adb shell cat /sys/kernel/debug/dma_buf/bufinfo > t0.txt
# ... 跑用例 1 小时 / 反复切换相机 / 拉起关闭视频播放 ...
adb shell cat /sys/kernel/debug/dma_buf/bufinfo > t1.txt

for f in t0 t1; do
  echo "== $f =="
  awk '/^[0-9]/{bh[$5]+=$1;ch[$5]++}
       END{for(h in bh)printf "%-22s %8.1f MB  (%d)\n",h,bh[h]/1048576,ch[h]}' $f.txt
done
```

经验法则：

- 用例结束、设备静置 30 秒后，`qcom_hgsl` / `qcom,system` / `system` 仍**单调上涨**即为泄漏嫌疑。
- **条数**比字节更灵敏：泄漏的 buffer 往往个头不大，但数量不断累积。
- 关注斜率，不看绝对值——GPU 的 exporter 天然条数很多。

### 8.2 归因：`dmabuf_dump` 工具详解

`dmabuf_dump` 是 Android 自带的 dma-buf 审计工具，二进制位于 `/system/bin/dmabuf_dump`，源码在 AOSP `system/memory/libmeminfo/libdmabufinfo/tools/dmabuf_dump.cpp`。

它的能力来源于对三类内核接口的交叉关联：

1. `/sys/kernel/debug/dma_buf/bufinfo` —— 全局 buffer 清单（inode、size、exporter）
2. `/proc/*/fdinfo/*` —— 每个进程持有哪些 dma-buf fd（fd → inode 映射）
3. `/proc/*/maps` —— mmap 进地址空间的 dma-buf 段（计算 RSS/PSS）

#### 8.2.1 三种工作模式

```text
Usage: dmabuf_dump [-abh] [PID] [-o <raw|csv>]
```

| 调用 | 视角 | 典型用途 |
|---|---|---|
| `dmabuf_dump` | **按进程** 列每个进程持有的 buffer | 查某进程持有了什么 |
| `dmabuf_dump <PID>` | 单进程明细 | 聚焦可疑进程 |
| `dmabuf_dump -b` | **按 buffer** 列每条 dma-buf | 逐个 inode 清点 |
| `dmabuf_dump -a` | **buffer × process** 交叉表 | 查 buffer 被谁共享 |
| `-o csv` | 附加到上述任意模式 | 导入电子表格做 diff |

#### 8.2.2 模式一：默认（按进程聚合）

```text
surfaceflinger:1240
        Name              Rss              Pss         nr_procs   Inode    Exporter
   <unknown>             4 kB             4 kB              1        82   qcom_hgsl
   <unknown>          8192 kB          8192 kB              1        84   qcom_hgsl
   qcom,system        32128 kB         32128 kB              1       176   qcom,system
   qcom,system           28 kB            28 kB              1       177   qcom,system
   ...
 PROCESS TOTAL        388052 kB        388052 kB

dmabuf total: 4504628 kB  kernel_rss: 4116576 kB
              userspace_rss: 388052 kB  userspace_pss: 388052 kB
```

列含义：

- **Name**：buffer 名字。系统 heap 分配时 kernel 会自动写成 heap 名（如 `qcom,system`）；GPU 等 exporter 不命名时显示 `<unknown>`，此时只能靠 Exporter 识别。
- **Rss / Pss**：从 `/proc/<pid>/maps` 推算出的该进程对这块 buffer 的物理内存占用。**只反映"已 mmap 到用户态地址空间"的部分**。
- **nr_procs**：有多少个进程打开了这个 buffer——值 = 1 意味着独占，> 1 表示共享（典型是 SurfaceFlinger 与 App 共享 GraphicBuffer）。
- **Inode**：全局唯一的 dma-buf inode，与 `bufinfo` 的 `ino` 字段**完全一致**，是跨快照做 diff 的主键。
- **Exporter**：分配时的 heap 名（`qcom_hgsl` / `qcom,system` / `system` …）。

末尾统计：

- `dmabuf total`：kernel 视角的 dma-buf 总字节（≈ `bufinfo` 全部相加）。
- `kernel_rss`：仅内核持有、**未 mmap 到任何用户进程**的部分（VIDC/GPU firmware 内部用、跨 VM 还没 mmap 的帧等）。
- `userspace_rss`/`userspace_pss`：已映射到某个用户进程的部分。三者关系：`dmabuf total ≈ kernel_rss + userspace_rss`。

本次取样：总 4.5 GB，其中 **kernel-only 占 4.1 GB**（大部分是 GPU/VIDC 内核持有），用户态 mmap 的只有 388 MB——这是理解"Android 里 dma-buf 内存去哪了"的关键。

#### 8.2.3 模式二：`-b` 按 buffer 视角

```text
----------------------- DMA-BUF per-buffer stats -----------------------
    Dmabuf Inode |     Size(bytes) |    Exporter Name
            1976 |            8192 |        qcom_hgsl
            4070 |          131072 |        qcom_hgsl
            6265 |         5652480 |      qcom,system
```

只列 inode / size / exporter，**不带进程归属**——等价于 `bufinfo` 的瘦身版。适合做跨时间点的"哪些 inode 新增/消失"diff：

```bash
adb shell dmabuf_dump -b | awk '{print $1,$3,$5}' > t0.txt
# 等一段时间
adb shell dmabuf_dump -b | awk '{print $1,$3,$5}' > t1.txt
comm -13 <(sort t0.txt) <(sort t1.txt)   # t1 新增的 inode
```

#### 8.2.4 模式三：`-a` 交叉表

```text
    Dmabuf Inode |  Size |  Fd Refs | Map Refs | qseecomd:642 | ... | surfaceflinger:1240 | ...
              36 |  20 kB|        1 |        0 | 2(0) refs    | ... | --                  | ...
              41 |25920kB|        1 |        0 | --           | ... | 2(0) refs           | ...
```

每行一个 buffer，每列一个进程。单元格 `2(0) refs` 的含义：

- 左边数字 = **fd 引用计数**（进程持有多少个 fd 指向该 buffer）
- 括号里 = **mmap 引用计数**（mmap 进地址空间的次数）
- `--` = 该进程未持有

另外两列：

- `Fd Ref Counts`：该 buffer 的全局 fd 引用总数
- `Map Ref Counts`：该 buffer 在所有进程里被 mmap 的总次数

**判泄漏的关键**：`Fd Refs > 0 且 Map Refs = 0` 的 buffer——被某进程 fd 持有但从没映射使用过，往往是应用忘记 `close(fd)` 造成的残留。

#### 8.2.5 典型定位流程

场景：开关某 App 多次后 GVM 内存逐步下降。

```bash
# 1) 采基线
adb shell dmabuf_dump -o csv > t0.csv

# 2) 开关 App 50 次

# 3) 再采
adb shell dmabuf_dump -o csv > t1.csv

# 4) 哪些 inode 只出现在 t1（新增且未释放）
awk -F, 'NR>1{print $5}' t0.csv | sort -u > t0.ino
awk -F, 'NR>1{print $5}' t1.csv | sort -u > t1.ino
comm -13 t0.ino t1.ino > leaked.ino

# 5) 泄漏 inode 归哪个进程持有
grep -Ff leaked.ino t1.csv | awk -F, '{print $1,$2}' | sort | uniq -c | sort -rn
```

持有这批 inode 的进程就是泄漏者。再用 `dmabuf_dump <pid>` 查它都打开了哪些 buffer，结合 Name/Exporter 判断是 GraphicBuffer（图形）、codec2 pool（视频）还是其它。

#### 8.2.6 与其它工具的 inode 对照

同一个 dma-buf，在不同地方的编号**完全相同**，这是做调试的锚点：

| 位置 | 字段 |
|---|---|
| `dmabuf_dump` | `Inode` 列 |
| `/sys/kernel/debug/dma_buf/bufinfo` | 第 6 列 `ino` |
| `/proc/<pid>/fdinfo/<fd>` | `ino:` 行 |
| `/proc/<pid>/maps` | anon_inode dma_buf 段的 inode 号 |
| `lsof` | `NODE` 列（当 TYPE 为 DMABUF） |

锁定一个可疑 inode 后，用 `grep <ino> /proc/*/fdinfo/* 2>/dev/null` 即可反查是谁在持有。

### 8.3 进程侧：fd 数量与 mmap 段

dma-buf 在用户态以 fd 形式持有，直接数 fd 即可：

```bash
# 进程持有的 dma-buf fd 数
adb shell "ls -l /proc/<pid>/fd | grep -c dma_buf"

# 进程地址空间里 dma-buf 映射占用
adb shell showmap <pid> | grep -E 'dma_buf|total'

# 哪些进程打开了 heap 设备节点
adb shell lsof | grep dma_heap
```

周期性采样 fd 数量，如果呈线性增长就是泄漏进程。

### 8.4 内核 trace：抓"只分配不释放"

`dma-buf` 本身没有独立 trace point，但可通过 kprobe 挂钩 `dma_buf_export` / `dma_buf_release`，配合 `dma_fence:*` 一起抓：

```bash
cd /sys/kernel/tracing
echo 1 > events/dma_fence/enable
echo 'p:dmabuf_alloc dma_buf_export' >> kprobe_events
echo 'p:dmabuf_free  dma_buf_release' >> kprobe_events
echo 1 > events/kprobes/dmabuf_alloc/enable
echo 1 > events/kprobes/dmabuf_free/enable
echo 1 > tracing_on
cat trace_pipe        # 或 perf record -e kprobes:* -ag
```

对每个 inode 统计 `alloc - free`，长时间残留非 0 即是未释放对象。

### 8.5 长线监控脚本

建议把以下四个维度写进一个周期性采集脚本（分钟级），画成时序图一眼就能看出泄漏：

- `bufinfo` 每个 exporter 的**字节总数**和**条数**
- `/proc/meminfo` 的 `MemAvailable` / `CmaFree`
- 关键进程（SurfaceFlinger / cameraserver / mediaserver / hwcomposer / HGSL daemon）的 dma-buf fd 数
- `dmabuf_dump -b` 每 exporter 的 PSS 合计

稳态工况围绕定值波动；持续斜率 > 0 即可定位到所属子系统。

### 8.6 常见陷阱

| 现象 | 真实原因 | 定位方向 |
|---|---|---|
| `qcom_hgsl` buffer 数千条且持续缓慢增长 | GL/EGL 对象未释放（常见于自定义 SurfaceTexture / ImageReader 未 close） | `dumpsys SurfaceFlinger --dmabuf`、Java 层 `HardwareBuffer` 生命周期 |
| `28027000.virtio-mmio` 段持续增长 | **PVM 侧** virtio backend 泄漏，不是 Guest 的问题 | 同步抓 PVM 的 `bufinfo` 做差 |
| `hab-aud` / `hab-ogles` 条数膨胀 | HAB 会话未正常关闭 | 查对应 HAB client 的 `habmm_socket_close` 调用路径 |
| `CmaFree` 掉到很低但 `bufinfo` 总量正常 | CMA 碎片化 / qseecom 占用，非 dma-buf 泄漏 | `/sys/kernel/debug/cma/*/count` |

### 8.7 Android 框架层辅助命令

```bash
# SurfaceFlinger 视角的 GraphicBuffer 明细
adb shell dumpsys SurfaceFlinger --dmabuf

# 单个包的 GraphicBuffer / Gfx dev 内存
adb shell dumpsys meminfo <pkg>

# GPU 侧内存（HGSL / KGSL 账本）
adb shell cat /sys/kernel/debug/kgsl/proc/*/mem 2>/dev/null
```

框架层数据能补齐 "buffer 属于哪个 App / 哪个 Layer" 这一步，和 `bufinfo` 的 inode 级数据互为佐证。

## 9. 参考

- 图形链路详解见 [Android 图形渲染架构详解](graphics.md)
- 显示 virtio-HAB 数据通道见 [Android Guest 显示数据通道深度解析](display-virtio-hab-datapath.md)
- HAB 机制见 [HAB 通信机制](hab-communication-mechanism.md)
- Gunyah device-tree 约定见 [Gunyah Device Tree](gunyah_devicetree.md)
