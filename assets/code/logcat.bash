#!/bin/bash

# =============================================================================
# 脚本名称: logcat.bash
# 功能: 模拟 adb logcat 的参数习惯，搜索离线日志文件。
#       1. 支持多 Tag 空格分隔 (自动转换为正则 OR)。
#       2. 支持直接在命令末尾指定搜索文件/目录 (无需 -f)。
# 核心: 基于 ripgrep (rg) + awk 的高性能过滤。
# =============================================================================

# --- 颜色定义 ---
COLOR_RESET="\033[0m"
COLOR_FILE="\033[35m" # 紫色文件名
COLOR_LINE="\033[32m" # 绿色行号

# --- 帮助函数 ---
function show_usage() {
    echo "Usage: logcat [options] [file/dir]"
    echo ""
    echo "Options:"
    echo "  -f <file/dir>           Specify file or directory to search (Optional if path is last arg)"
    echo "  -p <pid>                Filter by Process ID (PID)"
    echo "  -s <tags...>            Filter by Log Tag (Space separated, e.g., 'Tag1 Tag2')"
    echo "  -k <keyword>            Filter by Keyword (content search)"
    echo "  -t <start> <end>        Filter by Time Range (MM-DD HH:MM:SS)"
    echo "  --plain                 Output plain text (no filename/line numbers)"
    echo ""
    echo "Examples:"
    echo "  1. Time & Tag:    logcat -t \"09:28:00\" \"09:30:00\" -s SurfaceFlinger"
    echo "  2. Multiple Tags: logcat -s SurfaceFlinger InputDispatcher system.log"
    echo "  3. PID & File:    logcat -p 1375 ./crash_logs/"
    exit 1
}

# --- 核心搜索逻辑 ---
function execute_search() {
    local s_time="$1"
    local e_time="$2"
    local target="$3"  # 接收搜索目标
    local use_time_filter=1

    # 如果没有指定时间，则关闭时间过滤
    if [[ -z "$s_time" ]]; then
        use_time_filter=0
    fi

    # --- 策略优化 (极速模式) ---
    # 如果仅有关键字，无其他限制(无时间、无PID、无Tag)，直接使用 rg
    if [[ $use_time_filter -eq 0 && -z "$FILTER_PID" && -z "$FILTER_TAG" && -n "$FILTER_KEY" ]]; then
        local rg_opts="--line-number --with-filename"
        if [[ $PLAIN_MODE -eq 1 ]]; then rg_opts="--no-line-number --no-filename"; fi
        
        # 直接执行 rg，搜索目标为 $target
        rg $rg_opts "$FILTER_KEY" "$target"
        return
    fi

    # --- 默认模式 (rg + awk) ---
    local rg_pattern="."
    if [[ -n "$FILTER_KEY" ]]; then rg_pattern="$FILTER_KEY"; fi

    # rg 预搜索 -> xargs -> awk 精确处理
    rg --files-with-matches --null "$rg_pattern" "$target" | xargs -0 awk \
        -v s="$s_time" \
        -v e="$e_time" \
        -v enable_time="$use_time_filter" \
        -v p="$PLAIN_MODE" \
        -v f_pid="$FILTER_PID" \
        -v f_tag="$FILTER_TAG" \
        -v f_key="$FILTER_KEY" \
        -v c_file="$COLOR_FILE" \
        -v c_line="$COLOR_LINE" \
        -v c_reset="$COLOR_RESET" '
        BEGIN { }
        {
            # 1. 格式校验 (MM-DD HH:MM:SS.mmm)
            if ($1 !~ /^[0-9]{2}-[0-9]{2}$/ || $2 !~ /^[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]+$/) next

            # 2. 时间过滤
            if (enable_time == 1) {
                current_time = $1 " " $2
                if ((s != "" && current_time < s) || (e != "" && current_time > e)) next
            }

            # 3. 属性过滤
            if (f_pid != "" && $3 != f_pid) next
            
            # Tag 过滤 (正则匹配)
            # 使用 ~ 进行正则匹配，以支持 "Tag1|Tag2" 这种形式
            # 检查 $6 (Tag列) 是否匹配 f_tag 正则
            if (f_tag != "" && $6 !~ f_tag) next
            
            # Keyword 过滤
            if (f_key != "" && index($0, f_key) == 0) next

            # 4. 输出
            if (p == 1) {
                print $0
            } else {
                printf "%s%s%s:%s%s%s: %s\n", c_file, FILENAME, c_reset, c_line, FNR, c_reset, $0
            }
        }
    '
}

# --- 参数解析 ---

PLAIN_MODE=0
FILTER_PID=""
FILTER_TAG=""
FILTER_KEY=""
START_TIME=""
END_TIME=""
SEARCH_TARGET="." # 默认搜索当前目录

# 如果没有参数，显示帮助
if [ $# -eq 0 ]; then
    show_usage
fi

while [[ $# -gt 0 ]]; do
    key="$1"
    case $key in
        -f) # File / Directory (显式指定)
            if [[ -n "$2" && "$2" != -* ]]; then
                SEARCH_TARGET="$2"
                shift 2
            else
                echo "Warning: Option -f requires an argument (file/dir). Using current dir." >&2
                shift 1
            fi
            ;;
        -p) # Process ID
            if [[ -n "$2" && "$2" != -* ]]; then
                FILTER_PID="$2"
                shift 2
            else
                echo "Warning: Option -p requires an argument (PID). Ignoring." >&2
                shift 1
            fi
            ;;
        -s) # Tag (支持空格分隔多 Tag)
            shift # 移除 -s
            # 循环读取后续参数，直到遇到下一个以 - 开头的 flag 或参数结束
            while [[ $# -gt 0 && "$1" != -* ]]; do
                if [[ -z "$FILTER_TAG" ]]; then
                    FILTER_TAG="$1"
                else
                    # 拼接正则: Tag1|Tag2
                    FILTER_TAG="${FILTER_TAG}|$1"
                fi
                shift
            done
            
            if [[ -z "$FILTER_TAG" ]]; then
                echo "Warning: Option -s requires at least one tag." >&2
            fi
            ;;
        -k) # Keyword
            if [[ -n "$2" && "$2" != -* ]]; then
                FILTER_KEY="$2"
                shift 2
            else
                echo "Warning: Option -k requires an argument (Keyword). Ignoring." >&2
                shift 1
            fi
            ;;
        -t) # Time Range
            if [[ -n "$2" && "$2" != -* ]]; then
                START_TIME="$2"
                if [[ -n "$3" && "$3" != -* ]]; then
                    END_TIME="$3"
                    shift 3
                else
                    END_TIME="99-99 23:59:59.999"
                    shift 2
                fi
            else
                echo "Warning: Option -t requires at least one time argument. Ignoring." >&2
                shift 1
            fi
            ;;
        --plain)
            PLAIN_MODE=1
            shift
            ;;
        *)
            # 处理位置参数 (文件名/目录)
            # 如果当前参数不是以 - 开头，则认为是搜索目标
            if [[ "$1" != -* ]]; then
                SEARCH_TARGET="$1"
                shift 1
            else
                echo "Unknown option: $1"
                show_usage
            fi
            ;;
    esac
done

# --- 执行 ---
# 将搜索目标作为第三个参数传递
execute_search "$START_TIME" "$END_TIME" "$SEARCH_TARGET"