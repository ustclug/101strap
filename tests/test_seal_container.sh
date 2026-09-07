#!/bin/bash
# Run with the repository mounted read-only at /srv in a disposable container.
set -euo pipefail
test -f /run/.containerenv
test "$(id -u)" = 0
install -d /usr/share/101strap /var/lib/dbus /var/lib/systemd /var/lib/NetworkManager \
    /etc/ssh /home/seal-test /var/log/journal/old-machine
printf 'test fixture\n' > /usr/share/101strap/build-info.txt
printf '11111111111111111111111111111111\n' > /etc/machine-id
rm -f /var/lib/dbus/machine-id
printf '22222222222222222222222222222222\n' > /var/lib/dbus/machine-id
for file in /var/lib/systemd/random-seed /var/lib/NetworkManager/secret_key \
    /var/lib/NetworkManager/seen-bssids /var/lib/NetworkManager/timestamps \
    /etc/ssh/ssh_host_fixture_key /root/.bash_history /home/seal-test/.bash_history \
    /var/log/fixture.log /var/log/journal/old-machine/system.journal; do
    printf 'private build data\n' > "$file"
done
printf 'keep this config\n' > /etc/ssh/ssh_config.fixture
bash /srv/assets/seal-image.sh --image-root
test -f /etc/machine-id
test ! -s /etc/machine-id
test "$(readlink /var/lib/dbus/machine-id)" = /etc/machine-id
for file in /var/lib/systemd/random-seed /var/lib/NetworkManager/secret_key \
    /var/lib/NetworkManager/seen-bssids /var/lib/NetworkManager/timestamps \
    /etc/ssh/ssh_host_fixture_key /root/.bash_history /home/seal-test/.bash_history \
    /var/log/journal/old-machine; do
    test ! -e "$file"
done
test ! -s /var/log/fixture.log
test -s /etc/ssh/ssh_config.fixture
bash /srv/assets/seal-image.sh --image-root
systemd-machine-id-setup
first_id=$(cat /etc/machine-id)
[[ "$first_id" =~ ^[0-9a-f]{32}$ ]]
test "$first_id" != 11111111111111111111111111111111
test "$first_id" != 22222222222222222222222222222222
test "$(cat /var/lib/dbus/machine-id)" = "$first_id"
systemd-machine-id-setup
test "$(cat /etc/machine-id)" = "$first_id"
echo 'PASS: sealing, idempotence, machine-id initialization and persistence'
