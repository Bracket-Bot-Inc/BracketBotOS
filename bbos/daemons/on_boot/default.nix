let 
pkgs = import (fetchTarball {
  url = "https://github.com/NixOS/nixpkgs/archive/63dacb46bf939521bdc93981b4cbb7ecb58427a0.tar.gz";
  sha256 = "sha256:1lr1h35prqkd1mkmzriwlpvxcb34kmhc9dnr48gkm8hh089hifmx";
}) {};
in
let 
on_boot = pkgs.writeShellApplication {
  name = "on_boot";
  runtimeInputs = [ pkgs.dnsmasq ];
  text = ''
    # initialize hotspot
    host=$(hostname)
    SSID="$host"
    PASSWORD="12345678"
    CONNECTION_NAME="Hotspot"
    VIRTUAL_IFACE="wlan0-ap"
    OS_CORES="0"

    set_irqs() {
        for irq in /proc/irq/*/smp_affinity_list; do
            case "$irq" in
                # Skip local timers, IPIs, arch_timer, etc. that cannot be moved
                */1/*|*/2/*|*/3/*|*/4/*|*/5/*|*/6/*|*/7/*|*/8/*|*/9/*|*/13/*|*/14/*|*/21/*|*/23/*)
                    continue
                    ;;
            esac
            # Try to set affinity; suppress all output and errors
            echo $OS_CORES > "$irq" 2>/dev/null || true
        done
    }
  
    create_virtual_interface() {
    if ! sudo iw dev | grep -q "$VIRTUAL_IFACE"; then
        echo "Creating virtual interface $VIRTUAL_IFACE..."
        sudo iw dev wlan0 interface add "$VIRTUAL_IFACE" type __ap || echo "Failed to add virtual interface. Is iw installed?"
    else
        echo "Virtual interface $VIRTUAL_IFACE already exists."
    fi
    }
    bring_up_interface() {
        echo "Bringing up interface $VIRTUAL_IFACE..."
        sudo ip link set "$VIRTUAL_IFACE" up || echo "Failed to bring up interface $VIRTUAL_IFACE"
        sudo ip link set "$VIRTUAL_IFACE" multicast on
    }
    configure_hotspot() {
        echo "Configuring NetworkManager hotspot..."
        if nmcli c show "$CONNECTION_NAME" > /dev/null 2>&1; then
            echo "Deleting existing connection '$CONNECTION_NAME'..."
            sudo nmcli connection delete "$CONNECTION_NAME" || echo "Failed to delete existing connection $CONNECTION_NAME"
            sleep 1
        fi
        echo "Creating new hotspot connection '$CONNECTION_NAME'..."
        sudo nmcli connection add type wifi ifname "$VIRTUAL_IFACE" con-name "$CONNECTION_NAME" autoconnect yes ssid "$SSID" || echo "Failed to add connection $CONNECTION_NAME"
        sleep 1
        sudo nmcli connection modify "$CONNECTION_NAME" 802-11-wireless.mode ap || echo "Failed: set mode ap"
        sudo nmcli connection modify "$CONNECTION_NAME" 802-11-wireless.band bg || echo "Failed: set band bg"
        sudo nmcli connection modify "$CONNECTION_NAME" ipv4.method shared || echo "Failed: set ipv4 shared"
        sudo nmcli connection modify "$CONNECTION_NAME" wifi-sec.key-mgmt wpa-psk || echo "Failed: set key-mgmt wpa-psk"
        sudo nmcli connection modify "$CONNECTION_NAME" wifi-sec.psk "$PASSWORD" || echo "Failed: set psk"
        sleep 1
        echo "Activating hotspot connection '$CONNECTION_NAME'..."
        sudo nmcli connection up "$CONNECTION_NAME" || echo "Failed to bring up connection $CONNECTION_NAME"
        sleep 1
    }
    configure_ssh() {
        echo "Ensuring SSH service is enabled and running..."
        if ! systemctl is-active ssh >/dev/null 2>&1; then
            sudo systemctl enable ssh || echo "Failed: enable ssh"
            sudo systemctl start ssh || echo "Failed: start ssh"
        else
            sudo systemctl restart ssh || echo "Failed: restart ssh"
        fi
    }

    create_virtual_interface
    bring_up_interface
    configure_hotspot
    configure_ssh

    echo "Access Point Setup script finished."  

    
  '';
};
in pkgs.buildEnv {
  name = "on_boot";
  paths = [ on_boot ];
}
