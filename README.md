# usai-api-tester

A minimal CLI tool for testing and exploring the [USAi](https://www.usai.gov) federal government AI gateway API.

> "It looks like you're trying to query a federal AI. Would you like help with that?"

## What is USAi?

USAi provides a unified, OpenAI-compatible REST API that gives federal government users access to multiple LLM providers through a single gateway:

- **Google:** Gemini 2.5 Flash, Gemini 2.5 Pro
- **Anthropic:** Claude Haiku 3.5, Claude Sonnet 4.5, Claude Opus 4.5
- **Meta:** Llama 3.2 11B, Llama 4 Maverick
- **Embeddings:** Cohere English v3

## What does this app do?

This is a **stateless** API tester. Each prompt is an independent API call with no conversation history — exactly how the API works when you call it programmatically. It lets you:

- Verify your API key and connectivity
- Send prompts to any available model
- Compare responses across models using the same prompt
- Switch between models on the fly

This is **not** a chat application. It's a testing tool for people who will be building real integrations via code, agent workflows, or Jupyter notebooks.

## Requirements

- Python 3.10 or higher
- A USAi API key (request through your agency's process)
- Your agency-specific USAi API endpoint URL

## Setup

### Windows (Command Prompt or PowerShell)

```cmd
git clone https://github.com/brockwebb/usai-api-tester.git
cd usai-api-tester

python -m venv venv
venv\Scripts\activate

pip install -r requirements.txt
```

### macOS / Linux

```bash
git clone https://github.com/brockwebb/usai-api-tester.git
cd usai-api-tester

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```

### Conda (any OS)

```bash
git clone https://github.com/brockwebb/usai-api-tester.git
cd usai-api-tester

conda create -n usai python=3.12 -y
conda activate usai

pip install -r requirements.txt
```

## Configuration

### API Key & Endpoint

On first run, the app will prompt you for your API key and base URL, then save them to a `.env` file (which is git-ignored — your key stays local).

You can also set them up manually:

```bash
cp .env.example .env
```

Then edit `.env`:

```
USAI_API_KEY=your-actual-key-here
USAI_BASE_URL=https://your-agency-endpoint.usai.gov
```

**API keys rotate every 7 days.** When your key expires, the app will detect the 401 error and prompt you for a new one automatically.

### Models & Defaults

Edit `config.yaml` to change the default model, adjust temperature, set a system prompt, or update the model list if USAi adds/removes models.

## Usage

```bash
python usai_tester.py
```

Type a prompt and hit Enter. After each response, you get three options:

1. **New prompt** (default) — enter another prompt
2. **Compare** — send the same prompt to a different model and see both responses
3. **Switch model** — change your active model

Type `quit`, `exit`, or `q` to leave.

## Troubleshooting

| Problem | Fix |
|---|---|
| `Connection failed` | Check your base URL in `.env`. Make sure you're on your agency network / VPN. |
| `401 Unauthorized` | API key expired (7-day rotation). The app will prompt for a new one. |
| `429 Too Many Requests` | Rate limit is 3 calls/sec/key. Slow down or contact support@usai.gov. |
| `ModuleNotFoundError` | Make sure your virtual environment is activated and you ran `pip install -r requirements.txt`. |

## Project Structure

```
usai-api-tester/
├── .env.example      # Template for API key and base URL
├── .gitignore         # Keeps .env and other secrets out of git
├── config.yaml        # Models, defaults, non-secret configuration
├── LICENSE            # MIT
├── README.md          # You are here
├── requirements.txt   # Python dependencies
└── usai_tester.py     # The app (single file)
```

## License

MIT

## Support

For USAi API issues: [support@usai.gov](mailto:support@usai.gov)

For issues with this tester: [open an issue](https://github.com/brockwebb/usai-api-tester/issues)
