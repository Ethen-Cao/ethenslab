#!/bin/sh
# ============================================================
# [车端] OTA Watchdog 超时复现 - 数据采集
# 用法: adb push device_collect.sh /tmp/ && adb shell "chmod +x /tmp/device_collect.sh && /tmp/device_collect.sh"
# 输出: /log/wd_reproduce_<timestamp>/ 目录
# ============================================================

TRACEFS="/sys/kernel/debug/tracing"
LOG_DIR="/log/wd_reproduce_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$LOG_DIR"

# ---- 辅助函数 ----
get_ufs_irq_total() {
    grep "qcom-mcq-esi" /proc/interrupts \
        | awk '{for(i=2;i<=NF;i++){if($i~/^[0-9]+$/)s+=$i}} END{print s+0}'
}

count_matches() {
    _count=$(grep -ci "$2" "$1" 2>/dev/null) || true
    echo "${_count:-0}"
}

# ---- 自动选择对侧分区 ----
SLOT=$(cat /proc/cmdline | tr ' ' '\n' | grep slot_suffix | cut -d= -f2)
if [ "$SLOT" = "_a" ]; then
    TARGET="/dev/disk/by-partlabel/la_super_b"
elif [ "$SLOT" = "_b" ]; then
    TARGET="/dev/disk/by-partlabel/la_super_a"
else
    echo "错误: 无法识别启动槽位 '$SLOT'"; exit 1
fi
echo "当前启动槽位: $SLOT, 写入对侧分区: $TARGET"

# ---- 安全检查 ----
if grep -q "$TARGET" /proc/mounts; then
    echo "错误: $TARGET 已挂载！"; exit 1
fi

echo "============================================"
echo "  [车端] OTA Watchdog 超时复现 - 数据采集"
echo "  目标分区: $TARGET"
echo "  结果目录: $LOG_DIR"
echo "============================================"

# ---- 记录关键进程 PID ----
echo ""
echo "关键进程:" | tee "$LOG_DIR/pids.txt"
for proc in pmonitor ivcd mcd audiomgr updatemgr; do
    pid=$(pidof $proc 2>/dev/null)
    [ -n "$pid" ] && echo "  $proc: PID=$pid" | tee -a "$LOG_DIR/pids.txt"
done

# ============ 阶段 1: 采集基线 ============
echo ""
echo "[1/5] 采集 10 秒基线 DLT..."
dlt-receive -a localhost > "$LOG_DIR/dlt_baseline.txt" 2>&1 &
DLT_BASE_PID=$!
sleep 10
kill $DLT_BASE_PID 2>/dev/null; wait $DLT_BASE_PID 2>/dev/null
baseline_timeout=$(count_matches "$LOG_DIR/dlt_baseline.txt" "timeout")
echo "  基线 timeout 消息: $baseline_timeout"

# ============ 阶段 2: 配置 ftrace ============
echo ""
echo "[2/5] 配置 ftrace..."
echo 0 > "$TRACEFS/tracing_on"
echo > "$TRACEFS/trace"
echo 256000 > "$TRACEFS/buffer_size_kb"
echo 1 > "$TRACEFS/events/sched/sched_switch/enable"
echo "  buffer=256MB, 事件=sched_switch"

ufs_irq_before=$(get_ufs_irq_total)
echo "  UFS IRQ 基线: $ufs_irq_before"

# ============ 阶段 3: 启动并行监控 ============
echo ""
echo "[3/5] 启动监控..."
dlt-receive -a localhost > "$LOG_DIR/dlt_during_io.txt" 2>&1 &
DLT_PID=$!
echo "  DLT 采集: PID=$DLT_PID"

touch /tmp/wd_test_running
(
echo "ts_s,ctx_switches,ufs_irq_total" > "$LOG_DIR/sys_metrics.csv"
while [ -f /tmp/wd_test_running ]; do
    ts=$(date +%s)
    ctx=$(awk '/ctxt/ {print $2}' /proc/stat)
    ufs=$(get_ufs_irq_total)
    echo "$ts,$ctx,$ufs" >> "$LOG_DIR/sys_metrics.csv"
    usleep 500000 2>/dev/null || sleep 1
done
) &
MONITOR_PID=$!
echo "  系统指标采集: PID=$MONITOR_PID"

# ============ 阶段 4: 执行 I/O 风暴 ============
echo ""
echo "[4/5] I/O 风暴开始..."
echo 1 > "$TRACEFS/tracing_on"
t_start=$(date +%s)

# ---- 场景 A: 256MB buffered write → sync ----
echo ""
echo "=== 场景 A: 256MB write → sync ==="
sync; echo 3 > /proc/sys/vm/drop_caches; sleep 1
echo "  写入 256MB..."
dd if=/dev/zero of="$TARGET" bs=128k count=2048 2>> "$LOG_DIR/dd_output.txt"
echo "  sync..."
sync
echo "  完成"
sleep 2

# ---- 场景 B: 预填零 + 覆写 → sync ----
echo ""
echo "=== 场景 B: 预填零 256MB + 覆写 256MB → sync ==="
sync; echo 3 > /proc/sys/vm/drop_caches; sleep 1
echo "  预填零 256MB..."
dd if=/dev/zero of="$TARGET" bs=128k count=2048 2>> "$LOG_DIR/dd_output.txt"
echo "  覆写 256MB..."
dd if=/dev/urandom of="$TARGET" bs=128k count=2048 2>> "$LOG_DIR/dd_output.txt"
echo "  sync..."
sync
echo "  完成"
sleep 2

# ---- 场景 C: 1GB write → sync ----
echo ""
echo "=== 场景 C: 1GB write → sync ==="
sync; echo 3 > /proc/sys/vm/drop_caches; sleep 1
echo "  写入 1GB..."
dd if=/dev/zero of="$TARGET" bs=1048576 count=1024 2>> "$LOG_DIR/dd_output.txt"
echo "  sync..."
sync
echo "  完成"
sleep 2

# ---- 场景 D: 4 轮 256MB write+sync ----
echo ""
echo "=== 场景 D: 4x 256MB write+sync ==="
sync; echo 3 > /proc/sys/vm/drop_caches; sleep 1
for round in 1 2 3 4; do
    echo "  Round $round/4..."
    dd if=/dev/zero of="$TARGET" bs=128k count=2048 seek=$(( ($round - 1) * 2048 )) 2>> "$LOG_DIR/dd_output.txt"
    sync
done
echo "  完成"

t_end=$(date +%s)
elapsed_s=$((t_end - t_start))

# ============ 阶段 5: 收集数据 ============
echo ""
echo "[5/5] 收集数据..."

# 等待 pmonitor 延迟上报
echo "  等待 15 秒捕获延迟 timeout 上报..."
sleep 15

echo 0 > "$TRACEFS/tracing_on"
echo 0 > "$TRACEFS/events/sched/sched_switch/enable"

rm -f /tmp/wd_test_running
sleep 1
kill $DLT_PID $MONITOR_PID 2>/dev/null
wait $DLT_PID $MONITOR_PID 2>/dev/null

ufs_irq_after=$(get_ufs_irq_total)
ufs_irq_delta=$((ufs_irq_after - ufs_irq_before))

echo "  保存 ftrace..."
cat "$TRACEFS/trace" > "$LOG_DIR/trace.txt"
trace_lines=$(wc -l < "$LOG_DIR/trace.txt")

dmesg | tail -n 500 > "$LOG_DIR/dmesg_tail.txt"

# 保存测试元数据
cat > "$LOG_DIR/test_meta.txt" <<METAEOF
elapsed_s=$elapsed_s
ufs_irq_before=$ufs_irq_before
ufs_irq_after=$ufs_irq_after
ufs_irq_delta=$ufs_irq_delta
baseline_timeout=$baseline_timeout
trace_lines=$trace_lines
METAEOF

# ============ 车端快速摘要 ============
echo ""
echo "================================================"
echo "  车端采集完成"
echo "================================================"
echo "I/O 总耗时: ${elapsed_s} 秒"
echo "UFS IRQ 增量: $ufs_irq_delta"
echo "ftrace: $trace_lines 行"

wd_count=$(count_matches "$LOG_DIR/dlt_during_io.txt" "timeout")
echo "DLT timeout 消息: $wd_count (基线: $baseline_timeout)"

echo ""
echo "timeout/watchdog 相关 DLT:"
grep -i "timeout\|watchdog" "$LOG_DIR/dlt_during_io.txt" 2>/dev/null | head -n 20
echo ""
echo "pmonitor 相关 DLT:"
grep -i "pmon" "$LOG_DIR/dlt_during_io.txt" 2>/dev/null | grep -iv "SYS-" | head -n 10

echo ""
echo "数据目录: $LOG_DIR"
ls -lh "$LOG_DIR/"
echo ""
echo "下一步: 在电脑上运行 local_analyze.sh 进行 trace 分析"
echo "  adb pull $LOG_DIR/ data/"
