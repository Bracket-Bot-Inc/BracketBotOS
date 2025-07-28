#!/bin/bash
set -euxo pipefail
adduser bracketbot
usermod -aG sudo bracketbot
deluser --remove-home dietpi
rm -rf /home/dietpi

runasuser() {
       su - bracketbot -c "cd /home/bracketbot; source ~/.bashrc; $*"
}
runasuser "curl -LsSf https://astral.sh/uv/install.sh | sh"
runasuser "uv python install 3.11"
## clone repo and install
runasuser "git clone -b ipc https://oauth2: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@github.com/raghavauppuluri13/BracketBotOS.git"
runasuser "cd BracketBotOS; uv run ./install"

sudo apt purge ifupdown isc-dhcp-client isc-dhcp-server

sudo systemctl disable --now \
       ifupdown-pre.service \
       ifup@wlan0.service ifup@eth0.service \
       dietpi-wifi-monitor.service
# Prevent accidental resurrection
sudo systemctl mask networking.service ifupdown-pre.service

printf "auto lo\niface lo inet loopback\n" | sudo tee /etc/network/interfaces

sudo mkdir -p /etc/network/interfaces.d.disabled
sudo mv /etc/network/interfaces.d/* /etc/network/interfaces.d.disabled/ 2>/dev/null || true

# Make sure the kernel devices are now managed by NM
sudo nmcli dev set wlan0 managed yes
sudo nmcli dev set eth0  managed yes

sudo systemctl restart NetworkManager

sudo ip link set wlan0 down
sudo ip link set wlan0 up

echo "Rebooting..."
sudo reboot