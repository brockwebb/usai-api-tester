# Example: Text Classification

Batch-classify text items using the USAi API.

## What it does

Reads a CSV of text items, sends each to the configured model with a
classification prompt, writes results to an output CSV.

## Files

- `config.yaml` — model, prompt template, settings
- `data.csv` — input data (small sample included)
- `classify.py` — the script
- `output/` — results go here (gitignored)

## Usage

```bash
cd examples/01_classification
python classify.py
```

## Customizing

Edit `config.yaml` to change the model, prompt, or classification categories.
Swap `data.csv` with your own data. The script doesn't care what you're
classifying — it just formats the prompt and records the response.
