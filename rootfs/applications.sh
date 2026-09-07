#!/bin/bash
# Sourced only by rootfs/run-stage.sh.
# shellcheck disable=SC2034,SC2154
# Use mirrored flatpak remote.
chdo flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
if [[ "$BUILD_MIRROR_MODE" == ustc ]]; then
    chdo flatpak remote-modify flathub --url=https://mirrors.ustc.edu.cn/flathub
fi
chdo flatpak update -y

chdo echo "flatpak is OK."

chdo echo "---- Install web browser ---"

chdo install -d -m 0755 /etc/apt/keyrings
chdo wget -q https://packages.mozilla.org/apt/repo-signing-key.gpg -O- | chdo tee /etc/apt/keyrings/packages.mozilla.org.asc > /dev/null
MOZILLA_FINGERPRINT=$(chdo gpg --show-keys --with-colons /etc/apt/keyrings/packages.mozilla.org.asc | awk -F: '$1 == "fpr" && !found { print $10; found=1 }')
if [[ "$MOZILLA_FINGERPRINT" != 35BAA0B33E9EB396F59CA838C0BA5CE6DC6315A3 ]]; then
    echo "Mozilla signing key fingerprint mismatch: $MOZILLA_FINGERPRINT" >&2
    exit 1
fi
chdo echo "deb [arch=$ARCH signed-by=/etc/apt/keyrings/packages.mozilla.org.asc] $MOZILLA_MIRROR mozilla main" | chdo tee /etc/apt/sources.list.d/mozilla.list > /dev/null
chdo echo '
Package: *
Pin: release a=mozilla
Pin-Priority: 1000
' | chdo tee /etc/apt/preferences.d/mozilla
chdo apt-get -o APT::Update::Error-Mode=any update
inspkg firefox firefox-l10n-zh-cn
