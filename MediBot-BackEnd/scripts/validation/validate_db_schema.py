"""
SQLite schema validator: scripts/validation/validate_db_schema.py.
Dumps every table's schema (columns, types) and a sample row, so we build
sql_rag_chain against the REAL schema instead of guessing column names.
"""

import sqlite3

from medibot.core.config import SQLITE_DB_PATH

conn = sqlite3.connect(SQLITE_DB_PATH)
cursor = conn.cursor()

# List all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = [row[0] for row in cursor.fetchall()]
print(f"Tables found: {tables}\n")

for table in tables:
    print("=" * 70)
    print(f"TABLE: {table}")
    print("=" * 70)

    # Schema (column name, type, nullable, pk)
    cursor.execute(f"PRAGMA table_info({table});")
    columns = cursor.fetchall()
    print("Columns:")
    for col in columns:
        cid, name, dtype, notnull, default, pk = col
        print(f"  {name:25s} {dtype:12s} {'PK' if pk else ''} {'NOT NULL' if notnull else ''}")

    # Row count
    cursor.execute(f"SELECT COUNT(*) FROM {table};")
    count = cursor.fetchone()[0]
    print(f"\nRow count: {count}")

    # Sample rows
    cursor.execute(f"SELECT * FROM {table} LIMIT 3;")
    sample_rows = cursor.fetchall()
    col_names = [c[1] for c in columns]
    print(f"Sample rows (columns: {col_names}):")
    for row in sample_rows:
        print(f"  {row}")
    print()

conn.close()
