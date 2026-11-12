"""Build RKLLM calibration queries from Train-only utterances in the V11 workbook."""
from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

from openpyxl import load_workbook


def build_queries(workbook_path: Path, count: int, seed: int) -> list[str]:
    if not 300 <= count <= 1000:
        raise ValueError("count must be between 300 and 1000")
    wb = load_workbook(workbook_path, read_only=True, data_only=True)
    try:
        ws = wb["Train Data"]
        rows = ws.iter_rows(values_only=True)
        headers = next(rows)
        index = {str(value).strip(): i for i, value in enumerate(headers) if value is not None}
        required = {"LLM Output", "Query(국문)", "고정 분할"}
        if not required.issubset(index):
            raise ValueError(f"Train Data is missing columns: {sorted(required - index.keys())}")

        groups: dict[str, list[str]] = defaultdict(list)
        for row in rows:
            split = row[index["고정 분할"]]
            output = str(row[index["LLM Output"]] or "").strip()
            utterance = str(row[index["Query(국문)"]] or "").strip()
            if split != "Train" or not utterance or not output.startswith("<"):
                continue
            if output.startswith('<unsupported>(command="reject")'):
                continue
            groups[output].append(utterance)
    finally:
        wb.close()

    rng = random.Random(seed)
    for values in groups.values():
        rng.shuffle(values)
    if count > sum(len(values) for values in groups.values()):
        raise ValueError("requested count exceeds available unique active Train utterances")

    selected: list[str] = []
    labels = sorted(groups)
    while len(selected) < count:
        progressed = False
        for label in labels:
            if groups[label] and len(selected) < count:
                selected.append(groups[label].pop())
                progressed = True
        if not progressed:
            break
    rng.shuffle(selected)
    if len(selected) != len(set(selected)):
        raise ValueError("duplicate utterances found in calibration sample")
    return selected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", type=Path, help="Path to LLM 최종 데이터셋.xlsx")
    parser.add_argument("--count", type=int, default=600, help="Calibration utterances (300-1000, default 600)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, default=Path("data/queries.json"))
    args = parser.parse_args()

    queries = build_queries(args.workbook, args.count, args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(queries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(queries)} Train-only active-function utterances to {args.output}")
    print("Keep system_prompt in data/config.yaml identical to the V11 training prompt; queries.json contains utterances only.")


if __name__ == "__main__":
    main()
