#!/bin/bash
# Sourced only by rootfs/run-stage.sh.
# shellcheck disable=SC2034,SC2154
# Note: xfce4-statusnotifier is no longer needed.
inspkg desktop-base xubuntu-desktop-minimal dpkg vim htop strace bash-completion \
    python3-venv shellcheck jq manpages manpages-dev openssh-client curl \
    network-manager-gnome xfce4-terminal xfce4-indicator-plugin xfce4-whiskermenu-plugin mugshot \
    labwc xwayland \
    xfce4-pulseaudio-plugin pipewire-pulse pipewire-alsa wireplumber pavucontrol \
    software-properties-gtk language-pack-zh-hans language-pack-gnome-zh-hans fonts-noto-cjk fcitx5 fcitx5-chinese-addons fcitx5-config-qt im-config \
    language-selector-gnome fcitx5-frontend-gtk2 fcitx5-frontend-gtk3 fcitx5-frontend-gtk4 fcitx5-frontend-qt5 fcitx5-frontend-qt6 \
    mate-calc mousepad build-essential eog file-roller baobab evince synaptic \
    adwaita-icon-theme command-not-found gparted policykit-1-gnome \
    iputils-ping netplan.io wget gdb git flatpak xdg-desktop-portal-gtk \
    libgles2 psmisc

if [[ "$ARCH" == amd64 ]]; then
    inspkg xserver-xorg-video-vmware xserver-xorg-video-fbdev xserver-xorg-video-qxl \
        open-vm-tools open-vm-tools-desktop virtualbox-guest-x11
else
    inspkg spice-vdagent
fi

# Update command-not-found database and upgrade packages
chdo apt update
chdo apt upgrade -y

inspkg gvfs
