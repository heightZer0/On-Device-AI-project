"""mDNS 광고(D-05 제안). zeroconf 가 없거나 실패해도 서버는 계속 동작한다."""
import logging
import socket

log = logging.getLogger("p2.mdns")


class Mdns:
    def __init__(self, cfg):
        self.cfg, self._zc, self._info = cfg, None, None

    def start(self):
        m = self.cfg["mdns"]
        if not m.get("enabled"):
            return
        try:
            from zeroconf import ServiceInfo, Zeroconf
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("10.255.255.255", 1))          # UDP: 패킷은 나가지 않고 로컬 IP만 얻는다
            ip = s.getsockname()[0]
            s.close()
            stype = m["service_type"] + ".local."
            self._info = ServiceInfo(stype, f"{m['name']}.{stype}", addresses=[socket.inet_aton(ip)],
                                     port=self.cfg["server"]["port"])
            self._zc = Zeroconf()
            self._zc.register_service(self._info)
        except Exception as e:
            log.warning("mdns disabled: %s", type(e).__name__)

    def stop(self):
        try:
            if self._zc:
                self._zc.unregister_service(self._info)
                self._zc.close()
        except Exception:
            pass
