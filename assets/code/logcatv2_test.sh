#!/bin/bash

set -euo pipefail

LOGCATV2_BIN="${LOGCATV2_BIN:-/home/ethen/bin/logcatv2}"

if [[ ! -x "$LOGCATV2_BIN" ]]; then
    echo "logcatv2 binary not found or not executable: $LOGCATV2_BIN" >&2
    exit 1
fi

TEST_TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TEST_TMPDIR"' EXIT

FIXTURE_A="$TEST_TMPDIR/dlt_a.txt"
FIXTURE_B="$TEST_TMPDIR/dlt_b.txt"

cat > "$FIXTURE_A" <<'EOF'
0 2026/03/26 18:38:59.087967   42551563 237 ECU1 ivcd ivcd log error V 1 [file=ivcd_ivi_commumgr.c,line=494 socket_fd error -1 ]
1 2026/03/26 18:38:59.093374   42551618 238 ECU1 rpcd rpcd log error V 1 [file=rpcd_local.c,line=670 bus_id = 0x1 frame_id = 33777]
this is not a dlt line
EOF

cat > "$FIXTURE_B" <<'EOF'
0 2026/03/26 18:07:43.357536   23791818 066 ECU1 SYS- JOUR log info V 4 [2026/03/26 18:07:43.113299 openwfd_server[2204]: Notice: [1073737888][WFD_ResourceMgr_freeNativeImage:849]  nativeImage = 0x0xffff38032fe0 [1920x480] BUFFER ADDR (VA) = 0x0x4000  MAPPED BUFFER ADDR (VA) = 0x(nil)  BUFFER ADDR (PA) = 0x0xfec04000 BUFFER HANDLE = 0x0x3f]
1 2026/03/26 18:07:43.358347   23791822 069 ECU1 SYS- JOUR log info V 4 [2026/03/26 18:07:43.113767 openwfd_server[2204]: Informational: pidfd closed successfully]
2 2026/03/26 18:07:43.359999   23791824 070 ECU1 SYS- JOUR log fatal V 4 [2026/03/26 18:07:43.114000 qcxserver[1233]: Alert: diagnosticmanager.cpp:2024 DM_ReportEvent() DM is disabled, NON_SAFE CONFIG]
EOF

PASS_COUNT=0

fail() {
    echo "FAIL: $1" >&2
    exit 1
}

pass() {
    PASS_COUNT=$((PASS_COUNT + 1))
    echo "PASS: $1"
}

count_lines() {
    awk 'NF { c++ } END { print c + 0 }' <<<"$1"
}

strip_ansi() {
    awk '{ gsub(/\033\[[0-9;]*m/, ""); print }'
}

assert_eq() {
    local actual="$1"
    local expected="$2"
    local message="$3"
    if [[ "$actual" != "$expected" ]]; then
        echo "expected: $expected" >&2
        echo "actual:   $actual" >&2
        fail "$message"
    fi
    pass "$message"
}

assert_contains() {
    local haystack="$1"
    local needle="$2"
    local message="$3"
    if ! grep -Fq -- "$needle" <<<"$haystack"; then
        echo "needle not found: $needle" >&2
        echo "haystack:" >&2
        printf '%s\n' "$haystack" >&2
        fail "$message"
    fi
    pass "$message"
}

assert_not_contains() {
    local haystack="$1"
    local needle="$2"
    local message="$3"
    if grep -Fq -- "$needle" <<<"$haystack"; then
        echo "unexpected needle found: $needle" >&2
        echo "haystack:" >&2
        printf '%s\n' "$haystack" >&2
        fail "$message"
    fi
    pass "$message"
}

output="$("$LOGCATV2_BIN" --plain -f "$FIXTURE_A" "$FIXTURE_B")"
assert_eq "$(count_lines "$output")" "5" "plain output returns all supported DLT lines and skips garbage"

output="$("$LOGCATV2_BIN" --plain -s ivcd "$FIXTURE_A")"
assert_eq "$(count_lines "$output")" "1" "source filter matches regular DLT app or ctx"
assert_contains "$output" "socket_fd error -1" "regular DLT source filter returns ivcd line"

output="$("$LOGCATV2_BIN" --plain -s JOUR "$FIXTURE_B")"
assert_eq "$(count_lines "$output")" "3" "source filter matches JOUR outer context"

output="$("$LOGCATV2_BIN" --plain -s openwfd_server "$FIXTURE_B")"
assert_eq "$(count_lines "$output")" "2" "source filter matches JOUR inner proc"
assert_contains "$output" "pidfd closed successfully" "inner proc source filter includes second openwfd line"

output="$("$LOGCATV2_BIN" --plain -p 2204 "$FIXTURE_B")"
assert_eq "$(count_lines "$output")" "2" "pid filter matches JOUR inner pid"

output="$("$LOGCATV2_BIN" --plain -p 42551563 "$FIXTURE_A")"
assert_eq "$(count_lines "$output")" "0" "pid filter does not treat outer DLT numeric field as pid"

output="$("$LOGCATV2_BIN" --plain -k "socket_fd error" "$FIXTURE_A")"
assert_eq "$(count_lines "$output")" "1" "keyword filter matches message content"
assert_contains "$output" "socket_fd error -1" "keyword filter returns expected line"

output="$("$LOGCATV2_BIN" --plain -s openwfd_server -e "pidfd closed" "$FIXTURE_B")"
assert_eq "$(count_lines "$output")" "1" "exclude filter removes matching JOUR lines"
assert_not_contains "$output" "pidfd closed successfully" "exclude filter removes excluded text"

output="$("$LOGCATV2_BIN" --plain -t "18:38:59.087967" "18:38:59.087967" "$FIXTURE_A")"
assert_eq "$(count_lines "$output")" "1" "time-only range matches exact regular DLT timestamp"
assert_contains "$output" "18:38:59.087967" "time-only range keeps exact match"

output="$("$LOGCATV2_BIN" --plain -t "2026/03/26 18:07:43.357536" "2026/03/26 18:07:43.358347" -s openwfd_server "$FIXTURE_B")"
assert_eq "$(count_lines "$output")" "2" "full timestamp range works with JOUR proc source filter"

pushd "$TEST_TMPDIR" >/dev/null
output="$("$LOGCATV2_BIN" --plain -s ivcd)"
popd >/dev/null
assert_eq "$(count_lines "$output")" "1" "default search path uses current directory"

output="$("$LOGCATV2_BIN" -s ivcd "$FIXTURE_A" | strip_ansi)"
assert_contains "$output" "$FIXTURE_A:1:" "default output includes filename and line number"

echo "All ${PASS_COUNT} logcatv2 tests passed."
