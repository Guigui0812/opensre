"""Slash command: ``/agents`` (registered local AI agent fleet view).

Bare ``/agents`` renders the registered-agents dashboard; subcommands
drill into specific surfaces (currently ``conflicts``, ``claim``, ``release``,
with more landing as the monitor-local-agents initiative ships).
"""

from __future__ import annotations

import os

from rich.console import Console
from rich.markup import escape

from app.agents.conflicts import (
    DEFAULT_WINDOW_SECONDS,
    WriteEvent,
    detect_conflicts,
    render_conflicts,
)
from app.agents.coordination import BranchClaims
from app.agents.registry import AgentRegistry
from app.cli.interactive_shell.agents_view import render_agents_table
from app.cli.interactive_shell.command_registry.types import SlashCommand
from app.cli.interactive_shell.session import ReplSession
from app.cli.interactive_shell.theme import ERROR, HIGHLIGHT

_AGENTS_FIRST_ARGS: tuple[tuple[str, str], ...] = (
    ("claim", "claim a branch for an agent"),
    ("conflicts", "show file-write conflicts between local AI agents"),
    ("release", "release a branch claim"),
)


def _opensre_agent_id() -> str:
    return f"opensre:{os.getpid()}"


def _cmd_agents_list(console: Console) -> bool:
    """Render the registered ``AgentRecord`` set as a Rich table.

    Bare ``/agents`` resolves here. Metric cells (``cpu%``,
    ``tokens/min``, ``$/hr``, ``status``, ``uptime``) render as
    placeholders until the wiring from #1490 / #1494 lands; this
    surface only consumes what the registry already holds today.
    """
    registry = AgentRegistry()
    table = render_agents_table(registry.list())
    console.print(table)
    return True


def _cmd_agents_conflicts(console: Console) -> bool:
    # Real write-event collection comes from #1500 (filesystem blast-radius
    # watcher), out of scope for this PR. Until that lands, the event source
    # is empty and `/agents conflicts` reports "no conflicts detected".
    events: list[WriteEvent] = []
    conflicts = detect_conflicts(
        events,
        window_seconds=DEFAULT_WINDOW_SECONDS,
        opensre_agent_id=_opensre_agent_id(),
    )
    console.print(render_conflicts(conflicts))
    return True


def _cmd_agents_claim(console: Console, args: list[str]) -> bool:
    """Handle /agents claim <branch> <agent-name>."""
    if len(args) < 2:
        console.print(f"[{ERROR}]Usage:[/] /agents claim <branch> <agent-name>")
        return False

    branch = args[0].strip()
    agent_name = args[1].strip()

    # Look up the PID from the registry for the given agent name
    registry = AgentRegistry()
    pid = None
    for record in registry.list():
        if record.name == agent_name:
            pid = record.pid
            break

    if pid is None:
        console.print(
            f"[{ERROR}]Agent '{escape(agent_name)}' not found in registry. "
            "Use /agents to see registered agents."
        )
        return False

    claims = BranchClaims()
    existing = claims.get(branch)

    if existing is not None:
        console.print(
            f"[{ERROR}]Cannot claim:[/] {escape(branch)} is already held by "
            f"{escape(existing.agent_name)} (pid {existing.pid}). "
            "Use /agents release first."
        )
        return False

    claim = claims.claim(branch, agent_name, pid)
    if claim is None:
        # This shouldn't happen if our check above is correct, but handle it anyway
        console.print(f"[{ERROR}]Failed to claim {escape(branch)} for {escape(agent_name)}.")
        return False

    console.print(
        f"[{HIGHLIGHT}]Branch {escape(branch)} now held by {escape(agent_name)} (pid {pid})."
    )
    return True


def _cmd_agents_release(console: Console, args: list[str]) -> bool:
    """Handle /agents release <branch>."""
    if len(args) < 1:
        console.print(f"[{ERROR}]Usage:[/] /agents release <branch>")
        return False

    branch = args[0].strip()
    claims = BranchClaims()

    existing = claims.get(branch)
    if existing is None:
        console.print(f"[{ERROR}]{escape(branch)} is not currently held by any agent.")
        return False

    removed = claims.release(branch)
    if removed is None:
        console.print(f"[{ERROR}]Failed to release {escape(branch)}.")
        return False

    console.print(
        f"[{HIGHLIGHT}]Released {escape(branch)} (was held by {escape(removed.agent_name)})."
    )
    return True


def _cmd_agents(session: ReplSession, console: Console, args: list[str]) -> bool:
    if not args:
        return _cmd_agents_list(console)

    sub = args[0].lower().strip()

    if sub == "conflicts":
        return _cmd_agents_conflicts(console)

    if sub == "claim":
        return _cmd_agents_claim(console, args[1:])

    if sub == "release":
        return _cmd_agents_release(console, args[1:])

    console.print(
        f"[{ERROR}]unknown subcommand:[/] {escape(sub)}  "
        "(try [bold]/agents[/bold], [bold]/agents conflicts[/bold], "
        "[bold]/agents claim[/bold], or [bold]/agents release[/bold])"
    )
    session.mark_latest(ok=False, kind="slash")
    return True


COMMANDS: list[SlashCommand] = [
    SlashCommand(
        "/agents",
        "show registered local AI agents (subcommands: claim, conflicts, release)",
        _cmd_agents,
        first_arg_completions=_AGENTS_FIRST_ARGS,
    ),
]

__all__ = ["COMMANDS"]
