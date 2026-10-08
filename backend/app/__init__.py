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
    migrate.init_app(app, db, directory=app.config["MIGRATIONS_DIR"])
    jwt.init_app(app)
    cors.init_app(app, resources={r"/api/*": {"origins": app.config["FRONTEND_ORIGIN"]}})

    register_error_handlers(app)

    from app.routes.system import bp as system_bp

    app.register_blueprint(system_bp, url_prefix="/api")
    return app
