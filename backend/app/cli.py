import sys

import click
from flask import Flask

from app.config import REPO_ROOT
from app.seed.categories import ensure_categories
from app.seed.demo import seed_demo


def register_cli(app: Flask) -> None:
    @app.cli.command("seed")
    @click.option("--reset", is_flag=True, help="Delete and regenerate the demo user's data.")
    def seed(reset: bool) -> None:
        """Create reference categories and the demo user (idempotent)."""
        created = ensure_categories()
        click.echo(f"Categories: {created} created")
        result = seed_demo(reset=reset)
        if result.created:
            click.echo(f"Demo user {result.email}: {result.transactions} transactions generated")
        else:
            click.echo(f"Demo user {result.email} already exists (use --reset to regenerate)")

    @app.cli.command("sample-csv")
    @click.option("--months", default=6, show_default=True, type=click.IntRange(1, 36))
    @click.option("--out", default="sample_statement.csv", show_default=True, type=click.Path())
    def sample_csv(months: int, out: str) -> None:
        """Write a bank-statement CSV (a new persona) for trying the import feature."""
        from app.seed.sample_csv import sample_statement

        with open(out, "w", encoding="utf-8", newline="") as f:
            f.write(sample_statement(months))
        click.echo(f"Wrote {out} ({months} months ending last month)")

    @app.cli.group("ml")
    def ml_group() -> None:
        """Offline ML pipeline."""

    @ml_group.command("train")
    @click.option("--users", default=300, show_default=True, help="Synthetic population size.")
    def train(users: int) -> None:
        """Build the synthetic population, train and evaluate all models, save artifacts."""
        if str(REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT))
        from ml.pipeline import run

        result = run(n_users=users)
        click.echo(f"Training finished in {result['seconds']}s; metrics in ml/models/metrics/")
