"""Read the kernel neighbour table without shelling out to `arp` (net-tools)."""


def read_arp_table():
    """Return {ip: mac} for complete entries in /proc/net/arp (MACs lower-case, colon form)."""
    table = {}
    try:
        with open('/proc/net/arp') as f:
            next(f, None)  # header
            for line in f:
                parts = line.split()
                if len(parts) < 4:
                    continue
                ip, flags, mac = parts[0], parts[2], parts[3].lower()
                if flags == '0x0' or mac == '00:00:00:00:00:00':
                    continue  # incomplete entry
                table[ip] = mac
    except OSError:
        pass
    return table


def mac_for_ip(ip):
    return read_arp_table().get(ip)
