#!/bin/bash
# Sourced only by rootfs/run-stage.sh.
# shellcheck disable=SC2034,SC2154
cp /recipe/assets/toggle-hidpi "$ROOT/usr/local/bin/toggle-hidpi"
chmod +x "$ROOT/usr/local/bin/toggle-hidpi"

# Set xdg-user-dirs to English
mkdir -p "$ROOT/etc/skel/.config"
cat << 'EOF' > "$ROOT/etc/skel/.config/user-dirs.dirs"
# This file is written by xdg-user-dirs-update
# If you want to change or add directories, just edit the line you're
# interested in. All local changes will be retained on the next run.
# Format is XDG_xxx_DIR="$HOME/yyy", where yyy is a shell-escaped
# homedir-relative path, or XDG_xxx_DIR="/yyy", where /yyy is an
# absolute path. No other format is supported.
#
XDG_DESKTOP_DIR="$HOME/Desktop"
XDG_DOWNLOAD_DIR="$HOME/Downloads"
XDG_TEMPLATES_DIR="$HOME/Templates"
XDG_PUBLICSHARE_DIR="$HOME/Public"
XDG_DOCUMENTS_DIR="$HOME/Documents"
XDG_MUSIC_DIR="$HOME/Music"
XDG_PICTURES_DIR="$HOME/Pictures"
XDG_VIDEOS_DIR="$HOME/Videos"
EOF
echo "zh_CN" > "$ROOT/etc/skel/.config/user-dirs.locale"
mkdir -p "$ROOT/etc/skel/Desktop" "$ROOT/etc/skel/Downloads" "$ROOT/etc/skel/Templates" \
 "$ROOT/etc/skel/Public" "$ROOT/etc/skel/Documents" "$ROOT/etc/skel/Music" \
 "$ROOT/etc/skel/Pictures" "$ROOT/etc/skel/Videos"

# Install the project panel layout.
install -m 0644 /recipe/assets/xfce4-panel.xml "$ROOT/etc/xdg/xdg-xubuntu/xfce4/panel/default.xml"
# Remove "Mail reader"
sed -i "/mail-reader/d" "$ROOT/etc/xdg/xdg-xubuntu/menus/xfce-applications.menu"
sed -i "s/,xfce4-mail-reader.desktop//" "$ROOT/etc/xdg/xdg-xubuntu/xfce4/whiskermenu/defaults.rc"
# Remove the help shortcut to leave room for course applications.
sed -i "s/,xfhelp4.desktop//" "$ROOT/etc/xdg/xdg-xubuntu/xfce4/whiskermenu/defaults.rc"
# Use the system's default browser (Firefox).
sed -i "s/firefox/debian-sensible-browser/g" "$ROOT/etc/xdg/xdg-xubuntu/xfce4/helpers.rc"
# Use default selection color in xfce4-terminal
sed -i "/ColorSelectionUseDefault/d" "$ROOT/etc/xdg/xdg-xubuntu/xfce4/terminal/terminalrc"

# User and host configuration
# Use one XDG autostart entry for both Xfce X11 and Wayland sessions.
# im-config would otherwise start another daemon and force GTK_IM_MODULE on X11.
echo 'run_im none' > "$ROOT/etc/X11/xinit/xinputrc"
install -m 0644 "$ROOT/usr/share/applications/org.fcitx.Fcitx5.desktop" \
    "$ROOT/etc/xdg/autostart/org.fcitx.Fcitx5.desktop"

# https://fcitx-im.org/wiki/Using_Fcitx_5_on_Wayland
# LightDM loads /etc/environment through PAM for both session types.
cat << 'EOF' >> "$ROOT/etc/environment"
XMODIFIERS=@im=fcitx
QT_IM_MODULE=fcitx
QT_IM_MODULES="wayland;fcitx"
SDL_IM_MODULE=fcitx
EOF

# Leave GTK_IM_MODULE unset so native GTK Wayland clients use text-input-v3.
# GTK configuration and XSettings select fcitx for X11/XWayland clients.
echo 'gtk-im-module="fcitx"' > "$ROOT/etc/skel/.gtkrc-2.0"
for gtk_version in 3.0 4.0; do
    mkdir -p "$ROOT/etc/skel/.config/gtk-$gtk_version"
    cat << 'EOF' > "$ROOT/etc/skel/.config/gtk-$gtk_version/settings.ini"
[Settings]
gtk-im-module=fcitx
EOF
done
sed -i '/<property name="Gtk" type="empty">/a\    <property name="IMModule" type="string" value="fcitx"/>' \
    "$ROOT/etc/xdg/xdg-xubuntu/xfce4/xfconf/xfce-perchannel-xml/xsettings.xml"

# Work around GTK's symbolic SVG parser ignoring group transforms in elementary-xfce.
# Remove once fixed: https://github.com/shimmerproject/elementary-xfce/pull/541
echo 'GDK_DISABLE=icon-nodes' >> "$ROOT/etc/environment"

ln -sf /usr/share/zoneinfo/Asia/Shanghai "$ROOT/etc/localtime"
chdo dpkg-reconfigure --frontend noninteractive tzdata

echo "en_US.UTF-8 UTF-8" > "$ROOT/etc/locale.gen"
echo 'LANG=zh_CN.UTF-8
LANGUAGE="zh_CN.UTF-8"
LC_ALL="zh_CN.UTF-8"' > "$ROOT/etc/default/locale"
# /var/lib/locales/supported.d/zh-hans contains zh_CN.UTF-8
chdo locale-gen

chdo adduser --disabled-password --gecos "" "$IMAGE_USER"
echo "$IMAGE_USER:$PASSWORD" | chdo chpasswd
chdo adduser "$IMAGE_USER" sudo

echo "ustclug-linux101" > "$ROOT/etc/hostname"
echo "127.0.0.1 ustclug-linux101" >> "$ROOT/etc/hosts"

# Let NetworkManager manage networking
echo "network:
  version: 2
  renderer: NetworkManager" > "$ROOT/etc/netplan/01-netcfg.yaml"

# Let grub show menu for convenience of debugging
sed -i "s/GRUB_TIMEOUT_STYLE=hidden/GRUB_TIMEOUT_STYLE=menu/" "$ROOT/etc/default/grub"
sed -i "s/GRUB_TIMEOUT=0/GRUB_TIMEOUT=5/" "$ROOT/etc/default/grub"

# Show kernal messages at startup, instead of XUbuntu logo
chdo sed -i 's/quiet//g; s/splash//g; s/  / /g; s/="\s/="/g; s/\s"/"/g' /etc/default/grub

if [[ "$ARCH" == arm64 ]]; then
    # Keep graphical output while exposing boot diagnostics and a serial login.
    # shellcheck disable=SC2016
    echo 'GRUB_CMDLINE_LINUX="$GRUB_CMDLINE_LINUX console=tty0 console=ttyAMA0,115200"' >> "$ROOT/etc/default/grub"
fi

chdo apt-get autoremove -y
chdo apt-get clean
rm -rf "$ROOT/var/cache"/*
