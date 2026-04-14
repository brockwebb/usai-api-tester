"""
API Manager — shared engine for USAi API example projects.

Features:
- Token bucket rate limiter (default 3 calls/sec)
- Exponential backoff with jitter on 429/5xx
- Progress bar (% complete, processed/total, ETA)
- JSONL call logging
- Checkpoint/restart support
- 401 detection with interactive re-auth
"""

import json
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
import yaml
from dotenv import load_dotenv, set_key


def _find_dotenv(start_path: Path) -> Path | None:
    """
    Walk up from start_path looking for a .env file.
    Checks the directory itself, its parent, and grandparent.
    Returns the Path if found, else None.
    """
    search = start_path if start_path.is_dir() else start_path.parent
    for _ in range(3):
        candidate = search / ".env"
        if candidate.exists():
            return candidate
        search = search.parent
    return None


class APIManager:
    """
    Rate-limited, fault-tolerant API call manager for USAi.

    Features:
    - Token bucket rate limiter (default 3 calls/sec)
    - Exponential backoff with jitter on 429/5xx
    - Progress bar (% complete, processed/total, ETA)
    - JSONL call logging
    - Checkpoint/restart support
    - 401 detection with interactive re-auth
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        system_prompt: str = "",
        max_tokens: int = 1024,
        temperature: float | None = None,
        rate_limit: float = 3.0,
        max_retries: int = 5,
        backoff_base: float = 2.0,
        backoff_jitter: bool = True,
        log_file: str = "run.jsonl",
        checkpoint_file: str = "checkpoint.json",
        env_path: Path | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.system_prompt = system_prompt
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.rate_limit = rate_limit
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_jitter = backoff_jitter
        self.log_file = log_file
        self.checkpoint_file = checkpoint_file
        self.env_path = env_path

        # Rate limiter state: timestamps of recent calls
        self._call_times: list[float] = []

    @classmethod
    def from_config(cls, config_path: str) -> "APIManager":
        """
        Load from a project config.yaml.
        Reads .env for API key and base URL by walking up from the config location.
        """
        cfg_path = Path(config_path).resolve()
        with open(cfg_path) as f:
            config = yaml.safe_load(f)

        # Find and load .env
        env_path = _find_dotenv(cfg_path.parent)
        if env_path:
            load_dotenv(env_path, override=True)

        api_key = os.getenv("USAI_API_KEY", "")
        base_url = os.getenv("USAI_BASE_URL", "")

        if not api_key or api_key == "your-api-key-here":
            api_key = cls._prompt_for_api_key(reason="No API key found", env_path=env_path)

        if not base_url:
            base_url = cls._prompt_for_base_url(env_path=env_path)

        model = config.get("model")
        if not model:
            raise ValueError("config.yaml must specify 'model'")

        return cls(
            base_url=base_url,
            api_key=api_key,
            model=model,
            system_prompt=config.get("system_prompt", ""),
            max_tokens=config.get("max_tokens", 1024),
            temperature=config.get("temperature", None),
            rate_limit=config.get("rate_limit", 3.0),
            max_retries=config.get("max_retries", 5),
            backoff_base=config.get("backoff_base", 2.0),
            backoff_jitter=config.get("backoff_jitter", True),
            log_file=config.get("log_file", "run.jsonl"),
            checkpoint_file=config.get("checkpoint_file", "checkpoint.json"),
            env_path=env_path,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_batch(
        self,
        items: list,
        prompt_fn: callable,
        item_key_fn: callable = None,
    ) -> list[dict]:
        """
        Process a list of items through the API.

        Args:
            items: list of anything — the prompt_fn knows how to handle them
            prompt_fn: callable(item) -> str, formats the user prompt
            item_key_fn: callable(item, index) -> str, returns a unique key
                         for checkpointing. Defaults to str(index).

        Returns:
            list of dicts: {"key": str, "input": item, "response": str,
                            "model": str, "status": int, "tokens_in": int,
                            "tokens_out": int, "latency": float}
        """
        if item_key_fn is None:
            item_key_fn = lambda item, idx: str(idx)

        checkpoint = self._load_checkpoint()
        results = []
        total = len(items)
        start_time = time.time()
        processed = 0

        for idx, item in enumerate(items):
            key = item_key_fn(item, idx)

            # Resume from checkpoint
            if key in checkpoint:
                sys.stdout.write(f"\r  [skip] {key} (already done)  ")
                sys.stdout.flush()
                results.append(checkpoint[key])
                processed += 1
                self._print_progress(processed, total, start_time)
                continue

            prompt = prompt_fn(item)
            result = self._call_with_retries(key=key, prompt=prompt, item=item)
            results.append(result)
            processed += 1

            if result["status"] == 200:
                self._save_checkpoint(key, result)

            self._print_progress(processed, total, start_time)

        # Final newline so next output doesn't clobber the progress bar
        print()
        return results

    def call(self, prompt: str) -> dict:
        """
        Make a single API call. Handles rate limiting and retries.
        Returns dict with response, status, tokens, latency.
        Useful for interactive/ad-hoc calls outside of batch mode.
        """
        return self._call_with_retries(key="single", prompt=prompt, item=None)

    # ------------------------------------------------------------------
    # Internal: request execution
    # ------------------------------------------------------------------

    def _call_with_retries(self, *, key: str, prompt: str, item) -> dict:
        """Execute one API call with retry/backoff logic."""
        attempt = 0
        while True:
            self._wait_for_rate_limit()
            result = self._make_request(key=key, prompt=prompt, item=item)

            if result["status"] == 200:
                return result

            if result["status"] == 401:
                # Auth failure: prompt for new key, then retry (no backoff)
                print(f"\n  Auth failed (401). Key may have expired (rotates every 7 days).")
                self.api_key = self._prompt_for_api_key(
                    reason="API key expired or invalid",
                    env_path=self.env_path,
                )
                continue  # retry immediately with new key

            if result["status"] in (429,) or result["status"] >= 500:
                attempt += 1
                if attempt > self.max_retries:
                    print(f"\n  Giving up on {key} after {self.max_retries} retries (status {result['status']})")
                    return result
                delay = self._backoff_delay(attempt)
                print(f"\n  {result['status']} on {key}, retry {attempt}/{self.max_retries} in {delay:.1f}s...")
                time.sleep(delay)
                continue

            # Non-retryable error (4xx other than 401/429)
            return result

    def _make_request(self, *, key: str, prompt: str, item) -> dict:
        """Send one HTTP request. Returns result dict regardless of outcome."""
        url = f"{self.base_url}/api/v1/chat/completions"
        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        messages = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.append({"role": "user", "content": prompt})

        body: dict = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
        }
        if self.temperature is not None:
            body["temperature"] = self.temperature

        t0 = time.time()
        try:
            resp = requests.post(url, headers=headers, json=body, timeout=60)
        except requests.exceptions.Timeout:
            return self._error_result(key=key, item=item, prompt=prompt, status=0, error="timeout")
        except requests.exceptions.ConnectionError as exc:
            return self._error_result(key=key, item=item, prompt=prompt, status=0, error=f"connection: {exc}")

        latency = time.time() - t0
        status = resp.status_code

        if status == 200:
            data = resp.json()
            choice = data.get("choices", [{}])[0]
            response_text = choice.get("message", {}).get("content", "")
            usage = data.get("usage", {})
            tokens_in = usage.get("prompt_tokens", 0)
            tokens_out = usage.get("completion_tokens", 0)

            result = {
                "key": key,
                "input": item,
                "response": response_text,
                "model": self.model,
                "status": status,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "latency": latency,
            }
            self._log_call({
                "timestamp": datetime.utcnow().isoformat(timespec="seconds"),
                "key": key,
                "model": self.model,
                "status": status,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "latency": round(latency, 3),
                "prompt_preview": prompt[:100],
            })
            return result

        # Non-200
        self._log_call({
            "timestamp": datetime.utcnow().isoformat(timespec="seconds"),
            "key": key,
            "model": self.model,
            "status": status,
            "tokens_in": 0,
            "tokens_out": 0,
            "latency": round(latency, 3),
            "prompt_preview": prompt[:100],
            "error": resp.text[:200],
        })
        return self._error_result(key=key, item=item, prompt=prompt, status=status, error=resp.text[:200])

    @staticmethod
    def _error_result(*, key: str, item, prompt: str, status: int, error: str) -> dict:
        return {
            "key": key,
            "input": item,
            "response": "",
            "model": "",
            "status": status,
            "tokens_in": 0,
            "tokens_out": 0,
            "latency": 0.0,
            "error": error,
        }

    # ------------------------------------------------------------------
    # Rate limiter
    # ------------------------------------------------------------------

    def _wait_for_rate_limit(self):
        """Block until we can make another call within the rate limit."""
        now = time.time()
        window = 1.0  # 1-second sliding window

        # Drop timestamps older than 1 second
        self._call_times = [t for t in self._call_times if now - t < window]

        if len(self._call_times) >= self.rate_limit:
            # Must wait until the oldest call in the window ages out
            oldest = self._call_times[0]
            sleep_for = window - (now - oldest) + 0.001  # small buffer
            if sleep_for > 0:
                time.sleep(sleep_for)
            # Re-clean after sleep
            now = time.time()
            self._call_times = [t for t in self._call_times if now - t < window]

        self._call_times.append(time.time())

    # ------------------------------------------------------------------
    # Progress display
    # ------------------------------------------------------------------

    def _print_progress(self, current: int, total: int, start_time: float):
        """Overwrite current terminal line with progress info."""
        elapsed = time.time() - start_time
        pct = (current / total) * 100
        rate = current / elapsed if elapsed > 0 else 0
        eta = (total - current) / rate if rate > 0 else 0
        sys.stdout.write(
            f"\r  [{pct:5.1f}%] {current}/{total} | {rate:.1f} calls/sec | ETA: {eta:.0f}s  "
        )
        sys.stdout.flush()

    # ------------------------------------------------------------------
    # Backoff
    # ------------------------------------------------------------------

    def _backoff_delay(self, attempt: int) -> float:
        """Calculate exponential backoff delay for the given attempt number."""
        delay = self.backoff_base * (2 ** (attempt - 1))
        if self.backoff_jitter:
            delay += random.uniform(0, delay * 0.25)
        return delay

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _log_call(self, entry: dict):
        """Append a single call record to the JSONL log file."""
        try:
            log_path = Path(self.log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError as exc:
            print(f"\n  Warning: could not write to log file {self.log_file}: {exc}", file=sys.stderr)

    # ------------------------------------------------------------------
    # Checkpointing
    # ------------------------------------------------------------------

    def _load_checkpoint(self) -> dict:
        """Load checkpoint file if it exists, else return empty dict."""
        cp_path = Path(self.checkpoint_file)
        if cp_path.exists():
            try:
                with open(cp_path) as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save_checkpoint(self, key: str, result: dict):
        """Add result to checkpoint and write to disk."""
        cp_path = Path(self.checkpoint_file)
        cp_path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint = self._load_checkpoint()
        checkpoint[key] = result
        with open(cp_path, "w") as f:
            json.dump(checkpoint, f, indent=2)

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _prompt_for_api_key(reason: str = "No API key found", env_path: Path | None = None) -> str:
        """Prompt for a new API key and save it to .env."""
        print()
        print(f"  {reason}.")
        print("  Your key will be saved to .env (git-ignored).")
        print()

        while True:
            key = input("  API Key: ").strip()
            if key:
                break
            print("  Key cannot be empty.")

        target = env_path or Path(".env")
        if not target.exists():
            target.touch()
        set_key(str(target), "USAI_API_KEY", key)
        os.environ["USAI_API_KEY"] = key
        print(f"  Key saved to {target}")
        return key

    @staticmethod
    def _prompt_for_base_url(env_path: Path | None = None) -> str:
        """Prompt for base URL and save it to .env."""
        print()
        print("  No USAI_BASE_URL found in .env.")
        print("  Example: https://your-gateway.example.gov")
        print()

        while True:
            url = input("  Base URL: ").strip().rstrip("/")
            if url:
                break
            print("  URL cannot be empty.")

        target = env_path or Path(".env")
        if not target.exists():
            target.touch()
        set_key(str(target), "USAI_BASE_URL", url)
        os.environ["USAI_BASE_URL"] = url
        print(f"  URL saved to {target}")
        return url
