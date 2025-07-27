#!/usr/bin/env bash

# Define the image file names
RPI5="DietPi_OrangePi5Ultra-ARMv8-Bookworm.img.xz"
ORANGE_PI="DietPi_RPi5-ARMv8-Bookworm.img.xz"

# Check if an argument was provided
if [ -z "$1" ]; then
    echo "Error: Please specify 'rpi5' or 'orange_pi' as an argument"
    exit 1
fi

# Set the image file based on the argument
case "$1" in
    rpi5)
        IMAGE=$RPI5
        ;;
    orange_pi)
        IMAGE=$ORANGE_PI
        ;;
    *)
        echo "Error: Invalid argument. Use 'rpi5' or 'orange_pi'"
        exit 1
        ;;
esac

# Set the DIETPI_URL with the selected image
DIETPI_URL="https://dietpi.com/downloads/images/$IMAGE"
IMG_XZ_NAME="${DIETPI_URL##*/}"
IMG_NAME="${IMG_XZ_NAME%.xz}"
DEVICE=($(lsblk -dn -o NAME | grep -E '^sd' | sort | sed 's|^|/dev/|'))

# Step 1: Download image
if [[ -f "$IMG_NAME" ]]; then
  echo "[*] $IMG_NAME already exists, skipping download and decompression."
elif [[ -f "$IMG_XZ_NAME" ]]; then
  echo "[*] $IMG_XZ_NAME already exists, skipping download."
  echo "[*] Decompressing $IMG_XZ_NAME..."
  xz -dk "$IMG_XZ_NAME"
else
  echo "[*] Downloading DietPi image..."
  wget -q --show-progress "$DIETPI_URL"
  echo "[*] Decompressing $IMG_XZ_NAME..."
  xz -dk "$IMG_XZ_NAME"
fi

# Step 2: Flash
echo "[*] Flashing $IMG_NAME to $DEVICE..."
sudo dd if="$IMG_NAME" of="$DEVICE" bs=4M conv=fsync status=progress

echo "[*] Injecting custom config into root partition..."
sudo mkdir -p mnt
sudo mount ${DEVICE}2 mnt
sudo cp dietpi* mnt/boot
sudo cp Automation_Custom_Script.sh mnt/boot
sudo umount mnt

# Step 3: Sync
sync
echo "[✔] Flash complete. $IMG_NAME written to $DEVICE"
