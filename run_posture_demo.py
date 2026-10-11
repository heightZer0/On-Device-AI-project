"""
run_posture_demo.py — PostureEngine 동작 확인용 데모 (화면 글자는 OpenCV 한계로 영어)

키: c=기준 자세 수집 시작 | y=미리보기 확인 후 저장 | p=일시정지/재개 | d=디버그(S) 표시 토글 | ESC=종료
- 기준값은 숫자만 data/calibration.json 에 저장된다. 영상·프레임별 좌표는 저장하지 않는다.
- 이벤트(attention_started 등)는 콘솔에 출력된다. (TTS 연결은 P2/P3 몫)
※ 실제 카메라에서 아직 실행 확인을 하지 않은 코드이다.
"""
import argparse

import cv2
import numpy as np

from posture.engine import PostureEngine
from posture.rules.config import load_config

COLORS = {"normal": (0, 255, 0), "attention": (0, 0, 255), "unavailable": (0, 165, 255)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", help="설정 파일 경로 (기본: config/posture.yaml)")
    ap.add_argument("--camera", type=int, help="카메라 번호 (설정 파일의 camera_index 를 덮어씀)")
    ap.add_argument("--log", help="(개발용) 프레임별 H·ΔH·S·상태 CSV 경로. 좌표는 기록하지 않음. 실험 후 삭제")
    ap.add_argument("--subject", default="", help="가명 식별자(예: p1)")
    ap.add_argument("--note", default="", help="촬영 조건 메모(예: face_right_fixed)")
    a = ap.parse_args()

    cfg = load_config(a.config, **({"camera_index": a.camera} if a.camera is not None else {}))
    engine = PostureEngine(cfg)
    engine.on_event(lambda ev: print("EVENT", ev))
    if a.log:
        engine.start_experiment_log(a.log, a.subject, a.note)
    engine.start()
    debug = False
    try:
        while True:
            engine.step()
            src_frame = getattr(engine.source, "last_frame", None)
            view = src_frame.copy() if src_frame is not None else np.zeros((480, 640, 3), np.uint8)

            st = engine.get_state()
            pv = engine.preview_calibration()
            col = COLORS[st["state"]]
            lines = [f"STATE: {st['state'].upper()}" + (f" ({st['reason']})" if st["reason"] else ""),
                     f"camera: {engine.get_camera_status()}   monitoring: {engine.status}"]
            if st["indicators"]:
                lines.append(f"dH = {st['indicators']['head_relative_position']['delta']:+.3f}"
                             f"   (T_forward={cfg.T_forward}, hold {cfg.T_hold_sec}s)")
            if debug and "debug" in st:
                lines.append(f"[debug] shoulder shift S = {st['debug']['shoulder_screen_shift']}")
            if pv["phase"] == "collecting":
                lines.append(f"CAPTURING baseline... {pv.get('progress', 0) * 100:.0f}%  (hold a comfortable posture)")
            elif pv["phase"] == "ready":
                s = pv["summary"]
                lines.append(f"PREVIEW side={s['side']} d={s['d']:+d} H_base={s['H_base']:.3f} "
                             f"spread={s['spread_iqr']:.3f} -> press y to save, c to retry")
            elif pv["phase"] == "failed":
                lines.append(f"CALIBRATION FAILED: {pv['error']} -> press c to retry")
            for i, t in enumerate(lines):
                cv2.putText(view, t, (10, 28 + 26 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.6, col, 2)
            cv2.putText(view, "c:capture y:save p:pause d:debug ESC:quit", (10, view.shape[0] - 12),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
            cv2.imshow("posture engine demo", view)

            key = cv2.waitKey(1) & 0xFF
            if key == 27:
                break
            elif key == ord("c"):
                print("calibration start:", engine.begin_calibration())
            elif key == ord("y"):
                print("calibration confirm:", engine.confirm_calibration())
            elif key == ord("p"):
                engine.resume() if engine.status == "paused" else engine.pause()
            elif key == ord("d"):
                debug = not debug
                engine.set_debug(debug)
    finally:
        engine.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
