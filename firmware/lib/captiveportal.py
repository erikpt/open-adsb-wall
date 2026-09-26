"""Minimal captive-portal DNS responder (issue #21).

AP mode has no internet, so every DNS lookup a joining phone/laptop makes --
including its own captive-portal detection probes -- would otherwise just
time out, and the OS never learns there's a sign-in page waiting. Answering
every query with the AP's own IPv4 address (like a consumer router's setup
AP) makes those probes resolve to this device instead, so the HTTP-side
redirects in code.py can actually be reached and the OS auto-pops its
captive-portal sign-in browser.

Not a general resolver -- there is nothing upstream to forward to, and none
would be reachable from an AP-mode radio anyway. Handles exactly one
question of class IN, type A or ANY. Anything else (AAAA, HTTPS/SVCB, ...)
gets a NOERROR reply with no answer so the resolver moves on to an A query
instead of timing out; anything malformed or multi-question is dropped.
"""


def _ipv4_bytes(ip):
    return bytes(int(part) for part in ip.split("."))


class CaptiveDNS:
    """UDP DNS responder bound to :53 on `pool`. Call poll() once per loop tick."""

    def __init__(self, pool, ip):
        self._ip = _ipv4_bytes(ip)
        self._sock = pool.socket(pool.AF_INET, pool.SOCK_DGRAM)
        self._sock.setblocking(False)
        self._sock.bind(("0.0.0.0", 53))
        self._buf = bytearray(512)

    def poll(self):
        """Answer one pending query, if any is waiting. Never raises."""
        try:
            nbytes, addr = self._sock.recvfrom_into(self._buf)
        except OSError:
            return
        try:
            resp = self._build(self._buf, nbytes)
        except Exception as e:
            print("captiveportal: bad query", e)
            return
        if resp:
            try:
                self._sock.sendto(resp, addr)
            except OSError as e:
                print("captiveportal: send", e)

    def _build(self, buf, nbytes):
        """DNS reply bytes for one query, or None to drop it silently."""
        if nbytes < 12:
            return None
        req = bytes(buf[:nbytes])
        opcode = (req[2] >> 3) & 0x0F
        qdcount = (req[4] << 8) | req[5]
        if opcode != 0 or qdcount != 1:
            return None  # only a plain single-question lookup

        # Walk the QNAME (length-prefixed labels, 0x00 terminated) to find
        # where QTYPE/QCLASS start. Queries aren't expected to use name
        # compression (nothing precedes them to point back into) -- treat
        # one as malformed and drop it rather than guess.
        i = 12
        while True:
            if i >= nbytes:
                return None
            length = req[i]
            if length == 0:
                i += 1
                break
            if length & 0xC0:
                return None
            i += 1 + length
        if i + 4 > nbytes:
            return None
        qtype = (req[i] << 8) | req[i + 1]
        qclass = (req[i + 2] << 8) | req[i + 3]
        question = req[12:i + 4]

        answer_ok = qclass == 1 and qtype in (1, 255)  # IN, A or ANY
        ancount = 1 if answer_ok else 0

        out = bytearray(12)
        out[0:2] = req[0:2]                          # echo the transaction ID
        out[2:4] = (0x8180).to_bytes(2, "big")        # QR=1 RD=1 RA=1 RCODE=0
        out[4:6] = (1).to_bytes(2, "big")             # QDCOUNT
        out[6:8] = ancount.to_bytes(2, "big")         # ANCOUNT
        out += question
        if answer_ok:
            out += b"\xc0\x0c"                        # name: pointer to the question
            out += (1).to_bytes(2, "big")             # TYPE A
            out += (1).to_bytes(2, "big")             # CLASS IN
            out += (60).to_bytes(4, "big")            # TTL
            out += (4).to_bytes(2, "big")             # RDLENGTH
            out += self._ip
        return bytes(out)
