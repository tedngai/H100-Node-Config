"""Exact-length chat-formatted synthetic inputs, using the cached model tokenizer.

The subprocess only tokenizes on CPU in the existing container. It never loads
model weights, downloads files, sends inference, or modifies the container.
"""

import json
from pathlib import Path
import subprocess

from common import DEFAULT_CONTAINER, digest

CODING_CONTEXT_REVISION = "2449a5575bd7ef7259fa81fcc644ab00c94c09b5"

TOKENIZER_CODE = r'''
import hashlib, json, random, sys
from pathlib import Path
from transformers import AutoTokenizer
args = json.load(sys.stdin)
tokenizer = AutoTokenizer.from_pretrained(args['model'], local_files_only=True,
                                         **({'revision': args['revision']} if args.get('revision') else {}))
encode = lambda text: tokenizer.encode(text, add_special_tokens=False)
rng = random.Random(args['seed'])
teams = ['archival', 'facilities', 'library', 'conservation', 'inventory', 'maintenance']
objects = ['wooden crates', 'paper folders', 'spare lamps', 'canvas covers', 'empty cabinets', 'metal shelves']
places = ['north wing', 'south annex', 'east courtyard', 'west storeroom', 'central hall', 'basement office']
records = [
    f'Record {i}: The fictional {rng.choice(teams)} team catalogued {rng.choice(objects)} '
    f'in the {rng.choice(places)}. Batch {rng.randrange(100000, 999999)} contained '
    f'{rng.randrange(2, 90)} ordinary items; routine notes concern deliveries and maintenance.\n'
    for i in range(max(200, args['tokens'] // 20))
]
filler = encode(''.join(records))
results = []
for index in range(args['concurrency']):
    if args.get('purpose') == 'coding':
        task = args['coding_tasks'][index % len(args['coding_tasks'])]
        text = (
            f"Repository coding request {args['namespace']}/{index}; task {task['id']}.\n"
            "Inspect the source context and produce a minimal unified diff implementing "
            "the requested change, including focused regression tests when appropriate. "
            "Return only the diff; do not claim tests were run.\n"
            f"Task: {task['request']}\n"
            "Repository source context follows. Use relevant definitions and tests; "
            "do not apply changes.\n__CODE_CONTEXT__\n"
            "End of source context.\n"
        )
        formatted = tokenizer.apply_chat_template(
            [{'role': 'user', 'content': text}], tokenize=False,
            add_generation_prompt=True, enable_thinking=True)
        beginning, remainder = formatted.split('__CODE_CONTEXT__')
        beginning, end = encode(beginning), encode(remainder)
        remaining = args['tokens'] - len(beginning) - len(end)
        code_ids = encode(args['coding_context'])
        if remaining < 0 or not code_ids:
            raise ValueError('Coding prompt wrapper exceeds target, or source context is empty')
        if len(code_ids) < remaining:
            code_ids *= (remaining + len(code_ids) - 1) // len(code_ids)
        ids = beginning + code_ids[:remaining] + end
        assert len(ids) == args['tokens']
        results.append({'input_ids': ids, 'expected_codes': [], 'task_id': task['id']})
        continue

    codes = [f'{word}-{rng.randrange(100000, 999999)}' for word in ('MAPLE','RIVER','CLOUD')]
    text = (
        f'Independent session {args["namespace"]}/{index}.\n'
        'Read the synthetic archive and return exactly the ALPHA, BETA, and GAMMA codes.\n'
        f'ALPHA code is {codes[0]}.\n__LEFT_FILLER__\n'
        f'BETA code is {codes[1]}.\n__RIGHT_FILLER__\n'
        f'GAMMA code is {codes[2]}.\n'
        'Question: What are the codes? Return the three codes exactly, without explanation.'
    )
    if args.get('purpose') == 'decode':
        text += (
            '\nAfter listing the three codes, write a detailed technical tutorial of at least '
            '2000 words about continuous batching, KV caches, prefix reuse, speculative '
            'decoding, and latency/throughput trade-offs in an LLM inference server. '
            'Use worked examples and explain each mechanism. Do not stop after the codes.'
        )
    formatted = tokenizer.apply_chat_template([{'role': 'user', 'content': text}],
                   tokenize=False, add_generation_prompt=True, enable_thinking=False)
    beginning, remainder = formatted.split('__LEFT_FILLER__')
    middle, end = remainder.split('__RIGHT_FILLER__')
    beginning, middle, end = map(encode, (beginning, middle, end))
    remaining = args['tokens'] - len(beginning) - len(middle) - len(end)
    if remaining < 0 or remaining > len(filler):
        raise ValueError('Prompt target too small, or insufficient natural-text filler')
    left = remaining // 2
    ids = beginning + filler[:left] + middle + filler[left:remaining] + end
    assert len(ids) == args['tokens']
    results.append({'input_ids': ids, 'expected_codes': codes})
assert len({tuple(row['input_ids'][:256]) for row in results}) == args['concurrency']
print(json.dumps(results))
'''


def build_prompts(tokens, concurrency, namespace, model, seed=20261014,
                  container=DEFAULT_CONTAINER, revision=None, purpose="retrieval"):
    payload = {"tokens": tokens, "concurrency": concurrency,
               "namespace": namespace, "model": model, "seed": seed,
               "revision": revision, "purpose": purpose}
    if purpose == "coding":
        payload["coding_tasks"] = CODING_TASKS
        payload["coding_context"] = coding_context()
    result = subprocess.run(
        ["docker", "exec", "-i", container, "python3", "-B", "-c", TOKENIZER_CODE],
        input=json.dumps(payload),
        text=True, capture_output=True, timeout=180, check=True,
    )
    prompts = json.loads(result.stdout)
    for prompt in prompts:
        if len(prompt["input_ids"]) != tokens:
            raise ValueError("Tokenizer returned an unexpected prompt length")
        prompt["sha256"] = digest(prompt["input_ids"])
        if purpose == "coding":
            prompt["coding_context_revision"] = CODING_CONTEXT_REVISION
    if len(prompts) != concurrency:
        raise ValueError("Tokenizer returned an unexpected number of prompts")
    return prompts


CODING_TASKS = [
    {
        "id": "arrival-schedule-validation",
        "request": "In tests/benchmark.py, make planned_arrival_offsets reject numeric overflow and non-finite products, and add focused unit tests.",
    },
    {
        "id": "unknown-telemetry-policy",
        "request": "In tests/benchmark_policy.py, add a helper that classifies missing scheduler telemetry as unavailable rather than zero, with regression tests.",
    },
    {
        "id": "gpu-memory-parser",
        "request": "In tests/gpu_memory.py, harden parsing against duplicate device indices and malformed rows while preserving sorted per-GPU results; include tests.",
    },
    {
        "id": "profile-allocation-drift",
        "request": "In tests/profiles.py, make allocation-affecting expected fields explicit for a derived profile and test that unrelated baseline settings remain checked.",
    },
    {
        "id": "stream-token-accounting",
        "request": "In tests/benchmark.py, add a regression test for cumulative streaming token counts when text stops changing before the final token event.",
    },
    {
        "id": "audit-traffic-bounds",
        "request": "In tests/runtime_audit.py, improve handling of unparsed request-log entries without saving raw logs; add a focused test.",
    },
]


CODING_CONTEXT_FILES = (
    "benchmark.py", "benchmark_policy.py", "common.py", "gpu_memory.py",
    "profiles.py", "runtime_audit.py", "test_benchmark_policy.py",
    "test_harness.py",
)


def coding_context():
    """Return the exact harness source snapshot used by both A/B arms."""
    root = Path(__file__).resolve().parent
    sections = []
    for name in CODING_CONTEXT_FILES:
        result = subprocess.run(
            ["git", "-C", str(root.parent), "show",
             f"{CODING_CONTEXT_REVISION}:tests/{name}"],
            text=True, capture_output=True, check=True,
        )
        sections.append(f"# {name}\n{result.stdout}")
    return "\n".join(sections)
