#!/bin/bash
set -euxo pipefail
curl -LsSf https://astral.sh/uv/install.sh | sh

## clone repo and install
cd /home/bracketbot
git clone -b ipc https://oauth2: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@github.com/raghavauppuluri13/BracketBotOS.git
cd BracketBotOS
./install

# customize

NEW_HOSTNAME="orange"
# Set hostname immediately
sudo hostnamectl set-hostname "$NEW_HOSTNAME"
# Persist it in /etc/hostname
echo "$NEW_HOSTNAME" | sudo tee /etc/hostname
# Update /etc/hosts (replace old hostname with new one)
sudo sed -i "s/127\.0\.1\.1\s\+.*/127.0.1.1\t$NEW_HOSTNAME/" /etc/hosts
# (Optional) Print new hostname
echo "Hostname set to: $NEW_HOSTNAME"
## initialize bb user
NAME=bracketbot; usermod -l "$NAME" -d "/home/$NAME" -m dietpi && groupmod -n "$NAME" dietpi && sed -i "s/^dietpi/$NAME/" /etc/sudoers.d/dietpi && mv /etc/sudoers.d/dietpi /etc/sudoers.d/"$NAME"

sudo apt purge ifupdown isc-dhcp-client isc-dhcp-server \
                net-tools      # if you never need old `ifconfig`
sudo apt autoremove

sudo systemctl disable --now \
       networking.service \
       ifupdown-pre.service \
       ifup@wlan0.service ifup@eth0.service \
       dietpi-wifi-monitor.service
# Prevent accidental resurrection
sudo systemctl mask networking.service ifupdown-pre.service

sudo cp /etc/network/interfaces{,.bak}
printf "auto lo\niface lo inet loopback\n" | sudo tee /etc/network/interfaces

sudo mkdir -p /etc/network/interfaces.d.disabled
sudo mv /etc/network/interfaces.d/* /etc/network/interfaces.d.disabled/ 2>/dev/null || true

# Make sure the kernel devices are now managed by NM
sudo nmcli dev set wlan0 managed yes
sudo nmcli dev set eth0  managed yes

# Optional: keep Wi‑Fi power‑save off when associated
sudo tee /etc/NetworkManager/conf.d/wifi_powersave.conf <<'EOF'
[connection]
wifi.powersave = 2
EOF

sudo systemctl restart NetworkManager