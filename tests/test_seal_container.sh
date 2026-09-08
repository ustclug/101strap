#!/bin/bash
# This fixture changes system files; run only in a disposable container.
# Mount the repository read-only at /srv.
# ShellCheck 0.11 misreports calls to fail() inside these functions;
# all functions are defined before main runs.
# shellcheck disable=SC2218
set -euo pipefail

original_machine_id=11111111111111111111111111111111
original_dbus_id=22222222222222222222222222222222
journal_directory=/var/log/journal/old-machine
log_file=/var/log/fixture.log
ssh_config=/etc/ssh/ssh_config.fixture
ssh_config_content='keep this config'
private_files=(
    /var/lib/systemd/random-seed
    /var/lib/NetworkManager/secret_key
    /var/lib/NetworkManager/seen-bssids
    /var/lib/NetworkManager/timestamps
    /etc/ssh/ssh_host_fixture_key
    /root/.bash_history
    /home/seal-test/.bash_history
)

fail() {
    echo "FAIL: $*" >&2
    exit 1
}

prepare_fixture() {
    install -d /usr/share/101strap /var/lib/dbus /var/lib/systemd \
        /var/lib/NetworkManager /etc/ssh /home/seal-test "$journal_directory"
    printf 'test fixture\n' > /usr/share/101strap/build-info.txt
    # Remove existing IDs first: either path could be a symlink in the image.
    rm -f /etc/machine-id /var/lib/dbus/machine-id
    printf '%s\n' "$original_machine_id" > /etc/machine-id
    printf '%s\n' "$original_dbus_id" > /var/lib/dbus/machine-id

    local file
    for file in "${private_files[@]}" "$log_file" "$journal_directory/system.journal"; do
        printf 'private build data\n' > "$file"
    done
    printf '%s\n' "$ssh_config_content" > "$ssh_config"
}

verify_sealed_image() {
    [[ -f /etc/machine-id && ! -L /etc/machine-id ]] || fail '/etc/machine-id must remain a regular file'
    [[ ! -s /etc/machine-id ]] || fail '/etc/machine-id must be empty'
    [[ -L /var/lib/dbus/machine-id ]] || fail 'D-Bus machine-id must be a symlink'
    [[ "$(readlink /var/lib/dbus/machine-id)" == /etc/machine-id ]] ||
        fail 'D-Bus machine-id must point to /etc/machine-id'

    local file
    for file in "${private_files[@]}" "$journal_directory"; do
        [[ ! -e "$file" && ! -L "$file" ]] || fail "Private build data remains: $file"
    done
    [[ -f "$log_file" ]] || fail "Log path must be preserved: $log_file"
    [[ ! -s "$log_file" ]] || fail "Log contents must be cleared: $log_file"
    [[ "$(cat "$ssh_config")" == "$ssh_config_content" ]] ||
        fail "SSH client configuration changed: $ssh_config"
}

verify_machine_id_initialization() {
    systemd-machine-id-setup
    local first_id
    first_id=$(cat /etc/machine-id)
    [[ "$first_id" =~ ^[0-9a-f]{32}$ ]] || fail "Invalid generated machine-id: $first_id"
    [[ "$first_id" != "$original_machine_id" && "$first_id" != "$original_dbus_id" ]] ||
        fail 'Generated machine-id reused a build-time ID'
    [[ "$(cat /var/lib/dbus/machine-id)" == "$first_id" ]] ||
        fail 'D-Bus and systemd machine IDs differ'

    systemd-machine-id-setup
    [[ "$(cat /etc/machine-id)" == "$first_id" ]] ||
        fail 'Repeated machine-id initialization changed the ID'
}

main() {
    [[ -f /run/.containerenv || -f /.dockerenv ]] ||
        fail 'Run this test in a disposable container with the repo at /srv'
    [[ $EUID == 0 ]] || fail 'Run this test as root inside the disposable container'

    prepare_fixture
    echo 'Checking image sealing'
    bash /srv/assets/seal-image.sh --image-root
    verify_sealed_image

    echo 'Checking repeated sealing'
    bash /srv/assets/seal-image.sh --image-root
    verify_sealed_image

    echo 'Checking machine-id initialization and repeated setup'
    verify_machine_id_initialization
    echo 'PASS: sealing, repeated sealing, machine-id initialization and repeated setup'
}

main "$@"
