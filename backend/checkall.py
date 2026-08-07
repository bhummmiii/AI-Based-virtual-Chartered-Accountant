import psycopg

conn = psycopg.connect(
    "postgresql://postgres:Bhumi%402005@localhost:5432/ca_assistant_db"
)
cur = conn.execute(
    "SELECT tablename FROM pg_tables WHERE schemaname=%s ORDER BY tablename",
    ("public",),
)
tables = [r[0] for r in cur.fetchall()]
expected = [
    "clients",
    "users",
    "accounting_records",
    "gst_records",
    "tax_records",
    "audit_reports",
    "invoices",
    "documents",
    "government_rules",
    "notifications",
    "uploaded_documents",
    "alembic_version",
]
for t in expected:
    print(("OK   " if t in tables else "MISS ") + t)
print("Total tables:", len(tables))
conn.close()
