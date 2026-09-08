#!/bin/bash
# Run with the repository mounted read-only at /srv in a disposable container.
set -euo pipefail

test_directory=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
exec python3 "$test_directory/container/copy_metadata.py"
