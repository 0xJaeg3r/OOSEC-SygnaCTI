#!/usr/bin/env python3
"""
Syngnacti CLI
Multi-agent Cyber Threat Intelligence platform
"""

import sys
import os
import logging
import argparse
from dotenv import load_dotenv
from agent import CtiAgentSystem

load_dotenv()

logging.getLogger("agno").setLevel(logging.CRITICAL)
logging.getLogger("httpx").setLevel(logging.CRITICAL)

VERSION = "v1.0.0"

def print_banner(
        model_id: str,
        memory_enabled: bool = False,
        storage_enabled: bool = False,
        mcp_enabled: bool = False,
        mcp_count: int = 0
):
    """Prints welcome banner with configuration"""
    cwd = os.getcwd()
    home = os.path.expanduser("~")
    display_dir = cwd.replace(home, "~") if cwd.startswith(home) else cwd
    memory_status = "enabled" if memory_enabled else "disabled"
    storage_status = "enabled" if storage_enabled else "disabled"
    mcp_status = f"enabled ({mcp_count} servers)" if mcp_enabled and mcp_count > 0 else "disabled"

    banner = f"""
┌─────────────────────────────────────────────────────────────────┐
│ Syngnacti CTI Agent ({VERSION})                                 │
└─────────────────────────────────────────────────────────────────┘

model:     {model_id:<20}  /model to change
memory:    {memory_status:<20}  /memory to toggle
storage:   {storage_status:<20}  /storage to toggle
mcp:       {mcp_status:<20}  /mcp to toggle, /add-mcp to add servers
directory: {display_dir}

Describe a threat intelligence task or try one of these commands:

/model     - choose what model to use
/memory    - toggle conversation memory (default: off)
/storage   - toggle agent storage/state (default: off)
/mcp       - toggle MCP server support (default: off)
/add-mcp   - add a Model Context Protocol server
/status    - show current session configuration
/clear     - clear the screen
/help      - show detailed help information
/quit      - exit the CLI

Example tasks:
  - Search Telegram channels for recent ransomware activity and produce a report
  - Investigate dark web credential dumps targeting the financial sector
  - Find recent CVEs being actively exploited and cross-reference with threat intel
  - What APT groups are currently targeting healthcare in West Africa?

"""
    print(banner)

def print_help():
    """Prints detailed help information"""
    help_text = """
╔═══════════════════════════════════════════════════════════════╗
║  Syngnacti CTI - Help & Commands                              ║
╚═══════════════════════════════════════════════════════════════╝

COMMANDS:
  /model     - Switch between AI models
  /memory    - Toggle conversation memory on/off (default: off)
  /storage   - Toggle agent storage/state persistence (default: off)
  /mcp       - Toggle MCP server support on/off (default: off)
  /add-mcp   - Add a Model Context Protocol (MCP) server
  /status    - Display current model and configuration
  /clear     - Clear the terminal screen
  /help      - Show this help message
  /quit      - Exit the CLI

AVAILABLE MODELS:
  OpenAI:
    - gpt-5.2              - GPT-5.2 (Flagship) [Default]
    - gpt-5                - GPT-5 (Base Model)
    - o3                   - O3 Reasoning Model (Full)
    - o3-mini              - O3 Reasoning Model (Mini)

  Anthropic:
    - claude-opus-4-6      - Claude Opus 4.6 (Most Capable)
    - claude-sonnet-4-5    - Claude Sonnet 4.5 (Fast)

  Google:
    - gemini-2.5-pro       - Gemini 2.5 Pro (1M Context)
    - gemini-2.5-flash     - Gemini 2.5 Flash (Fast)

  Other (via LiteLLM):
    - Any model from 100+ providers
    - See: https://docs.litellm.ai/docs/providers

STORAGE & MEMORY:
  Memory: Stores conversation history for context across sessions
    - Use /memory to toggle
    - Stored in: ~/.sygnacti/agent_memory.db

  Storage: Persists agent state and internal data
    - Use /storage to toggle
    - Stored in: ~/.sygnacti/agent_storage.db
    - Enables add_history_to_context for better context awareness
    - Independent from memory, can be used together

MCP SERVERS:
  Model Context Protocol (MCP) allows agents to connect to external
  data sources and tools. Add servers with /add-mcp command.

  Popular Examples:
    - Filesystem: npx -y @modelcontextprotocol/server-filesystem /path
    - Git: npx -y @modelcontextprotocol/server-git
    - Memory: npx -y @modelcontextprotocol/server-memory
    - Fetch: npx -y @modelcontextprotocol/server-fetch
    - Context7 (Docs): npx -y @upstash/context7-mcp@latest

  Full list: https://github.com/modelcontextprotocol/servers

AGENT TEAM:
  CTI Manager (Team Leader)
    Coordinates all agents and delivers the final intelligence report.

  Telegram Recon Specialist
    Searches Telegram channels for IOCs, threat actor chatter,
    breach announcements, and emerging campaigns.

  Web Search Agent
    Corroborates and enriches findings from vendor advisories,
    CVE databases (NVD, MITRE), and government alerts (CISA, FBI).

  Dark Web Investigation Agent
    Queries .onion search engines, browses dark web sites,
    extracts intel from forums, marketplaces, and leak sites.

  CTI Reporter
    Synthesizes all findings into a structured intelligence report
    with MITRE ATT&CK mappings and actionable recommendations.

TOOLS:
  Collection:
    - Telegram channel search (list, search, multi-channel)
    - Dark web search (parallel .onion engine querying)
    - Dark web browsing (browse any .onion site)
    - Web search (Tavily API)
  System:
    - File operations (read, write, search)
    - Shell commands (echo, pipe, ls, cat, find)

PREREQUISITES:
  - Tor must be running for dark web tools (sudo systemctl start tor)
  - Telegram must be authenticated (python telegram_search_tool.py auth +phone)
  - Playwright browsers installed (playwright install chromium)

EXAMPLE QUERIES:
  - Search my Telegram channels for mentions of LockBit and produce a report
  - Investigate dark web activity related to credential dumps for African banks
  - What is the latest ransomware landscape? Full investigation across all sources.
  - Find recent CVEs being actively exploited in the wild
  - Search for threat intelligence related to APT groups targeting healthcare

API KEYS:
  Set in .env file or as environment variables:
    - OPENAI_API_KEY      - For GPT models (platform.openai.com)
    - ANTHROPIC_API_KEY   - For Claude models (console.anthropic.com)
    - GOOGLE_API_KEY      - For Gemini models (aistudio.google.com)
    - TELEGRAM_API_ID     - Telegram API ID (my.telegram.org)
    - TELEGRAM_API_HASH   - Telegram API hash
    - TAVILY_API_KEY      - For web search (tavily.com)
"""
    print(help_text)


def clear_screen():
    """Clear the terminal screen"""
    os.system('cls' if os.name == 'nt' else 'clear')


def add_mcp_server():
    """Interactively add a new MCP server"""
    print("\n╔═══════════════════════════════════════════════════════════════╗")
    print("║  Add Model Context Protocol (MCP) Server                     ║")
    print("╚═══════════════════════════════════════════════════════════════╝")
    print("\nPopular MCP Servers (Command-based):")
    print("  1. Filesystem - Access local files and directories")
    print("  2. Git - Read and search Git repositories")
    print("  3. Memory - Knowledge graph-based persistent memory")
    print("  4. Fetch - Web content fetching and conversion")
    print("  5. Context7 - Library documentation access")
    print("\nRemote MCP Servers (URL-based):")
    print("  6. Custom URL - Connect to remote HTTP/SSE MCP server")
    print("\nCustom:")
    print("  0. Custom command or URL")

    choice = input("\nSelect (0-6) or press Enter to cancel: ").strip()

    if not choice:
        print("Cancelled")
        return None

    server_config = {}

    if choice == "1":
        path = input("\nEnter directory path (default: current directory): ").strip()
        if not path:
            path = "."
        server_config = {
            'name': f'Filesystem ({path})',
            'command': f'npx -y @modelcontextprotocol/server-filesystem {path}'
        }
    elif choice == "2":
        server_config = {
            'name': 'Git Repository',
            'command': 'npx -y @modelcontextprotocol/server-git'
        }
    elif choice == "3":
        server_config = {
            'name': 'Memory Graph',
            'command': 'npx -y @modelcontextprotocol/server-memory'
        }
    elif choice == "4":
        server_config = {
            'name': 'Web Fetch',
            'command': 'npx -y @modelcontextprotocol/server-fetch'
        }
    elif choice == "5":
        server_config = {
            'name': 'Context7 Docs',
            'command': 'npx -y @upstash/context7-mcp@latest'
        }
    elif choice == "6":
        name = input("\nServer name: ").strip()
        url = input("Server URL (e.g., 'https://example.com/mcp'): ").strip()

        if not name or not url:
            print("Name and URL are required")
            return None

        server_config = {
            'name': name,
            'url': url,
            'transport': 'streamable-http'
        }
    elif choice == "0":
        name = input("\nServer name: ").strip()
        server_type = input("Type (command/url): ").strip().lower()

        if not name or server_type not in ['command', 'url']:
            print("Valid name and type (command/url) are required")
            return None

        if server_type == 'command':
            command = input("npx command (e.g., 'npx -y @example/mcp-server'): ").strip()
            if not command:
                print("Command is required")
                return None
            server_config = {
                'name': name,
                'command': command
            }
        else:
            url = input("Server URL: ").strip()
            if not url:
                print("URL is required")
                return None
            server_config = {
                'name': name,
                'url': url,
                'transport': 'streamable-http'
            }
    else:
        print("Invalid choice")
        return None

    print(f"\nMCP server configured: {server_config['name']}")
    if 'command' in server_config:
        print(f"  Command: {server_config['command']}")
    else:
        print(f"  URL: {server_config['url']}")
        print(f"  Transport: {server_config['transport']}")
    return server_config


def get_model_input():
    """Get model ID from user"""
    print("\nAvailable Models:")
    print("\n  OpenAI:")
    print("    1. gpt-5.2              (Flagship) [Default]")
    print("    2. gpt-5                (Base Model)")
    print("    3. o3                   (Reasoning)")
    print("    4. o3-mini              (Reasoning, Mini)")
    print("\n  Anthropic:")
    print("    5. claude-opus-4-6      (Most Capable)")
    print("    6. claude-sonnet-4-5    (Fast)")
    print("\n  Google:")
    print("    7. gemini-2.5-pro       (1M Context)")
    print("    8. gemini-2.5-flash     (Fast)")
    print("\n    0. Enter custom model ID")

    choice = input("\nSelect (0-8) or press Enter for default: ").strip()

    models = {
        "1": "gpt-5.2",
        "2": "gpt-5",
        "3": "o3",
        "4": "o3-mini",
        "5": "claude-opus-4-6",
        "6": "claude-sonnet-4-5",
        "7": "gemini-2.5-pro",
        "8": "gemini-2.5-flash",
    }

    if choice == "0":
        custom_model = input("Enter custom model ID: ").strip()
        return custom_model if custom_model else "gpt-5.2"
    else:
        return models.get(choice, "gpt-5.2")


def print_status(model_id: str, memory_enabled: bool = False, storage_enabled: bool = False, mcp_enabled: bool = False, mcp_servers: list = []):
    """Print current session status"""
    cwd = os.getcwd()
    home = os.path.expanduser("~")
    display_dir = cwd.replace(home, "~") if cwd.startswith(home) else cwd

    memory_status = "Enabled (storing conversation history)" if memory_enabled else "Disabled"
    if memory_enabled:
        memory_status += "\n           Database: ~/.sygnacti/ocelot_agents.db"

    storage_status = "Enabled (persistent agent state + history context)" if storage_enabled else "Disabled"
    if storage_enabled:
        storage_status += "\n           Database: ~/.sygnacti/agent_storage.db"

    mcp_servers = mcp_servers or []

    mcp_info = "Disabled"
    if mcp_enabled:
        if mcp_servers:
            mcp_info = f"Enabled ({len(mcp_servers)} servers configured)"
        else:
            mcp_info = "Enabled (no servers added yet - use /add-mcp)"

    status_text = f"""
╔═══════════════════════════════════════════════════════════════╗
║  Session Configuration                                        ║
╚═══════════════════════════════════════════════════════════════╝

Version:   {VERSION}
Model:     {model_id}
Memory:    {memory_status}
Storage:   {storage_status}
MCP:       {mcp_info}
Directory: {display_dir}

Active Agents:
  1. CTI Manager (Team Leader)
  2. Telegram Recon Specialist
  3. Web Search Agent
  4. Dark Web Investigation Agent
  5. CTI Reporter

Available Tools:
  Collection:
    - Telegram channel search (list, search, multi-channel)
    - Dark web search (parallel .onion engine querying)
    - Dark web browsing (browse any .onion site)
    - Web search (Tavily)
  System:
    - File operations (read, write, search)
    - Shell commands (echo, pipe, ls, cat, find)"""

    if mcp_servers:
        status_text += "\n\nConfigured MCP Servers:"
        for i, server in enumerate(mcp_servers, 1):
            name = server.get('name', f'Server {i}')
            status_text += f"\n  {i}. {name}"
            if 'command' in server:
                status_text += f"\n     Command: {server['command']}"
            elif 'url' in server:
                status_text += f"\n     URL: {server['url']}"
                status_text += f"\n     Transport: {server.get('transport', 'streamable-http')}"

    print(status_text)


def main():
    """Main CLI loop"""
    parser = argparse.ArgumentParser(description='Syngnacti CTI Agent CLI')
    parser.add_argument('--model', type=str, help='LLM model ID to use')
    parser.add_argument('--memory', action='store_true', help='Enable conversation memory')
    parser.add_argument('--storage', action='store_true', help='Enable agent storage/state persistence')
    parser.add_argument('--mcp', action='store_true', help='Enable MCP server support')
    args = parser.parse_args()

    model_id = args.model or os.getenv('LLM_MODEL_ID', '').strip() or "gpt-5.2"
    memory_enabled = args.memory
    storage_enabled = args.storage
    mcp_enabled = args.mcp
    mcp_servers = []

    # Check for API key based on selected model
    api_key_map = {
        "gpt": ("OPENAI_API_KEY", "https://platform.openai.com/api-keys"),
        "o3": ("OPENAI_API_KEY", "https://platform.openai.com/api-keys"),
        "claude": ("ANTHROPIC_API_KEY", "https://console.anthropic.com"),
        "gemini": ("GOOGLE_API_KEY", "https://aistudio.google.com"),
    }

    required_key = None
    key_url = None
    for prefix, (key_name, url) in api_key_map.items():
        if prefix in model_id.lower():
            required_key = key_name
            key_url = url
            break

    if required_key and not os.getenv(required_key):
        print(f"\nERROR: {required_key} not found!")
        print(f"\nPlease set your API key:")
        print("  1. Create a .env file in the project root")
        print(f"  2. Add your {required_key} to the .env file")
        print(f"  3. Get an API key from: {key_url}\n")
        sys.exit(1)

    try:
        agent_system = CtiAgentSystem(
            model_name=model_id,
            use_memory=memory_enabled,
            use_storage=storage_enabled,
            use_mcp=mcp_enabled,
            mcp_servers=mcp_servers
        )
        current_model = model_id
    except Exception as e:
        print(f"\nFailed to initialize Syngnacti: {e}")
        print("\nMake sure you have the correct API key configured for your model.")
        sys.exit(1)

    clear_screen()
    print_banner(current_model, memory_enabled, storage_enabled, mcp_enabled, len(mcp_servers))

    while True:
        try:
            user_input = input("\nsyngnacti > ").strip()

            if not user_input:
                continue

            if user_input.startswith('/'):
                command = user_input.lower()

                if command in ['/quit', '/exit', '/q']:
                    print("\nGoodbye!")
                    break

                elif command in ['/help', '/h']:
                    print_help()
                    continue

                elif command in ['/clear', '/cls']:
                    clear_screen()
                    print_banner(current_model, memory_enabled, storage_enabled, mcp_enabled, len(mcp_servers))
                    continue

                elif command in ['/status']:
                    print_status(current_model, memory_enabled, storage_enabled, mcp_enabled, mcp_servers)
                    continue

                elif command in ['/memory']:
                    memory_enabled = not memory_enabled
                    new_status = "enabled" if memory_enabled else "disabled"
                    print(f"\nMemory {new_status}")
                    print(f"Reinitializing agents with memory {new_status}...")
                    try:
                        agent_system = CtiAgentSystem(
                            model_name=current_model,
                            use_memory=memory_enabled,
                            use_storage=storage_enabled,
                            use_mcp=mcp_enabled,
                            mcp_servers=mcp_servers
                        )
                        print(f"Agents reinitialized with memory {new_status}")
                        clear_screen()
                        print_banner(current_model, memory_enabled, storage_enabled, mcp_enabled, len(mcp_servers))
                    except Exception as e:
                        print(f"Failed to toggle memory: {e}")
                        memory_enabled = not memory_enabled
                    continue

                elif command in ['/storage']:
                    storage_enabled = not storage_enabled
                    new_status = "enabled" if storage_enabled else "disabled"
                    print(f"\nStorage {new_status}")
                    print(f"Reinitializing agents with storage {new_status}...")
                    try:
                        agent_system = CtiAgentSystem(
                            model_name=current_model,
                            use_memory=memory_enabled,
                            use_storage=storage_enabled,
                            use_mcp=mcp_enabled,
                            mcp_servers=mcp_servers
                        )
                        print(f"Agents reinitialized with storage {new_status}")
                        clear_screen()
                        print_banner(current_model, memory_enabled, storage_enabled, mcp_enabled, len(mcp_servers))
                    except Exception as e:
                        print(f"Failed to toggle storage: {e}")
                        storage_enabled = not storage_enabled
                    continue

                elif command in ['/mcp']:
                    mcp_enabled = not mcp_enabled
                    new_status = "enabled" if mcp_enabled else "disabled"
                    print(f"\nMCP {new_status}")

                    if mcp_enabled and not mcp_servers:
                        print("No MCP servers configured yet. Use /add-mcp to add servers.")

                    print(f"Reinitializing agents with MCP {new_status}...")
                    try:
                        agent_system = CtiAgentSystem(
                            model_name=current_model,
                            use_memory=memory_enabled,
                            use_storage=storage_enabled,
                            use_mcp=mcp_enabled,
                            mcp_servers=mcp_servers
                        )
                        print(f"Agents reinitialized with MCP {new_status}")
                        clear_screen()
                        print_banner(current_model, memory_enabled, storage_enabled, mcp_enabled, len(mcp_servers))
                    except Exception as e:
                        print(f"Failed to toggle MCP: {e}")
                        mcp_enabled = not mcp_enabled
                    continue

                elif command in ['/add-mcp']:
                    new_server = add_mcp_server()
                    if new_server:
                        mcp_servers.append(new_server)
                        print(f"\nAdded to MCP servers list")

                        if mcp_enabled:
                            print(f"Reinitializing agents with new MCP server...")
                            try:
                                agent_system = CtiAgentSystem(
                                    model_name=current_model,
                                    use_memory=memory_enabled,
                                    use_storage=storage_enabled,
                                    use_mcp=mcp_enabled,
                                    mcp_servers=mcp_servers
                                )
                                print(f"Agents reinitialized with {len(mcp_servers)} MCP servers")
                            except Exception as e:
                                print(f"Failed to reinitialize with new MCP server: {e}")
                                mcp_servers.pop()
                        else:
                            print("Tip: Use /mcp to enable MCP server support")
                    continue

                elif command in ['/model']:
                    new_model = get_model_input()
                    if new_model != current_model:
                        print(f"\nSwitching to {new_model}...")
                        try:
                            agent_system = CtiAgentSystem(
                                model_name=new_model,
                                use_memory=memory_enabled,
                                use_storage=storage_enabled,
                                use_mcp=mcp_enabled,
                                mcp_servers=mcp_servers
                            )
                            current_model = new_model
                            print(f"Now using {new_model}")
                            clear_screen()
                            print_banner(current_model, memory_enabled, storage_enabled, mcp_enabled, len(mcp_servers))
                        except Exception as e:
                            print(f"Failed to switch model: {e}")
                    continue

                else:
                    print(f"Unknown command: {user_input}")
                    print("Type /help for available commands")
                    continue

            # Send query to the CTI agent team
            print()
            agent_system.run_assessment(user_input, stream=True)

        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break

        except Exception as e:
            print(f"\nError: {e}")
            print("Please try again or type /help for assistance.")


if __name__ == "__main__":
    main()
