"""Mark command-line interface (Typer + Rich).

Commands are organized to mirror the build phases. Phase 1 wires up `init`,
`product`, and `status`; later phases add `generate`, `queue`, `approve`,
`post`, `analytics`, `trends`, `insights`, and `run`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import db as db_module
from . import store
from .config import ProductConfig, load_product_yaml

console = Console()

app = typer.Typer(no_args_is_help=True, add_completion=False,
                  help="Mark — a personal autonomous AI marketing engine.")
product_app = typer.Typer(no_args_is_help=True, help="Manage products / campaigns.")
app.add_typer(product_app, name="product")


# --------------------------------------------------------------------------- #
# Global context
# --------------------------------------------------------------------------- #
class Ctx:
    def __init__(self, home: Optional[Path], dry_run: bool):
        self.home = home
        self.dry_run = dry_run
        self._app = None

    def app(self):
        if self._app is None:
            from .app import get_app

            self._app = get_app(home=self.home, force_mock=self.dry_run)
        return self._app


@app.callback()
def _main(
    ctx: typer.Context,
    home: Optional[Path] = typer.Option(None, "--home", help="Project home dir (default: cwd)."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Force offline/mock mode for all providers."),
):
    ctx.obj = Ctx(home, dry_run)


def _app(ctx: typer.Context):
    return ctx.obj.app()


# --------------------------------------------------------------------------- #
# init
# --------------------------------------------------------------------------- #
@app.command()
def init(ctx: typer.Context):
    """Initialize the database and config directories."""
    a = _app(ctx)
    a.paths.ensure()
    console.print(Panel.fit(
        f"[bold green]Mark initialized.[/]\n"
        f"home:    {a.paths.home}\n"
        f"db:      {a.paths.db_path}\n"
        f"config:  {a.paths.default_config}\n"
        f"media:   {a.paths.media_dir}",
        title="init",
    ))
    # Seed the example product if nothing exists yet and the template is present.
    example = a.paths.products_dir / "example.yaml"
    if not store.list_products(a.conn) and example.exists():
        if typer.confirm("No products yet. Import config/products/example.yaml?", default=True):
            p = load_product_yaml(example)
            store.upsert_product(a.conn, p, active=True)
            console.print(f"[green]Imported and activated product:[/] {p.id}")
    _print_provider_status(a)
    console.print("\nNext: [bold]mark product list[/] · [bold]mark generate[/] · [bold]mark status[/]")


# --------------------------------------------------------------------------- #
# product
# --------------------------------------------------------------------------- #
@product_app.command("add")
def product_add(
    ctx: typer.Context,
    from_yaml: Optional[Path] = typer.Option(None, "--from", help="Import a product YAML instead of prompting."),
):
    """Create a product config (interactive) or import one from YAML."""
    a = _app(ctx)
    if from_yaml:
        p = load_product_yaml(from_yaml)
    else:
        p = _prompt_product()
        # Persist a YAML copy alongside the built-in example.
        _write_product_yaml(a.paths.products_dir / f"{p.id}.yaml", p)
    store.upsert_product(a.conn, p, active=True)
    console.print(f"[green]Saved & activated product:[/] [bold]{p.id}[/] ({p.name})")


@product_app.command("list")
def product_list(ctx: typer.Context):
    """List all products."""
    a = _app(ctx)
    products = store.list_products(a.conn)
    if not products:
        console.print("[yellow]No products yet.[/] Add one with [bold]mark product add[/].")
        raise typer.Exit()
    table = Table(title="Products")
    table.add_column("active", justify="center")
    table.add_column("id", style="bold")
    table.add_column("name")
    table.add_column("platforms")
    for p in products:
        platforms = ", ".join(db_module.loads(p["platforms"], []))
        table.add_row("●" if p["active"] else "", p["id"], p["name"], platforms)
    console.print(table)


@product_app.command("activate")
def product_activate(ctx: typer.Context, product_id: str):
    """Set the active product."""
    a = _app(ctx)
    if not store.get_product(a.conn, product_id):
        console.print(f"[red]No such product:[/] {product_id}")
        raise typer.Exit(code=1)
    store.set_active_product(a.conn, product_id)
    console.print(f"[green]Active product set to:[/] {product_id}")


# --------------------------------------------------------------------------- #
# generate / queue / preview / approve / reject
# --------------------------------------------------------------------------- #
@app.command()
def generate(
    ctx: typer.Context,
    product: Optional[str] = typer.Option(None, "--product", "-p", help="Product id (default: active)."),
    platform: Optional[str] = typer.Option(None, "--platform", help="Generate for a single platform only."),
    count: int = typer.Option(1, "--count", "-n", help="Pieces per platform."),
):
    """Generate content (saved as drafts) for all platforms or one."""
    from .llm import LLM
    from . import pipeline

    a = _app(ctx)
    prod = _resolve_product_or_exit(a, product)
    llm = LLM(a)

    platforms = [platform] if platform else None
    with console.status("[bold]Generating content…[/]"):
        results = pipeline.generate_all(a, llm, prod, platforms=platforms, count=count)

    table = Table(title=f"Generated {len(results)} draft(s) for {prod['id']}")
    table.add_column("id", justify="right")
    table.add_column("platform")
    table.add_column("type")
    table.add_column("status")
    table.add_column("hook")
    for r in results:
        table.add_row(str(r["id"]), r["platform"], r["content_type"], r["status"],
                      (r["hook"] or "")[:48])
    console.print(table)
    console.print("Review with [bold]mark queue[/] · [bold]mark preview <id>[/] · "
                  "approve with [bold]mark approve <id>[/]")


@app.command()
def queue(ctx: typer.Context,
          status_filter: str = typer.Option("draft", "--status", help="Filter by status.")):
    """Show pending content."""
    a = _app(ctx)
    rows = store.list_content(a.conn, status=status_filter, limit=200)
    if not rows:
        console.print(f"[yellow]No content with status '{status_filter}'.[/]")
        raise typer.Exit()
    table = Table(title=f"Queue ({status_filter})")
    for col in ("id", "platform", "type", "hook", "created"):
        table.add_column(col, justify="right" if col == "id" else "left")
    for r in rows:
        table.add_row(str(r["id"]), r["platform"], r["content_type"],
                      (r["hook"] or "")[:46], str(r["created_at"])[:16])
    console.print(table)


@app.command()
def preview(ctx: typer.Context, content_id: int):
    """Show a piece of content in full, including media paths."""
    a = _app(ctx)
    c = store.get_content(a.conn, content_id)
    if not c:
        console.print(f"[red]No content with id {content_id}.[/]")
        raise typer.Exit(code=1)
    hashtags = db_module.loads(c["hashtags"], [])
    media = db_module.loads(c["media_paths"], [])
    sctx = db_module.loads(c["strategy_context"], {})
    body = (
        f"[bold]#{c['id']}[/]  [cyan]{c['platform']}[/] · {c['content_type']} · "
        f"[bold]{c['status']}[/]\n\n"
        f"[bold]Hook:[/] {c['hook']}\n\n"
        f"[bold]Caption:[/]\n{c['caption']}\n\n"
        f"[bold]Hashtags:[/] {' '.join(hashtags)}\n"
    )
    if sctx:
        body += (f"\n[dim]topic: {sctx.get('topic')} · angle: {sctx.get('angle')} · "
                 f"hook_style: {sctx.get('hook_style')} · tone: {sctx.get('tone')}"
                 f" · novelty_sim: {sctx.get('novelty_max_sim')}[/]\n")
    if media:
        body += "\n[bold]Media:[/]\n" + "\n".join(f"  {m}" for m in media)
    console.print(Panel(body, title=f"content {c['id']}"))


@app.command()
def approve(ctx: typer.Context,
            content_id: Optional[int] = typer.Argument(None),
            all_drafts: bool = typer.Option(False, "--all", help="Approve all drafts.")):
    """Approve content for posting."""
    from datetime import datetime, timezone

    from . import characters as characters_mod

    a = _app(ctx)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    def _approve_row(row: dict) -> None:
        already = row["status"] == "approved"
        store.set_content_status(a.conn, row["id"], "approved", approved_at=now)
        if not already:  # character lore advances on FIRST approval only
            try:
                characters_mod.on_content_approved(a, row)
            except Exception:
                pass

    if all_drafts:
        rows = store.list_content(a.conn, status="draft", limit=1000)
        for r in rows:
            _approve_row(r)
        console.print(f"[green]Approved {len(rows)} draft(s).[/]")
        return
    if content_id is None:
        console.print("[red]Provide a content id or --all.[/]")
        raise typer.Exit(code=1)
    row = store.get_content(a.conn, content_id)
    if not row:
        console.print(f"[red]No content with id {content_id}.[/]")
        raise typer.Exit(code=1)
    _approve_row(row)
    console.print(f"[green]Approved content {content_id}.[/]")


@app.command()
def reject(ctx: typer.Context, content_id: int,
           feedback: str = typer.Option("", "--feedback", "-f", help="Why (used for learning).")):
    """Reject content (records feedback the system learns from)."""
    a = _app(ctx)
    if not store.get_content(a.conn, content_id):
        console.print(f"[red]No content with id {content_id}.[/]")
        raise typer.Exit(code=1)
    store.set_content_status(a.conn, content_id, "rejected", rejection_feedback=feedback)
    console.print(f"[yellow]Rejected content {content_id}.[/] {feedback}")


# --------------------------------------------------------------------------- #
# post
# --------------------------------------------------------------------------- #
@app.command()
def post(
    ctx: typer.Context,
    content_id: Optional[int] = typer.Argument(None, help="Post one specific piece."),
    product: Optional[str] = typer.Option(None, "--product", "-p"),
    now: bool = typer.Option(False, "--now", help="Post immediately (default for this command)."),
):
    """Post approved content. (Optimal-time scheduling runs under `mark run`.)"""
    from .posting import manager

    a = _app(ctx)
    if a.is_mock("upload_post"):
        console.print("[yellow]upload-post is in mock mode[/] — nothing goes live; "
                      "posts are simulated and recorded.")

    if content_id is not None:
        c = store.get_content(a.conn, content_id)
        if not c:
            console.print(f"[red]No content with id {content_id}.[/]")
            raise typer.Exit(code=1)
        if c["status"] not in ("approved", "draft"):
            console.print(f"[yellow]Content {content_id} is '{c['status']}'.[/] Posting anyway.")
        resp = manager.post_content(a, c)
        _report_posts([{"content_id": content_id, "platform": c["platform"], "response": resp}])
        return

    prod = store.resolve_product(a.conn, product)
    results = manager.post_approved(a, product_id=prod["id"] if prod else None)
    if not results:
        console.print("[yellow]No approved content to post.[/] Approve some with "
                      "[bold]mark approve --all[/].")
        raise typer.Exit()
    _report_posts(results)


def _report_posts(results: list[dict]) -> None:
    table = Table(title="Posting results")
    table.add_column("content", justify="right")
    table.add_column("platform")
    table.add_column("status")
    table.add_column("post id / error")
    for r in results:
        resp = r["response"]
        if resp.get("error"):
            table.add_row(str(r["content_id"]), r["platform"], "[red]failed[/]", resp["error"][:40])
        else:
            res = resp["results"].get(r["platform"], {})
            table.add_row(str(r["content_id"]), r["platform"], "[green]posted[/]",
                          f"{res.get('post_id')}  (req {resp.get('request_id')})")
    console.print(table)


# --------------------------------------------------------------------------- #
# trends / analytics
# --------------------------------------------------------------------------- #
@app.command()
def trends(
    ctx: typer.Context,
    refresh: bool = typer.Option(True, "--refresh/--no-refresh", help="Pull fresh trends first."),
    product: Optional[str] = typer.Option(None, "--product", "-p"),
    limit: int = typer.Option(15, "--limit"),
):
    """Show current trending topics (ranked by relevance to the product)."""
    from .llm import LLM
    from .trends import aggregator

    a = _app(ctx)
    prod = _resolve_product_or_exit(a, product)
    if refresh:
        with console.status("[bold]Fetching trends…[/]"):
            aggregator.refresh(a, LLM(a), prod)
    rows = aggregator.recent_trends(a, limit=limit)
    if not rows:
        console.print("[yellow]No trends cached.[/] Run with --refresh.")
        raise typer.Exit()
    table = Table(title="Trending topics")
    table.add_column("source")
    table.add_column("topic")
    table.add_column("score", justify="right")
    table.add_column("stage")
    table.add_column("relevance", justify="right")
    stage_style = {"new": "green", "rising": "cyan", "mature": "dim", "declining": "red"}
    for r in rows:
        meta = r.get("metadata") or {}
        rel = meta.get("relevance", "")
        stage = r.get("stage") or "?"
        notes = []
        if meta.get("safe") is False:
            notes.append("⚠ origin")
        if meta.get("sound_dependent"):
            notes.append("♫ manual")
        stage_s = f"[{stage_style.get(stage, 'white')}]{stage}[/]" + \
            ((" " + " ".join(notes)) if notes else "")
        table.add_row(r["source"], r["topic"], f"{r['trend_score']:.3f}", stage_s, str(rel))
    console.print(table)


@app.command()
def react(
    ctx: typer.Context,
    topic: Optional[str] = typer.Option(None, "--topic", "-t",
                                        help="Trend topic (default: hottest qualifying)."),
    product: Optional[str] = typer.Option(None, "--product", "-p"),
    platform: Optional[list[str]] = typer.Option(None, "--platform"),
):
    """Ride a hot trend NOW — generate trend content without waiting for the cron."""
    from .llm import LLM
    from .trends import aggregator

    a = _app(ctx)
    prod = _resolve_product_or_exit(a, product)
    trend = None
    if topic:
        for t in aggregator.recent_trends(a, limit=100, max_age_hours=48):
            if t["topic"].strip().lower() == topic.strip().lower():
                trend = t
                break
        if trend is None:
            console.print(f"[red]Trend “{topic}” not found in recent trends.[/]")
            raise typer.Exit(1)
    with console.status("[bold]Riding the trend…[/]"):
        rows = aggregator.react(a, LLM(a), prod, trend=trend,
                                platforms=list(platform) if platform else None)
    if not rows:
        console.print("[yellow]Nothing drafted[/] — no qualifying hot trend, or the "
                      "daily reaction cap is reached.")
        raise typer.Exit()
    for row in rows:
        console.print(f"[green]Drafted[/] #{row['id']} [{row['platform']}] — {row['hook']}")


@app.command()
def strategies(
    ctx: typer.Context,
    product: Optional[str] = typer.Option(None, "--product", "-p"),
    platform: Optional[str] = typer.Option(None, "--platform"),
):
    """Show the strategy catalog (and which strategies fit where)."""
    from . import strategies as strategies_mod

    a = _app(ctx)
    prod = store.resolve_product(a.conn, product)
    table = Table(title="Strategy catalog")
    for col in ("id", "emotion", "humor", "weight", "platforms"):
        table.add_column(col)
    pool = strategies_mod.STRATEGIES
    if prod and platform:
        pool = strategies_mod.eligible(a, prod, platform)
    allow = strategies_mod.product_allowlist(prod) if prod else None
    for s in pool:
        marker = "" if (allow is None or s.id in allow) else " [dim](off)[/]"
        table.add_row(s.id + marker, s.emotional_target, s.humor_level,
                      f"{s.mix_weight:.2f}", ", ".join(sorted(s.platforms)))
    console.print(table)


character_app = typer.Typer(help="Manage AI ambassador characters.")
app.add_typer(character_app, name="character")


@character_app.command("list")
def character_list(ctx: typer.Context,
                   product: Optional[str] = typer.Option(None, "--product", "-p")):
    """List characters for a product."""
    from . import characters as characters_mod

    a = _app(ctx)
    prod = _resolve_product_or_exit(a, product)
    rows = characters_mod.list_for_product(a, prod["id"], include_inactive=True)
    if not rows:
        console.print("[yellow]No characters.[/] Add YAML bibles under "
                      "config/characters/ and run [bold]mark character sync[/].")
        raise typer.Exit()
    table = Table(title=f"Characters — {prod['name']}")
    for col in ("id", "name", "role", "active", "sheet", "lore"):
        table.add_column(col)
    for c in rows:
        lore = c.get("lore_state") or {}
        lore_s = ", ".join(f"{k}={v}" for k, v in lore.items()
                           if isinstance(v, (int, float)))[:60]
        table.add_row(str(c["id"]), c["name"], c.get("role") or "",
                      "yes" if c["active"] else "no",
                      "✓" if c.get("reference_image") else "—", lore_s)
    console.print(table)


@character_app.command("sync")
def character_sync(ctx: typer.Context):
    """Sync character bibles from config/characters/*.yaml into the database."""
    from . import characters as characters_mod

    a = _app(ctx)
    synced = characters_mod.sync_from_config(a)
    console.print(f"[green]Synced {len(synced)} character(s).[/]")


@character_app.command("sheet")
def character_sheet(ctx: typer.Context, character_id: int):
    """Generate (or regenerate) a character's reference sheet image."""
    from . import characters as characters_mod
    from .llm import LLM

    a = _app(ctx)
    c = characters_mod.get(a, character_id)
    if not c:
        console.print(f"[red]Character {character_id} not found.[/]")
        raise typer.Exit(1)
    with console.status(f"[bold]Rendering {c['name']}'s reference sheet…[/]"):
        from . import db as db_module

        db_module.update(a.conn, "characters", character_id, reference_image=None)
        path = characters_mod.ensure_reference_image(a, LLM(a), characters_mod.get(a, character_id))
    console.print(f"[green]Sheet saved:[/] {path}")


@app.command()
def analytics(
    ctx: typer.Context,
    days: int = typer.Option(7, "--days", help="Look-back window."),
    product: Optional[str] = typer.Option(None, "--product", "-p"),
    collect: bool = typer.Option(False, "--collect", "-c", help="Pull fresh metrics first."),
):
    """Show recent post performance."""
    from .analytics import collector

    a = _app(ctx)
    prod = store.resolve_product(a.conn, product)
    pid = prod["id"] if prod else None
    if collect:
        with console.status("[bold]Collecting metrics…[/]"):
            got = collector.collect(a, product_id=pid)
        console.print(f"[green]Collected metrics for {len(got)} post(s).[/]")
    rows = collector.recent_performance(a, product_id=pid, days=days)
    if not rows:
        console.print("[yellow]No metrics yet.[/] Post something, then "
                      "[bold]mark analytics --collect[/].")
        raise typer.Exit()
    table = Table(title=f"Performance (last {days}d)")
    for col in ("content", "platform", "type", "views", "likes", "comments", "eng.rate"):
        table.add_column(col, justify="right" if col != "platform" and col != "type" else "left")
    for r in rows:
        table.add_row(str(r["content_id"]), r["platform"], r["content_type"],
                      f"{r['views']:,}", f"{r['likes']:,}", f"{r['comments']:,}",
                      f"{r['engagement_rate']:.3f}")
    console.print(table)


# --------------------------------------------------------------------------- #
# learn / insights
# --------------------------------------------------------------------------- #
@app.command()
def learn(
    ctx: typer.Context,
    product: Optional[str] = typer.Option(None, "--product", "-p"),
    days: int = typer.Option(7, "--days", help="Reward window for the feedback loop."),
):
    """Run the feedback loop: collect metrics, update the bandit, re-index winners, analyze."""
    from .learning import feedback
    from .llm import LLM

    a = _app(ctx)
    prod = _resolve_product_or_exit(a, product)
    with console.status("[bold]Running feedback loop…[/]"):
        report = feedback.run(a, LLM(a), prod, days=days)
    lift = report.get("holdout_lift")
    lift_line = (f"\nholdout lift:        [bold]{lift['lift_pct']:+.1f}%[/] "
                 f"(bandit {lift['bandit_avg_reward']} over {lift['bandit_posts']} posts "
                 f"vs random {lift['holdout_avg_reward']} over {lift['holdout_posts']})"
                 if lift else "\nholdout lift:        (not enough data yet)")
    baselines = ", ".join(f"{k}={v}" for k, v in (report.get("baselines") or {}).items())
    console.print(Panel.fit(
        f"platform baselines:  [bold]{baselines or '—'}[/]\n"
        f"rewards applied:     {report['rewards_applied']}"
        f" (awaiting baseline: {report['awaiting_baseline']})\n"
        f"new winners:         {report['new_winners']}  (total {report['total_winners']})\n"
        f"sentiment:           {report['sentiment']}{lift_line}",
        title="feedback loop",
    ))
    _render_insights(report["insights"])


@app.command()
def insights(ctx: typer.Context, product: Optional[str] = typer.Option(None, "--product", "-p")):
    """Show the latest analyzer insights."""
    from .learning import feedback

    a = _app(ctx)
    prod = _resolve_product_or_exit(a, product)
    data = feedback.latest_insights(a, prod["id"])
    if not data:
        console.print("[yellow]No insights yet.[/] Run [bold]mark learn[/] first.")
        raise typer.Exit()
    console.print(f"[dim]generated {data.get('_created_at')}[/]")
    _render_insights(data)


def _render_insights(ins: dict) -> None:
    def fmt_list(x):
        return ", ".join(x) if x else "—"

    def fmt_map(x):
        return ", ".join(f"{k}:{v}" for k, v in x.items()) if x else "—"

    console.print(Panel(
        f"[bold]Top topics:[/] {fmt_list(ins.get('top_performing_topics'))}\n"
        f"[bold]Worst topics:[/] {fmt_list(ins.get('worst_performing_topics'))}\n"
        f"[bold]Best hook styles:[/] {fmt_list(ins.get('best_hook_styles'))}\n"
        f"[bold]Best content types:[/] {fmt_map(ins.get('best_content_types'))}\n"
        f"[bold]Best posting times:[/] {fmt_map(ins.get('best_posting_times'))}\n"
        f"[bold]Sentiment:[/] {ins.get('audience_sentiment_summary')}\n\n"
        f"[bold]Recommended adjustments:[/]\n" +
        "\n".join(f"  • {r}" for r in ins.get('recommended_adjustments', [])) +
        f"\n\n[dim]{ins.get('raw_analysis', '')}[/]",
        title="insights",
    ))


# --------------------------------------------------------------------------- #
# run (autonomous scheduler)
# --------------------------------------------------------------------------- #
@app.command()
def run(
    ctx: typer.Context,
    once: bool = typer.Option(False, "--once", help="Run the core jobs once and exit."),
    daemon: bool = typer.Option(False, "--daemon", help="Hint to background the process."),
):
    """Start the autonomous scheduler (generation, posting, analytics, trends, feedback)."""
    import logging

    from .llm import LLM
    from .scheduler import engine

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    a = _app(ctx)
    llm = LLM(a)

    if once:
        with console.status("[bold]Running jobs once…[/]"):
            engine.run_once(a, llm)
        console.print("[green]Ran one cycle.[/] See [bold]mark queue[/] / [bold]mark analytics[/].")
        return

    sched = engine.build_scheduler(a, llm)
    _print_schedule(engine.upcoming(a, llm))
    if not a.settings.approval.auto_approve:
        console.print("[yellow]auto_approve is off[/] — generated content waits for "
                      "[bold]mark approve[/] before the posting jobs will send it.")
    if daemon:
        console.print("[dim]Tip: background with `nohup mark run >mark.log 2>&1 &`.[/]")
    console.print("[bold green]Scheduler running.[/] Press Ctrl+C to stop.\n")
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        console.print("\n[yellow]Scheduler stopped.[/]")


def _print_schedule(jobs: list[dict]) -> None:
    table = Table(title="Upcoming jobs")
    table.add_column("job")
    table.add_column("next run")
    for j in jobs:
        table.add_row(j["name"], j["next"])
    console.print(table)


# --------------------------------------------------------------------------- #
# web
# --------------------------------------------------------------------------- #
@app.command()
def web(
    ctx: typer.Context,
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8321, "--port"),
    autopilot: bool = typer.Option(False, "--autopilot",
                                   help="Start the autonomous scheduler with the server."),
    open_browser: bool = typer.Option(True, "--open/--no-open",
                                      help="Open the app in your browser."),
):
    """Launch the Mark web app (dashboard, campaigns, content studio)."""
    from .web import server

    state: Ctx = ctx.obj
    url = f"http://{host}:{port}"
    console.print(f"[bold green]Mark web[/] → [link={url}]{url}[/link]"
                  + ("  [dim](autopilot on)[/]" if autopilot else ""))
    if open_browser:
        import threading
        import webbrowser

        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    server.serve(home=state.home, host=host, port=port,
                 force_mock=state.dry_run, autopilot=autopilot)


# --------------------------------------------------------------------------- #
# status
# --------------------------------------------------------------------------- #
@app.command()
def status(ctx: typer.Context):
    """Show system status: active product, content counts, providers, spend."""
    a = _app(ctx)
    active = store.get_active_product(a.conn)
    console.print(Panel.fit(
        f"[bold]Active product:[/] {active['id'] + ' (' + active['name'] + ')' if active else '[red]none[/]'}",
        title="status",
    ))

    counts = db_module.query(
        a.conn,
        "SELECT status, COUNT(*) AS n FROM content GROUP BY status ORDER BY status",
    )
    if counts:
        t = Table(title="Content")
        t.add_column("status")
        t.add_column("count", justify="right")
        for r in counts:
            t.add_row(r["status"], str(r["n"]))
        console.print(t)

    _print_provider_status(a)
    _print_spend(a)

    # Upcoming scheduled jobs (best-effort).
    try:
        from .llm import LLM
        from .scheduler import engine

        jobs = engine.upcoming(a, LLM(a), limit=6)
        if jobs:
            t = Table(title="Next scheduled jobs")
            t.add_column("job")
            t.add_column("next run")
            for j in jobs:
                t.add_row(j["name"], j["next"])
            console.print(t)
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _resolve_product_or_exit(a, product_id: Optional[str]) -> dict:
    prod = store.resolve_product(a.conn, product_id)
    if not prod:
        console.print("[red]No active product.[/] Add one with [bold]mark product add[/] "
                      "or pass [bold]--product <id>[/].")
        raise typer.Exit(code=1)
    return prod


def _print_provider_status(a) -> None:
    t = Table(title="Providers")
    t.add_column("provider")
    t.add_column("mode")
    for name, label in [("openai", "OpenAI (text/image/tts/embed)"),
                        ("fal", "fal.ai (video)"),
                        ("upload_post", "upload-post.com (posting/analytics)"),
                        ("elevenlabs", "ElevenLabs (tts)")]:
        mode = "[yellow]mock[/]" if a.is_mock(name) else "[green]live[/]"
        t.add_row(label, mode)
    console.print(t)
    if not a.fully_live:
        console.print("[dim]Some providers are in mock mode (missing keys or --dry-run). "
                      "The pipeline still runs end-to-end with synthetic assets.[/]")


def _print_spend(a) -> None:
    row = db_module.query_one(
        a.conn,
        "SELECT COALESCE(SUM(usd),0) AS usd, COUNT(*) AS n, "
        "COALESCE(SUM(mocked),0) AS mocked FROM costs",
    )
    if row and row["n"]:
        console.print(f"[dim]API calls logged: {row['n']} "
                      f"({row['mocked']} mocked) · estimated spend: ${row['usd']:.4f}[/]")


def _prompt_product() -> ProductConfig:
    console.print("[bold]New product[/] — answer a few questions:")
    pid = typer.prompt("id (slug, e.g. sudoapply)")
    name = typer.prompt("name")
    description = typer.prompt("description (what it does)")
    target_audience = typer.prompt("target audience")
    brand_voice = typer.prompt("brand voice / tone")
    website_url = typer.prompt("website url", default="")
    platforms_raw = typer.prompt("platforms (comma-separated)",
                                 default="tiktok,instagram,x,linkedin")
    platforms = [p.strip() for p in platforms_raw.split(",") if p.strip()]
    cadence = {p: typer.prompt(f"posts/day for {p}", default=1, type=int) for p in platforms}
    return ProductConfig(
        id=pid, name=name, description=description, target_audience=target_audience,
        brand_voice=brand_voice, website_url=website_url or None,
        platforms=platforms, posting_cadence=cadence,
    )


def _write_product_yaml(path: Path, p: ProductConfig) -> None:
    import yaml

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(p.model_dump(exclude_none=True), sort_keys=False))


if __name__ == "__main__":
    app()
