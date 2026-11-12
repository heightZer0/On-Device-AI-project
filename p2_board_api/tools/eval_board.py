"""Compare OpenAI-compatible command models on the V11 Eval, Boundary and new-expression sets."""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
import yaml
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import command  # noqa: E402


class ValidationServices:
    state = "MONITORING"
    session = "evaluation-session"
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


def load_cases(path: Path) -> dict[str, list[dict[str, str]]]:
    wb = load_workbook(path, read_only=True, data_only=True)
    cases: dict[str, list[dict[str, str]]] = {}
    try:
        for sheet_name in ("Eval Data", "Boundary Eval", "신규 표현 평가"):
            if sheet_name not in wb.sheetnames:
                continue
            ws = wb[sheet_name]
            rows = ws.iter_rows(values_only=True)
            first = next(rows, None)
            if first is None:
                continue
            columns = {str(value).strip(): i for i, value in enumerate(first) if value is not None}
            expected_key = next((key for key in ("LLM Output", "정답 명령") if key in columns), None)
            utterance_key = next((key for key in ("Query(국문)", "발화") if key in columns), None)
            if not expected_key or not utterance_key:
                continue
            entries = []
            for row in rows:
                expected = str(row[columns[expected_key]] or "").strip()
                utterance = str(row[columns[utterance_key]] or "").strip()
                if expected and utterance:
                    entries.append({"expected": expected, "utterance": utterance})
            cases[sheet_name] = entries
    finally:
        wb.close()
    if not cases.get("Eval Data") or not cases.get("Boundary Eval"):
        raise ValueError("workbook must contain populated Eval Data and Boundary Eval sheets")
    return cases


def canonical(raw: str) -> tuple | None:
    cleaned = re.sub(r"<think>.*?</think>", "", raw or "", flags=re.DOTALL)
    cleaned = re.sub(r"\s+", "", cleaned).strip()
    parsed = command._parse(cleaned, require_suda_end=True)
    validated = command._validate(parsed, cleaned, ValidationServices(), command._schema())
    return validated.function, validated.command, tuple(sorted(validated.params.items()))


def infer(client: httpx.Client, url: str, model: str, system_prompt: str, utterance: str) -> tuple[str, float]:
    payload = {
        "model": model,
        "stream": False,
        "temperature": 0,
        "top_k": 1,
        "enable_thinking": False,
        "max_tokens": 64,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": utterance},
        ],
    }
    started = time.perf_counter()
    for attempt in range(4):
        response = client.post(url, json=payload)
        if response.status_code != 503 or attempt == 3:
            response.raise_for_status()
            result = response.json()["choices"][0]["message"]["content"]
            return str(result), (time.perf_counter() - started) * 1000
        time.sleep(0.5 * (attempt + 1))
    raise RuntimeError("unreachable")


def summarize(target: str, cases: dict[str, list[dict[str, str]]], results: list[dict]) -> None:
    for sheet_name, entries in cases.items():
        rows = [r for r in results if r["dataset"] == sheet_name and r["target"] == target]
        correct = sum(r["match"] is True for r in rows)
        valid = sum(r["valid"] is True for r in rows)
        print(f"{target} | {sheet_name}: exact={correct}/{len(entries)} ({100*correct/len(entries):.2f}%), "
              f"schema-valid={valid}/{len(entries)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--board-url", default="http://127.0.0.1:8080/v1/chat/completions")
    parser.add_argument("--server-url", help="Optional baseline model endpoint for side-by-side comparison")
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "api.yaml")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()

    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    system_prompt = cfg.get("llm_system_prompt", "")
    if not system_prompt.strip():
        raise ValueError("llm_system_prompt is empty in the selected config")
    model = cfg.get("llm_model", "rkllm")
    cases = load_cases(args.workbook)
    targets = {"board": args.board_url}
    if args.server_url:
        targets["server"] = args.server_url

    results = []
    with httpx.Client(timeout=args.timeout) as client:
        for target, url in targets.items():
            for dataset, entries in cases.items():
                for index, case in enumerate(entries, start=1):
                    record = {"target": target, "url": url, "dataset": dataset, "index": index,
                              "utterance": case["utterance"], "expected": case["expected"]}
                    try:
                        raw, latency_ms = infer(client, url, model, system_prompt, case["utterance"])
                        expected = canonical(case["expected"])
                        actual = canonical(raw)
                        record.update(raw_output=raw, latency_ms=round(latency_ms, 1),
                                      valid=True, match=actual == expected)
                    except Exception as exc:
                        record.update(raw_output=None, valid=False, match=False,
                                      error=f"{type(exc).__name__}: {exc}")
                    results.append(record)
                    print(f"{target} {dataset} {index}/{len(entries)}: "
                          f"{'OK' if record['match'] else 'MISS'}", flush=True)

    for target in targets:
        summarize(target, cases, results)
    output = args.output or Path(f"eval_board_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    output.write_text(json.dumps({"results": results}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Detailed responses saved to {output}")


if __name__ == "__main__":
    main()
