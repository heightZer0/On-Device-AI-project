"""Inspect generated calibration targets without correcting or overwriting them."""
from pathlib import Path
from collections import Counter
import hashlib
import json
import random
import re

import yaml

d = Path('/work/data')
cfg = yaml.safe_load((d / 'config.yaml').read_text(encoding='utf-8'))
if hashlib.sha256(cfg['system_prompt'].encode()).hexdigest() != '0dca87f844ea82dc754491ffcd662840952fd33a2699f074a94bcee3692bb57d':
    raise RuntimeError('System prompt changed.')
ref = json.loads((d / 'reference.json').read_text(encoding='utf-8'))
records = json.loads(Path(cfg['calib_out']).read_text(encoding='utf-8'))
if len(records) != len(ref):
    raise RuntimeError(f'Count mismatch: generated={len(records)}, expected={len(ref)}')

allowed = {
    '<posture>(command="check", type="0")<suda_end>',
    '<posture>(command="check", type="1")<suda_end>',
    '<monitor>(command="start")<suda_end>',
    '<monitor>(command="pause")<suda_end>',
    '<monitor>(command="stop")<suda_end>',
    *{f'<stretch>(command="recommend", part="{i}")<suda_end>' for i in range(4)},
    '<clarify>(command="body_part")<suda_end>',
    '<clarify>(command="intent")<suda_end>',
    '<clarify>(command="time")<suda_end>',
    '<sitting>(command="time")<suda_end>',
    '<break>(command="check")<suda_end>',
    '<break>(command="set_alarm", minutes="N")<suda_end>',
    '<unsupported>(command="reject")<suda_end>',
}
bad = []; mismatches = []; distribution = Counter()
for i, (record, expected) in enumerate(zip(records, ref), 1):
    if not isinstance(record, dict) or not isinstance(record.get('input'), str) or not isinstance(record.get('target'), str):
        raise RuntimeError(f'Bad input/target schema at {i}')
    if cfg['system_prompt'] not in record['input'] or expected['query'] not in record['input']:
        raise RuntimeError(f'Input/prompt mismatch at {i}')
    # For reporting only: strip an EMPTY think block, never non-empty reasoning.
    target = re.sub(r'^\s*<think>\s*</think>\s*', '', record['target'], count=1).strip()
    distribution[target] += 1
    detail = {'index': i, 'query': expected['query'], 'expected': expected['expected_command'], 'raw_target': record['target']}
    if target not in allowed:
        bad.append(detail)
    if target != expected['expected_command']:
        mismatches.append(detail)

print('Generated:', len(records), '| format errors:', len(bad), '| differs from Train labels:', len(mismatches))
print('Not a held-out accuracy score. No generated targets have been edited.')
print('Output distribution:', json.dumps(dict(distribution), ensure_ascii=False))
for title, items in [('FORMAT ERRORS', bad), ('LABEL DIFFERENCES', mismatches)]:
    print('\n' + title)
    for item in items:
        print(json.dumps(item, ensure_ascii=False))
indices = list(range(min(10, len(records))))
remaining = list(range(10, len(records)))
indices += random.Random(20261111).sample(remaining, min(10, len(remaining)))
print('\nFIRST TEN + UP TO TEN RANDOM SAMPLES')
for i in indices:
    print(json.dumps({'index': i+1, 'query': ref[i]['query'], 'target': records[i]['target']}, ensure_ascii=False))
if bad:
    raise SystemExit('STOP: inspect malformed targets before any convert.')
if len(records) == 16 and mismatches:
    raise SystemExit('STOP: inspect the smoke mismatches before full calibration.')
print('Review complete. Check the reported differences before authorizing convert.')
