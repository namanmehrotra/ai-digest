"""Modal app — top-level entry point.

Defines the deployed Modal functions (cron jobs + HTTPS MCP endpoint).
Run `modal deploy modal_app.py` to deploy. See SPEC.md §11.
"""

from __future__ import annotations

import modal

app = modal.App("ai-digest")

# Build a Python image with our deps from pyproject.toml, then mount source.
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install_from_pyproject("pyproject.toml")
    .add_local_dir("src", "/root/src")
    .add_local_file("sources.yaml", "/root/sources.yaml")
)

secret = modal.Secret.from_name("ai-digest-prod")


# ---------------------------------------------------------------------------
# Scheduled functions
# ---------------------------------------------------------------------------


@app.function(
    image=image,
    secrets=[secret],
    schedule=modal.Cron("0 0,12 * * *"),  # every 12h UTC
    timeout=900,
)
async def ingest_run() -> None:
    """Fetch all sources, dedup, tag, embed, store. See SPEC §9.1."""
    from src.ingest.fetcher import run_ingest

    await run_ingest()


@app.function(
    image=image,
    secrets=[secret],
    schedule=modal.Cron("0 12 * * 2,5"),  # Tue + Fri at 12:00 UTC (~7am ET)
    timeout=600,
)
async def weekly_digest() -> None:
    """Compose and send the scheduled digest. See SPEC §9.3."""
    from src.digest.sender import send_scheduled_digest

    await send_scheduled_digest()


@app.function(
    image=image,
    secrets=[secret],
    schedule=modal.Cron("15 0,12 * * *"),  # 15 min after each ingest
    timeout=300,
)
async def high_signal_check() -> None:
    """Check for high-signal events; fire interrupt email if cooldown clear. See SPEC §9.4."""
    from src.high_signal import check_and_fire

    await check_and_fire()


# ---------------------------------------------------------------------------
# MCP HTTPS endpoint
# ---------------------------------------------------------------------------


@app.function(image=image, secrets=[secret], timeout=120)
@modal.asgi_app()
def mcp_endpoint():
    """MCP HTTPS endpoint. See SPEC §9.5."""
    from src.mcp_server import build_app

    return build_app()


# ---------------------------------------------------------------------------
# Manual triggers for local testing
# Usage: modal run modal_app.py::ingest_now
# ---------------------------------------------------------------------------


@app.local_entrypoint()
def ingest_now() -> None:
    ingest_run.remote()


@app.local_entrypoint()
def digest_now() -> None:
    weekly_digest.remote()


@app.local_entrypoint()
def high_signal_now() -> None:
    high_signal_check.remote()
