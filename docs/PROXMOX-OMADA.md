# Running the base station as a Proxmox VM with Omada APs

Cameras talk to the base station at layer 2 (DHCP from it, then TCP 4000 to
172.14.0.1), so the camera SSID is put on its own VLAN and only the base-station
VM sits on that VLAN. Cameras get no route to the internet.

```
Arlo Pro 4 ))) Omada EAP (SSID NETGEARxx, 2.4 GHz, WPA2-AES, VLAN 14)
                    │ tagged VLAN 14 over the normal LAN cabling
Proxmox host: ens9 ── ens9.14 ── vmbr1 ── VM net1 = eth1 172.14.0.1/24 (dnsmasq, arlo :4000)
              ens9 ── vmbr0 ───────────── VM net0 = eth0 LAN (viewer :3003, API :5000, RTSP :8554)
```

## 1. Proxmox: camera bridge

`/etc/network/interfaces` (then `ifreload -a`; existing guests are untouched):

```
auto ens9.14
iface ens9.14 inet manual

auto vmbr1
iface vmbr1 inet manual
	bridge-ports ens9.14
	bridge-stp off
	bridge-fd 0
```

## 2. VM

Debian 12 genericcloud image, 2 vCPU, 2 GB (balloon 1 GB), 32 GB disk.
Debian 12 (Python 3.11) matters: the pinned Flask 1.x stack does not build on 3.13.

```bash
qm create 105 --name arlo-base --machine q35 --cores 2 --memory 2048 --balloon 1024 \
  --net0 virtio,bridge=vmbr0 --net1 virtio,bridge=vmbr1 --scsihw virtio-scsi-single \
  --agent enabled=1 --onboot 1 --serial0 socket --vga serial0
qm set 105 --scsi0 local-zfs:0,import-from=/var/lib/vz/template/iso/debian-12-genericcloud-amd64.qcow2,discard=on,ssd=1
qm resize 105 scsi0 32G
# cloud-init drive on SCSI, NOT ide2: the Debian "cloud" kernel has no AHCI driver,
# so on q35 an ide2 cloud-init drive is invisible and cloud-init silently does nothing.
qm set 105 --scsi1 local-zfs:cloudinit --boot order=scsi0 --ciuser admin \
  --sshkeys ~/.ssh/authorized_keys --ipconfig0 ip=dhcp --ipconfig1 ip=172.14.0.1/24
qm start 105
```

Then inside the VM: copy the repo, `cp config/install.conf.example config/install.conf`, set
`AP_MODE="external"`, `ARLO_INTERFACE="eth1"`, `ETH_INTERFACE="eth0"`, SSID/password, and run
`sudo scripts/install.sh --yes`.

## 3. Omada

* Create a WPA2-Personal / AES, 2.4 GHz-only SSID with the same name + password as
  `WIFI_SSID` / `WIFI_PASSWORD`, VLAN = custom VLAN ID 14, PMF off, 802.11r off.
* No LAN network / gateway interface is needed for VLAN 14 - the VM is the only
  "router" on it, and it does not forward.
* Limit the SSID to the APs that cover the cameras with per-AP *WLAN override*
  (disable the SSID on the other APs).

## 4. Pairing (WPS)

Arlo cameras receive the SSID/password through WPS push-button when their Sync
button is pressed; Omada APs have no WPS. Options:

1. **USB WiFi adapter passed through to the VM** (`qm set 105 --usb0 host=<vid:pid>`),
   `PAIRING_WIFI_INTERFACE=wlx...` in install.conf, re-run the installer, then
   `sudo arlo-pair` and press Sync on the camera. The adapter is only used for the
   minute of pairing; afterwards the camera joins the Omada SSID (same SSID/PSK).
2. Any spare router with WPS, in AP mode, same SSID/PSK, its LAN port on VLAN 14 -
   press its WPS button, then the camera's Sync button.
3. No VLAN-capable switch? Use the spare router **standalone** (power only, no
   cables): same SSID/PSK, 2.4 GHz only, WPA2-AES, DHCP server off, WPS on. Press its
   WPS button, then the camera's Sync button; as soon as WPS succeeds, power the
   router off. The camera has the credentials, finds the same SSID on the Omada AP,
   gets DHCP from the VM and registers. (Untested; if the camera drops the
   credentials because it could not register, use option 1 or 2.)

Arlo Pro 3/4 must be **removed from the Arlo account and factory reset** first.
