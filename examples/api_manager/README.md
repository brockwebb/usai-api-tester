# API Manager

The shared engine for all USAi API example projects.

## What it does

- **Rate limiting**: Hard cap at 3 calls/sec/key (configurable). Never violates.
- **Exponential backoff**: On 429 and 5xx errors. Configurable retries, base delay, jitter.
- **Progress display**: Percentage complete, items processed, ETA. Terminal-friendly.
- **Logging**: Every call logged to JSONL — timestamp, model, status, tokens, latency.
- **Checkpointing**: Results written incrementally. Crash at item 47/50? Restart skips 1-47.
- **Auth handling**: Detects 401, pauses, prompts for new key, continues.

## Usage

```python
from api_manager import APIManager

manager = APIManager.from_config("config.yaml")

results = manager.run_batch(
    items=my_data,
    prompt_fn=lambda item: f"Classify this: {item['text']}",
)
```

## Config

The project config.yaml is passed to the manager. Required fields:

```yaml
model: "gemini-2.5-flash"
system_prompt: "You are a classifier."
max_tokens: 256
temperature: 0.0

# API manager settings
rate_limit: 3          # calls per second
max_retries: 5
backoff_base: 2.0      # seconds, doubles each retry
backoff_jitter: true
log_file: "run.jsonl"
checkpoint_file: "checkpoint.json"
```
