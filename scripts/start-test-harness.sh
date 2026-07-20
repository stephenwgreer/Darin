#!/bin/bash
set -eu
cd "$(dirname "$0")/.."
/home/stwgre/.bun/bin/bun run --watch test_harness/server.ts
