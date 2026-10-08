import click
from flask import Flask

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
