"""
웹캠 + MediaPipe Pose → RawFrame. cv2/mediapipe 는 실제로 쓸 때만 import 한다(테스트는 가짜 소스 사용).

- 요청한 side 의 귀·어깨(+캘리브레이션용 눈·코)만 읽는다. 골반 이하 인덱스는 읽지 않는다.
- 프레임/좌표를 디스크에 저장하지 않는다. last_frame 은 화면 표시용으로 메모리에만 둔다.
- 카메라 열기 실패·끊김은 예외 대신 None 을 돌려주고, camera_retry_sec 간격으로 재연결을 시도한다.
- MediaPipe 에는 좌우 반전하지 않은 프레임을 넣는다.
"""
import os
import time

from posture.pose_estimation.frame import RawFrame

_IDS = {
    "left":  {"ear": 7, "shoulder": 11, "eye": 2},
    "right": {"ear": 8, "shoulder": 12, "eye": 5},
}
_NOSE = 0


class MediaPipeSource:
    def __init__(self, cfg):
        self.cfg = cfg
        self.status = "unavailable"        # ready | error | unavailable  (P2 /status 의 camera 값)
        self.last_frame = None
        self._cap = None
        self._pose = None
        self._last_try = -1e9

    def _open(self) -> bool:
        import cv2
        idx = self.cfg.camera_index
        cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW) if os.name == "nt" else cv2.VideoCapture(idx)
        if cap.isOpened():
            self._cap, self.status = cap, "ready"
            return True
        cap.release()
        self.status = "error"
        return False

    def _ensure_pose(self):
        if self._pose is None:
            import mediapipe as mp
            self._pose = mp.solutions.pose.Pose(
                static_image_mode=False, model_complexity=self.cfg.model_complexity,
                smooth_landmarks=True, min_detection_confidence=0.5, min_tracking_confidence=0.5)

    def read(self, sides=("left", "right")):
        import cv2
        now = time.monotonic()
        if self._cap is None:
            if now - self._last_try < self.cfg.camera_retry_sec:
                time.sleep(0.05)
                return None
            self._last_try = now
            if not self._open():
                return None
        ok, frame = self._cap.read()
        if not ok:                                 # 프레임 끊김: 해제 후 재연결 시도
            self.status = "error"
            self._cap.release()
            self._cap, self._last_try = None, now
            return None
        self._ensure_pose()
        ts = time.monotonic()
        h, w = frame.shape[:2]
        self.last_frame = frame
        res = self._pose.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        pose = None
        if res.pose_landmarks:
            lm = res.pose_landmarks.landmark
            pose = {}
            for s in sides:
                ids = _IDS[s]
                ear, sh, eye, nose = lm[ids["ear"]], lm[ids["shoulder"]], lm[ids["eye"]], lm[_NOSE]
                pose[s] = {
                    "xe": ear.x * w, "ye": ear.y * h, "xs": sh.x * w, "ys": sh.y * h,
                    "xn": nose.x * w, "ex": eye.x * w, "ey": eye.y * h,
                    "ve": ear.visibility, "vs": sh.visibility, "vey": eye.visibility,
                }
        return RawFrame(ts=ts, width=w, height=h, pose=pose)

    def close(self):
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        if self._pose is not None:
            self._pose.close()
            self._pose = None
        self.status = "unavailable"
