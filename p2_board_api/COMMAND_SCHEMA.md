# P4 command contract and model handoff

## Command processor

`command.process(raw, services, utterance=None, options=None)` is the public entry point. It parses exactly one `<function>(key="value")<suda_end>` result, checks the schema and the current P2 state, and executes only a `ValidatedCommand`. The schema is in `command/schema/commands.yaml`; wording, out-of-scope terms, and stretch instructions are data files under `config/` and `command/schema/`.

For now `require_suda_end: false`: the parser accepts one command with or without the end marker because the quantized RKLLM output has not yet been checked. It still rejects duplicate markers, prose around the command, malformed arguments, and multiple commands. Once the board output is checked, update this single schema setting.

Supported output families: posture check types 0/1; monitor start/pause/stop; stretch recommend parts 0–3; clarify body_part; sitting time; break check; break set_alarm minutes 1–180. Out-of-scope checks and preconditions run before execution. `time_crosscheck_mode` is `off`, `confirm` (default), or `override`.

## Swap in the quantized model

P2 already talks to an OpenAI-compatible endpoint. In `config/api.yaml`, point `llm_url` at the model server's `/v1/chat/completions` URL and set `llm_model` to the model ID expected by that server. No parser, P2 route, or Android change should be needed if the server returns `choices[0].message.content` with the command string.

The `.rkllm` file alone is not an inference server. To finish the hardware adapter, the model handoff must also include the matching RKLLM runtime/library and version, board architecture, tested launch/API method (or server package), context limit, and the exact training chat template and `<suda_end>` behavior. The RKLLM C binding must be implemented against that delivered header/runtime; it is intentionally not guessed in this board-free implementation. Until then, an OpenAI-compatible development server can exercise the entire P2→P4 parser/executor path.

## Board-free checks

Run unit coverage from `p2_board_api` with `python -m pytest tests -q` after adding/receiving the P4 table tests. For direct processor checks, call `command.process_raw(raw, fake_services)`; this bypasses model inference but exercises parsing, validation, prerequisites, and execution.

With a reachable model server, test the authenticated route:

```powershell
$headers = @{ Authorization = "Bearer $env:BAJAHOE_DEVICE_TOKEN" }
$body = @{ source = "voice"; utterance = "내 자세 괜찮아?" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/command -Headers $headers -ContentType "application/json" -Body $body
```

For deterministic tests independent of the model, replace `utterance` with a raw `command`, for example:

```json
{"source":"app","command":"<monitor>(command=\"start\")<suda_end>"}
```

The production `main` uses P1 and the configured LLM endpoint. Without a board/camera, run the FastAPI fixture tests or a harness with `FakeEngine`; the app's Demo mode only tests app screens and does not test the P2 API connection.
