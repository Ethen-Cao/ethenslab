#!/bin/bash

set -euo pipefail

SAFE_UNZIP_BIN="${SAFE_UNZIP_BIN:-/home/ethen/bin/safe_unzip_timestamped.py}"
DLT2TXT_BIN="${DLT2TXT_BIN:-/home/ethen/bin/dlt2txt.sh}"
LOGCAT_BIN="${LOGCAT_BIN:-/home/ethen/bin/logcat}"
LOGCATV2_BIN="${LOGCATV2_BIN:-/home/ethen/bin/logcatv2}"

CMD_NAME="$(basename "$0")"
TOOL_MODE="auto"
WORK_ROOT=""
CLEANUP_WORK_ROOT=0
AUTO_WORK_ROOT_CREATED=0

declare -a INPUTS=()
declare -a FILTER_ARGS=()
declare -a ANALYSIS_TARGETS=()
declare -a CONVERT_SCAN_ROOTS=()
declare -a DIRECT_DLT_FILES=()

function show_usage() {
    cat <<EOF
Usage:
  ${CMD_NAME} [wrapper-options] <input...> -- [filter-options]
  ${CMD_NAME} [wrapper-options] <input...>

Wrapper options:
  --tool <auto|logcat|logcatv2>   Select filter tool. Default: auto
  --work-root <dir>               Extraction workspace for archive inputs
  --cleanup                       Remove auto-created work root after run
  -h, --help                      Show this help

Filter options:
  Everything after '--' is passed through to the selected filter tool.
  Typical examples: --plain -t ... -s ... -k ... -e ... -p ...

Examples:
  ${CMD_NAME} issue_logs.zip -- --plain -s ivcd -k "socket_fd error"
  ${CMD_NAME} ./linux_log --tool logcatv2 -- -t "18:07" "18:08" -s openwfd_server
  ${CMD_NAME} android_bundle.tar.gz --tool logcat -- -t "03-26 18:07:00" "03-26 18:08:00" -s ActivityManager
EOF
    exit 1
}

function log_info() {
    printf '[%s] %s\n' "${CMD_NAME}" "$*" >&2
}

function log_warn() {
    printf '[%s] Warning: %s\n' "${CMD_NAME}" "$*" >&2
}

function die() {
    printf '[%s] Error: %s\n' "${CMD_NAME}" "$*" >&2
    exit 1
}

function ensure_cmd() {
    local path="$1"
    [[ -x "$path" ]] || die "required tool not executable: $path"
}

function is_archive_path() {
    local name
    name="$(basename "$1")"
    name="${name,,}"
    [[ "$name" == *.zip || "$name" == *.tar || "$name" == *.tar.gz || "$name" == *.tgz || "$name" == *.tar.xz || "$name" == *.txz || "$name" == *.tar.bz2 || "$name" == *.tbz || "$name" == *.gz || "$name" == *.7z || "$name" == *.rar ]]
}

function add_analysis_target() {
    local target="$1"
    ANALYSIS_TARGETS+=("$target")
}

function add_convert_root() {
    local root="$1"
    CONVERT_SCAN_ROOTS+=("$root")
}

function contains_filter_path_override() {
    local arg
    for arg in "${FILTER_ARGS[@]}"; do
        [[ "$arg" == "-f" ]] && return 0
    done
    return 1
}

function prepare_work_root() {
    if [[ -n "$WORK_ROOT" ]]; then
        mkdir -p "$WORK_ROOT"
        WORK_ROOT="$(realpath "$WORK_ROOT")"
        return
    fi

    WORK_ROOT="$(mktemp -d /tmp/analyze_archive_logs.XXXXXX)"
    AUTO_WORK_ROOT_CREATED=1
}

function extract_archive_input() {
    local input="$1"
    local idx="$2"
    local slot="${WORK_ROOT}/input_${idx}"

    mkdir -p "$slot"
    log_info "extracting archive: $input -> $slot"
    "$SAFE_UNZIP_BIN" --keep -o "$slot" "$input"
    add_analysis_target "$slot"
    add_convert_root "$slot"
}

function prepare_inputs() {
    local idx=0
    local input

    for input in "${INPUTS[@]}"; do
        idx=$((idx + 1))
        [[ -e "$input" ]] || die "input not found: $input"

        if [[ -f "$input" ]] && is_archive_path "$input"; then
            prepare_work_root
            extract_archive_input "$input" "$idx"
            continue
        fi

        if [[ -f "$input" ]] && [[ "${input,,}" == *.dlt ]]; then
            DIRECT_DLT_FILES+=("$input")
            add_convert_root "$(dirname "$input")"
            continue
        fi

        add_analysis_target "$input"

        if [[ -d "$input" ]]; then
            add_convert_root "$input"
        elif [[ -f "$input" ]]; then
            add_convert_root "$(dirname "$input")"
        fi
    done
}

function convert_dlt_files() {
    local -a unique_dirs=()
    local dir
    local seen=""

    if [[ ${#CONVERT_SCAN_ROOTS[@]} -eq 0 ]]; then
        return
    fi

    while IFS= read -r -d '' dir; do
        unique_dirs+=("$dir")
    done < <(
        find "${CONVERT_SCAN_ROOTS[@]}" -type f -name '*.dlt' -printf '%h\0' 2>/dev/null | sort -zu
    )

    if [[ ${#unique_dirs[@]} -eq 0 ]]; then
        return
    fi

    for dir in "${unique_dirs[@]}"; do
        log_info "converting dlt files in: $dir"
        (
            cd "$dir"
            "$DLT2TXT_BIN"
        )
    done
}

function materialize_direct_dlt_targets() {
    local dlt txt
    for dlt in "${DIRECT_DLT_FILES[@]}"; do
        txt="${dlt%.dlt}.txt"
        if [[ -f "$txt" ]]; then
            add_analysis_target "$txt"
        else
            log_warn "expected converted txt not found for: $dlt"
        fi
    done
}

function detect_tool() {
    local tool="$1"

    if [[ "$tool" != "auto" ]]; then
        printf '%s\n' "$tool"
        return
    fi

    if rg -m 1 '^[0-9]+ [0-9]{4}/[0-9]{2}/[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]+' "${ANALYSIS_TARGETS[@]}" >/dev/null 2>&1; then
        printf '%s\n' "logcatv2"
        return
    fi

    if rg -m 1 '^[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]+' "${ANALYSIS_TARGETS[@]}" >/dev/null 2>&1; then
        printf '%s\n' "logcat"
        return
    fi

    die "could not auto-detect matching log format under prepared targets"
}

function run_filter() {
    local selected_tool="$1"
    local -a cmd=()

    case "$selected_tool" in
        logcat) cmd=("$LOGCAT_BIN") ;;
        logcatv2) cmd=("$LOGCATV2_BIN") ;;
        *) die "unsupported tool: $selected_tool" ;;
    esac

    contains_filter_path_override && die "do not pass -f after '--'; input paths belong before '--'"

    log_info "using filter tool: $selected_tool"
    log_info "analysis targets:"
    printf '  %s\n' "${ANALYSIS_TARGETS[@]}" >&2

    "${cmd[@]}" "${FILTER_ARGS[@]}" -f "${ANALYSIS_TARGETS[@]}"
}

function cleanup_if_needed() {
    if [[ "$AUTO_WORK_ROOT_CREATED" -eq 1 && "$CLEANUP_WORK_ROOT" -eq 1 && -n "$WORK_ROOT" && -d "$WORK_ROOT" ]]; then
        rm -rf "$WORK_ROOT"
    fi
}

trap cleanup_if_needed EXIT

while [[ $# -gt 0 ]]; do
    case "$1" in
        --tool)
            [[ $# -ge 2 ]] || die "--tool requires a value"
            TOOL_MODE="$2"
            shift 2
            ;;
        --work-root)
            [[ $# -ge 2 ]] || die "--work-root requires a value"
            WORK_ROOT="$2"
            CLEANUP_WORK_ROOT=0
            shift 2
            ;;
        --cleanup)
            CLEANUP_WORK_ROOT=1
            shift
            ;;
        -h|--help)
            show_usage
            ;;
        --)
            shift
            FILTER_ARGS=("$@")
            break
            ;;
        -*)
            die "unknown wrapper option before '--': $1"
            ;;
        *)
            INPUTS+=("$1")
            shift
            ;;
    esac
done

[[ ${#INPUTS[@]} -gt 0 ]] || show_usage
[[ "$TOOL_MODE" == "auto" || "$TOOL_MODE" == "logcat" || "$TOOL_MODE" == "logcatv2" ]] || die "--tool must be auto, logcat, or logcatv2"

ensure_cmd "$SAFE_UNZIP_BIN"
ensure_cmd "$DLT2TXT_BIN"
ensure_cmd "$LOGCAT_BIN"
ensure_cmd "$LOGCATV2_BIN"

prepare_inputs
convert_dlt_files
materialize_direct_dlt_targets

[[ ${#ANALYSIS_TARGETS[@]} -gt 0 ]] || die "no analysis targets prepared"

SELECTED_TOOL="$(detect_tool "$TOOL_MODE")"
if [[ -n "$WORK_ROOT" ]]; then
    log_info "work root: $WORK_ROOT"
fi
run_filter "$SELECTED_TOOL"
