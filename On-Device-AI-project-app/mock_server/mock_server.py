"""바자회 모의 기기 서버.

오렌지파이 없이 PC에서 앱을 테스트하기 위한 서버다. PROTOCOL.md 규격을 따른다.

설치:
    pip install aiohttp pillow zeroconf

실행:
    python mock_server.py               # 자동 시나리오
    python mock_server.py --manual      # 키보드로 상태 바꾸기
    python mock_server.py --port 8080 --no-mdns

수동 모드 키 입력 후 Enter:
    g = 바른 자세, b = 고개 숙임, c = 너무 가까움, t = 어깨 기울어짐, n = 자리 비움,
    a = 자동 시나리오로 돌아가기, f = 다음 자세설정 실패시키기, q = 종료

휴대폰과 PC가 같은 Wi-Fi에 있어야 한다. 에뮬레이터에서는 IP에 10.0.2.2 를 입력한다.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import math
import socket
import sys
import threading
import time

from aiohttp import web, WSMsgType

try:
    from PIL import Image, ImageDraw
except ImportError:  # 미리보기 없이도 동작
    Image = None

DEVICE_INFO = {
    "device_id": "mock-0001",
    "name": "바자회 모의 기기",
    "version": "1.0.0-mock",
    "camera": "front",
}

SCENARIO = [  # (지속 초, state, issues)
    (15, "good", []),
    (10, "bad", ["head_down"]),
    (8, "good", []),
    (8, "bad", ["too_close"]),
    (6, "no_person", []),
    (10, "good", []),
    (9, "bad", ["shoulder_tilt"]),
]


class Device:
    def __init__(self) -> None:
        self.mode = "idle"
        self.mode_since = time.monotonic()
        self.manual: tuple[str, list[str]] | None = None
        self.fail_next_calibration = False
        self.ws: web.WebSocketResponse | None = None
        self.volume = 70
        self.muted = False

    def set_mode(self, mode: str) -> None:
        if mode != self.mode:
            print(f"[mode] {self.mode} -> {mode}")
        self.mode = mode
        self.mode_since = time.monotonic()

    def elapsed(self) -> float:
        return time.monotonic() - self.mode_since

    def detect(self) -> dict:
        t = self.elapsed()
        return {"type": "detect", "face": t > 1.0, "shoulders": t > 1.5, "stable": t > 2.5}

    def status(self) -> dict:
        if self.manual:
            state, issues = self.manual
        else:
            total = sum(d for d, _, _ in SCENARIO)
            t = self.elapsed() % total
            for dur, state, issues in SCENARIO:
                if t < dur:
                    break
                t -= dur
        score = {"good": 92, "bad": 58, "no_person": 0}[state]
        score += int(4 * math.sin(time.monotonic()))
        return {
            "type": "status",
            "ts": int(time.time() * 1000),
            "state": state,
            "score": max(0, min(100, score)),
            "issues": issues,
            "metrics": {"shoulder_tilt_deg": 9.0 if "shoulder_tilt" in issues else 1.2,
                        "head_drop": 0.3 if "head_down" in issues else 0.02,
                        "distance_ratio": 1.3 if "too_close" in issues else 1.0},
        }


device = Device()


async def info(_: web.Request) -> web.Response:
    return web.json_response(DEVICE_INFO)


def render_frame(t: float) -> bytes:
    img = Image.new("RGB", (640, 480), (70, 86, 82))
    d = ImageDraw.Draw(img)
    sway = 6 * math.sin(t * 1.3)
    cx = 320 + sway
    d.ellipse((cx - 55, 90, cx + 55, 225), fill=(40, 52, 49))
    d.rectangle((cx - 25, 210, cx + 25, 265), fill=(40, 52, 49))
    d.rounded_rectangle((cx - 150, 255, cx + 150, 480), radius=60, fill=(40, 52, 49))
    d.text((12, 12), f"MOCK CAMERA  {time.strftime('%H:%M:%S')}", fill=(230, 240, 236))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=70)
    return buf.getvalue()


async def stream(request: web.Request) -> web.StreamResponse:
    if Image is None:
        return web.Response(status=503, text="pillow not installed")
    resp = web.StreamResponse(headers={
        "Content-Type": "multipart/x-mixed-replace; boundary=frame",
        "Cache-Control": "no-cache",
    })
    await resp.prepare(request)
    print("[stream] preview opened")
    start = time.monotonic()
    try:
        while True:
            jpg = render_frame(time.monotonic() - start)
            await resp.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                             + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n")
            await asyncio.sleep(0.1)
    except (ConnectionResetError, asyncio.CancelledError):
        pass
    finally:
        print("[stream] preview closed")
    return resp


async def ws_handler(request: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse(heartbeat=10)
    await ws.prepare(request)
    if device.ws is not None and not device.ws.closed:
        await device.ws.close()
    device.ws = ws
    print(f"[ws] app connected from {request.remote}")

    async def pump() -> None:
        while not ws.closed:
            if device.mode == "calibrate":
                await ws.send_json(device.detect())
            elif device.mode == "monitor":
                await ws.send_json(device.status())
            await asyncio.sleep(0.5)

    pump_task = asyncio.create_task(pump())
    try:
        async for msg in ws:
            if msg.type != WSMsgType.TEXT:
                continue
            try:
                data = json.loads(msg.data)
            except json.JSONDecodeError:
                continue
            kind = data.get("type")
            print(f"[recv] {data}")
            if kind == "mode":
                device.set_mode(data.get("mode", "idle"))
            elif kind == "calibrate":
                await asyncio.sleep(0.6)
                if device.fail_next_calibration:
                    device.fail_next_calibration = False
                    await ws.send_json({"type": "calibration", "ok": False, "reason": "unstable"})
                else:
                    await ws.send_json({"type": "calibration", "ok": True})
            elif kind == "session" and data.get("action") == "start":
                device.set_mode("monitor")
            elif kind == "config":
                device.volume = int(data.get("volume", device.volume))
                device.muted = bool(data.get("muted", device.muted))
                print(f"[config] volume={device.volume} muted={device.muted}")
            elif kind == "test_sound":
                if device.muted:
                    print("[sound] (음소거 상태라 재생 안 함)")
                else:
                    print(f"[sound] 띵동~ 테스트 안내음 재생 (볼륨 {device.volume}%)")
                    print("\a", end="", flush=True)  # 터미널 벨
    finally:
        pump_task.cancel()
        print("[ws] app disconnected")
    return ws


def keyboard_loop(loop: asyncio.AbstractEventLoop) -> None:
    keys = {
        "g": ("good", []), "b": ("bad", ["head_down"]), "c": ("bad", ["too_close"]),
        "t": ("bad", ["shoulder_tilt"]), "n": ("no_person", []),
    }
    for line in sys.stdin:
        k = line.strip().lower()
        if k in keys:
            device.manual = keys[k]
            print(f"[manual] {device.manual}")
        elif k == "a":
            device.manual = None
            print("[manual] auto scenario")
        elif k == "f":
            device.fail_next_calibration = True
            print("[manual] next calibration will fail")
        elif k == "q":
            loop.call_soon_threadsafe(loop.stop)
            return


def local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def start_mdns(port: int):
    try:
        from zeroconf import ServiceInfo, Zeroconf
    except ImportError:
        print("[mdns] zeroconf not installed, skip (앱에서 IP 직접 입력)")
        return None
    ip = local_ip()
    info = ServiceInfo(
        "_bajahoe._tcp.local.",
        "Bajahoe-Mock._bajahoe._tcp.local.",
        addresses=[socket.inet_aton(ip)],
        port=port,
        properties={"name": DEVICE_INFO["name"], "ver": "1"},
    )
    zc = Zeroconf()
    zc.register_service(info)
    print(f"[mdns] advertising Bajahoe-Mock at {ip}:{port}")
    return zc, info


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--manual", action="store_true", help="키보드로 상태 제어")
    ap.add_argument("--no-mdns", action="store_true")
    args = ap.parse_args()

    if args.manual:
        device.manual = ("good", [])

    app = web.Application()
    app.router.add_get("/api/info", info)
    app.router.add_get("/stream.mjpg", stream)
    app.router.add_get("/ws", ws_handler)

    mdns = None if args.no_mdns else start_mdns(args.port)
    print(f"바자회 모의 서버: http://{local_ip()}:{args.port}  (에뮬레이터는 10.0.2.2)")
    if args.manual:
        print("키 입력: g 바른자세 / b 고개숙임 / c 너무가까움 / t 어깨기울어짐 / n 자리비움 / a 자동 / f 설정실패 / q 종료")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    if args.manual:
        threading.Thread(target=keyboard_loop, args=(loop,), daemon=True).start()
    runner = web.AppRunner(app)
    loop.run_until_complete(runner.setup())
    loop.run_until_complete(web.TCPSite(runner, "0.0.0.0", args.port).start())
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if mdns:
            zc, svc = mdns
            zc.unregister_service(svc)
            zc.close()
        loop.run_until_complete(runner.cleanup())


if __name__ == "__main__":
    main()
