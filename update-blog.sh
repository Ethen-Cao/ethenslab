#!/usr/bin/env bash
set -euo pipefail

hugo --minify -d docs
git add .
git commit -m "update post"
git push origin master
