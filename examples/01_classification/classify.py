#!/usr/bin/env python3
"""
Text Classification Example — USAi API

Reads text items from a CSV, classifies each using the configured model,
writes results to a timestamped output CSV.

Usage:
    cd examples/01_classification
    python classify.py
"""

import csv
import json
import sys
from pathlib import Path

import yaml

# Add parent dir so we can import api_manager
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from api_manager import APIManager


def parse_response(response_text: str) -> dict:
    """Parse model response, expecting JSON with category and confidence."""
    try:
        text = response_text.strip()
        # Handle cases where the model wraps JSON in markdown code fences
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        parsed = json.loads(text)
        return {
            "category": parsed.get("category", "PARSE_ERROR"),
            "confidence": parsed.get("confidence", None),
        }
    except (json.JSONDecodeError, AttributeError):
        return {
            "category": response_text.strip()[:100],
            "confidence": None,
        }


def main():
    # Load project config
    config_path = Path(__file__).resolve().parent / "config.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)

    # Create output directory
    output_dir = Path(__file__).resolve().parent / config.get("output_dir", "output")
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

    # Parse responses and assemble CSV rows
    output_fname = f"results_{manager.run_timestamp}.csv"
    output_path = output_dir / output_fname

    enriched = []
    for r in results:
        parsed = parse_response(r.get("response", ""))
        enriched.append({
            "key": r["key"],
            "text": r["input"].get(text_col, "") if r.get("input") else "",
            "category": parsed["category"],
            "confidence": parsed["confidence"],
            "finish_reason": r.get("finish_reason", ""),
            "model": r.get("model", ""),
            "tokens_in": r.get("tokens_in", 0),
            "tokens_out": r.get("tokens_out", 0),
            "latency": r.get("latency", 0.0),
        })

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "id", "text", "category", "confidence",
                "finish_reason", "model", "tokens_in", "tokens_out", "latency",
            ],
        )
        writer.writeheader()
        for row in enriched:
            writer.writerow({
                "id": row["key"],
                "text": row["text"],
                "category": row["category"],
                "confidence": "" if row["confidence"] is None else f"{row['confidence']:.2f}",
                "finish_reason": row["finish_reason"],
                "model": row["model"],
                "tokens_in": row["tokens_in"],
                "tokens_out": row["tokens_out"],
                "latency": f"{row['latency']:.2f}",
            })

    print(f"\n  Results written to {output_path}")
    print(f"  Log written to {manager.log_file}")

    # Flag truncated responses — finish_reason == "length" means max_tokens was too low
    truncated = [row for row in enriched if row["finish_reason"] == "length"]
    if truncated:
        print(f"\n  WARNING: {len(truncated)} responses were truncated (max_tokens too low)")
        print(f"  Affected items: {[row['key'] for row in truncated[:5]]}")
        if len(truncated) > 5:
            print(f"  ...and {len(truncated) - 5} more")


if __name__ == "__main__":
    main()
