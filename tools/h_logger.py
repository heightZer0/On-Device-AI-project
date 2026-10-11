"""
tools/h_logger.py — 0단계 실험용 귀·어깨 좌표 로거 (명세 P1-3의 2~3단계, P7 E1~E4용)

- 모델(.joblib)을 쓰지 않는다. 이미지 픽셀 좌표(x*width, y*height)만 CSV 로 기록한다. 영상은 저장하지 않는다.
- 양쪽(left/right) 귀·어깨를 모두 기록해 side 선택 검증에 쓴다.
- 낮은 visibility도 버리지 않고 플래그로 구분한다 (감지율·측정 불가 비율 계산용).
- 분석 시에는 valid==1 인 프레임을 우선 사용하고, in_frame 은 별도로 확인한다.
- ※ 실험이 끝나면 생성된 CSV는 삭제한다 (프레임별 좌표 원본 저장 금지 원칙).
- 사용: python tools/h_logger.py --list-cameras  /  python tools/h_logger.py --camera 1 --subject p1 --note face_right_fixed
"""
import argparse
import csv
import math
import os
import time
from datetime import datetime

import cv2
import mediapipe as mp

NOSE = 0
SIDES = {  # MediaPipe Pose 표준 인덱스
    "left":  {"ear": 7, "shoulder": 11, "eye": 2},
    "right": {"ear": 8, "shoulder": 12, "eye": 5},
}
HEADER = [
    "ts", "subject", "note", "side",
    "x_ear", "y_ear", "x_shoulder", "y_shoulder", "x_nose",
    "vis_ear", "vis_shoulder", "vis_nose", "vis_eye",
    "L_ref_A", "L_ref_B", "L_ref_C",
    "detected", "valid", "in_frame",
]


def open_cam(idx):
    return cv2.VideoCapture(idx, cv2.CAP_DSHOW) if os.name == "nt" else cv2.VideoCapture(idx)


def list_cameras(max_index=5):
    """0~4번 카메라를 하나씩 미리보기로 띄워 외부 웹캠 번호를 확인한다."""
    for i in range(max_index):
        cap = open_cam(i)
        if not cap.isOpened():
            print(f"index {i}: 없음")
            cap.release()
            continue
        ok, fr = cap.read()
        if ok:
            print(f"index {i}: 열림, 해상도 {fr.shape[1]}x{fr.shape[0]}")
            cv2.putText(fr, f"cam {i}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
            cv2.imshow("camera preview", fr)
            cv2.waitKey(2000)
        else:
            print(f"index {i}: 열렸지만 프레임을 읽지 못함")
        cap.release()
    cv2.destroyAllWindows()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--camera", type=int, default=1, help="카메라 번호. 노트북 내장 캠이 0이면 외부 웹캠은 보통 1")
    ap.add_argument("--list-cameras", action="store_true", help="카메라 번호별 미리보기 후 종료")
    ap.add_argument("--subject", default="", help="가명 식별자(예: p1)")
    ap.add_argument("--note", default="", help="촬영 조건 메모(예: face_right_fixed, chair_moved)")
    ap.add_argument("--vis-thr", type=float, default=0.5, help="T_vis 후보 (TODO(실험))")
    ap.add_argument("--margin", type=float, default=0.05, help="frame_margin 후보, 이미지 크기 비율 (TODO(실험))")
    ap.add_argument("--complexity", type=int, default=1, help="0 lite / 1 full / 2 heavy")
    a = ap.parse_args()

    if a.list_cameras:
        list_cameras()
        return

    cap = open_cam(a.camera)
    if not cap.isOpened():
        raise RuntimeError(f"카메라 {a.camera}번을 열 수 없습니다. --list-cameras 로 번호를 확인하세요.")
    print(f"카메라 {a.camera}번 열림 ({int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))})")

    out_name = f"h_log_{a.subject or 'x'}_{datetime.now():%Y%m%d_%H%M%S}.csv"
    fh = open(out_name, "w", newline="", encoding="utf-8")
    writer = csv.DictWriter(fh, fieldnames=HEADER, restval="")
    writer.writeheader()
    print("로그 파일:", out_name, "(실험 후 삭제)  |  ESC로 종료")

    t0, n_frames, fps = time.time(), 0, 0.0
    try:
        with mp.solutions.pose.Pose(
            static_image_mode=False, model_complexity=a.complexity, smooth_landmarks=True,
            min_detection_confidence=0.5, min_tracking_confidence=0.5,
        ) as pose:
            while True:
                ok, frame = cap.read()
                if not ok:
                    print("웹캠 프레임을 읽지 못했습니다.")
                    break
                h, w = frame.shape[:2]
                ts = f"{time.time() - t0:.3f}"
                results = pose.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))  # 반전하지 않은 프레임
                lm = results.pose_landmarks.landmark if results.pose_landmarks else None

                mx, my = a.margin * w, a.margin * h
                cv2.rectangle(frame, (int(mx), int(my)), (int(w - mx), int(h - my)), (120, 120, 120), 1)

                for side, ids in SIDES.items():
                    row = {"ts": ts, "subject": a.subject, "note": a.note, "side": side, "detected": 0, "valid": 0}
                    if lm is not None:
                        ear, sh, eye, nose = lm[ids["ear"]], lm[ids["shoulder"]], lm[ids["eye"]], lm[NOSE]
                        xe, ye, xs, ys = ear.x * w, ear.y * h, sh.x * w, sh.y * h
                        valid = ear.visibility >= a.vis_thr and sh.visibility >= a.vis_thr
                        in_frame = all(mx <= x <= w - mx and my <= y <= h - my for x, y in ((xe, ye), (xs, ys)))
                        row.update({
                            "x_ear": f"{xe:.1f}", "y_ear": f"{ye:.1f}",
                            "x_shoulder": f"{xs:.1f}", "y_shoulder": f"{ys:.1f}",
                            "x_nose": f"{nose.x * w:.1f}",
                            "vis_ear": f"{ear.visibility:.3f}", "vis_shoulder": f"{sh.visibility:.3f}",
                            "vis_nose": f"{nose.visibility:.3f}", "vis_eye": f"{eye.visibility:.3f}",
                            "L_ref_A": (f"{math.hypot(xe - eye.x * w, ye - eye.y * h):.1f}"
                                        if eye.visibility >= a.vis_thr else ""),
                            "L_ref_B": h,
                            "L_ref_C": f"{abs(ys - ye):.1f}",
                            "detected": 1, "valid": int(valid), "in_frame": int(in_frame),
                        })
                        col = (0, 255, 0) if valid and in_frame else (0, 0, 255)
                        off = 0 if side == "left" else 150
                        cv2.circle(frame, (int(xe), int(ye)), 6, col, -1)
                        cv2.circle(frame, (int(xs), int(ys)), 6, col, -1)
                        cv2.line(frame, (int(xe), int(ye)), (int(xs), int(ys)), col, 1)
                        cv2.putText(frame, f"{side[0].upper()} e{ear.visibility:.2f} s{sh.visibility:.2f}",
                                    (10 + off, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 1)
                    writer.writerow(row)

                n_frames += 1
                if n_frames % 30 == 0:
                    fps = n_frames / (time.time() - t0)
                cv2.putText(frame, f"cam {a.camera}  FPS {fps:.1f}  vis_thr {a.vis_thr}  ESC=quit", (10, 25),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                cv2.imshow("h_logger", frame)
                if cv2.waitKey(1) & 0xFF == 27:
                    break
    finally:
        cap.release()
        cv2.destroyAllWindows()
        fh.close()
        print(f"종료. 평균 FPS {n_frames / max(time.time() - t0, 1e-6):.1f}, 프레임 {n_frames}개")


if __name__ == "__main__":
    main()
