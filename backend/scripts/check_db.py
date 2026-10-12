from app.database.session import engine
from sqlalchemy import text

with engine.connect() as conn:
    tables = conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name LIKE 'gov_%'")).fetchall()
    print("Gov tables:", [t[0] for t in tables])
    alembic_rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    print("Alembic current version:", alembic_rev)
