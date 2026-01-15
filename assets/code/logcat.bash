#!/bin/bash

# =============================================================================
# 脚本名称: logcat.bash
# 逻辑模式: Scoped OR (时间限定下的或逻辑)
#          Time AND ( PID OR Tag OR Keyword )
# 功能: 
#       1. 支持多 Tag、多 PID、多关键字 (空格分隔)。
#       2. 支持多文件/目录搜索。
#       3. 智能区分关键字和文件路径。
# 核心: 基于 ripgrep (rg) + awk。
# =============================================================================

# --- 颜色定义 ---
COLOR_RESET="\033[0m"
COLOR_FILE="\033[35m" # 紫色文件名
COLOR_LINE="\033[32m" # 绿色行号

# --- 帮助函数 ---
function show_usage() {
    echo "Usage: logcat [options] [file/dir...]"
    echo ""
    echo "Logic: Time_Range AND ( PID OR Tag OR Keyword )"
    echo ""
    echo "Options:"
    echo "  -f <paths...>           Specify files/dirs to search (Space separated)"
    echo "  -p <pids...>            Filter by Process ID (Space separated)"
    echo "  -s <tags...>            Filter by Log Tag (Space separated)"
    echo "  -k <keywords...>        Filter by Keyword (Space separated, Regex OR)"
    echo "  -t <start> <end>        Filter by Time Range (MM-DD HH:MM:SS)"
    echo "  --plain                 Output plain text (no filename/line numbers)"
    echo ""
    echo "Examples:"
    echo "  1. PID OR Keyword: logcat -p 1234 -k \"Error\" (Show PID 1234 OR any Error)"
    echo "  2. Scoped OR:      logcat -t \"09:00\" \"09:05\" -s AudioFlinger -k Fatal"
    exit 1
}

# --- 核心搜索逻辑 ---
function execute_search() {
    local s_time="$1"
    local e_time="$2"
    local use_time_filter=1

    # 如果没有指定时间，则关闭时间过滤
    if [[ -z "$s_time" ]]; then
        use_time_filter=0
    fi

    # 如果没有指定搜索目标，默认为当前目录
    if [[ ${#SEARCH_TARGETS[@]} -eq 0 ]]; then
        SEARCH_TARGETS=(".")
    fi

    # --- 逻辑变更说明 (Scoped OR) ---
    # 为了保证 (PID or Tag or Key) 的逻辑正确性，我们不能单独使用 rg 过滤某一个字段。
    # 必须把所有行交给 awk，让 awk 来判断是否满足任意一个条件。
    # 因此，rg 这里仅作为文件读取器 (输出所有行)，不再进行预过滤 (rg_pattern=".")。
    # 唯一的例外是：如果用户没有 PID 也没 Tag，只有 Keyword，rg 依然可以预过滤。

    local rg_pattern="."
    if [[ -z "$FILTER_PID" && -z "$FILTER_TAG" && -n "$FILTER_KEY" ]]; then
        rg_pattern="$FILTER_KEY"
    fi

    # rg 读取 -> xargs -> awk 逻辑判断
    rg --files-with-matches --null "$rg_pattern" "${SEARCH_TARGETS[@]}" | xargs -0 awk \
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

            # 2. 时间过滤 (Gatekeeper - 依然是一票否决 AND 关系)
            # 只有时间满足了，才配进行后面的 OR 判断
            if (enable_time == 1) {
                current_time = $1 " " $2
                if ((s != "" && current_time < s) || (e != "" && current_time > e)) next
            }

            # 3. 属性过滤 (Scoped OR 逻辑)
            
            has_condition = 0  # 标记用户是否指定了至少一个筛选条件
            is_matched = 0     # 标记当前行是否命中

            # --- 检查 PID ---
            if (f_pid != "") {
                has_condition = 1
                if ($3 ~ f_pid) is_matched = 1
            }

            # --- 检查 Tag ---
            # 优化：如果已经 matched 了，就不必检查 Tag 了 (因为是 OR)
            if (f_tag != "" && is_matched == 0) {
                has_condition = 1
                if ($6 ~ f_tag) is_matched = 1
            }

            # --- 检查 Keyword ---
            if (f_key != "" && is_matched == 0) {
                has_condition = 1
                if ($0 ~ f_key) is_matched = 1
            }

            # 4. 输出决策
            # 如果 has_condition == 0 (用户只查时间，或没给条件)，默认输出。
            # 如果 has_condition == 1，则必须 is_matched == 1 才输出。
            if (has_condition == 0 || is_matched == 1) {
                if (p == 1) {
                    print $0
                } else {
                    printf "%s%s%s:%s%s%s: %s\n", c_file, FILENAME, c_reset, c_line, FNR, c_reset, $0
                }
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
# 使用数组存储多个搜索目标
declare -a SEARCH_TARGETS=()

if [ $# -eq 0 ]; then
    show_usage
fi

# 辅助函数：判断参数是否应停止解析
function is_stop_arg() {
    local arg="$1"
    if [[ "$arg" == -* ]]; then return 0; fi          # 是 flag
    if [[ -e "$arg" ]]; then return 0; fi             # 文件存在
    if [[ "$arg" == /* || "$arg" == ./* || "$arg" == ../* ]]; then return 0; fi # 看起来像路径
    return 1 # 继续解析
}

while [[ $# -gt 0 ]]; do
    key="$1"
    case $key in
        -f) # File / Directory
            shift
            while [[ $# -gt 0 ]]; do
                if [[ "$1" == -* ]]; then break; fi
                SEARCH_TARGETS+=("$1")
                shift
            done
            if [[ ${#SEARCH_TARGETS[@]} -eq 0 ]]; then
                echo "Warning: Option -f requires at least one file/dir." >&2
            fi
            ;;
        -p) # Process ID
            shift
            _pids=""
            while [[ $# -gt 0 ]]; do
                is_stop_arg "$1" && break
                if [[ -z "$_pids" ]]; then _pids="$1"; else _pids="${_pids}|$1"; fi
                shift
            done
            if [[ -n "$_pids" ]]; then
                FILTER_PID="^(${_pids})$"
            else
                echo "Warning: Option -p requires at least one PID." >&2
            fi
            ;;
        -s) # Tag
            shift
            while [[ $# -gt 0 ]]; do
                is_stop_arg "$1" && break
                if [[ -z "$FILTER_TAG" ]]; then FILTER_TAG="$1"; else FILTER_TAG="${FILTER_TAG}|$1"; fi
                shift
            done
            if [[ -z "$FILTER_TAG" ]]; then
                echo "Warning: Option -s requires at least one tag." >&2
            fi
            ;;
        -k) # Keyword
            shift
            while [[ $# -gt 0 ]]; do
                is_stop_arg "$1" && break
                if [[ -z "$FILTER_KEY" ]]; then FILTER_KEY="$1"; else FILTER_KEY="${FILTER_KEY}|$1"; fi
                shift
            done
            if [[ -z "$FILTER_KEY" ]]; then
                echo "Warning: Option -k requires at least one keyword." >&2
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
            if [[ "$1" != -* ]]; then
                SEARCH_TARGETS+=("$1")
                shift 1
            else
                echo "Unknown option: $1"
                show_usage
            fi
            ;;
    esac
done

# --- 执行 ---
execute_search "$START_TIME" "$END_TIME"