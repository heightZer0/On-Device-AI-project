import os
import time

from helpers import make_cfg
from posture.engine import PostureEngine
from posture.pose_estimation.frame import RawFrame


class FakeSource:
    """합성 좌표를 돌려주는 가짜 소스. H 속성으로 머리 위치를 조작한다."""

    def __init__(self, dt=0.1):
        self.t, self.dt, self.H, self.fail = 0.0, dt, 0.0, False
        self.requested, self.status, self.closed = [], "ready", False

    def read(self, sides=("left", "right")):
        self.requested.append(tuple(sides))
        if self.fail:
            self.status = "error"
            return None
        self.status = "ready"
        t, self.t = self.t, self.t + self.dt
        pose = {}
        for s in sides:
            v = 0.9 if s == "left" else 0.6
            xe = 300.0 + self.H * 100.0
            pose[s] = dict(xe=xe, ye=200.0, xs=300.0, ys=300.0, xn=xe + 10, ex=xe + 5, ey=200.0,
                           ve=v, vs=v, vey=v)
        return RawFrame(ts=t, width=640, height=480, pose=pose)

    def close(self):
        self.closed = True


def make_engine(tmp_path, **kw):
    src = FakeSource()
    cfg = make_cfg(calibration_path=str(tmp_path / "calibration.json"), **kw)
    eng = PostureEngine(cfg, src, clock=lambda: src.t)
    events = []
    eng.on_event(events.append)
    return eng, src, events


def calibrate(eng):
    det = eng.begin_calibration()
    assert det["detected"]["any"] is True
    for _ in range(100):
        eng.step()
        if eng.preview_calibration()["phase"] != "collecting":
            break
    pv = eng.preview_calibration()
    assert pv["phase"] == "ready", pv
    return pv


def test_full_flow_calibrate_confirm_monitor_alert(tmp_path):
    eng, src, events = make_engine(tmp_path)
    pv = calibrate(eng)
    assert pv["summary"]["side"] == "left" and pv["summary"]["d"] == 1
    assert eng.get_state()["reason"] == "not_calibrated"          # confirm 전에는 기준 없음
    assert eng.confirm_calibration()["ok"] is True
    assert os.path.exists(tmp_path / "calibration.json")

    eng.start()
    src.requested.clear()
    src.H = 0.5                                                    # 기준보다 전방
    for _ in range(80):
        eng.step()
    assert [e["type"] for e in events] == ["attention_started"]
    assert eng.get_state()["state"] == "attention"
    assert set(src.requested) == {("left",)}                       # 모니터링 중에는 고정된 side 만 요청


def test_confirm_requires_ready_preview(tmp_path):
    eng, _, _ = make_engine(tmp_path)
    assert eng.confirm_calibration() == {"ok": False, "error": "not_ready"}
    eng.begin_calibration()
    assert eng.confirm_calibration()["ok"] is False                # 수집 중에는 저장 불가


def test_calibration_persists_across_restart(tmp_path):
    eng, _, _ = make_engine(tmp_path)
    calibrate(eng)
    cal = eng.confirm_calibration()["calibration"]
    eng2, _, _ = make_engine(tmp_path)
    assert eng2.get_calibration() == cal


def test_camera_failure_becomes_unavailable_not_exception(tmp_path):
    eng, src, _ = make_engine(tmp_path)
    calibrate(eng)
    eng.confirm_calibration()
    eng.start()
    for _ in range(5):
        eng.step()
    assert eng.get_state()["state"] == "normal"
    src.fail = True
    for _ in range(5):
        eng.step()                                                 # 예외 없이 처리
    st = eng.get_state()
    assert st["state"] == "unavailable" and eng.get_camera_status() == "error"
    src.fail = False                                               # 복구
    for _ in range(10):
        eng.step()
    assert eng.get_state()["state"] == "normal" and eng.get_camera_status() == "ready"


def test_control_is_idempotent_and_paused_reads_nothing(tmp_path):
    eng, src, _ = make_engine(tmp_path)
    assert [eng.start(), eng.start()] == ["running", "running"]
    assert [eng.pause(), eng.pause()] == ["paused", "paused"]
    n = len(src.requested)
    assert eng.step() is False and len(src.requested) == n         # 일시정지 중에는 카메라를 읽지 않음
    assert [eng.resume(), eng.resume()] == ["running", "running"]
    assert [eng.stop(), eng.stop()] == ["stopped", "stopped"]
    assert eng.pause() == "stopped" and eng.resume() == "stopped"


def test_debug_flag_controls_S_exposure(tmp_path):
    eng, src, _ = make_engine(tmp_path)
    calibrate(eng)
    eng.confirm_calibration()
    eng.start()
    for _ in range(5):
        eng.step()
    assert "debug" not in eng.get_state()
    eng.set_debug(True)
    for _ in range(5):
        eng.step()
    assert "shoulder_screen_shift" in eng.get_state()["debug"]


def test_nothing_but_calibration_json_is_written(tmp_path):
    eng, src, _ = make_engine(tmp_path)
    calibrate(eng)
    eng.confirm_calibration()
    eng.start()
    src.H = 0.5
    for _ in range(80):
        eng.step()
    assert os.listdir(tmp_path) == ["calibration.json"]            # 영상·프레임별 좌표 파일 없음


def test_background_thread_emits_events_and_closes(tmp_path):
    eng, src, events = make_engine(tmp_path)
    calibrate(eng)
    eng.confirm_calibration()
    src.H = 0.5
    eng.start()
    eng.run_in_background()
    deadline = time.time() + 3.0
    while time.time() < deadline and not events:
        time.sleep(0.02)
    eng.close()
    assert [e["type"] for e in events][:1] == ["attention_started"] and src.closed


def test_experiment_log_has_metrics_but_no_coordinates(tmp_path):
    import csv
    eng, src, _ = make_engine(tmp_path)
    calibrate(eng)
    eng.confirm_calibration()
    log = str(tmp_path / "exp.csv")
    eng.start_experiment_log(log, subject="p1", note="face_right_fixed")
    eng.start()
    src.H = 0.3
    for _ in range(20):
        eng.step()
    eng.stop_experiment_log()
    rows = list(csv.DictReader(open(log, encoding="utf-8")))
    assert len(rows) == 20 and rows[0]["subject"] == "p1" and rows[0]["note"] == "face_right_fixed"
    assert list(rows[0]) == ["ts", "subject", "note", "side", "d", "state", "reason", "H", "dH", "S", "confidence"]
    assert float(rows[-1]["dH"]) > 0.2
    assert not any(c in rows[0] for c in ("x_ear", "y_ear", "x_shoulder", "y_shoulder"))   # 좌표 원본 없음
