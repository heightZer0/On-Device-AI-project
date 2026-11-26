"""Read-only config/tokenizer/header check. No model weights are loaded."""
import hashlib
import json
import sys
from pathlib import Path

import yaml
from safetensors import safe_open
from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer

sys.path.insert(0, '/opt/scripts')
from common import render_prompt

p = Path('/work/model')
d = Path('/work/data')
cfg = yaml.safe_load((d / 'config.yaml').read_text(encoding='utf-8'))
expected_hash = '0dca87f844ea82dc754491ffcd662840952fd33a2699f074a94bcee3692bb57d'
actual_hash = hashlib.sha256(cfg['system_prompt'].encode()).hexdigest()
if actual_hash != expected_hash:
    raise RuntimeError('Wrong V11 system prompt. Do not continue.')
if cfg['dtype'] != 'float16' or cfg['calib_dtype'] != 'float16':
    raise RuntimeError('Expected explicit float16 for this preparation package.')
queries = json.loads(Path(cfg['queries']).read_text(encoding='utf-8'))
reference = json.loads((d / 'reference.json').read_text(encoding='utf-8'))
if queries != [r['query'] for r in reference]:
    raise RuntimeError('queries.json differs from its source reference.')
model_cfg = AutoConfig.from_pretrained(p, local_files_only=True)
if type(model_cfg) not in AutoModelForCausalLM._model_mapping:
    raise RuntimeError('Provided AutoModelForCausalLM does not accept this config.')
tok = AutoTokenizer.from_pretrained(p, local_files_only=True)
if not tok.chat_template:
    raise RuntimeError('Tokenizer has no usable chat template.')
print('Tokenizer:', len(tok), '| usable chat template:', bool(tok.chat_template))
lengths = [len(tok(render_prompt(cfg, q, tok), add_special_tokens=True)['input_ids']) for q in queries]
needed = max(lengths) + int(cfg['calib_max_new_tokens'])
print('System prompt SHA256:', actual_hash)
print('Queries:', len(queries), '| command kinds:', len({r['expected_command'] for r in reference}))
print('Prompt tokens min/max:', min(lengths), max(lengths))
print('Max prompt + generation budget:', needed, '| max_context:', cfg['max_context'])
if needed > int(cfg['max_context']):
    raise RuntimeError('Context budget exceeded. STOP: do not truncate the system prompt or run convert.')
with safe_open(str(p / 'model.safetensors'), framework='pt', device='cpu') as f:
    print('Safetensors header OK; tensors:', len(f.keys()))
print('Prompt ending:', repr(render_prompt(cfg, queries[0], tok)[-160:]))
if (d / 'data_quant.json').exists():
    raise RuntimeError('data_quant.json already exists. Preserve/review it before rerunning calib.')
print('PREFLIGHT PASSED. No model weight loading, inference, or quantization performed.')
