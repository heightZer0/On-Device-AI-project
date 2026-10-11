"""카메라 프레임에서 뽑은 좌표 묶음 (cv2/mediapipe 의존 없음 → 테스트에서 가짜로 대체 가능)."""
from dataclasses import dataclass
from typing import Optional


@dataclass
class RawFrame:
    ts: float                 # 단조 시계(초)
    width: int
    height: int
    # {"left"|"right": {xe,ye,xs,ys,xn,ex,ey,ve,vs,vey}}  (픽셀 좌표 + visibility), 사람 미검출이면 None
    pose: Optional[dict]
