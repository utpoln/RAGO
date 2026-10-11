# Command-A 111B — discontinued

**Status: discontinued by author decision, not completed.** Do not treat
this directory's contents as a finished external-validation model or
include it in any scored analysis.

## What happened

A technical pilot (48 planned calls, 37 completed before being cut
short by an unrelated background-task time limit) confirmed Command-A
111B worked correctly via MindRouter: 37/37 successful calls, 0
truncations (`finish_reason: "stop"` on every call), 0 empty responses,
and GO-term-formatted output fully compatible with the existing frozen
parser. See the pilot output: `command-a-111b_pilot.jsonl`.

The pilot also measured latency at **45-58 seconds per call** (mean
~50s). At that rate the full 243 x 3 x 4 = 2,916-call run was
projected to take approximately 35-40 hours. The full run was launched
and reached **8 of 2,916 calls** before the author decided this runtime
was not worth it for one of four external-validation models, and asked
to drop Command-A from the experiment. The process was stopped
cleanly (no crash, no API error) at that point.

## Disposition

- `command-a-111b_pilot.jsonl` (37 records) and `command-a-111b.jsonl`
  (8 records) are kept as-is for the audit trail. Neither is scientific
  data -- 8 calls is far too small a sample to analyze, and the pilot
  was explicitly a technical-only check per the original protocol.
- No claims were extracted, scored, or analyzed from either file.
- Command-A 111B is **not** part of the external-validation model set
  reported in the manuscript. The final set is: Llama 3.3 70B, Qwen3
  32B, Gemma3 12B, plus the already-completed GPT-5.5.
- Nothing frozen (the five-model development files, the primary
  held-out results, or the GPT-5.5 results) was touched by this run or
  its discontinuation.
