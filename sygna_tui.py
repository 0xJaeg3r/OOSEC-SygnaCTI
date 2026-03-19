#!/usr/bin/env python3
"""
Syngnacti CTI TUI — Terminal User Interface for the Cyber Threat Intelligence Agent.
Built with Textual, architecture.
"""

import argparse
import logging
import os
import re
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from textual.timer import Timer

from dotenv import load_dotenv
from rich.align import Align
from rich.console import Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.style import Style
from rich.text import Text
from textual import events, on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static, TextArea, Tree
from textual.widgets.tree import TreeNode

from agent import CtiAgentSystem
from agno.run.agent import RunEvent as AgentRunEvent
from agno.run.team import TeamRunOutput, TeamRunEvent

load_dotenv()

logger = logging.getLogger(__name__)

VERSION = "v1.0.0"
PRIMARY = "#06b6d4"
ACCENT = "#f59e0b"

# Fixed agent team definitions for the sidebar tree.
AGENT_TEAM: list[dict[str, Any]] = [
    {"id": "manager", "name": "CTI Manager", "role": "Team Leader — coordinates all agents", "parent": None},
    {"id": "telegram", "name": "Telegram Recon", "role": "Telegram OSINT collection", "parent": "manager"},
    {"id": "web_search", "name": "Web Search", "role": "Open-source web intelligence", "parent": "manager"},
    {"id": "dw_refiner", "name": "Query Refiner", "role": "Optimizes dark web queries", "parent": "manager"},
    {"id": "dw_searcher", "name": "Dark Web Searcher", "role": "Executes .onion search", "parent": "manager"},
    {"id": "dw_filter", "name": "Results Filter", "role": "Triages dark web results", "parent": "manager"},
    {"id": "dw_browser", "name": "Dark Web Browser", "role": "Extracts .onion site intel", "parent": "manager"},
    {"id": "reporter", "name": "CTI Reporter", "role": "Synthesizes final report", "parent": "manager"},
]

# Patterns for extracting IOCs from responses.
_CVE_RE = re.compile(r"CVE-\d{4}-\d{4,}")
_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_HASH_RE = re.compile(r"\b[a-fA-F0-9]{32,64}\b")
_DOMAIN_RE = re.compile(
    r"\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+"
    r"(?:com|net|org|io|onion|ru|cn|xyz|top|info|biz)\b"
)


# ─────────────────────────────────────────────────────────
# Reusable widgets
# ─────────────────────────────────────────────────────────


class ChatTextArea(TextArea):  # type: ignore[misc]
    """Chat input with Enter-to-send and Shift+Enter for newlines."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._app_ref: "SygnaTUIApp | None" = None

    def set_app_reference(self, app: "SygnaTUIApp") -> None:
        self._app_ref = app

    def on_mount(self) -> None:
        self._update_height()

    def _on_key(self, event: events.Key) -> None:
        if event.key == "shift+enter":
            self.insert("\n")
            event.prevent_default()
            return

        if event.key == "enter" and self._app_ref:
            text_content = str(self.text).strip()  # type: ignore[has-type]
            if text_content:
                self.text = ""
                self._app_ref._send_user_message(text_content)
                event.prevent_default()
                return

        super()._on_key(event)

    @on(TextArea.Changed)  # type: ignore[misc]
    def _update_height(self, _event: TextArea.Changed | None = None) -> None:
        if not self.parent:
            return
        line_count = self.document.line_count
        target = min(max(1, line_count), 8)
        new_h = target + 2
        current = self.parent.styles.height
        if current is None or current.value != new_h:
            self.parent.styles.height = new_h
            self.scroll_cursor_visible()


# ─────────────────────────────────────────────────────────
# Splash screen
# ─────────────────────────────────────────────────────────


class SplashScreen(Static):  # type: ignore[misc]
    ALLOW_SELECT = False
    BANNER = (
        " ███████╗██╗   ██╗ ██████╗ ███╗   ██╗ █████╗\n"
        " ██╔════╝╚██╗ ██╔╝██╔════╝ ████╗  ██║██╔══██╗\n"
        " ███████╗ ╚████╔╝ ██║  ███╗██╔██╗ ██║███████║\n"
        " ╚════██║  ╚██╔╝  ██║   ██║██║╚██╗██║██╔══██║\n"
        " ███████║   ██║   ╚██████╔╝██║ ╚████║██║  ██║\n"
        " ╚══════╝   ╚═╝    ╚═════╝ ╚═╝  ╚═══╝╚═╝  ╚═╝"
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._step = 0
        self._timer: Timer | None = None
        self._panel_static: Static | None = None

    def compose(self) -> ComposeResult:
        self._step = 0
        panel = self._build_panel(self._shine_text(0))
        ps = Static(panel, id="splash_content")
        self._panel_static = ps
        yield ps

    def on_mount(self) -> None:
        self._timer = self.set_interval(0.05, self._tick)

    def on_unmount(self) -> None:
        if self._timer:
            self._timer.stop()
            self._timer = None

    def _tick(self) -> None:
        if not self._panel_static:
            return
        self._step += 1
        self._panel_static.update(self._build_panel(self._shine_text(self._step)))

    def _build_panel(self, start_line: Text) -> Panel:
        content = Group(
            Align.center(Text(self.BANNER.strip("\n"), style=PRIMARY, justify="center")),
            Align.center(Text(" ")),
            Align.center(self._welcome()),
            Align.center(Text(VERSION, style=Style(color="white", dim=True))),
            Align.center(Text("Multi-Agent Cyber Threat Intelligence", style=Style(color="white", dim=True))),
            Align.center(Text(" ")),
            Align.center(start_line.copy()),
        )
        return Panel.fit(content, border_style=PRIMARY, padding=(1, 6))

    def _welcome(self) -> Text:
        t = Text("Welcome to ", style=Style(color="white", bold=True))
        t.append("SyngnaCTI", style=Style(color=PRIMARY, bold=True))
        t.append("!", style=Style(color="white", bold=True))
        return t

    def _shine_text(self, phase: int) -> Text:
        full = "Initializing CTI Agents"
        pos = phase % (len(full) + 8)
        t = Text()
        for i, ch in enumerate(full):
            d = abs(i - pos)
            if d <= 1:
                s = Style(color="bright_white", bold=True)
            elif d <= 3:
                s = Style(color="white", bold=True)
            elif d <= 5:
                s = Style(color="#a3a3a3")
            else:
                s = Style(color="#525252")
            t.append(ch, style=s)
        return t


# ─────────────────────────────────────────────────────────
# Modal screens
# ─────────────────────────────────────────────────────────


class HelpScreen(ModalScreen):  # type: ignore[misc]
    def compose(self) -> ComposeResult:
        yield Grid(
            Label("Syngnacti Help", id="help_title"),
            Label(
                "F1           Help\n"
                "Ctrl+Q / C   Quit\n"
                "ESC          Stop / Cancel\n"
                "Enter        Send message\n"
                "Shift+Enter  New line in input\n"
                "Tab          Switch panels\n"
                "↑ / ↓        Navigate agent tree\n"
                "\nChat commands:\n"
                "  /model <id>   Switch LLM model\n"
                "  /status       Show configuration\n"
                "  /clear        Clear chat history\n"
                "  /help         This screen",
                id="help_content",
            ),
            id="dialog",
        )

    def on_key(self, _event: events.Key) -> None:
        self.app.pop_screen()


class QuitScreen(ModalScreen):  # type: ignore[misc]
    def compose(self) -> ComposeResult:
        yield Grid(
            Label("Quit Syngnacti?", id="quit_title"),
            Grid(
                Button("Yes", variant="error", id="quit"),
                Button("No", variant="default", id="cancel"),
                id="quit_buttons",
            ),
            id="quit_dialog",
        )

    def on_mount(self) -> None:
        self.query_one("#cancel", Button).focus()

    def on_key(self, event: events.Key) -> None:
        if event.key in ("left", "right", "up", "down"):
            focused = self.focused
            target = "#cancel" if focused and focused.id == "quit" else "#quit"
            self.query_one(target, Button).focus()
            event.prevent_default()
        elif event.key == "enter":
            if self.focused and isinstance(self.focused, Button):
                self.focused.press()
            event.prevent_default()
        elif event.key == "escape":
            self.app.pop_screen()
            event.prevent_default()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "quit":
            self.app.action_custom_quit()
        else:
            self.app.pop_screen()


class ModelSelectScreen(ModalScreen):  # type: ignore[misc]
    """Modal for quick model selection."""

    MODELS: ClassVar[list[tuple[str, str]]] = [
        ("gpt-5.2", "GPT-5.2 (Flagship)"),
        ("gpt-5", "GPT-5"),
        ("o3", "O3 Reasoning"),
        ("claude-opus-4-6", "Claude Opus 4.6"),
        ("claude-sonnet-4-5", "Claude Sonnet 4.5"),
        ("gemini-2.5-pro", "Gemini 2.5 Pro"),
        ("gemini-2.5-flash", "Gemini 2.5 Flash"),
    ]

    def compose(self) -> ComposeResult:
        lines = "\n".join(f"  {i + 1}. {label:<28} [{mid}]" for i, (mid, label) in enumerate(self.MODELS))
        yield Grid(
            Label("Select Model", id="model_title"),
            Label(lines + "\n\n  0. Cancel", id="model_list"),
            id="model_dialog",
        )

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape" or event.character == "0":
            self.app.pop_screen()
            event.prevent_default()
            return
        if event.character and event.character.isdigit():
            idx = int(event.character) - 1
            if 0 <= idx < len(self.MODELS):
                model_id = self.MODELS[idx][0]
                self.app.pop_screen()
                self.app._switch_model(model_id)  # type: ignore[attr-defined]
            event.prevent_default()


# ─────────────────────────────────────────────────────────
# Findings panel (replaces Strix VulnerabilitiesPanel)
# ─────────────────────────────────────────────────────────


class FindingsPanel(VerticalScroll):  # type: ignore[misc]
    """Scrollable panel showing IOCs and threat intel findings extracted from responses."""

    SEVERITY_COLORS: ClassVar[dict[str, str]] = {
        "critical": "#dc2626",
        "high": "#ea580c",
        "medium": "#d97706",
        "low": "#22c55e",
        "info": "#3b82f6",
    }

    TYPE_SEVERITY: ClassVar[dict[str, str]] = {
        "cve": "high",
        "ip": "medium",
        "hash": "medium",
        "domain": "info",
    }

    TYPE_ICONS: ClassVar[dict[str, str]] = {
        "cve": "🛡",
        "ip": "🌐",
        "hash": "🔑",
        "domain": "🔗",
    }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._findings: list[dict[str, str]] = []

    def add_finding(self, title: str, finding_type: str = "info") -> None:
        severity = self.TYPE_SEVERITY.get(finding_type, "info")
        entry = {"title": title, "severity": severity, "type": finding_type}
        # Deduplicate by title
        if any(f["title"] == title for f in self._findings):
            return
        self._findings.append(entry)
        self._render()

    def clear_findings(self) -> None:
        self._findings.clear()
        for child in list(self.children):
            child.remove()

    def has_findings(self) -> bool:
        return len(self._findings) > 0

    def _render(self) -> None:
        for child in list(self.children):
            child.remove()

        if not self._findings:
            return

        # Header
        header = Text()
        header.append(f"Extracted IOCs ({len(self._findings)})", style=f"bold {PRIMARY}")
        self.mount(Static(header, classes="finding-item"))

        for f in self._findings:
            color = self.SEVERITY_COLORS.get(f["severity"], "#3b82f6")
            icon = self.TYPE_ICONS.get(f["type"], "●")
            label = Text()
            label.append(f"{icon} ", style=Style(color=color))
            label.append(f["title"], style=Style(color="#d4d4d4"))
            self.mount(Static(label, classes="finding-item"))


# ─────────────────────────────────────────────────────────
# Main application
# ─────────────────────────────────────────────────────────


class SygnaTUIApp(App):  # type: ignore[misc]
    CSS_PATH = "assets/sygna_tui.tcss"
    ALLOW_SELECT = True
    SIDEBAR_MIN_WIDTH = 120

    show_splash: reactive[bool] = reactive(default=True)
    selected_agent_id: reactive[str | None] = reactive(default=None)

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("f1", "toggle_help", "Help", priority=True),
        Binding("ctrl+q", "request_quit", "Quit", priority=True),
        Binding("ctrl+c", "request_quit", "Quit", priority=True),
        Binding("escape", "cancel_or_back", "Cancel", priority=True),
    ]

    def __init__(
        self,
        model_name: str = "gpt-5.2",
        use_memory: bool = False,
        use_storage: bool = False,
        use_mcp: bool = False,
    ) -> None:
        super().__init__()
        self.model_name = model_name
        self.use_memory = use_memory
        self.use_storage = use_storage
        self.use_mcp = use_mcp

        self.agent_system: CtiAgentSystem | None = None
        self.agent_nodes: dict[str, TreeNode] = {}

        # Map Agno agent names → sidebar tree IDs
        self._agent_name_to_id: dict[str, str] = {
            "CTI Team": "manager",
            "Telegram Recon Specialist": "telegram",
            "Web Search Agent": "web_search",
            "Dark Web Query Refiner": "dw_refiner",
            "Dark Web Searcher": "dw_searcher",
            "Dark Web Results Filter": "dw_filter",
            "Dark Web Browser": "dw_browser",
            "CTI Reporter": "reporter",
        }

        # Map Agno URL-safe member IDs → display names (used by delegate_task_to_member)
        self._member_id_to_name: dict[str, str] = {
            "telegram-recon-specialist": "Telegram Recon",
            "web-search-agent": "Web Search",
            "dark-web-query-refiner": "Query Refiner",
            "dark-web-searcher": "Dark Web Searcher",
            "dark-web-results-filter": "Results Filter",
            "dark-web-browser": "Dark Web Browser",
            "cti-reporter": "CTI Reporter",
        }

        # Chat state
        self._messages: list[dict[str, str]] = []
        self._streaming_content: str = ""
        self._activity_log: list[tuple[str, str]] = []  # (line, style) pairs
        self._status_detail: str = ""  # current activity for status bar
        self._is_busy = False  # True during assessment or model switch
        self._cancel_requested = False

        # Sweep animation state
        self._spinner_frame: int = 0
        self._animation_timer: Any = None
        self._sweep_num_squares: int = 6
        self._sweep_colors: list[str] = [
            "#000000", "#031a25", "#052e42", "#0d4a5e",
            "#0891b2", "#06b6d4", "#22d3ee", "#67e8f9",
        ]

    # ── Compose & lifecycle ──────────────────────────────

    def compose(self) -> ComposeResult:
        if self.show_splash:
            yield SplashScreen(id="splash_screen")

    def on_mount(self) -> None:
        self.title = "syngnacti"
        self.set_timer(3.5, self._hide_splash)

    def _hide_splash(self) -> None:
        self.show_splash = False

    def watch_show_splash(self, show_splash: bool) -> None:
        if not show_splash and self.is_mounted:
            try:
                self.query_one("#splash_screen").remove()
            except ValueError:
                pass
            self._build_main_ui()

    # ── Build the main interface ─────────────────────────

    def _build_main_ui(self) -> None:
        main = Vertical(id="main_container")
        self.mount(main)

        content = Horizontal(id="content_container")
        main.mount(content)

        # -- Chat area --
        chat_area = Vertical(id="chat_area_container")
        chat_display = Static("", id="chat_display")
        chat_history = VerticalScroll(chat_display, id="chat_history")
        chat_history.can_focus = True

        status_text = Static("", id="status_text")
        status_text.ALLOW_SELECT = False
        keymap = Static("", id="keymap_indicator")
        keymap.ALLOW_SELECT = False
        status_bar = Horizontal(status_text, keymap, id="status_bar", classes="hidden")

        prompt = Static("> ", id="chat_prompt")
        prompt.ALLOW_SELECT = False
        chat_input = ChatTextArea("", id="chat_input", show_line_numbers=False)
        chat_input.set_app_reference(self)
        input_container = Horizontal(prompt, chat_input, id="chat_input_container")

        # -- Sidebar --
        agents_tree = Tree("Agents", id="agents_tree")
        agents_tree.root.expand()
        agents_tree.show_root = False
        agents_tree.show_guide = True
        agents_tree.guide_depth = 3
        agents_tree.guide_style = "dashed"

        findings = FindingsPanel(id="findings_panel", classes="hidden")

        stats_display = Static("", id="stats_display")
        stats_scroll = VerticalScroll(stats_display, id="stats_scroll")

        sidebar = Vertical(agents_tree, findings, stats_scroll, id="sidebar")

        content.mount(chat_area)
        content.mount(sidebar)

        chat_area.mount(chat_history)
        chat_area.mount(status_bar)
        chat_area.mount(input_container)

        self.call_after_refresh(self._focus_chat_input)
        self.call_after_refresh(self._populate_agent_tree)
        self.call_after_refresh(self._update_stats)
        self.call_after_refresh(self._begin_startup)

    def _begin_startup(self) -> None:
        """Show initializing message and kick off agent init in background."""
        self._add_system_message("Initializing CTI agents...")
        self._init_agent_system()

    # ── Agent system initialization (non-blocking) ───────

    @work(thread=True, exclusive=True, group="init")
    def _init_agent_system(self) -> None:
        self._is_busy = True
        try:
            system = CtiAgentSystem(
                model_name=self.model_name,
                use_memory=self.use_memory,
                use_storage=self.use_storage,
                use_mcp=self.use_mcp,
            )
            self.agent_system = system
            self.call_from_thread(self._on_agent_system_ready)
        except Exception as e:
            logger.exception("Agent init failed")
            self.call_from_thread(self._add_system_message, f"Failed to initialize agents: {e}")
        finally:
            self._is_busy = False

    def _on_agent_system_ready(self) -> None:
        """Called on the main thread once agent system is initialized."""
        self._add_system_message(
            "Syngnacti CTI Agent ready.\n\n"
            "Describe a threat intelligence task to begin. Examples:\n"
            "  • Search Telegram for recent ransomware activity\n"
            "  • Investigate dark web credential dumps targeting banks\n"
            "  • Find actively exploited CVEs with cross-references\n"
            "  • What APT groups are targeting healthcare in West Africa?\n\n"
            f"Model: {self.model_name}  |  F1 for help  |  /model to switch"
        )
        self._set_agent_status("idle")

    # ── Agent tree ───────────────────────────────────────

    def _populate_agent_tree(self) -> None:
        try:
            tree = self.query_one("#agents_tree", Tree)
        except ValueError:
            return

        for defn in AGENT_TEAM:
            aid = defn["id"]
            label = f"○ {defn['name']}"
            parent_id = defn["parent"]

            if parent_id and parent_id in self.agent_nodes:
                parent = self.agent_nodes[parent_id]
                node = parent.add(label, data={"agent_id": aid, "role": defn["role"]})
                parent.allow_expand = True
                parent.expand()
            else:
                node = tree.root.add(label, data={"agent_id": aid, "role": defn["role"]})

            node.allow_expand = aid == "manager"
            if aid == "manager":
                node.expand()
            self.agent_nodes[aid] = node

        # Auto-select the manager
        if "manager" in self.agent_nodes:
            tree.select_node(self.agent_nodes["manager"])
            self.selected_agent_id = "manager"

    @on(Tree.NodeHighlighted)  # type: ignore[misc]
    def _on_tree_highlight(self, event: Tree.NodeHighlighted) -> None:
        if self.show_splash or len(self.screen_stack) > 1:
            return
        node = event.node
        if node.data:
            self.selected_agent_id = node.data.get("agent_id")

    @on(Tree.NodeSelected)  # type: ignore[misc]
    def _on_tree_select(self, event: Tree.NodeSelected) -> None:
        node = event.node
        if node.allow_expand:
            if node.is_expanded:
                node.collapse()
            else:
                node.expand()

    def watch_selected_agent_id(self, agent_id: str | None) -> None:
        if not self.show_splash:
            self._update_stats()

    def _set_agent_status(self, status: str) -> None:
        """Update all agent node labels with a status icon."""
        icons = {
            "idle": "○",
            "running": "⚪",
            "completed": "🟢",
            "failed": "🔴",
        }
        icon = icons.get(status, "○")
        for defn in AGENT_TEAM:
            aid = defn["id"]
            if aid in self.agent_nodes:
                self.agent_nodes[aid].set_label(f"{icon} {defn['name']}")

    def _set_single_agent_status(self, agent_name: str, status: str) -> None:
        """Update a single agent's tree node icon by its Agno agent name."""
        icons = {"idle": "○", "running": "⚪", "completed": "🟢", "failed": "🔴"}
        icon = icons.get(status, "○")
        aid = self._agent_name_to_id.get(agent_name)
        if aid and aid in self.agent_nodes:
            defn = next((a for a in AGENT_TEAM if a["id"] == aid), None)
            if defn:
                self.agent_nodes[aid].set_label(f"{icon} {defn['name']}")

    # ── Chat management ──────────────────────────────────

    def _send_user_message(self, message: str) -> None:
        if self._is_busy:
            self._add_system_message("Busy — please wait for current operation to finish.")
            return

        if message.startswith("/"):
            self._handle_command(message)
            return

        self._add_message("user", message)
        self._run_assessment(message)

    def _handle_command(self, command: str) -> None:
        cmd = command.lower().strip()

        if cmd == "/status":
            mem = "on" if self.use_memory else "off"
            stor = "on" if self.use_storage else "off"
            mcp = "on" if self.use_mcp else "off"
            self._add_system_message(
                f"Model: {self.model_name}\nMemory: {mem}  |  Storage: {stor}  |  MCP: {mcp}"
            )
        elif cmd == "/clear":
            self._messages.clear()
            self._streaming_content = ""
            try:
                panel = self.query_one("#findings_panel", FindingsPanel)
                panel.clear_findings()
                panel.add_class("hidden")
            except (ValueError, Exception):
                pass
            self._refresh_chat()
        elif cmd.startswith("/model"):
            parts = command.split(None, 1)
            if len(parts) > 1:
                self._switch_model(parts[1].strip())
            else:
                self.push_screen(ModelSelectScreen())
        elif cmd == "/help":
            self.action_toggle_help()
        else:
            self._add_system_message(f"Unknown command: {command}\nType /help for available commands.")

    @work(thread=True, exclusive=True, group="init")
    def _switch_model(self, new_model: str) -> None:
        self._is_busy = True
        self.call_from_thread(self._add_system_message, f"Switching to {new_model}...")
        try:
            system = CtiAgentSystem(
                model_name=new_model,
                use_memory=self.use_memory,
                use_storage=self.use_storage,
                use_mcp=self.use_mcp,
            )
            self.model_name = new_model
            self.agent_system = system
            self.call_from_thread(self._add_system_message, f"Now using {new_model}")
            self.call_from_thread(self._update_stats)
        except Exception as e:
            self.call_from_thread(self._add_system_message, f"Failed to switch: {e}")
        finally:
            self._is_busy = False

    def _add_message(self, role: str, content: str) -> None:
        self._messages.append({"role": role, "content": content})
        self._refresh_chat()

    def _add_system_message(self, content: str) -> None:
        self._add_message("system", content)

    def _refresh_chat(self) -> None:
        if self.show_splash or not self.is_mounted:
            return
        try:
            display = self.query_one("#chat_display", Static)
            history = self.query_one("#chat_history", VerticalScroll)
        except (ValueError, Exception):
            return

        try:
            is_at_bottom = history.scroll_y >= history.max_scroll_y
        except (AttributeError, ValueError):
            is_at_bottom = True

        parts: list[Any] = []
        for i, msg in enumerate(self._messages):
            if i > 0:
                parts.append(Text(""))

            role = msg["role"]
            content = msg["content"]

            if role == "user":
                header = Text()
                header.append("▍ ", style=f"bold {PRIMARY}")
                header.append("You", style=f"bold {PRIMARY}")
                parts.append(header)
                parts.append(Text(content))
            elif role == "assistant":
                header = Text()
                header.append("▍ ", style=f"bold {ACCENT}")
                header.append("CTI Team", style=f"bold {ACCENT}")
                parts.append(header)
                parts.append(Markdown(content))
            else:
                line = Text()
                line.append("▍ ", style="dim")
                line.append(content, style="dim")
                parts.append(line)

        # Append activity log while assessment is running
        if self._activity_log and self._is_busy:
            if self._messages:
                parts.append(Text(""))
            header = Text()
            header.append("▍ ", style="bold #8b5cf6")
            header.append("Activity", style="bold #8b5cf6")
            parts.append(header)
            for entry_text, entry_style in self._activity_log:
                parts.append(Text(entry_text, style=entry_style))

        # Append streaming content while assessment is running
        if self._streaming_content:
            if self._messages or self._activity_log:
                parts.append(Text(""))
            header = Text()
            header.append("▍ ", style=f"bold {ACCENT}")
            header.append("CTI Team", style=f"bold {ACCENT}")
            parts.append(header)
            parts.append(Markdown(self._streaming_content))

        display.update(Group(*parts) if parts else Text(""))
        if is_at_bottom:
            self.call_later(history.scroll_end, animate=False)

    # ── Assessment execution (background thread) ─────────

    def _resolve_member_name(self, member_id: str) -> str:
        """Convert a URL-safe member ID to a display name."""
        return self._member_id_to_name.get(member_id, member_id)

    def _log_activity(self, line: str, style: str = "dim") -> None:
        """Append a styled line to the live activity log and refresh."""
        self._activity_log.append((line, style))
        if len(self._activity_log) > 50:
            self._activity_log = self._activity_log[-50:]
        self._status_detail = line
        self.call_from_thread(self._refresh_chat)

    @work(thread=True, exclusive=True, group="assessment")
    def _run_assessment(self, task: str) -> None:
        self._is_busy = True
        self._streaming_content = ""
        self._activity_log = []
        self._status_detail = ""
        self._cancel_requested = False
        self.call_from_thread(self._set_agent_status, "idle")
        self.call_from_thread(self._set_single_agent_status, "CTI Team", "running")
        self.call_from_thread(self._show_status_bar, True)

        if not self.agent_system:
            self.call_from_thread(self._add_system_message, "Agent system not initialized yet — please wait.")
            self._is_busy = False
            self.call_from_thread(self._show_status_bar, False)
            return

        try:
            response = self.agent_system.cti_team.run(
                task,
                stream=True,
                stream_events=True,
                session_id=self.agent_system.session_id,
                yield_run_output=True,
            )

            full_content = ""
            for resp in response:
                if self._cancel_requested:
                    break

                if isinstance(resp, TeamRunOutput):
                    continue

                if not hasattr(resp, "event"):
                    continue

                event = resp.event

                # ── Team-level content (final response deltas) ──
                if event == TeamRunEvent.run_content:
                    if isinstance(resp.content, str):
                        full_content += resp.content
                        self._streaming_content = full_content
                        self.call_from_thread(self._refresh_chat)
                    continue

                # ── Team-level delegation (tool_call = delegate_task_to_member) ──
                if event == TeamRunEvent.tool_call_started:
                    tool = getattr(resp, "tool", None)
                    if tool and tool.tool_name == "delegate_task_to_member":
                        raw_id = (tool.tool_args or {}).get("member_id", "member")
                        member = self._resolve_member_name(raw_id)
                        task_desc = (tool.tool_args or {}).get("task", "")
                        summary = (task_desc[:80] + "...") if len(task_desc) > 80 else task_desc
                        self._log_activity(f"▸ Delegating to {member}: {summary}", PRIMARY)
                    elif tool:
                        self._log_activity(f"▸ Team calling {tool.tool_name}", PRIMARY)
                    continue

                if event == TeamRunEvent.tool_call_completed:
                    tool = getattr(resp, "tool", None)
                    if tool and tool.tool_name == "delegate_task_to_member":
                        raw_id = (tool.tool_args or {}).get("member_id", "member")
                        member = self._resolve_member_name(raw_id)
                        self._log_activity(f"✓ {member} completed", PRIMARY)
                    continue

                # ── Agent-level events (individual member activity) ──
                agent_name = getattr(resp, "agent_name", None)

                if event == AgentRunEvent.run_started:
                    self._log_activity(f"● {agent_name or 'Agent'} started")
                    if agent_name:
                        self.call_from_thread(self._set_single_agent_status, agent_name, "running")
                    continue

                if event == AgentRunEvent.tool_call_started:
                    tool = getattr(resp, "tool", None)
                    tool_name = tool.tool_name if tool else "tool"
                    self._log_activity(f"  ↳ {agent_name or 'Agent'} calling {tool_name}", "#22c55e")
                    continue

                if event == AgentRunEvent.tool_call_completed:
                    tool = getattr(resp, "tool", None)
                    tool_name = tool.tool_name if tool else "tool"
                    self._log_activity(f"  ✓ {agent_name or 'Agent'}: {tool_name} done", "#22c55e")
                    continue

                if event == AgentRunEvent.run_completed:
                    self._log_activity(f"● {agent_name or 'Agent'} finished")
                    if agent_name:
                        self.call_from_thread(self._set_single_agent_status, agent_name, "completed")
                    continue

            # Commit final content as a permanent message.
            self._streaming_content = ""
            if self._cancel_requested:
                if full_content.strip():
                    self.call_from_thread(self._add_message, "assistant", full_content + "\n\n⚠ Interrupted by user")
                else:
                    self.call_from_thread(self._add_system_message, "Assessment cancelled.")
            elif full_content.strip():
                self.call_from_thread(self._add_message, "assistant", full_content)
                self.call_from_thread(self._extract_findings, full_content)
            else:
                self.call_from_thread(self._add_system_message, "No response received.")

        except Exception as e:
            self._streaming_content = ""
            self.call_from_thread(self._add_system_message, f"Error: {e}")

        finally:
            self._is_busy = False
            self._streaming_content = ""
            self._activity_log = []
            self._status_detail = ""
            self._cancel_requested = False
            self.call_from_thread(self._set_agent_status, "completed")
            self.call_from_thread(self._show_status_bar, False)
            self.call_from_thread(self._focus_chat_input)

    # ── IOC / Findings extraction ────────────────────────

    def _extract_findings(self, content: str) -> None:
        """Parse response for IOCs and populate the findings panel."""
        try:
            panel = self.query_one("#findings_panel", FindingsPanel)
        except (ValueError, Exception):
            return

        found_any = False

        for cve in set(_CVE_RE.findall(content)):
            panel.add_finding(cve, "cve")
            found_any = True

        for ip in set(_IPV4_RE.findall(content)):
            # Skip common non-IOC IPs
            if ip.startswith(("127.", "0.", "255.", "10.0.0.", "192.168.")):
                continue
            panel.add_finding(ip, "ip")
            found_any = True

        for domain in set(_DOMAIN_RE.findall(content)):
            # Skip very short or generic domains
            if len(domain) > 8 and domain not in ("example.com", "example.org"):
                panel.add_finding(domain, "domain")
                found_any = True

        for h in set(_HASH_RE.findall(content)):
            # Only show hashes that look real (not substrings of hex text)
            if len(h) in (32, 40, 64):
                panel.add_finding(h[:16] + "..." + h[-8:] if len(h) > 32 else h, "hash")
                found_any = True

        if found_any:
            panel.remove_class("hidden")

    # ── Status bar / sweep animation ─────────────────────

    def _show_status_bar(self, show: bool) -> None:
        try:
            bar = self.query_one("#status_bar", Horizontal)
        except (ValueError, Exception):
            return
        if show:
            bar.remove_class("hidden")
            self._start_animation()
        else:
            bar.add_class("hidden")
            self._stop_animation()

    def _start_animation(self) -> None:
        if self._animation_timer is None:
            self._animation_timer = self.set_interval(0.06, self._sweep_tick)

    def _stop_animation(self) -> None:
        if self._animation_timer:
            self._animation_timer.stop()
            self._animation_timer = None

    def _sweep_tick(self) -> None:
        if not self._is_busy:
            self._stop_animation()
            return
        try:
            status_text = self.query_one("#status_text", Static)
            keymap = self.query_one("#keymap_indicator", Static)
        except (ValueError, Exception):
            return

        text = Text()
        text.append_text(self._sweep_frame())
        detail = self._status_detail if self._status_detail else "Running assessment..."
        text.append(detail, style="dim")
        status_text.update(text)

        km = Text()
        km.append("esc", style="white")
        km.append(" stop  ", style="dim")
        km.append("ctrl-q", style="white")
        km.append(" quit", style="dim")
        keymap.update(km)

    def _sweep_frame(self) -> Text:
        n = self._sweep_num_squares
        nc = len(self._sweep_colors)
        offset = nc - 1
        max_pos = (n - 1) + offset
        total = max_pos + offset
        cycle = total * 2
        self._spinner_frame = (self._spinner_frame + 1) % cycle
        wave = total - abs(total - self._spinner_frame)
        sweep = wave - offset

        t = Text()
        for i in range(n):
            d = abs(i - sweep)
            ci = max(0, nc - 1 - d)
            if ci == 0:
                t.append("·", style=Style(color="#0a2530"))
            else:
                t.append("▪", style=Style(color=self._sweep_colors[ci]))
        t.append(" ")
        return t

    # ── Stats display ────────────────────────────────────

    def _update_stats(self) -> None:
        try:
            stats = self.query_one("#stats_display", Static)
        except (ValueError, Exception):
            return

        text = Text()
        text.append("Configuration\n", style=f"bold {PRIMARY}")
        text.append("Model: ", style="dim")
        text.append(f"{self.model_name}\n")
        text.append("Memory: ", style="dim")
        text.append(f"{'on' if self.use_memory else 'off'}\n")
        text.append("Storage: ", style="dim")
        text.append(f"{'on' if self.use_storage else 'off'}\n")
        text.append("MCP: ", style="dim")
        text.append(f"{'on' if self.use_mcp else 'off'}\n")

        # Show selected agent info
        if self.selected_agent_id:
            defn = next((a for a in AGENT_TEAM if a["id"] == self.selected_agent_id), None)
            if defn:
                text.append(f"\nSelected Agent\n", style=f"bold {PRIMARY}")
                text.append(f"{defn['name']}\n", style="bold")
                text.append(f"{defn['role']}\n", style="dim")

        text.append(f"\n{VERSION}", style="dim white")
        stats.update(text)

    # ── Focus management ─────────────────────────────────

    def _focus_chat_input(self) -> None:
        if self.show_splash or len(self.screen_stack) > 1:
            return
        try:
            inp = self.query_one("#chat_input", ChatTextArea)
            inp.show_vertical_scrollbar = False
            inp.show_horizontal_scrollbar = False
            inp.focus()
        except (ValueError, Exception):
            self.call_after_refresh(self._focus_chat_input)

    # ── Keyboard actions ─────────────────────────────────

    def action_toggle_help(self) -> None:
        if self.show_splash:
            return
        if isinstance(self.screen, HelpScreen):
            self.pop_screen()
            return
        if len(self.screen_stack) > 1:
            return
        self.push_screen(HelpScreen())

    def action_request_quit(self) -> None:
        if self.show_splash:
            self.action_custom_quit()
            return
        if len(self.screen_stack) > 1:
            return
        self.push_screen(QuitScreen())

    def action_cancel_or_back(self) -> None:
        """ESC: cancel running assessment, or pop modal, or do nothing."""
        if len(self.screen_stack) > 1:
            self.pop_screen()
            return
        if self._is_busy and not self._cancel_requested:
            self._cancel_requested = True
            self._add_system_message("Cancelling assessment...")

    def action_custom_quit(self) -> None:
        self._cancel_requested = True
        self.exit()

    # ── Mouse selection → clipboard ──────────────────────

    def on_mouse_up(self, _event: events.MouseUp) -> None:
        self.set_timer(0.05, self._auto_copy)

    def _auto_copy(self) -> None:
        """Try to copy selected text to clipboard. Safely handles missing APIs."""
        selected = ""
        try:
            screen = self.screen
            selections = getattr(screen, "selections", None)
            if selections:
                get_text = getattr(screen, "get_selected_text", None)
                clear = getattr(screen, "clear_selection", None)
                if get_text and clear:
                    selected = get_text()
                    clear()
        except Exception:
            pass

        # Fallback: check ChatTextArea selection
        if not selected or not selected.strip():
            try:
                chat_input = self.query_one("#chat_input", ChatTextArea)
                selected = chat_input.selected_text
            except Exception:
                pass

        if selected and selected.strip():
            if self._clipboard_write(selected):
                self.notify("Copied to clipboard", timeout=2)

    def _clipboard_write(self, text: str) -> bool:
        """Copy text to the system clipboard, falling back to OSC 52."""
        import shutil
        import subprocess

        candidates: list[list[str]] = []
        session = os.environ.get("XDG_SESSION_TYPE", "")

        if session == "wayland" or os.environ.get("WAYLAND_DISPLAY"):
            candidates.append(["wl-copy"])
        if session == "x11" or os.environ.get("DISPLAY"):
            candidates.append(["xclip", "-selection", "clipboard"])
            candidates.append(["xsel", "--clipboard", "--input"])
        # XWayland fallback
        if session == "wayland" and os.environ.get("DISPLAY"):
            candidates.append(["xclip", "-selection", "clipboard"])

        for cmd in candidates:
            if shutil.which(cmd[0]):
                try:
                    subprocess.run(cmd, input=text.encode("utf-8"), check=True, timeout=3)
                    return True
                except (subprocess.SubprocessError, OSError):
                    continue

        # Last resort: Textual's built-in OSC 52
        self.copy_to_clipboard(text)
        return True

    # ── Responsive layout ────────────────────────────────

    def on_resize(self, event: events.Resize) -> None:
        if self.show_splash or not self.is_mounted:
            return
        try:
            sidebar = self.query_one("#sidebar", Vertical)
            chat_area = self.query_one("#chat_area_container", Vertical)
        except (ValueError, Exception):
            return
        if event.size.width < self.SIDEBAR_MIN_WIDTH:
            sidebar.add_class("-hidden")
            chat_area.add_class("-full-width")
        else:
            sidebar.remove_class("-hidden")
            chat_area.remove_class("-full-width")


# ─────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Syngnacti CTI TUI")
    parser.add_argument("--model", type=str, default="gpt-5.2", help="LLM model ID")
    parser.add_argument("--memory", action="store_true", help="Enable conversation memory")
    parser.add_argument("--storage", action="store_true", help="Enable agent storage")
    parser.add_argument("--mcp", action="store_true", help="Enable MCP support")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    app = SygnaTUIApp(
        model_name=args.model,
        use_memory=args.memory,
        use_storage=args.storage,
        use_mcp=args.mcp,
    )
    app.run()


if __name__ == "__main__":
    main()






