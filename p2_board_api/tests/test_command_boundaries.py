import pytest

import command


class Services:
    state = "MONITORING"
    session = "test-session"
    _health = {"camera": "ready"}

    def calibrated(self):
        return True

    def ensure_camera_ready(self):
        return True

    def get_posture(self):
        return {"state": "normal", "indicators": {}}

    def get_session(self):
        return {"session_id": self.session, "sitting_sec": 600}

    def get_last_session(self):
        return None


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
