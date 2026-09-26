"""Host-side check for lib/captiveportal.py. Run: python3 tests/test_captiveportal.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "firmware", "lib"))

from captiveportal import CaptiveDNS  # noqa: E402

IP = "192.168.4.1"


class FakeSocket:
    def __init__(self):
        self.blocking = None
        self.bound = None

    def setblocking(self, flag):
        self.blocking = flag

    def bind(self, addr):
        self.bound = addr

    def recvfrom_into(self, buf):
        raise OSError("no data (unused by these tests)")

    def sendto(self, data, addr):
        raise OSError("no send (unused by these tests)")


class FakePool:
    AF_INET = 0
    SOCK_DGRAM = 1

    def socket(self, family, type_):
        assert family == self.AF_INET and type_ == self.SOCK_DGRAM
        return FakeSocket()


def make_dns(ip=IP):
    return CaptiveDNS(FakePool(), ip)


def qname(name):
    out = b""
    for label in name.split("."):
        out += bytes([len(label)]) + label.encode("ascii")
    return out + b"\x00"


def build_query(tid, name, qtype, qclass=1):
    header = tid.to_bytes(2, "big")
    header += (0x0100).to_bytes(2, "big")  # standard query, RD=1
    header += (1).to_bytes(2, "big")       # QDCOUNT=1
    header += (0).to_bytes(2, "big")       # ANCOUNT
    header += (0).to_bytes(2, "big")       # NSCOUNT
    header += (0).to_bytes(2, "big")       # ARCOUNT
    question = qname(name) + qtype.to_bytes(2, "big") + qclass.to_bytes(2, "big")
    return header + question


def header_fields(resp):
    tid = (resp[0] << 8) | resp[1]
    flags = (resp[2] << 8) | resp[3]
    qdcount = (resp[4] << 8) | resp[5]
    ancount = (resp[6] << 8) | resp[7]
    return tid, flags, qdcount, ancount


def test_a_query_answers_with_configured_ip():
    dns = make_dns()
    req = build_query(0x1234, "captive.apple.com", 1)  # A
    resp = dns._build(bytearray(req), len(req))
    assert resp is not None
    tid, flags, qdcount, ancount = header_fields(resp)
    assert tid == 0x1234
    assert flags == 0x8180, hex(flags)  # QR=1 RD=1 RA=1 RCODE=0
    assert qdcount == 1
    assert ancount == 1
    assert resp[-4:] == bytes(int(p) for p in IP.split(".")), resp[-4:]


def test_any_query_also_answered():
    dns = make_dns()
    req = build_query(0xABCD, "example.com", 255)  # ANY
    resp = dns._build(bytearray(req), len(req))
    assert resp is not None
    tid, flags, qdcount, ancount = header_fields(resp)
    assert flags == 0x8180
    assert ancount == 1
    assert resp[-4:] == bytes(int(p) for p in IP.split("."))


def test_aaaa_query_no_answer_but_well_formed():
    dns = make_dns()
    req = build_query(0x5555, "captive.apple.com", 28)  # AAAA
    resp = dns._build(bytearray(req), len(req))
    assert resp is not None
    tid, flags, qdcount, ancount = header_fields(resp)
    assert tid == 0x5555
    assert flags == 0x8180  # still NOERROR, just no answer records
    assert qdcount == 1
    assert ancount == 0
    assert len(resp) == 12 + len(qname("captive.apple.com")) + 4  # header + question only


def test_malformed_short_packet_dropped():
    dns = make_dns()
    req = b"\x00\x01\x02\x03\x04"  # 5 bytes: shorter than a DNS header
    resp = dns._build(bytearray(req.ljust(12, b"\x00")), len(req))
    assert resp is None


def test_truncated_question_dropped():
    dns = make_dns()
    # Full 12-byte header claiming one question, but the question is cut off.
    req = build_query(0x0001, "a", 1)[:14]
    buf = bytearray(req)
    resp = dns._build(buf, len(req))
    assert resp is None


def test_transaction_id_echoed():
    dns = make_dns()
    for tid in (0x0000, 0x0001, 0xFFFF, 0x8000):
        req = build_query(tid, "captive.apple.com", 1)
        resp = dns._build(bytearray(req), len(req))
        assert resp is not None
        got_tid, _, _, _ = header_fields(resp)
        assert got_tid == tid, (tid, got_tid)


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
            n += 1
    print("ok", n, "tests")
