# USAi API Examples

Practical examples for building with the USAi API. Each project is a
self-contained use case powered by a shared API manager.

## Prerequisites

Before running any example, use the main `usai_tester.py` in the repo root
to verify your API key and endpoint are working. That's what it's for.

All examples read credentials from the `.env` file in the repo root.

## Architecture

```
usai_tester.py              ← Step 1: verify connectivity
examples/
├── api_manager/             ← Shared engine: rate limiting, backoff, logging
├── 01_classification/       ← Each project: config + data + small script
├── 02_.../
```

Every project follows the same pattern:
1. A `config.yaml` defining the model, prompts, and parameters
2. A data file (CSV, JSON, or text)
3. A short Python script that loads config, feeds data through the API manager, writes results

The API manager handles:
- Rate limiting (3 calls/sec hard cap, configurable)
- Exponential backoff with jitter on 429/5xx
- Progress display (% complete, ETA)
- Per-call logging to JSONL
- Checkpointing (crash-safe, restartable)
- Auth failure detection with re-prompt

Projects don't talk to the API directly. They go through the manager.

## Running an example

```bash
cd examples/01_classification
python classify.py
```

Each project README has specific instructions.
