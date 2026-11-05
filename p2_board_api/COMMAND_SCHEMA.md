# P4 명령 계약 (P0 v10.3 / V6)

P2 accepts one normalized command per `/api/v1/command`. It removes `<think>…</think>`, whitespace, then requires an exact match to the 16 command forms in `command/schema/commands.yaml`. Commands outside the allowlist never execute.

The accepted families are posture check (types `0`, `1`), monitor start/pause/stop, stretch recommend (parts `0`–`3`), clarify (`body_part`, `intent`, `time`), sitting time, break check, break alarm (`minutes="N"`), and unsupported reject. Numeric minutes in LLM output are rejected; `parse_duration_minutes` extracts the actual duration from the STT utterance and enforces 1–180 minutes.

`clarify` responses use HTTP 200 with `success: true` and `result.awaiting` set to `body_part|intent|time`. P2 stores `original_utterance`, action, known slots, choices, expiry, and retry count in process memory for 30 seconds. The client may pass `conversation_id`; it is separate from measurement `session_id`.

After a successful stretch guide is included in the P2 response, P2 caches its part and exercise ID for five minutes. “Another movement” selects an unseen exercise from that part; “repeat” selects the previous exercise. Explicitly named new parts take precedence. Guide IDs and fixed content live in `config/stretch_exercises.yaml`. This is an in-memory single-process cache; multi-worker deployments need a shared store.

Voice `/command` prerequisites follow V6. REST app controls (`/monitoring/start|pause|stop`) retain their idempotent behavior. `multi_guard` defaults to `unsupported_only`; `block` also blocks detected multi-feature utterances joined by a connector. `ai_log_enabled` defaults to false; enabling it writes utterance text, model output, validation summary, request ID, model version, latency, and error code to `data/ai_log.jsonl`. Audio is never logged.

The OpenAI-compatible client sends only the user utterance (the system prompt belongs to the model server's chat template) with deterministic generation settings. The matching RKLLM `chat_template.json` cannot be derived from this repository alone: use the exact V6 training tokenizer and system prompt artifact before deploying the board model.
