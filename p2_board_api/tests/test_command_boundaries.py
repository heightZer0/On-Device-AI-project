import pytest

import command


class Services:
    def __init__(self, *, state="MONITORING", sitting_sec=600, posture=None, session="test-session"):
        self.state, self.sitting_sec, self.posture, self.session = state, sitting_sec, posture, session
    _health = {"camera": "ready"}

    def calibrated(self):
        return True

    def ensure_camera_ready(self):
        return True

    def get_posture(self):
        return self.posture or {"state": "normal", "indicators": {}}

    def get_session(self):
        return {"session_id": self.session, "sitting_sec": self.sitting_sec} if self.session else None

    def get_last_session(self):
        return None


def test_updated_posture_and_stretch_voice_phrases():
    posture = command.process(
        '<posture>(command="check", type="0")<suda_end>', Services())
    assert posture["tts_text"] == "현재는 머리 위치를 기준으로 자세를 확인하고 있어요. 등록한 기준 자세에 가까워요."

    stretch = command.process(
        '<stretch>(command="recommend", part="1")<suda_end>', Services())
    assert stretch["tts_text"] == "턱을 살짝 당긴 상태로 5초 정도 유지해 주세요."
    assert stretch["result"]["title"] == "턱 당기기"  # 제목은 화면용으로 유지


def test_break_check_uses_exact_hour_boundary_and_updated_phrases():
    raw = '<break>(command="check")<suda_end>'
    before = command.process(raw, Services(sitting_sec=3599))
    at_boundary = command.process(raw, Services(sitting_sec=3600))
    assert before["tts_text"] == "현재 착석 시간은 59분이에요. 아직 1시간이 지나지 않았어요."
    assert at_boundary["tts_text"] == "1시간 이상 앉아 있었어요. 잠깐 일어나 몸을 풀어 주세요."


def test_posture_not_started_and_detection_failure_have_separate_messages():
    raw = '<posture>(command="check", type="0")<suda_end>'
    stopped = command.process(raw, Services(state="IDLE"))
    missed = command.process(raw, Services(posture={"state": "unavailable", "reason": "ear_not_detected"}))
    camera = command.process(raw, Services(posture={"state": "unavailable", "reason": "camera_disconnected"}))
    assert stopped["tts_text"] == "먼저 자세 측정을 시작해 주세요."
    assert missed["tts_text"] == "머리와 어깨가 카메라에 보이도록 위치를 조정해 주세요."
    assert camera["tts_text"] == "카메라 연결을 확인한 뒤 다시 요청해 주세요."


@pytest.mark.parametrize("utterance", ["몸이 기울었어", "자세가 틀어졌어", "한쪽으로 비뚤어졌어", "몸이 치우쳤어"])
def test_overall_posture_vocabulary_is_not_guarded(utterance):
    result = command.process(
        '<posture>(command="check", type="0")<suda_end>', Services(), utterance=utterance
    )
    assert result["code"] == "OK"


def test_negated_unsupported_part_does_not_block_supported_stretch():
    result = command.process(
        '<stretch>(command="recommend", part="1")<suda_end>',
        Services(), utterance="손목 말고 목 스트레칭 알려줘",
    )
    assert result["code"] == "OK" and result["result"]["part"] == 1


def test_unnegated_unsupported_stretch_part_is_still_blocked():
    result = command.process(
        '<stretch>(command="recommend", part="1")<suda_end>',
        Services(), utterance="손목 스트레칭 알려줘",
    )
    assert result["code"] == "UNSUPPORTED"


@pytest.mark.parametrize(("utterance", "expected"), [
    ("마흔 분 뒤에 쉬라고 알려줘", 40),
    ("스물한 분 뒤에 쉬라고 알려줘", 21),
    ("스무 분 뒤에 쉬라고 알려줘", 20),
    ("영 분 뒤에 쉬라고 알려줘", 0),
    ("두 시간 이십오 분 뒤에 쉬라고 알려줘", 145),
])
def test_korean_duration_parser(utterance, expected):
    assert command.parse_duration_minutes(utterance) == expected


def test_zero_minute_alarm_is_rejected_as_invalid_range():
    result = command.process(
        '<break>(command="set_alarm", minutes="N")<suda_end>',
        Services(), utterance="영 분 뒤에 쉬라고 알려줘",
    )
    assert result["code"] == "INVALID_TIME_RANGE"


@pytest.mark.parametrize("utterance", ["3시 30분에 쉬라고 알려줘", "세 시에 쉬라고 알려줘"])
def test_clock_times_are_not_parsed_as_relative_duration(utterance):
    assert command.parse_duration_minutes(utterance) is None


def test_deictic_this_time_is_not_parsed_as_two_hours():
    assert command.parse_duration_minutes("이 시간에 쉬라고 알려줘") is None


def test_guard_does_not_match_inside_another_korean_word():
    result = command.process(
        '<posture>(command="check", type="0")<suda_end>', Services(),
        utterance="개발하다가 자세 확인해줘",
    )
    assert result["code"] == "OK"
