"""Azure authentication helpers."""

from __future__ import annotations

import json
import subprocess

from azure.identity import AzureCliCredential
from azure.mgmt.subscription import SubscriptionClient
from rich.console import Console
from rich.prompt import Prompt

console = Console()


def get_credential() -> AzureCliCredential:
    """Get Azure credential via CLI authentication."""
    return AzureCliCredential()


def get_current_subscription_id() -> str | None:
    """Return the subscription ID currently selected in ``az account show``."""
    try:
        result = subprocess.run(
            ["az", "account", "show", "--query", "id", "-o", "tsv"],
            capture_output=True, text=True, check=True,
        )
        sub_id = result.stdout.strip()
        return sub_id if sub_id else None
    except Exception:
        return None


def list_subscriptions(credential: AzureCliCredential) -> list[dict]:
    """List all accessible Azure subscriptions."""
    client = SubscriptionClient(credential)
    subs = []
    for sub in client.subscriptions.list():
        subs.append({
            "id": sub.subscription_id,
            "name": sub.display_name,
            "state": str(sub.state),
        })
    return subs


def resolve_subscriptions(
    credential: AzureCliCredential,
    subscription_csv: str | None = None,
) -> list[str]:
    """Resolve subscription IDs from a comma-separated string, or use the current CLI default.

    Falls back to interactive prompt only when the current subscription cannot
    be determined.  Returns a list of subscription IDs.
    """
    subs = list_subscriptions(credential)
    if not subs:
        console.print(
            "[red]No subscriptions found. Ensure you are logged in with 'az login'.[/red]"
        )
        raise SystemExit(1)

    sub_map = {s["id"]: s for s in subs}

    if subscription_csv:
        requested = [s.strip() for s in subscription_csv.split(",") if s.strip()]
        resolved: list[str] = []
        for req_id in requested:
            if req_id not in sub_map:
                console.print(
                    f"[red]Subscription '{req_id}' not found or not accessible.[/red]"
                )
                raise SystemExit(1)
            resolved.append(req_id)
        names = ", ".join(sub_map[s]["name"] for s in resolved)
        console.print(f"Using {len(resolved)} subscription(s): [bold]{names}[/bold]")
        return resolved

    # Try the current AZ CLI subscription before falling back to interactive
    current_sub = get_current_subscription_id()
    if current_sub and current_sub in sub_map:
        console.print(
            f"Using current subscription: "
            f"[bold]{sub_map[current_sub]['name']}[/bold] ({current_sub})"
        )
        return [current_sub]

    # Interactive selection (allow multiple)
    console.print("\n[bold]Available subscriptions:[/bold]")
    for i, sub in enumerate(subs, 1):
        console.print(f"  {i}. {sub['name']} ({sub['id']})")

    choice = Prompt.ask(
        "\nSelect subscription(s) (comma-separated numbers, e.g. 1,3)",
        default="1",
    )
    indices = [int(c.strip()) for c in choice.split(",") if c.strip().isdigit()]
    selected = []
    for idx in indices:
        if 1 <= idx <= len(subs):
            selected.append(subs[idx - 1]["id"])
    if not selected:
        console.print("[red]No valid selection.[/red]")
        raise SystemExit(1)

    names = ", ".join(sub_map[s]["name"] for s in selected)
    console.print(f"\nUsing {len(selected)} subscription(s): [bold]{names}[/bold]")
    return selected


def select_subscription(
    credential: AzureCliCredential, subscription_id: str | None = None,
) -> str:
    """Select a single subscription — kept for backward compatibility."""
    result = resolve_subscriptions(credential, subscription_id)
    return result[0]


def extract_subscription_id(resource_id: str) -> str | None:
    """Extract the subscription ID from an Azure resource ID."""
    parts = resource_id.split("/")
    try:
        idx = [p.lower() for p in parts].index("subscriptions")
        return parts[idx + 1]
    except (ValueError, IndexError):
        return None
