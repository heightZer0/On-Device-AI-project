"""Local camera check for P1. Displays a preview and reports aggregate detections only.

No video, frame coordinates, landmarks, or per-frame values are written to disk.
"""
import argparse
import os
import time

import cv2
import mediapipe as mp

SIDES = {"left": (7, 11), "right": (8, 12)}


def open_cam(idx):
    return cv2.VideoCapture(idx, cv2.CAP_DSHOW) if os.name == "nt" else cv2.VideoCapture(idx)


def list_cameras(max_index=5):
    for i in range(max_index):
        cap = open_cam(i)
        if not cap.isOpened():
            print(f"index {i}: 없음")
            cap.release()
            continue
        ok, frame = cap.read()
        if ok:
            print(f"index {i}: 열림, 해상도 {frame.shape[1]}x{frame.shape[0]}")
            cv2.imshow("camera preview (local only)", frame)
            cv2.waitKey(1000)
        else:
            print(f"index {i}: 열렸지만 프레임을 읽지 못함")
        cap.release()
    cv2.destroyAllWindows()


def main():
    ap = argparse.ArgumentParser(description="P1 카메라·랜드마크 검출 확인 (데이터 저장 없음)")
    ap.add_argument("--camera", type=int, default=1)
    ap.add_argument("--list-cameras", action="store_true")
    ap.add_argument("--complexity", type=int, default=1, choices=(0, 1, 2))
    a = ap.parse_args()
    if a.list_cameras:
        list_cameras()
        return

    cap = open_cam(a.camera)
    if not cap.isOpened():
        raise RuntimeError(f"카메라 {a.camera}번을 열 수 없습니다. --list-cameras 로 확인하세요.")
    counts = {s: 0 for s in SIDES}
    frames, started = 0, time.monotonic()
    try:
        with mp.solutions.pose.Pose(static_image_mode=False, model_complexity=a.complexity,
                                    smooth_landmarks=True, min_detection_confidence=0.5,
                                    min_tracking_confidence=0.5) as pose:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                result = pose.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                landmarks = result.pose_landmarks.landmark if result.pose_landmarks else None
                for row, (side, (ear_id, shoulder_id)) in enumerate(SIDES.items()):
                    visible = bool(landmarks and landmarks[ear_id].visibility >= 0.5
                                   and landmarks[shoulder_id].visibility >= 0.5)
                    counts[side] += int(visible)
                    cv2.putText(frame, f"{side}: {'detected' if visible else 'not detected'}",
                                (10, 30 + 28 * row),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (30, 220, 30) if visible else (40, 40, 230), 2)
                frames += 1
                cv2.imshow("P1 local camera check (ESC to exit)", frame)
                if cv2.waitKey(1) & 0xFF == 27:
                    break
    finally:
        cap.release()
        cv2.destroyAllWindows()
    elapsed = max(time.monotonic() - started, 1e-6)
    ratios = {s: round(n / max(frames, 1), 3) for s, n in counts.items()}
    print({"frames_processed": frames, "elapsed_sec": round(elapsed, 2),
           "processing_fps": round(frames / elapsed, 2), "usable_detection_ratio": ratios})


if __name__ == "__main__":
    main()
