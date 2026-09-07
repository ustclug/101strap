#!/bin/bash
# Run only inside the finished, offline image chroot, after package installation.
set -euo pipefail
if [[ "${1:-}" != --image-root || ! -f /usr/share/101strap/build-info.txt || $EUID != 0 ]]; then
    echo "Run this script inside the 101strap image chroot with --image-root." >&2
    exit 1
fi

# The image intentionally ships only an SSH client. If a server is added later,
# implement first-boot host-key generation before removing its packaged keys.
if [[ "$(dpkg-query -W '-f=${Status}' openssh-server 2>/dev/null || true)" == 'install ok installed' ]]; then
    echo "Refusing to seal an SSH server image without first-boot host-key generation." >&2
    exit 1
fi

# Empty (not absent) avoids rerunning systemd first-boot presets. systemd still
# generates an ID at boot. D-Bus must not supply an old ID as a fallback.
rm -f /etc/machine-id /var/lib/dbus/machine-id
install -m 0444 /dev/null /etc/machine-id
install -d /var/lib/dbus
ln -s /etc/machine-id /var/lib/dbus/machine-id
rm -f /var/lib/systemd/random-seed /var/lib/NetworkManager/secret_key \
    /var/lib/NetworkManager/seen-bssids /var/lib/NetworkManager/timestamps
if [[ -d /etc/ssh ]]; then
    find /etc/ssh -maxdepth 1 -type f -name 'ssh_host_*' -delete
fi
for account_home in /root /home/*; do
    [[ -d "$account_home" && ! -L "$account_home" ]] || continue
    rm -f "$account_home/.bash_history" "$account_home/.lesshst" \
        "$account_home/.python_history" "$account_home/.wget-hsts"
done
# Keep log paths and permissions, but not build-time contents or old journal IDs.
find /var/log -xdev -type f -exec truncate -s 0 -- {} +
if [[ -d /var/log/journal ]]; then
    find /var/log/journal -type f -delete
    find /var/log/journal -mindepth 1 -depth -type d -empty -delete
fi
test ! -s /etc/machine-id
test "$(readlink /var/lib/dbus/machine-id)" = /etc/machine-id
