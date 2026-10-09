"""
Submits a 48-request pilot batch (4 proteins x 3 namespaces x 4 prompts)
for a named configuration. Prompts are imported unmodified from the
frozen scripts/llm_prompting_heldout.py::build_prompts() -- not retyped,
not restructured for caching (scientific content unchanged).
"""
import os, sys, json, importlib.util
from pathlib import Path
from openai import OpenAI

HERE = Path(__file__).parent
RAGO = HERE.parent.parent

spec = importlib.util.spec_from_file_location("m", RAGO / "scripts" / "llm_prompting_heldout.py")
mod = importlib.util.module_from_spec(spec)
_real_argv = sys.argv
sys.argv = ["x", "--api_key", "unused"]
spec.loader.exec_module(mod)
sys.argv = _real_argv
build_prompts = mod.build_prompts
NAMESPACES = mod.NAMESPACES

MODEL_ID = "gpt-5.5-2026-04-23"

CONFIGS = {
    "A": {"reasoning_effort": "low", "max_completion_tokens": 4000},
    "B": {"reasoning_effort": "medium", "max_completion_tokens": 4000},
}

def main(config_name):
    cfg = CONFIGS[config_name]
    pilot = json.load(open(HERE / "pilot_sample.json"))
    entries = pilot["pilot_protein_records"]

    requests = []
    for entry in entries:
        for ns in NAMESPACES:
            prompts = build_prompts(entry, ns)
            for prompt_id, prompt_text in prompts.items():
                custom_id = f"{entry['accession']}|{ns}|{prompt_id}"
                requests.append({
                    "custom_id": custom_id,
                    "method": "POST",
                    "url": "/v1/chat/completions",
                    "body": {
                        "model": MODEL_ID,
                        "messages": [{"role": "user", "content": prompt_text}],
                        "max_completion_tokens": cfg["max_completion_tokens"],
                        "reasoning_effort": cfg["reasoning_effort"],
                        "seed": 42,
                    },
                })
    assert len(requests) == 48, f"expected 48 requests, got {len(requests)}"

    batch_input_path = HERE / "raw" / f"config_{config_name}_batch_input.jsonl"
    with open(batch_input_path, "w") as f:
        for r in requests:
            f.write(json.dumps(r) + "\n")

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    upload = client.files.create(file=open(batch_input_path, "rb"), purpose="batch")
    batch = client.batches.create(input_file_id=upload.id, endpoint="/v1/chat/completions",
                                   completion_window="24h",
                                   metadata={"config": config_name, "purpose": "pilot_cost_optimization"})
    print(f"Config {config_name}: batch {batch.id}  status={batch.status}  input_file={upload.id}")
    with open(HERE / "logs" / f"config_{config_name}_batch_id.txt", "w") as f:
        f.write(batch.id)
    return batch.id


if __name__ == "__main__":
    main(sys.argv[1])
