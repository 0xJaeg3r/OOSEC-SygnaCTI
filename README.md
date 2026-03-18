# Syngnacti

**Multi-agent Cyber Threat Intelligence platform** built on the [Agno](https://github.com/agno-agi/agno) framework. A coordinated team of AI agents collects, correlates, and reports on cyber threats from Telegram channels, the open web, and the dark web.

## How it works

A CTI Manager agent receives your query and delegates tasks to specialized agents. Each agent has purpose-built tools and a tailored prompt. The manager synthesizes their findings and produces a structured intelligence report.

```
                          +-----------------------+
                          |     CTI Manager       |
                          |  (Team Leader/Router) |
                          +----------+------------+
                                     |
                    delegates to team members
                                     |
    +----------------+---------------+---------------+----------------+
    |                |               |               |                |
+---v---+      +----v----+    +-----v------+   +----v----+    +------v-----+
|Telegram|     |   Web   |    | Dark Web   |   |   CTI   |    | Dark Web   |
| Recon  |     | Search  |    |  Pipeline  |   | Reporter|    |  Browser   |
+--------+     +---------+    +-----+------+   +---------+    +------------+
|list_   |     |Tavily   |          |          |Synthesize|   |browse_onion|
|channels|     |web      |    +-----+-----+   |findings  |   |_site       |
|search_ |     |search   |    |     |     |   |into      |   +------------+
|channel |     |API      |    |     |     |   |reports   |
+--------+     +---------+    v     v     v   +---------+
    |               |       Query Filter Searcher
Telegram API   Public Web  Refiner       |search_dark_web
(Telethon)     (Tavily)                  |
                                      Tor Network
                                   (Playwright + SOCKS5)
```

### Agent roles

| Agent | Role | Tools |
|-------|------|-------|
| **CTI Manager** | Receives queries, delegates to specialists, resolves conflicting intel, delivers final report | `delegate_task_to_member` (Agno built-in) |
| **Telegram Recon Specialist** | Searches Telegram channels for IOCs, threat actor chatter, breach announcements | `list_channels`, `search_channel`, `search_multiple_channels` |
| **Web Search Agent** | Corroborates and enriches findings from vendor advisories, CVE databases, government alerts | Tavily web search |
| **Dark Web Query Refiner** | Optimizes search queries for dark web search engines | _(no tools — LLM-only)_ |
| **Dark Web Searcher** | Executes searches across .onion search engines | `search_dark_web` |
| **Dark Web Results Filter** | Triages and selects the most relevant dark web results | _(no tools — LLM-only)_ |
| **Dark Web Browser** | Browses .onion sites and extracts threat intelligence | `browse_onion_site` |
| **CTI Reporter** | Produces structured intelligence reports with executive summaries, MITRE ATT&CK mappings, and recommendations | File tools |

### Report structure

The CTI Reporter outputs reports in this format:

1. **Executive Summary** -- key findings in 2-3 sentences
2. **Threat Overview** -- who, what, why
3. **Technical Analysis** -- IOCs, TTPs mapped to MITRE ATT&CK, kill chain progression
4. **Impact Assessment** -- affected sectors, regions, systems
5. **Recommendations** -- prioritized defensive actions
6. **Sources** -- attribution for each finding (Telegram channel, web source, .onion URL)

Each finding includes a confidence level (High / Medium / Low) based on source reliability and corroboration.

## Prerequisites

- Python 3.12+
- At least one LLM API key (OpenAI, Anthropic, or Google)
- Telegram API credentials (for Telegram collection)
- Tor service (for dark web collection)
- Playwright + Chromium (for dark web browsing)
- Tavily API key (for web search corroboration)
- `wl-clipboard` (Wayland) or `xclip` (X11) for TUI clipboard support (optional)

## Setup

### 1. Clone and create a virtual environment

```bash
git clone https://github.com/your-username/syngnacti.git
cd syngnacti
python3 -m venv venv
source venv/bin/activate   # Linux/macOS
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Install Playwright browsers

```bash
playwright install chromium
```

### 4. Install and start Tor

The dark web search tool routes all traffic through Tor's SOCKS5 proxy on `127.0.0.1:9050`.

```bash
# Install
sudo apt install tor          # Debian/Ubuntu
sudo pacman -S tor            # Arch
brew install tor              # macOS

# Start
sudo systemctl start tor

# Enable on boot (optional)
sudo systemctl enable tor

# Verify
ss -tlnp | grep 9050
```

You should see Tor listening on port 9050. If not, the dark web tools will fail with "unreachable after 3 attempts".

### 5. Configure credentials

Create a `.env` file in the project root:

```env
# LLM API key (at least one required)
OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY=sk-ant-...
# GOOGLE_API_KEY=...

# Telegram API (required for Telegram collection)
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=abcdef1234567890abcdef1234567890

# Web search (required for web corroboration)
TAVILY_API_KEY=tvly-...
```

#### Getting API keys

| Service | Where to get it |
|---------|----------------|
| OpenAI | https://platform.openai.com/api-keys |
| Anthropic | https://console.anthropic.com/settings/keys |
| Google AI | https://aistudio.google.com/apikey |
| Telegram | https://my.telegram.org > API development tools |
| Tavily | https://tavily.com |

### 6. Authenticate with Telegram (one-time)

```bash
python telegram_search_tool.py auth +1234567890
```

Enter the verification code sent to your phone. If 2FA is enabled, you'll be prompted for your password. The session is saved to `sessions/` and persists across runs.

## Usage

### TUI (recommended)

```bash
python sygna_tui.py
```

The terminal UI provides a full interactive experience:

- **Real-time activity log** — see which agents are active, what tools they're calling, and delegation status as it happens
- **Live streaming** — the final report streams into the chat with full **markdown rendering** (headers, tables, bullet lists, code blocks)
- **Agent sidebar** — tree view of all agents with live status indicators (idle/running/completed)
- **IOC extraction** — CVEs, IPs, domains, and hashes are automatically extracted from reports and displayed in a findings panel
- **Model selection** — switch models at runtime via `/model` or the modal picker
- **Clipboard support** — highlight text to copy (requires `wl-clipboard` on Wayland or `xclip` on X11)

```bash
# Start with a specific model
python sygna_tui.py --model claude-opus-4-6

# Start with memory and storage enabled
python sygna_tui.py --memory --storage

# Start with MCP support
python sygna_tui.py --mcp
```

#### Keybindings

| Key | Action |
|-----|--------|
| `Enter` | Send message |
| `Shift+Enter` | New line in input |
| `F1` | Help screen |
| `Esc` | Cancel running assessment |
| `Ctrl+Q` / `Ctrl+C` | Quit |
| `Tab` | Switch panels |
| `↑` / `↓` | Navigate agent tree |

#### Chat commands

| Command | Description |
|---------|-------------|
| `/model [id]` | Switch LLM model (opens picker if no ID given) |
| `/status` | Show current configuration |
| `/clear` | Clear chat history and findings |
| `/help` | Show help screen |

### CLI

```bash
python sygna_cli.py
```

The interactive CLI provides:

- Model switching at runtime (`/model`) -- supports OpenAI, Anthropic, Google, and LiteLLM
- Conversation memory toggle (`/memory`) -- persists context across sessions
- Agent storage toggle (`/storage`) -- persists agent state and history
- MCP server support (`/add-mcp`, `/mcp`) -- connect external tool servers
- Session status (`/status`) -- view active agents, tools, and configuration

```bash
# Start with a specific model
python sygna_cli.py --model claude-opus-4-6

# Start with memory and storage enabled
python sygna_cli.py --memory --storage

# Start with MCP support
python sygna_cli.py --mcp
```

Type `/help` in the CLI for full command reference.

### Quick start (script mode)

```bash
python agent.py
```

This runs the default example task. Edit `agent.py:main()` to change the query.

### Programmatic usage

```python
from agent import CtiAgentSystem

system = CtiAgentSystem(model_name="gpt-5.2")
system.run_assessment(
    "Investigate dark web activity related to credential dumps for African banks"
)
```

### Example prompts

```
Search my Telegram channels for any mentions of LockBit and produce a threat intelligence report

What is the latest ransomware landscape? Perform a full investigation across all sources.

Investigate dark web activity related to credential dumps targeting the financial sector

Find recent CVEs being actively exploited and cross-reference with Telegram threat intel channels

Search for threat intelligence related to APT groups targeting healthcare in West Africa
```

### Using different models

```python
# OpenAI (default)
system = CtiAgentSystem(model_name="gpt-5.2")

# Anthropic
system = CtiAgentSystem(model_name="claude-sonnet-4-5-20250929")

# Google
system = CtiAgentSystem(model_name="gemini-2.5-pro")

# Any model via LiteLLM (fallback)
system = CtiAgentSystem(model_name="together_ai/meta-llama/Llama-3-70b")
```

### Optional features

```python
# Enable conversation memory (persists across sessions)
system = CtiAgentSystem(model_name="gpt-5.2", use_memory=True)

# Enable session storage (conversation history within a session)
system = CtiAgentSystem(model_name="gpt-5.2", use_storage=True)

# Connect MCP tool servers
system = CtiAgentSystem(
    model_name="gpt-5.2",
    use_mcp=True,
    mcp_servers=[
        {"command": "npx -y @some/mcp-server"},
        {"url": "http://localhost:8080/mcp", "transport": "streamable-http"},
    ],
)
```

### Accessing individual agents

```python
system = CtiAgentSystem(model_name="gpt-5.2")

# Get a specific agent for direct use (bypasses the team)
telegram_agent = system.get_agent("telegram_search")
web_agent = system.get_agent("web_search")
dark_web_agent = system.get_agent("dark_web_investigation_agent")
reporter = system.get_agent("reports")
```

## Dark web search tool

The dark web module (`dark_web_search_tool.py`) can be used standalone or as part of the agent system.

### How it works

1. Launches a headless Chromium browser routed through Tor's SOCKS5 proxy
2. Queries multiple .onion search engines in parallel (up to 6 concurrent)
3. Uses a two-phase page loading strategy: fast `domcontentloaded` + `networkidle` wait for JS-rendered content
4. If a direct search URL fails (e.g. CSRF token required), falls back to loading the homepage, finding the search form, and submitting it
5. Classifies each page (search results, login, captcha, error, directory, content)
6. Extracts results using 4 fallback parsing strategies
7. Resolves redirect URLs to actual .onion destinations
8. Deduplicates results across engines by normalized URL

### Standalone usage

```python
from dark_web_search_tool import search_dark_web, browse_onion_site

# Search across all configured engines
results = search_dark_web("ransomware", max_results=10)
print(results)

# Browse a specific .onion site
page = browse_onion_site("http://example.onion/some-page")
print(page)
```

### Adding search engines

Edit `SEARCH_URLS` in `dark_web_search_tool.py`:

```python
SEARCH_URLS = {
    "ahmia": "http://juhanurmihxlp77nkq76byazcldy2hlmovfu2epvl5ankdibsot4csyd.onion",
    "your_engine": "http://your-engine-address.onion/",
}
```

If you know the engine's search URL pattern, add it to `SEARCH_PATTERNS`:

```python
SEARCH_PATTERNS = {
    "ahmia": "/search/?q={q}",
    "your_engine": "/find?query={q}",
}
```

Engines without a verified pattern fall back to `/search/?q=` first, then the form-based submission fallback.

### Page classification

The tool automatically detects and handles:

| Page type | Behavior |
|-----------|----------|
| **Search results** | Parses results via multi-strategy extraction |
| **Login page** | Reports form fields and whether registration is available |
| **Captcha** | Reports the site is captcha-protected |
| **Error page** | Reports the error message |
| **Directory** | Extracts .onion links with descriptions |
| **Content** | Returns page text (up to 5000 chars) |

## Telegram search tool

The Telegram module (`telegram_search_tool.py`) works both as a CLI tool and as agent functions.

### CLI usage

```bash
# List all channels you're a member of
python telegram_search_tool.py channels

# Search a single channel
python telegram_search_tool.py search 1234567 "ransomware" --days-back 30

# Search across multiple channels
python telegram_search_tool.py long-search "APT28" 1234567 2345678 --depth 3months

# JSON output (pipe to jq, etc.)
python telegram_search_tool.py search 1234567 "CVE-2024" --json
```

### CLI reference

| Command | Description |
|---------|-------------|
| `auth <phone>` | One-time Telegram authentication |
| `channels` | List joined channels with IDs and member counts |
| `search <channel_id> <keyword>` | Search a single channel |
| `long-search <keyword> <id1> [id2] ...` | Search across multiple channels |

| Flag | Applies to | Description |
|------|-----------|-------------|
| `--limit N` | `search`, `long-search` | Max messages to scan per channel (default: 1000) |
| `--days-back N` | `search` | Only search the last N days |
| `--depth` | `long-search` | `1week`, `1month`, `3months`, `6months`, `1year`, `all` |
| `--json` | `channels`, `search`, `long-search` | Output as JSON |

## Project structure

```
syngnacti/
├── sygna_tui.py              # Terminal UI — Textual-based TUI with streaming, activity log, markdown reports
├── assets/
│   └── sygna_tui.tcss        # TUI stylesheet
├── sygna_cli.py              # Interactive CLI — model switching, memory, storage, MCP servers
├── agent.py                  # CtiAgentSystem class — agent creation, team orchestration, model selection
├── prompt.py                 # Role prompts for all 8 agents (manager + 7 specialists)
├── tools.py                  # Tool registry — aggregates CLI, Telegram, and dark web tools
├── telegram_search_tool.py   # Telegram OSINT — Telethon-based channel search (CLI + agent tool)
├── dark_web_search_tool.py   # Dark web OSINT — Playwright + Tor parallel search engine querying
├── requirements.txt          # Python dependencies
├── .env                      # API credentials (not committed — add to .gitignore)
└── sessions/                 # Telegram session files (auto-created, not committed)
```

## Troubleshooting

### TUI: clipboard "Copied" notification but nothing in clipboard

Install a system clipboard utility:

```bash
# Wayland
sudo apt install wl-clipboard

# X11
sudo apt install xclip
```

### TUI: no activity log during assessment

Make sure you're running with `stream_events=True` (this is the default in the TUI). If you see "Running assessment..." with no activity lines, the agent system may not be emitting intermediate events — try a different model.

### Dark web search: "unreachable after 3 attempts"

Tor is not running or not installed.

```bash
# Check if Tor is running
ss -tlnp | grep 9050

# Start Tor
sudo systemctl start tor
```

### Dark web search returns no results but engine is reachable

The search engine may require a CSRF token or use JS-only search. The form-based fallback handles most cases, but some engines have non-standard search interfaces. Check the debug output (`debug_mode=True` in agent.py) to see what page type was detected.

### Telegram: "Not authenticated. Run 'auth' first."

```bash
python telegram_search_tool.py auth +1234567890
```

### Telegram: "TELEGRAM_API_ID and TELEGRAM_API_HASH must be set"

Add your Telegram credentials to `.env`:

```env
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=abcdef1234567890abcdef1234567890
```

Get them from https://my.telegram.org > API development tools.

### Playwright: "Browser not found"

```bash
playwright install chromium
```

### Agent answers directly instead of delegating

The CTI Manager's prompt explicitly instructs it to always delegate. If you see it answering without tool calls, this is typically the LLM ignoring instructions. Try:
- Using a more capable model (GPT-5.2, Claude Opus)
- Making the query more specific so the manager can clearly route it

### "Error running asyncio.run(): This event loop is already running"

This is handled automatically by `_run_async()` in both the Telegram and dark web tools. If you see this error, it means the workaround failed. Ensure you're using the sync wrapper functions (`search_dark_web`, `browse_onion_site`, `list_channels`, etc.) and not calling the `_async` functions directly.

## Configuration

### Dark web tool settings

Edit constants at the top of `dark_web_search_tool.py`:

```python
MAX_RETRIES = 2           # Retry attempts per page load
RETRY_DELAY = 5           # Seconds between retries
DEFAULT_TIMEOUT = 90_000  # Page load timeout (ms)
MAX_CONCURRENT = 6        # Max parallel browser tabs
```

### Tor proxy

Default: `socks5://127.0.0.1:9050`. To use a different Tor instance, edit `_launch_tor_browser()` in `dark_web_search_tool.py`.

## Disclaimer

This tool is designed for **authorized security research, threat intelligence, and defensive cybersecurity operations**. It is intended for use by security professionals, SOC analysts, threat intelligence teams, and researchers operating within legal and ethical boundaries.

- Only use this tool on systems and platforms you are authorized to access
- Comply with all applicable laws and regulations in your jurisdiction
- Dark web browsing carries inherent risks — use appropriate operational security
- The authors are not responsible for misuse of this tool

## License

MIT
