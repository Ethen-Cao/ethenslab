+++
title = 'PREEMPT_RT 下 AF_UNIX close() 与定时器超时的底层原理'
date = '2026-03-28T18:00:00+08:00'
draft = true
+++

## 一、背景

### 1.1 问题现象

在系统执行 OTA 升级期间，pmonitor 频繁报出多进程心跳超时（watchdog timeout），涉及 `3_ivcd`、`4_mcd`、`8_audiomgr`、`UPDATE_MAIN_MATRIX_01` 等多个进程。超时持续数秒，期间系统关键任务（看门狗喂狗、心跳上报）完全停滞。

### 1.2 系统环境

| 项目 | 说明 |
|---|---|
| SoC | Qualcomm SA8395P |
| 内核 | Linux PREEMPT_RT（实时抢占内核） |
| 存储 | UFS（Universal Flash Storage） |
| OTA 工具 | `zstdext`（基于 zstd 的差分解压工具，buffered I/O 写入块设备） |
| 看门狗 | pmonitor 心跳监控，超时阈值 3000ms |

### 1.3 根因概述

通过对 31GB ftrace 数据和 DLT 日志的深入分析，确认了两条独立但同源的失效路径：

**路径一：BH 锁饥饿（ivcd/mcd/audiomgr 超时）**

```
zstdext buffered write + fsync
  → 大量脏页集中回写到 UFS
  → UFS IRQ handler（irq/314-qcom-mc）在 irq_forced_thread_fn() 中持有 per-CPU BH 锁
  → handler 内部被 folio writeback 锁阻塞，BH 锁长达 ~5 秒不释放
  → watchdog 线程的 close() → unix_release_sock() → local_bh_disable() 被阻塞
  → 无法向 pmonitor 发送心跳 → 超时
```

**路径二：Soft hrtimer 延迟（updatemgr 超时）**

```
UFS I/O 密集导致 CPU 上 IRQ 线程高频运行
  → ktimers/N 线程虽然有 RT 优先级但 soft hrtimer 处理受干扰
  → SCHED_NORMAL 线程的 futex/select/poll 超时定时器（soft hrtimer）延迟数秒
  → 500ms 的 msgque_recv_wait 实际阻塞 5.5 秒
  → 看门狗喂狗间隔远超 1000ms 阈值 → 超时
```

**两条路径的共同触发源：zstdext OTA 刷写产生的密集 UFS I/O。**

### 1.4 zstdext 的 I/O 模式（源码分析）

OTA 刷写时 `updatemgr` 调用 zstdext 的命令格式：

```bash
zstdext --seg-size=256 -d --patch-from=/path/to/boot.patch /dev/zero -o=/dev/disk/by-partlabel/boot_b
```

从 `zstdext` 源码（`programs/fileio.c`）确认，每个 segment 的 I/O 序列为：

```
对于第 i 个 segment（当前 seg-size=256MB）：

① fseek(f, 256MB × i)                              // 定位到 segment 起始偏移
② fwrite(64KB zeros) × 4096 次 = 256MB 预填零       // buffered I/O，写入 page cache
③ fseek(f, 256MB × i)                              // 回到 segment 起始
④ 解压循环: fwrite(128KB) × ~2048 次 = ~256MB 解压数据  // buffered I/O
⑤ fsync(fileno(dstFile))                           // ← 触发所有脏页集中回写到 UFS
⑥ fclose(dstFile)
```

关键参数：

| 参数 | 来源 | 值 | 说明 |
|---|---|---|---|
| `seg-size` | OTA 包中 `zstd.segsize` 配置文件（编译期默认 128，实际配置为 256） | 256 (MB) | 每次 fsync 前累积的数据量 |
| 解压输出缓冲区 | `ZSTD_DStreamOutSize()` = `ZSTD_BLOCKSIZE_MAX` | 128 KB | 每次 fwrite 的大小，固定值 |
| 预填零块大小 | `fileio.c:708` 硬编码 | 64 KB | 块设备预填零的单次写入大小 |

**`seg-size` 直接决定了每次 `fsync()` 刷入 UFS 的脏页数量**：

| seg-size | 每次 fsync 脏页数 | 预填零 I/O 量 | fsync 触发频率 |
|---|---|---|---|
| 8 MB | ~2,048 | 8 MB | 高（每 8MB 一次） |
| 16 MB | ~4,096 | 16 MB | |
| 32 MB | ~8,192 | 32 MB | |
| 64 MB | ~16,384 | 64 MB | |
| 128 MB | ~32,768 | 128 MB | |
| 256 MB（当前） | ~65,536 | 256 MB | 低（每 256MB 一次） |

seg-size 越大，单次 fsync 的 I/O 风暴越猛烈，UFS IRQ handler 连续处理的 CQE 数量越多，BH 锁持有时间越长。

## 二、测试目的

1. **找到 `seg-size` 的最佳值**：在保证 OTA 刷写总耗时可接受的前提下，使 UFS IRQ handler 单次 BH 锁持有时间不超过 watchdog 超时阈值，消除心跳超时
2. **量化预填零的 I/O 开销**：评估去除块设备预填零后的性能提升
3. **验证 Direct I/O 替代方案的可行性**：评估改造 zstdext 为 Direct I/O 后能否从根本上消除 page cache writeback 路径的锁争用
4. **建立 UFS 硬件性能基线**：了解 UFS 的物理吞吐上限，为参数调优提供硬件约束参考

## 三、测试方法

### 3.1 测试一：zstdext seg-size 对系统实时性的影响（核心测试）

**原理**：使用真实 OTA patch 文件和目标分区，遍历不同 `seg-size` 值，通过 ftrace 监控 UFS IRQ handler 的 BH 锁持有时间和系统调度行为。

**脚本**：

```bash
#!/bin/sh
# ==========================================================================
# zstdext seg-size 调优测试
# 目的：找到不触发 watchdog timeout 的最大 seg-size（吞吐与实时性平衡点）
# ==========================================================================

# ============ 配置区域 ============
TARGET_PART="/dev/disk/by-partlabel/boot_b"      # 备用分区（确认为非当前启动分区！）
PATCH_FILE="/path/to/update/pvm/boot/boot.patch"  # 真实 OTA patch 文件
ZSTDEXT_BIN="/path/to/zstdext"                    # zstdext 二进制路径
SEG_SIZES="16 32 64 128 256"                       # 待测试的 seg-size 值（MB），256 为当前基线
TRACEFS="/sys/kernel/debug/tracing"

LOG_DIR="/tmp/zstdext_segtest_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$LOG_DIR"

echo "============================================"
echo "  zstdext seg-size 调优测试"
echo "  目标分区: $TARGET_PART"
echo "  测试 seg-size: $SEG_SIZES"
echo "  结果目录: $LOG_DIR"
echo "============================================"

# 检查分区是否挂载
if grep -q "$TARGET_PART" /proc/mounts; then
    echo "错误：$TARGET_PART 处于挂载状态，请先 umount！"
    exit 1
fi

# 表头
printf "%-10s | %-12s | %-15s | %-10s\n" \
    "seg-size" "耗时(ms)" "IRQ最长运行(us)" "WD超时"
printf '%0.s-' $(seq 1 55); echo

for seg in $SEG_SIZES; do
    # 清空 page cache
    sync
    echo 3 > /proc/sys/vm/drop_caches

    # 配置 ftrace：监控 sched_switch
    echo 0 > "$TRACEFS/tracing_on"
    echo > "$TRACEFS/trace"
    echo 128000 > "$TRACEFS/buffer_size_kb"     # 128MB ring buffer
    echo 1 > "$TRACEFS/events/sched/sched_switch/enable"
    echo 1 > "$TRACEFS/tracing_on"

    # 记录 UFS IRQ 计数（测试前）
    ufs_irq_before=$(grep -E "qcom-mc" /proc/interrupts \
        | awk '{sum=0; for(i=2;i<=NF;i++) sum+=$i; print sum}')

    # 运行 zstdext
    t_start=$(date +%s%N)
    "$ZSTDEXT_BIN" --seg-size="$seg" -d \
        --patch-from="$PATCH_FILE" /dev/zero \
        -o="$TARGET_PART" > "$LOG_DIR/zstdext_seg${seg}.log" 2>&1
    t_end=$(date +%s%N)
    elapsed_ms=$(( (t_end - t_start) / 1000000 ))

    # 停止 ftrace
    echo 0 > "$TRACEFS/tracing_on"
    echo 0 > "$TRACEFS/events/sched/sched_switch/enable"

    # UFS IRQ 计数（测试后）
    ufs_irq_after=$(grep -E "qcom-mc" /proc/interrupts \
        | awk '{sum=0; for(i=2;i<=NF;i++) sum+=$i; print sum}')
    ufs_irq_delta=$((ufs_irq_after - ufs_irq_before))

    # 保存 trace 快照
    cat "$TRACEFS/trace" > "$LOG_DIR/trace_seg${seg}.txt"

    # 从 trace 中提取 UFS IRQ 线程最长连续运行时间
    # irq/3xx-qcom-mc 在 sched_switch 中的运行时间差
    irq_max_us=$(awk '
        /irq\/[0-9]+-qcom-mc.*==>/ { # IRQ 线程被切出
            split($4, a, ".")
            t_out = a[1] * 1000000 + a[2]
            if (t_in > 0 && t_out > t_in) {
                d = t_out - t_in
                if (d > max) max = d
            }
        }
        /==>.*irq\/[0-9]+-qcom-mc/ { # IRQ 线程被切入
            split($4, a, ".")
            t_in = a[1] * 1000000 + a[2]
        }
        END { printf "%d", max }
    ' "$LOG_DIR/trace_seg${seg}.txt")

    # 检查是否有 watchdog timeout（从 zstdext 运行期间的 dmesg/dlt）
    wd_timeout="No"
    if dmesg | tail -200 | grep -qi "watchdog.*timeout"; then
        wd_timeout="YES"
    fi

    printf "%-10s | %-12s | %-15s | %-10s\n" \
        "${seg}MB" "${elapsed_ms}" "${irq_max_us}" "$wd_timeout"

    # 记录详细信息到日志
    cat >> "$LOG_DIR/summary.log" <<EOF
seg-size=${seg}MB:
  耗时: ${elapsed_ms} ms
  UFS IRQ 增量: ${ufs_irq_delta}
  IRQ handler 最长运行: ${irq_max_us} us
  Watchdog timeout: ${wd_timeout}

EOF

    # 等待 UFS GC 和系统恢复
    sleep 5
done

echo ""
printf '%0.s-' $(seq 1 55); echo
echo "测试完成！详细结果: $LOG_DIR/summary.log"
echo "Trace 文件: $LOG_DIR/trace_seg*.txt"
echo ""
echo "分析要点："
echo "  1. 找到耗时可接受且 WD超时=No 的最大 seg-size"
echo "  2. 在对应 trace 中确认 IRQ handler 单次运行 < 500ms"
echo "  3. 该值即为推荐的 --seg-size 参数"
```

**观测指标**：

| 指标 | 获取方式 | 判定标准 |
|---|---|---|
| OTA 总耗时 | 脚本计时 | 不超过当前方案耗时的 1.5 倍 |
| UFS IRQ handler 最长连续运行时间 | ftrace sched_switch 时间差 | < 500ms（watchdog 阈值的一半） |
| 是否触发 watchdog timeout | dmesg / DLT 日志 | 无超时 |
| UFS IRQ 总次数 | `/proc/interrupts` 差值 | 观察趋势 |

### 3.2 测试二：系统实时性并行监控

在测试一运行期间，在另一个终端启动以下监控脚本，采集系统级实时性指标：

```bash
#!/bin/sh
# 系统实时性指标采集（与 seg-size 测试并行运行）
LOG="/tmp/realtime_monitor_$(date +%Y%m%d_%H%M%S).csv"

echo "timestamp,softirq_hrtimer,ctx_switches,ufs_irq_total" > "$LOG"

while true; do
    ts=$(date +%s.%N)
    hrtimer=$(awk '/HRTIMER/ {sum=0; for(i=2;i<=NF;i++) sum+=$i; print sum}' /proc/softirqs)
    ctx=$(awk '/ctxt/ {print $2}' /proc/stat)
    ufs=$(grep -E "qcom-mc" /proc/interrupts \
        | awk '{sum=0; for(i=2;i<=NF;i++) sum+=$i; print sum}')
    echo "$ts,$hrtimer,$ctx,$ufs" >> "$LOG"
    sleep 0.5
done
```

用于事后分析：
- HRTIMER softirq 增长速率是否在 zstdext 运行期间骤降（表明 soft hrtimer 处理被阻塞）
- 上下文切换频率是否异常下降（表明 CPU 被 IRQ handler 霸占）

### 3.3 测试三：UFS 硬件性能基线（参考测试）

此测试使用 Direct I/O 绕过 page cache，测量 UFS 硬件的纯物理吞吐量，作为调优的**硬件上限参考**。**注意：此测试结果不能直接映射到 `--seg-size` 参数**，因为 zstdext 使用 buffered I/O，瓶颈在软件锁争用而非硬件吞吐。

```bash
#!/bin/sh
# UFS Direct I/O 基线测试
# 目的：了解硬件吞吐上限，仅作参考

TARGET_DEV="/dev/disk/by-partlabel/la_super_b"
TEST_SIZE="512m"

echo "============================================"
echo "  UFS Direct I/O 基线测试"
echo "  目标设备: $TARGET_DEV"
echo "============================================"

if grep -q "$TARGET_DEV" /proc/mounts; then
    echo "错误：$TARGET_DEV 处于挂载状态！"
    exit 1
fi

# 顺序写基线
echo ""
echo ">>> 顺序写基线（bs=4m, iodepth=4）<<<"
fio --name=seq_write_baseline \
    --filename="$TARGET_DEV" \
    --rw=write \
    --direct=1 \
    --ioengine=libaio \
    --iodepth=4 \
    --bs=4m \
    --size="$TEST_SIZE" \
    --numjobs=1 \
    --group_reporting

echo ""
echo "此吞吐量为 UFS 硬件上限。"
echo "zstdext buffered I/O 的实际吞吐通常低于此值，"
echo "因为瓶颈在 page cache writeback 路径的锁争用，不在硬件。"
```

### 3.4 测试四：去除预填零的效果验证

zstdext 源码 `fileio.c:705-717` 在写块设备时会先用零填充整个 segment，这会产生额外的脏页。验证去除此逻辑后的效果：

```bash
# 对比测试：原始 zstdext vs 去除预填零的 zstdext

# 原始版本
time $ZSTDEXT_BIN --seg-size=64 -d --patch-from=$PATCH_FILE /dev/zero -o=$TARGET_PART

sync; echo 3 > /proc/sys/vm/drop_caches; sleep 5

# 修改版本（去除预填零）
time $ZSTDEXT_BIN_PATCHED --seg-size=64 -d --patch-from=$PATCH_FILE /dev/zero -o=$TARGET_PART
```

## 四、优化措施

按实施成本从低到高、见效速度从快到慢排列：

### 4.1 调小 seg-size（应用层，无需改代码，见效最快）

**修改方式**：在 OTA 包中的 `zstd.segsize` 配置文件中调整值。

```
# zstd.segsize 文件内容
--seg-size=32
```

或修改 OTA 包中 `zstd.segsize` 配置文件的值（当前实际配置为 256），或修改 `zstdcli.c:81` 的编译期默认值：

```c
#define DEFAULT_SEG_SIZE_OF_ZSTD 128  // 编译期默认值（实际被 OTA 配置文件覆盖为 256）
```

**原理**：减小 seg-size → 每次 `fsync()` 刷入的脏页数减少 → UFS IRQ handler 单次处理的 CQE 减少 → BH 锁持有时间缩短。

**预期效果**：

| seg-size | 每次 fsync 脏页 | 预期 BH 锁持有时间 | 对吞吐的影响 |
|---|---|---|---|
| 256 MB（当前） | ~65,536 | 数秒（触发超时） | 最高 |
| 128 MB | ~32,768 | 减半 | 轻微下降 |
| 64 MB | ~16,384 | 约 1/4 | 轻微下降 |
| 32 MB | ~8,192 | 约 1/8 | 轻微下降 |
| 16 MB | ~4,096 | 约 1/16 | 可能下降（fsync 频率增加） |

**代价**：seg-size 越小，fsync 频率越高，UFS 的 FTL（Flash Translation Layer）需要更频繁地执行 flush 操作。总吞吐可能略有下降，但预计不超过 20%（因为 UFS 的物理带宽是瓶颈，fsync 频率在合理范围内不会显著影响）。

**推荐**：测试一完成后，选择满足"无 watchdog timeout + 总耗时可接受"的最大 seg-size。

### 4.2 去除块设备预填零（修改 zstdext 源码，低风险）

**当前行为**（`programs/fileio.c:705-717`）：

```c
if(UTIL_isBlockDevice(dstFileName)) {
    uint32_t wt_size = SEG_SIZE;
    uint32_t block_size = 64 KB;
    uint8_t buf[block_size];
    int i = wt_size/block_size;
    memset(buf, 0, block_size);
    while(i-->0)
        fwrite(&buf, block_size, 1, f);  // 预填零：128MB 额外脏页
    fseek(f, offset, SEEK_SET);
}
```

**问题**：块设备不需要预分配空间（不像文件系统上的 sparse file），这 256MB 的零页写入是**无意义的额外 I/O 负担**。如果 writeback 在解压数据覆写之前就开始刷零页，则产生双倍的 UFS I/O。

**修改建议**：

```c
if(UTIL_isBlockDevice(dstFileName)) {
    // 块设备无需预填零，直接定位到目标偏移
    fseek(f, offset, SEEK_SET);
}
```

**效果**：每个 segment 减少最多 256MB 的无效 I/O。在 page cache 压力大时，可将 UFS I/O 量降低接近一半。

### 4.3 复用 heartbeat socket（修改 pmonitor 客户端库，低风险）

**当前行为**：`pmonitorif_sendheartbeat()` 每次心跳执行 `socket() → sendto() → close()`。其中 `close()` 路径经过 `unix_release_sock() → local_bh_disable()`，在 PREEMPT_RT 内核中需要获取 per-CPU BH 锁——正是被 UFS IRQ handler 长期占用的那把锁。

**修改建议**：

```c
// 修改前：每次心跳 open+close
int32_t pmonitorif_sendheartbeat(const char *pname, int32_t pid) {
    int32_t sockfd = socket(AF_UNIX, SOCK_DGRAM, 0);
    sendto(sockfd, &msg, sizeof(msg), 0, ...);
    close(sockfd);   // ← 每次都竞争 BH 锁
}

// 修改后：复用 socket，避免 close() 路径
static int32_t g_heartbeat_sockfd = -1;

int32_t pmonitorif_sendheartbeat(const char *pname, int32_t pid) {
    if (g_heartbeat_sockfd < 0) {
        g_heartbeat_sockfd = socket(AF_UNIX, SOCK_DGRAM, 0);
    }
    sendto(g_heartbeat_sockfd, &msg, sizeof(msg), 0, ...);
    // 不 close，进程退出时自动释放
}
```

**效果**：心跳发送路径完全绕开 BH 锁竞争。即使 UFS I/O 风暴仍在发生，watchdog 线程也不会被阻塞在 `close()` 上。

### 4.4 UFS IRQ 亲和性隔离（系统配置，无需改代码）

将 UFS IRQ 线程绑定到非关键 CPU 核心，避免 BH 锁饥饿影响关键进程：

```bash
# 查看当前 UFS IRQ 亲和性
cat /proc/irq/314/smp_affinity

# 绑定到 CPU 6-7（假设非关键核心）
echo c0 > /proc/irq/314/smp_affinity   # 二进制 11000000 = CPU 6,7
```

**局限性**：需要同时将关键线程（watchdog、pmonitor）绑定到其他 CPU，否则调度器可能将它们迁移到 IRQ 所在核心。

### 4.5 提升关键线程为 RT 调度类（修改应用代码）

针对第十一章分析的 soft hrtimer 延迟问题，将依赖超时机制的关键线程提升为 `SCHED_FIFO`：

```c
// 在 process_main_matrix_task() 线程入口处
struct sched_param param;
param.sched_priority = 1;  // 最低 RT 优先级即可
pthread_setschedparam(pthread_self(), SCHED_FIFO, &param);
```

**原理**：PREEMPT_RT 内核中，`SCHED_FIFO/RR` 线程的 `futex_wait`/`select`/`poll` 超时使用 **hard hrtimer**（硬中断上下文处理，微秒级精度），而 `SCHED_NORMAL` 线程使用 **soft hrtimer**（`ktimers/N` 线程处理，可被延迟数秒）。

### 4.6 改造 zstdext 使用 Direct I/O（修改源码，效果最彻底）

**修改方式**：在 `fileio.c` 中打开目标块设备时添加 `O_DIRECT` 标志，并确保写入缓冲区对齐。

**原理**：Direct I/O 绕过 page cache，数据从用户态内存直接 DMA 到 UFS 控制器。完成回调走 `dio_bio_complete()` 而非 `folio_end_writeback()`，不涉及 folio writeback 锁，UFS IRQ handler 在 BH 锁内的处理时间大幅缩短。

**效果**：
- 完全消除 folio writeback 锁争用
- 消除预填零问题
- 消除 dirty ratio 触发的不可控回写
- 延迟更稳定可预测

**代价**：
- 需要写入缓冲区按扇区对齐（通常 4KB）
- 失去 page cache 的写合并优化，小块写入性能可能下降
- zstdext 的 sparse file 优化（跳过零块）需要适配

### 4.7 UFS MCQ IRQ 改为原生线程化（内核修改，从根本上消除 BH 锁）

修改 UFS 驱动注册方式，使 IRQ handler 走 `irq_thread_fn`（无 BH 锁包裹）而非 `irq_forced_thread_fn`：

```diff
// drivers/ufs/host/ufs-qcom.c
- ret = devm_request_irq(hba->dev, desc->irq,
-                        ufs_qcom_mcq_esi_handler,
-                        IRQF_SHARED, "qcom-mcq-esi", desc);
+ ret = devm_request_threaded_irq(hba->dev, desc->irq,
+                                 NULL,
+                                 ufs_qcom_mcq_esi_handler,
+                                 IRQF_SHARED | IRQF_ONESHOT,
+                                 "qcom-mcq-esi", desc);
```

**社区先例**：hisi_sas 驱动已用相同方式将 SCSI HBA 的 CQ 中断改为原生线程化（已合入 Linux 主线）。

**效果**：IRQ handler 不再持有 per-CPU BH 锁，无论 handler 运行多久都不会饿死其他线程的 `close()`/`local_bh_disable()` 路径。

## 五、优化措施优先级总结

| 优先级 | 措施 | 修改范围 | 风险 | 效果 |
|---|---|---|---|---|
| **P0** | 调小 seg-size | OTA 配置文件 | 极低 | 降低单次 I/O 风暴强度 |
| **P0** | 复用 heartbeat socket | pmonitor 客户端库 | 低 | 心跳路径绕开 BH 锁 |
| **P1** | 去除块设备预填零 | zstdext 源码 1 处 | 低 | 减少一半无效 I/O |
| **P1** | 关键线程 RT 优先级 | 应用代码 | 低 | 消除 soft hrtimer 延迟 |
| **P2** | UFS IRQ 亲和性隔离 | 系统配置 | 低 | 隔离 BH 锁影响范围 |
| **P2** | 改造 Direct I/O | zstdext 源码 | 中 | 根治 page cache 锁争用 |
| **P3** | UFS IRQ 原生线程化 | 内核驱动 1 处 | 中 | 根治 BH 锁问题 |
