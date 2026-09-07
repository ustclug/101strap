#!/bin/bash
# Exercise privileged metadata only inside a disposable container.
set -euo pipefail
[[ -f /run/.containerenv || -f /.dockerenv ]]
[[ $EUID == 0 ]]
python3 - <<'PY'
import os
from pathlib import Path
import stat
import struct
import subprocess
import tempfile

with tempfile.TemporaryDirectory() as directory:
    source = Path(directory) / 'source'
    target = Path(directory) / 'target'
    (source / 'etc').mkdir(parents=True)
    target.mkdir()
    data = source / 'etc/owned'
    data.write_text('owned data')
    os.chown(data, 1701, 1702)
    data.chmod(0o6751)
    cap = source / 'etc/capability'
    cap.write_text('capability data')
    cap.chmod(0o755)
    os.setxattr(cap, 'security.capability', struct.pack('<IIIII', 0x02000001, 1 << 10, 0, 0, 0))
    acl = source / 'etc/acl'
    acl.write_text('acl data')
    entries = [(1, 6, 0xffffffff), (2, 4, 1701), (4, 0, 0xffffffff),
               (16, 4, 0xffffffff), (32, 0, 0xffffffff)]
    os.setxattr(acl, 'system.posix_acl_access', struct.pack('<I', 2) + b''.join(struct.pack('<HHI', *entry) for entry in entries))
    subprocess.run(['bash', '/srv/rootfs/copy.sh', str(source), str(target)], check=True)
    output = target / 'etc/owned'
    assert (output.stat().st_uid, output.stat().st_gid) == (1701, 1702)
    assert stat.S_IMODE(output.stat().st_mode) == 0o6751
    for name, attr in [('capability', 'security.capability'), ('acl', 'system.posix_acl_access')]:
        assert os.getxattr(source / 'etc' / name, attr) == os.getxattr(target / 'etc' / name, attr)
print('PASS: numeric ownership, setuid/setgid permissions, ACLs and capabilities')
PY
