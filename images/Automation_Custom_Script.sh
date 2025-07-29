#!/bin/bash
set -euxo pipefail

deluser --remove-home dietpi
rm -rf /home/dietpi

adduser --disabled-password --gecos "" bracketbot
echo "bracketbot:1234" | chpasswd

usermod -aG sudo bracketbot
SUDOERS_FILE="/etc/sudoers.d/bracketbot"
echo "bracketbot ALL=(ALL) NOPASSWD:ALL" > "$SUDOERS_FILE" chmod 0440 "$SUDOERS_FILE"

runasuser() {
       su - bracketbot -c "cd /home/bracketbot; source ~/.bashrc; $*"
}
runasuser "curl -LsSf https://astral.sh/uv/install.sh | sh"
runasuser "uv python install 3.11"
# clone repo and install
runasuser "git clone -b ipc https://oauth2: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@github.com/raghavauppuluri13/BracketBotOS.git"
runasuser "cd BracketBotOS; uv run ./install"

# allows uv python to run as nice
runasuser "sudo setcap 'cap_sys_nice=eip' \$(readlink -f \$(uv python find))"

# disable spammy kernel logs
echo 'dmesg -n 1' >> /etc/rc.local

sudo apt purge -y ifupdown isc-dhcp-client isc-dhcp-server

sudo systemctl disable --now \
       ifupdown-pre.service \
       ifup@wlan0.service ifup@eth0.service \
       dietpi-wifi-monitor.service || true
# Prevent accidental resurrection
sudo systemctl mask networking.service ifupdown-pre.service

printf "auto lo\niface lo inet loopback\n" | sudo tee /etc/network/interfaces

sudo tee /etc/NetworkManager/conf.d/90-disable-mac-rand.conf >/dev/null <<'EOF'
[device]
wifi.scan-rand-mac-address=no

[connection]
wifi.cloned-mac-address=permanent
EOF
sudo systemctl restart NetworkManager

echo "Rebooting..."
sudo reboot