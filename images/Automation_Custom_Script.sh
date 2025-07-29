#!/bin/bash
set -euxo pipefail

# add overlay for uart2-m0
mkdir -p /boot/overlay-user
cp /boot/dtb/rockchip/overlay/rk3588-uart2-m0.dtbo /boot/overlay-user/

# make bracketbot the only user
deluser --remove-home dietpi
rm -rf /home/dietpi

adduser --disabled-password --gecos "" bracketbot
echo "bracketbot:1234" | chpasswd

usermod -aG sudo bracketbot
SUDOERS_FILE="/etc/sudoers.d/bracketbot"
echo "bracketbot ALL=(ALL) NOPASSWD:ALL" > "$SUDOERS_FILE"
chmod 0440 "$SUDOERS_FILE"

# install bracketbot
runasuser() {
       su - bracketbot -c "cd /home/bracketbot; source ~/.bashrc; $*"
}
runasuser "curl -LsSf https://astral.sh/uv/install.sh | sh"
runasuser "uv python install 3.11"
runasuser "git clone -b ipc https://oauth2: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@github.com/raghavauppuluri13/BracketBotOS.git"
runasuser "cd BracketBotOS; uv run ./install"
# allows uv python to set process priority
runasuser "sudo setcap 'cap_sys_nice=eip' \$(readlink -f \$(uv python find))"
runasuser "sudo setcap 'cap_sys_nice=eip' \$(nix-build 'https://github.com/NixOS/nixpkgs/archive/63dacb46bf939521bdc93981b4cbb7ecb58427a0.tar.gz' -A python311 --no-out-link)/bin/python3.11"

# disable spammy kernel logs
echo 'dmesg -n 1' >> /etc/rc.local

# Use NetworkManager instead of ifupdown
sudo apt purge -y ifupdown isc-dhcp-client isc-dhcp-server

sudo systemctl disable --now \
       ifupdown-pre.service \
       dnsmasq.service \
       ifup@wlan0.service ifup@eth0.service \
       dietpi-wifi-monitor.service || true
sudo systemctl mask networking.service ifupdown-pre.service
printf "auto lo\niface lo inet loopback\n" | sudo tee /etc/network/interfaces

# disable mac randomization
sudo tee /etc/NetworkManager/conf.d/90-disable-mac-rand.conf >/dev/null <<'EOF'
[device]
wifi.scan-rand-mac-address=no

[connection]
wifi.cloned-mac-address=permanent
EOF
sudo systemctl restart NetworkManager

# add bracketbot to dialout and video groups
sudo usermod -aG dialout bracketbot
sudo usermod -aG video bracketbot

echo "Rebooting..."
sudo reboot