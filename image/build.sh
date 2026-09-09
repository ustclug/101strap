#!/bin/bash

set -e

# shellcheck source=config.sh
source /srv/config.sh
/bin/bash /srv/image/assemble.sh
if [[ "$FORMAT" == all ]]; then
    /bin/bash /srv/image/export.sh
fi
