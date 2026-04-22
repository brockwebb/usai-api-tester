# Lab: Text Classification with the USAi API

This lab walks you through batch text classification using the USAi API.
Along the way you'll learn about token limits, temperature, error handling,
and crash recovery — the things that matter when you move from "it works
once" to "it works in production."

## Prerequisites

- Completed setup with `usai_tester.py` (your API key and endpoint work)
- Python virtual environment activated with requirements installed

## Quick Start

```bash
cd examples/01_classification
python classify.py
```

This will classify ~50 text items, writing results to `output/results_<timestamp>.csv`.

## Lab Exercises

### Exercise 1: What happens when max_tokens is too low?

Open `config.yaml` and change `max_tokens` from `256` to `50`. Run the script.

Look at the output. You'll see a warning about truncated responses. Open the
results CSV and find those rows — the `finish_reason` column will say `length`
instead of `stop`, and the category will be garbage (cut off mid-word).

This is one of the most common silent failures in LLM pipelines. The model
didn't error — it just ran out of room. Your results look complete but they're
wrong.

**Question to consider:** How would you automate detection of this in a
production pipeline? (Hint: the `finish_reason` field is already in your
results. What would you build around it?)

Set `max_tokens` back to `256` before continuing.

### Exercise 2: Why temperature 0.0?

The config sets `temperature: 0.0`. This minimizes stochastic variance in
the output — the model will tend to give the same answer for the same input
across runs.

Note "minimizes," not "eliminates." Even at temperature 0.0, other parameters
can influence output: `top_p`, internal model state, gateway routing decisions,
and provider-side non-determinism. This is why every parameter is recorded in
`config.yaml` — reproducibility requires knowing exactly what you sent.

**Try it:** Run the classification twice with `temperature: 0.0`. Compare the
results CSVs. Most classifications will match, but don't be surprised if a few
differ — especially on ambiguous texts.

Now change `temperature` to `1.0` and run again. Compare. You'll see more
variation, and some classifications will be creative interpretations rather
than straightforward assignments.

### Exercise 3: Can you trust model confidence?

Each result includes a `confidence` score. This is self-reported by the model,
not a calibrated probability.

**Look at your results.** Find cases where confidence is high (>0.9) but the
classification seems wrong or questionable. Find cases where confidence is
moderate (0.5-0.7) but the classification is clearly correct.

Models are notoriously poorly calibrated on their own uncertainty. A model
reporting 0.95 confidence is not meaningfully different from one reporting 0.80.
Treat self-reported confidence as a rough signal for triage, not as a
measurement. For production systems, consider calibration techniques, human
review of low-confidence items, or ensemble methods (comparing across models).

### Exercise 4: Crash recovery

This exercise demonstrates checkpoint-based recovery — critical for long-running
batch jobs where network blips, machine sleep, or other interruptions can kill
a process mid-run.

1. Delete any existing checkpoint: `rm -f output/checkpoint.json`
2. Start the classification: `python classify.py`
3. Watch the progress. When it reaches roughly 40-60%, press `Ctrl+C` to kill it.
4. Look at `output/checkpoint.json` — it contains results for every completed item.
5. Run `python classify.py` again.
6. Watch the progress — it skips all previously completed items and picks up
   where it left off.

In production, interruptions are not exceptional — they're expected. Network
timeouts, API rate limits, machine sleep policies, VPN disconnects, and
deployment restarts all kill long-running jobs. Checkpointing means you lose
minutes, not hours.

**Note:** Some government machines have aggressive sleep policies. For
long-running batch jobs, consider tools like `caffeinate` (macOS),
`powercfg` (Windows), or running inside a `screen`/`tmux` session on a server.

### Exercise 5: Compare models

Edit `config.yaml` and change the `model` field to a different model (e.g.,
`claude_4_5_sonnet` or whatever your API's model list showed in the tester).
Run the classification again.

Compare the two results CSVs. Where do the models agree? Where do they
disagree? Are disagreements on the ambiguous items you'd expect?

This is the foundation of model evaluation for your use case. The "best"
model isn't the one with the highest benchmark score — it's the one that
performs best on YOUR data with YOUR categories.

## Understanding the Output Files

### results_<timestamp>.csv

One row per input item. Columns:
- `id` — item identifier from input data
- `text` — the original text that was classified
- `category` — the model's classification
- `confidence` — model's self-reported confidence (see Exercise 3 caveats)
- `finish_reason` — `stop` means normal completion, `length` means truncated
- `model` — which model produced this result
- `tokens_in` — prompt tokens consumed
- `tokens_out` — completion tokens consumed
- `latency` — response time in seconds

### run_<timestamp>.jsonl

The API call log. One JSON object per line, one line per API call. Records
every call including retries and failures. Use this for:
- **Debugging**: which call failed and why?
- **Cost tracking**: total tokens consumed across the run
- **Performance analysis**: latency patterns, retry frequency
- **Audit trail**: what was sent to the API and when?

### checkpoint.json

Crash recovery state. Maps item keys to completed results. The script checks
this on startup and skips completed items. Delete this file to force a full
re-run. This file is NOT timestamped because the restart logic needs a stable
filename to find it.

## What's Next?

Once you're comfortable with this pattern, look at the other examples or
build your own. Every project follows the same structure:
1. A `config.yaml` with model and API manager settings
2. A data file
3. A short script that formats prompts and calls the API manager

The API manager handles rate limiting, retries, logging, and checkpointing.
Your script just handles the domain logic.
