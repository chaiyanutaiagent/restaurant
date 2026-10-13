"""Full release migration path, ONLY on an empty disposable schema snapshot."""
from sqlalchemy import create_engine, text
from alembic.config import Config
from alembic import command
from app.config import settings

engine=create_engine(settings.retail_database_url_sync)
with engine.connect() as connection:
    assert str(connection.scalar(text("SELECT current_database()"))).endswith("_intake_test")
    assert connection.scalar(text("SELECT count(*) FROM companies"))==0
config=Config("alembic-boundaries.ini",ini_section="retail")
# The UAT schema-only snapshot has no version row; its observed version is p13.
command.stamp(config,"p13retail0007")
command.upgrade(config,"retailtransfer0010")
command.downgrade(config,"p13retail0007")
print("PASS full p13 -> WP84 -> catalog -> transfers chain and empty-schema downgrade")
