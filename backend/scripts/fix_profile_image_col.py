from app.database.session import engine
from sqlalchemy import text

with engine.connect() as conn:
    res = conn.execute(text("SELECT column_name, data_type, character_maximum_length FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'profile_image';")).fetchall()
    print("CURRENT COLUMN:", res)
    conn.execute(text("ALTER TABLE users ALTER COLUMN profile_image TYPE TEXT;"))
    conn.commit()
    res2 = conn.execute(text("SELECT column_name, data_type, character_maximum_length FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'profile_image';")).fetchall()
    print("UPDATED COLUMN:", res2)
