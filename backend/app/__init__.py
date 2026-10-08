import logging

from flask import Flask

from app.config import Config, get_config
from app.extensions import cors, db, jwt, migrate
from app.utils.http import register_error_handlers


def create_app(config: type[Config] | None = None) -> Flask:
    config = config or get_config()
    logging.basicConfig(
        level=config.LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    app = Flask(__name__)
    app.config.from_object(config)

    db.init_app(app)
    migrate.init_app(app, db, directory=app.config["MIGRATIONS_DIR"], render_as_batch=True)
    jwt.init_app(app)
    cors.init_app(app, resources={r"/api/*": {"origins": app.config["FRONTEND_ORIGIN"]}})

    from app import models  # noqa: F401  (registers every table on db.metadata)
    from app.cli import register_cli
    from app.routes import (
        analytics,
        auth,
        coach,
        forecast,
        goals,
        health,
        holdings,
        profile,
        risks,
        simulation,
        system,
        transactions,
        twin,
    )
    from app.utils.auth import register_jwt_handlers

    register_error_handlers(app)
    register_jwt_handlers(app)
    for module in (
        system,
        auth,
        profile,
        transactions,
        holdings,
        twin,
        analytics,
        health,
        forecast,
        risks,
        simulation,
        goals,
        coach,
    ):
        app.register_blueprint(module.bp, url_prefix=f"/api{module.bp.url_prefix or ''}")
    register_cli(app)
    return app
