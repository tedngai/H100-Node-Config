"""Exact-length chat-formatted synthetic inputs, using the cached model tokenizer.

The subprocess only tokenizes on CPU in the existing container. It never loads
model weights, downloads files, sends inference, or modifies the container.
"""

import json
import subprocess

from common import DEFAULT_CONTAINER, digest

TOKENIZER_CODE = r'''
import hashlib, json, random, sys
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
    result = subprocess.run(
        ["docker", "exec", "-i", container, "python3", "-B", "-c", TOKENIZER_CODE],
        input=json.dumps({"tokens": tokens, "concurrency": concurrency,
                          "namespace": namespace, "model": model, "seed": seed,
                          "revision": revision, "purpose": purpose}),
        text=True, capture_output=True, timeout=180, check=True,
    )
    prompts = json.loads(result.stdout)
    for prompt in prompts:
        if len(prompt["input_ids"]) != tokens:
            raise ValueError("Tokenizer returned an unexpected prompt length")
        prompt["sha256"] = digest(prompt["input_ids"])
    if len(prompts) != concurrency:
        raise ValueError("Tokenizer returned an unexpected number of prompts")
    return prompts
