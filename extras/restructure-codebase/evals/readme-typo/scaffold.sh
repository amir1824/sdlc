#!/usr/bin/env bash
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "$here/../_shared/shop-fixture.sh"
printf '# shop\n\nA tiny library. You will recieve a total from cartTotal.\n' > README.md
