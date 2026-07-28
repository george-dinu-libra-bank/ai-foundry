# Raw run output

The evidence behind the numbers in [../NOTES.md](../NOTES.md) and
[../data/questions.md](../data/questions.md). Both files are generated — regenerate them
rather than editing them.

| File | Produced by | Contains |
|---|---|---|
| `retrieval-before-after.json` | `uv run python scripts/measure_retrieval.py --json ...` | Both arms of the before/after comparison: per-probe ranks, scores, top source, and the point counts after one and two identical ingests. |
| `questions-run.json` | `uv run python scripts/run_questions.py --json ...` | The full 15-question run: every answer in full, the sources retrieved, top score, verdict, token usage and latency. |

Commands are run from `code/backend/`. Both scripts wipe or read the live Qdrant
collection, so the numbers correspond to the corpus in `data/` at the recorded commit.
