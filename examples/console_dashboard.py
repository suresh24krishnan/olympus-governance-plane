from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.columns import Columns
from rich.align import Align
from rich.text import Text
from rich.theme import Theme

# Tier-0 Branding & Theme
custom_theme = Theme({
    "info": "cyan",
    "warning": "yellow",
    "danger": "bold red",
    "success": "bold green",
    "verdict": "bold reverse"
})
console = Console(theme=custom_theme)

def display_banner():
    """Renders the high-level project identity."""
    console.print(
        Panel.fit(
            "[bold cyan]PROJECT OLYMPUS[/bold cyan] | [dim]Strategic Verdict Plane[/dim]\n"
            "[dim]Governance Trilogy: Aegis (Shield) | Vulcan (Forge) | Sentinel (Watchman)[/dim]",
            border_style="cyan",
            title="[bold white]V1.0.0-PROD[/bold white]"
        )
    )

def display_command_envelope(case_id: str, prompt: str, policy_flags: list[str]):
    """Visualizes the pre-inference policy gate and case metadata."""
    tbl = Table(show_header=False, box=None, padding=(0, 2))
    tbl.add_row("[bold cyan]CASE_ID[/bold cyan]", f"[white]{case_id}[/white]")

    flag_str = ", ".join(policy_flags) if policy_flags else "None (Clean)"
    flag_style = "bold red" if policy_flags else "green"
    tbl.add_row("[bold cyan]POLICY_GATE[/bold cyan]", f"[{flag_style}]{flag_str}[/{flag_style}]")

    safe_prompt = prompt.replace('"', '\\"')
    tbl.add_row("[bold cyan]INPUT_PROMPT[/bold cyan]", f"[italic white]\"{safe_prompt}\"[/italic white]")

    console.print(Panel(tbl, title="[bold blue]1.0 Command Ingestion[/bold blue]", border_style="blue"))

def display_jury_panels(primary, secondary):
    """Side-by-side view of the dual-model arbitration debate."""
    def make_panel(v, title, border):
        body = f"[bold]Verdict:[/bold] {v.verdict}\n"
        body += f"[bold]Risk Assessment:[/bold] {v.risk}\n\n"
        body += "[bold underline]Reasoning Evidence:[/bold underline]\n"
        for r in v.reasoning:
            body += f" • {r}\n"
        return Panel(body, title=title, border_style=border, expand=True)

    console.print(
        Columns(
            [
                make_panel(primary, f"🏛️ PRIMARY ({primary.model})", "magenta"),
                make_panel(secondary, f"⚖️ JURY ({secondary.model})", "purple"),
            ],
            equal=True,
            expand=True
        )
    )

def display_final_verdict(verdict: str, confidence: float, divergence: float):
    """The deterministic output of the Verdict Plane."""
    text_style = {"ALLOW": "success", "DENY": "danger", "ESCALATE": "warning"}.get(verdict, "white")
    border = {"ALLOW": "green", "DENY": "bold red", "ESCALATE": "yellow"}.get(verdict, "white")

    verdict_text = Text(f"\n{verdict}\n", style=text_style)
    metrics_text = Text(f"Confidence: {confidence:.2f} | Divergence: {divergence:.2f}", style="dim")

    console.print(
        Align.center(
            Panel.fit(
                Text.assemble(verdict_text, metrics_text),
                title="[bold white]2.0 CONSENSUS VERDICT[/bold white]",
                border_style=border,
                padding=(1, 5)
            )
        )
    )

def display_sentinel_action(message: str, ticket_key: str = None):
    """The execution response from the Watchman."""
    output = Text(f"LOG: {message}", style="white")
    if ticket_key:
        output.append(f"\nACTION: Updated System-of-Record -> {ticket_key}", style="bold yellow")

    console.print(Panel(output, title="[bold white]3.0 SENTINEL ENFORCEMENT[/bold white]", border_style="white"))
