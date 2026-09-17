import socket
import struct
import network

MCAST_GRP = "224.0.0.251"
MCAST_PORT = 5353


def _pack_name(name):
    out = b""
    for part in name.split("."):
        out += bytes([len(part)]) + part.encode()
    return out + b"\x00"


def _parse_qname(data, offset):
    labels = []
    while True:
        length = data[offset]
        if length == 0:
            offset += 1
            break
        if length & 0xC0:
            # Kompressionszeiger - in eingehenden Anfragen nicht zu erwarten,
            # aber sicherheitshalber abbrechen statt falsch zu parsen
            offset += 2
            break
        offset += 1
        labels.append(data[offset:offset + length].decode())
        offset += length
    return ".".join(labels), offset


def run(hostname="raytec"):
    """Minimaler mDNS-Responder: beantwortet A-Anfragen fuer <hostname>.local
    mit der aktuellen WLAN-IP. Blockiert dauerhaft - auf zweitem Core
    (_thread) laufen lassen, parallel zum Webserver."""
    fqdn = hostname + ".local"
    wlan = network.WLAN(network.STA_IF)

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(socket.getaddrinfo("0.0.0.0", MCAST_PORT)[0][-1])
    local_ip = wlan.ifconfig()[0]
    mreq = (bytes(int(x) for x in MCAST_GRP.split(".")) +
            bytes(int(x) for x in local_ip.split(".")))
    s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

    print("mDNS-Responder laeuft fuer", fqdn)

    while True:
        try:
            data, sender = s.recvfrom(512)
        except Exception as e:
            print("mDNS recv-Fehler:", e)
            continue
        try:
            if len(data) < 12:
                continue
            tid, flags, qdcount = struct.unpack("!HHH", data[0:6])
            if qdcount < 1 or (flags & 0x8000):
                continue  # nur Anfragen (kein QR-Bit), mind. eine Frage
            name, offset = _parse_qname(data, 12)
            if offset + 4 > len(data):
                continue
            qtype, qclass = struct.unpack("!HH", data[offset:offset + 4])
            if name.lower() != fqdn.lower() or qtype not in (1, 255):
                continue
            if not wlan.isconnected():
                continue
            ip = wlan.ifconfig()[0]
            ip_bytes = bytes(int(x) for x in ip.split("."))
            resp = struct.pack("!HHHHHH", tid, 0x8400, 0, 1, 0, 0)
            resp += _pack_name(fqdn)
            resp += struct.pack("!HHIH", 1, 1, 120, 4)
            resp += ip_bytes
            s.sendto(resp, (MCAST_GRP, MCAST_PORT))
        except Exception as e:
            print("mDNS Verarbeitungsfehler:", e)
