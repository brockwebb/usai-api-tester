#!/usr/bin/env python3
"""
USAi API Tester — A minimal CLI tool for testing the USAi federal AI gateway.

"It looks like you're trying to query a federal AI. Would you like help with that?"

Usage:
    python usai_tester.py

Requires Python 3.10+
"""

import json
import os
import random
import sys
import textwrap
import time
from pathlib import Path

import requests
import yaml
from colorama import Fore, Style, init as colorama_init
from dotenv import load_dotenv, set_key

# ---------------------------------------------------------------------------
# Constants & config
# ---------------------------------------------------------------------------

APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.yaml"
ENV_PATH = APP_DIR / ".env"
ENV_EXAMPLE_PATH = APP_DIR / ".env.example"

VERSION = "0.1.0"

# Clippy-adjacent quips
STARTUP_QUIPS = [
    '"It looks like you\'re trying to query a federal AI. Would you like help with that?"',
    '"Per my last API call..."',
    '"Have you tried turning the model off and on again?"',
    '"All models are wrong. Some are useful. Let\'s find out which."',
    '"Stateless, like my memory of your last prompt."',
    '"No context was harmed in the making of this API call."',
    '"Welcome back. I have no idea who you are. That\'s by design."',
    '"Remember: every call is a first date. No history, no baggage."',
]

SWITCH_QUIPS = [
    "Switching models. New model, who dis?",
    "Swapping brains. Stand by.",
    "Different model, same stateless energy.",
    "Let's see what this one thinks.",
    "Plot twist: trying a different model.",
]

COMPARE_QUIPS = [
    "Same prompt, different brain. Let's compare.",
    "Second opinion incoming.",
    "Two models enter, one response wins.",
    "A/B testing, government style.",
]

# Terminal width for formatting
TERM_WIDTH = min(os.get_terminal_size().columns if sys.stdout.isatty() else 80, 100)


# ---------------------------------------------------------------------------
# Color helpers
# ---------------------------------------------------------------------------

def c_header(text: str) -> str:
    return f"{Fore.CYAN}{Style.BRIGHT}{text}{Style.RESET_ALL}"

def c_model(text: str) -> str:
    return f"{Fore.CYAN}{text}{Style.RESET_ALL}"

def c_prompt(text: str) -> str:
    return f"{Fore.WHITE}{Style.BRIGHT}{text}{Style.RESET_ALL}"

def c_response(text: str) -> str:
    return f"{Fore.GREEN}{text}{Style.RESET_ALL}"

def c_error(text: str) -> str:
    return f"{Fore.RED}{text}{Style.RESET_ALL}"

def c_warn(text: str) -> str:
    return f"{Fore.YELLOW}{text}{Style.RESET_ALL}"

def c_dim(text: str) -> str:
    return f"{Style.DIM}{text}{Style.RESET_ALL}"

def c_menu(text: str) -> str:
    return f"{Fore.MAGENTA}{text}{Style.RESET_ALL}"


def separator(char: str = "─") -> str:
    return c_dim(char * TERM_WIDTH)


def print_wrapped(text: str, color_fn=None, indent: str = "  "):
    """Print text wrapped to terminal width with optional color."""
    wrapped = textwrap.fill(text, width=TERM_WIDTH - len(indent),
                            initial_indent=indent, subsequent_indent=indent)
    if color_fn:
        print(color_fn(wrapped))
    else:
        print(wrapped)


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_config() -> dict:
    """Load config.yaml or die trying."""
    if not CONFIG_PATH.exists():
        print(c_error(f"Config file not found: {CONFIG_PATH}"))
        print("Copy config.yaml from the repo and customize it.")
        sys.exit(1)
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def get_model_by_id(config: dict, model_id: str) -> dict | None:
    """Look up a model entry by its ID."""
    for m in config.get("models", []):
        if m["id"] == model_id:
            return m
    return None


# ---------------------------------------------------------------------------
# API key management
# ---------------------------------------------------------------------------

def load_api_key() -> str | None:
    """Load API key from .env file."""
    load_dotenv(ENV_PATH, override=True)
    return os.getenv("USAI_API_KEY")


def load_base_url(config: dict) -> str:
    """Load base URL from .env or fall back to config.yaml."""
    load_dotenv(ENV_PATH, override=True)
    env_url = os.getenv("USAI_BASE_URL")
    if env_url and env_url != "https://your-agency-endpoint.usai.gov":
        return env_url.rstrip("/")
    cfg_url = config.get("base_url", "")
    if cfg_url and cfg_url != "https://your-agency-endpoint.usai.gov":
        return cfg_url.rstrip("/")
    return ""


def prompt_for_api_key(reason: str = "No API key found") -> str:
    """Prompt user for API key and save to .env."""
    print()
    print(c_warn(f"  {reason}."))
    print(c_dim("  Your key will be saved to .env (git-ignored)."))
    print()

    while True:
        key = input(f"  {c_header('API Key')}: ").strip()
        if key:
            break
        print(c_error("  Key cannot be empty."))

    # Create .env if it doesn't exist (copy from example if available)
    if not ENV_PATH.exists():
        if ENV_EXAMPLE_PATH.exists():
            import shutil
            shutil.copy(ENV_EXAMPLE_PATH, ENV_PATH)
        else:
            ENV_PATH.touch()

    set_key(str(ENV_PATH), "USAI_API_KEY", key)
    os.environ["USAI_API_KEY"] = key
    print(c_dim("  Key saved to .env"))
    return key


def prompt_for_base_url() -> str:
    """Prompt user for the API base URL and save to .env."""
    print()
    print(c_warn("  No API base URL configured."))
    print(c_dim("  Find your endpoint in the USAi console under the API tab (left menu)."))
    print()

    while True:
        url = input(f"  {c_header('Base URL')}: ").strip().rstrip("/")
        if url.startswith("http"):
            break
        print(c_error("  URL must start with http:// or https://"))

    if not ENV_PATH.exists():
        ENV_PATH.touch()

    set_key(str(ENV_PATH), "USAI_BASE_URL", url)
    os.environ["USAI_BASE_URL"] = url
    print(c_dim("  URL saved to .env"))
    return url


# ---------------------------------------------------------------------------
# Model discovery
# ---------------------------------------------------------------------------

def fetch_models(base_url: str, api_key: str) -> list[dict]:
    """
    Call /api/v1/models to get the actual available models from the API.
    Returns a list of model dicts with at least 'id' and 'owned_by'.
    """
    url = f"{base_url}/api/v1/models"
    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=30)
    except requests.exceptions.ConnectionError:
        print(c_error("\n  Connection failed fetching models."))
        print(c_dim(f"  Tried: {url}"))
        return []
    except requests.exceptions.Timeout:
        print(c_error("\n  Timed out fetching models."))
        return []

    if resp.status_code == 401:
        print(c_error("\n  Authentication failed (401) fetching models."))
        return []

    if resp.status_code != 200:
        print(c_error(f"\n  Failed to fetch models: HTTP {resp.status_code}"))
        try:
            print(c_dim(f"  {resp.json()}"))
        except Exception:
            print(c_dim(f"  {resp.text[:300]}"))
        return []

    data = resp.json()
    models = data.get("data", [])
    return models


def build_model_list(api_models: list[dict], config: dict) -> list[dict]:
    """
    Build the working model list from the API response.
    Uses the actual model IDs from the API. Merges in any config overrides
    (temp ranges, defaults) if they exist, but the API is the source of truth.
    """
    # Config models keyed by ID for quick lookup
    config_lookup = {}
    for m in config.get("models", []):
        config_lookup[m["id"]] = m

    result = []
    for api_model in api_models:
        model_id = api_model.get("id", "")
        owned_by = api_model.get("owned_by", "Unknown")

        # Check if config has overrides for this model
        cfg = config_lookup.get(model_id, {})

        result.append({
            "id": model_id,
            "name": cfg.get("name", model_id),  # fall back to ID as display name
            "provider": cfg.get("provider", owned_by),
            "temp_range": cfg.get("temp_range", [0.0, 1.0]),
            "temp_default": cfg.get("temp_default", 0.5),
        })

    return result


# ---------------------------------------------------------------------------
# API calls
# ---------------------------------------------------------------------------

def call_chat_completion(
    base_url: str,
    api_key: str,
    model_id: str,
    user_prompt: str,
    config: dict,
    system_prompt: str | None = None,
) -> dict:
    """
    Make a chat completion request to USAi API.
    Returns the full response dict or raises an exception.
    """
    url = f"{base_url}/api/v1/chat/completions"

    messages = []
    # Add system prompt if configured
    sys_prompt = system_prompt or config.get("system_prompt", "")
    if sys_prompt:
        messages.append({"role": "system", "content": sys_prompt})
    messages.append({"role": "user", "content": user_prompt})

    # Build request body
    body: dict = {
        "model": model_id,
        "messages": messages,
    }

    # Add optional parameters if set
    max_tokens = config.get("max_tokens")
    if max_tokens:
        body["max_tokens"] = max_tokens

    temp = config.get("temperature")
    if temp is not None:
        body["temperature"] = temp
    else:
        # Use model-specific default
        model_info = get_model_by_id(config, model_id)
        if model_info and model_info.get("temp_default") is not None:
            body["temperature"] = model_info["temp_default"]

    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    response = requests.post(url, headers=headers, json=body, timeout=120)
    return response


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def display_response(response: requests.Response, model_id: str, config: dict):
    """Parse and display an API response."""
    model_info = get_model_by_id(config, model_id)
    model_label = model_info["name"] if model_info else model_id

    if response.status_code == 200:
        data = response.json()
        # Extract the response text
        choices = data.get("choices", [])
        if choices:
            content = choices[0].get("message", {}).get("content", "(empty response)")
        else:
            content = "(no choices returned)"

        # Display
        print()
        print(f"  {c_model(model_label)} {c_dim('says:')}")
        print(separator())
        print_wrapped(content, c_response)
        print(separator())

        # Token usage
        usage = data.get("usage", {})
        if usage:
            prompt_tok = usage.get("prompt_tokens", 0)
            comp_tok = usage.get("completion_tokens", 0)
            print(c_dim(f"  tokens: {prompt_tok} in → {comp_tok} out"))

    elif response.status_code == 401:
        print(c_error("\n  Authentication failed (401)."))
        print(c_warn("  Your API key may have expired (keys rotate every 7 days)."))
        return "auth_failed"

    elif response.status_code == 429:
        print(c_error("\n  Rate limited (429)."))
        print(c_warn("  USAi allows 3 calls/second/key. Slow down or contact support@usai.gov."))

    else:
        print(c_error(f"\n  Request failed: HTTP {response.status_code}"))
        try:
            err_body = response.json()
            print(c_dim(f"  {json.dumps(err_body, indent=2)}"))
        except Exception:
            print(c_dim(f"  {response.text[:500]}"))

    return None


def display_model_menu(config: dict) -> str | None:
    """Show model selection menu, return chosen model ID."""
    models = config.get("models", [])
    if not models:
        print(c_error("  No models available."))
        return None

    print()
    print(f"  {c_header('Available Models')}")
    print(separator())

    # Group by provider
    providers: dict[str, list] = {}
    for m in models:
        providers.setdefault(m["provider"], []).append(m)

    idx = 1
    index_map = {}
    for provider, provider_models in providers.items():
        print(c_dim(f"  {provider}"))
        for m in provider_models:
            index_map[idx] = m["id"]
            print(f"    {c_menu(str(idx))}. {m['name']} {c_dim('(' + m['id'] + ')')}")
            idx += 1

    print(separator())

    while True:
        choice = input(f"  {c_header('Select model')} [1-{len(index_map)}]: ").strip()
        if choice.lower() in ("quit", "exit", "q"):
            print(f"\n  {c_dim('Goodbye.')}")
            sys.exit(0)
        if choice.isdigit() and int(choice) in index_map:
            return index_map[int(choice)]
        print(c_error(f"  Enter a number 1-{len(index_map)}"))


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def print_banner():
    """Print the startup banner."""
    banner = """
    ██╗   ██╗███████╗ █████╗ ██╗
    ██║   ██║██╔════╝██╔══██╗██║
    ██║   ██║███████╗███████║██║
    ██║   ██║╚════██║██╔══██║██║
    ╚██████╔╝███████║██║  ██║██║
     ╚═════╝ ╚══════╝╚═╝  ╚═╝╚═╝"""
    print(c_header(banner))
    print(f"    {Fore.WHITE}{Style.BRIGHT}API Tester{Style.RESET_ALL}  {c_dim(f'v{VERSION}')}")
    print()
    print_wrapped(random.choice(STARTUP_QUIPS), c_dim)
    print()


def main():
    colorama_init(autoreset=False)

    print_banner()

    # Load config
    config = load_config()

    # Resolve base URL
    base_url = load_base_url(config)
    if not base_url:
        base_url = prompt_for_base_url()

    # Resolve API key
    api_key = load_api_key()
    if not api_key or api_key == "your-api-key-here":
        api_key = prompt_for_api_key()

    # Fetch live model list from the API
    print(c_dim("  Fetching available models from API..."))
    api_models = fetch_models(base_url, api_key)

    # Handle auth failure during model fetch
    while not api_models:
        print(c_warn("\n  Could not retrieve models."))
        print(c_dim("  This usually means bad URL, bad key, or no network."))
        retry = input(f"\n  {c_header('r')}etry / new {c_header('k')}ey / new {c_header('u')}rl / {c_header('q')}uit: ").strip().lower()
        if retry == "q":
            sys.exit(0)
        elif retry == "k":
            api_key = prompt_for_api_key("Enter a new API key")
        elif retry == "u":
            base_url = prompt_for_base_url()
        # retry (or any other input) just tries again
        print(c_dim("\n  Retrying..."))
        api_models = fetch_models(base_url, api_key)

    # Build working model list (API is source of truth, config provides overrides)
    live_models = build_model_list(api_models, config)
    config["models"] = live_models

    print(c_dim(f"  Found {len(live_models)} models."))

    # Always let the user pick their model
    print()
    current_model = display_model_menu(config)
    if not current_model:
        sys.exit(1)
    model_info = get_model_by_id(config, current_model)

    print()
    print(f"  {c_dim('Endpoint:')} {base_url}")
    print(f"  {c_dim('Model:')}    {c_model(model_info['name'])}")
    print(f"  {c_dim('Type')} {c_header('quit')} {c_dim('or')} {c_header('exit')} {c_dim('to leave.')}")
    print(separator())

    last_prompt = None

    while True:
        print()
        print(c_dim("  ┌ stateless call — no conversation history"))
        try:
            user_input = input(f"  {c_prompt('│ You')}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n\n  {c_dim('Goodbye.')}")
            break

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit", "q"):
            print(f"\n  {c_dim('Goodbye.')}")
            break

        last_prompt = user_input

        # Make the API call
        print(c_dim("\n  Thinking..."))
        start = time.time()
        try:
            resp = call_chat_completion(base_url, api_key, current_model, user_input, config)
        except requests.exceptions.ConnectionError:
            print(c_error("\n  Connection failed. Check your base URL and network."))
            print(c_dim(f"  Tried: {base_url}"))
            continue
        except requests.exceptions.Timeout:
            print(c_error("\n  Request timed out (120s). The model may be overloaded."))
            continue
        except Exception as e:
            print(c_error(f"\n  Unexpected error: {e}"))
            continue

        elapsed = time.time() - start

        result = display_response(resp, current_model, config)

        # Handle auth failure — re-prompt for key
        if result == "auth_failed":
            api_key = prompt_for_api_key("API key expired or invalid")
            print(c_dim("  Try your prompt again."))
            continue

        print(c_dim(f"  response time: {elapsed:.1f}s"))

        # Post-response menu
        while True:
            print()
            print(f"  {c_menu('1')}. {c_dim('New prompt (default — just hit Enter)')}")
            print(f"  {c_menu('2')}. {c_dim('Compare — same prompt, different model')}")
            print(f"  {c_menu('3')}. {c_dim('Switch model')}")
            print(f"  {c_menu('4')}. {c_dim('Exit')}")
            print()

            try:
                choice = input(f"  {c_header('Choice')} [1]: ").strip()
            except (EOFError, KeyboardInterrupt):
                print(f"\n\n  {c_dim('Goodbye.')}")
                sys.exit(0)

            if choice.lower() in ("quit", "exit", "q"):
                print(f"\n  {c_dim('Goodbye.')}")
                sys.exit(0)

            if choice in ("", "1"):
                break  # Back to prompt

            elif choice == "2":
                # Compare: pick a model, re-send last prompt
                if not last_prompt:
                    print(c_warn("  No previous prompt to compare."))
                    break

                print(f"\n  {c_dim(random.choice(COMPARE_QUIPS))}")
                compare_model = display_model_menu(config)
                if not compare_model:
                    continue

                print(c_dim(f"\n  Re-sending to {compare_model}..."))
                start = time.time()
                try:
                    resp2 = call_chat_completion(
                        base_url, api_key, compare_model, last_prompt, config
                    )
                except Exception as e:
                    print(c_error(f"\n  Error: {e}"))
                    continue

                elapsed2 = time.time() - start
                result2 = display_response(resp2, compare_model, config)

                if result2 == "auth_failed":
                    api_key = prompt_for_api_key("API key expired or invalid")
                    continue

                print(c_dim(f"  response time: {elapsed2:.1f}s"))
                # Stay in menu to allow further comparisons

            elif choice == "3":
                # Switch model
                print(f"\n  {c_dim(random.choice(SWITCH_QUIPS))}")
                new_model = display_model_menu(config)
                if new_model:
                    current_model = new_model
                    model_info = get_model_by_id(config, current_model)
                    print(f"\n  {c_dim('Now using:')} {c_model(model_info['name'])}")
                break  # Back to prompt

            elif choice == "4":
                print(f"\n  {c_dim('Goodbye.')}")
                sys.exit(0)

            else:
                print(c_dim("  Just 1, 2, 3, or 4."))


if __name__ == "__main__":
    main()
