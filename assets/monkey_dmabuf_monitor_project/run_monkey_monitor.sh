#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 monkey_dmabuf_black_screen_monitor.py --config default_config.json --output-root runs "$@"
