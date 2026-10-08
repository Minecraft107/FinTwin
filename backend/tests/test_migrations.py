"""The Alembic migration must build exactly the schema the models describe."""

import pytest
from flask_migrate import downgrade, upgrade
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app import create_app
from app.config import TestingConfig
from app.extensions import db


@pytest.fixture
def migrated_app(tmp_path):
    class FileDbConfig(TestingConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'migrated.db'}"

    app = create_app(FileDbConfig)
    with app.app_context():
        upgrade()
        yield app
        db.session.remove()
        db.engine.dispose()


def test_migration_matches_models(migrated_app):
    inspector = inspect(db.engine)
    migrated = set(inspector.get_table_names()) - {"alembic_version"}
    assert migrated == set(db.metadata.tables)
    for name, table in db.metadata.tables.items():
        migrated_columns = {c["name"] for c in inspector.get_columns(name)}
        assert migrated_columns == set(table.columns.keys()), name


def test_migrated_schema_enforces_enum_checks(migrated_app):
    with pytest.raises(IntegrityError):
        db.session.execute(
            text(
                "INSERT INTO expense_categories (name, kind, color, icon)"
                " VALUES ('X', 'bogus', '#000', 'x')"
            )
        )
    db.session.rollback()


def test_downgrade_removes_everything(migrated_app):
    downgrade(revision="base")
    engine = create_engine(migrated_app.config["SQLALCHEMY_DATABASE_URI"])
    assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
    engine.dispose()
