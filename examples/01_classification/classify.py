#!/usr/bin/env python3
"""
Text Classification Example — USAi API

Reads text items from a CSV, classifies each using the configured model,
writes results to output CSV.

Usage:
    cd examples/01_classification
    python classify.py
"""

import csv
import sys
from pathlib import Path

import yaml

# Add parent dir so we can import api_manager
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from api_manager import APIManager


def main():
    # Load project config
    config_path = Path(__file__).resolve().parent / "config.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)

    # Create output directory
    output_dir = Path(__file__).resolve().parent / "output"
    output_dir.mkdir(exist_ok=True)

    # Load data
    input_path = Path(__file__).resolve().parent / config["input_file"]
    with open(input_path, newline="") as f:
        reader = csv.DictReader(f)
        items = list(reader)

    print(f"  Loaded {len(items)} items from {config['input_file']}")

    # Build the prompt function
    categories = config.get("categories", [])
    cat_str = ", ".join(categories)
    text_col = config.get("text_column", "text")

    def make_prompt(item):
        return f"Categories: {cat_str}\n\nText: {item[text_col]}\n\nCategory:"

    # Initialize API manager and run
    manager = APIManager.from_config(str(config_path))
    results = manager.run_batch(
        items=items,
        prompt_fn=make_prompt,
        item_key_fn=lambda item, idx: item.get("id", str(idx)),
    )

    # Write results
    output_path = Path(__file__).resolve().parent / config["output_file"]
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["id", "text", "category", "model", "tokens_in", "tokens_out", "latency"],
        )
        writer.writeheader()
        for r in results:
            writer.writerow({
                "id": r["key"],
                "text": r["input"].get(text_col, "") if r["input"] else "",
                "category": r["response"].strip(),
                "model": r["model"],
                "tokens_in": r["tokens_in"],
                "tokens_out": r["tokens_out"],
                "latency": f"{r['latency']:.2f}",
            })

    print(f"\n  Results written to {config['output_file']}")
    print(f"  Log written to {config['log_file']}")


if __name__ == "__main__":
    main()
