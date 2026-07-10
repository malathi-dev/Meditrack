import sqlite3

DB_NAME = "meditrack.db"

conn = sqlite3.connect(DB_NAME)
cur = conn.cursor()

# Disable foreign key checks temporarily
cur.execute("PRAGMA foreign_keys = OFF;")

# Delete all data from tables
tables = [
    "bill_items",
    "bills",
    "medicines",
    "customers"
]

for table in tables:
    cur.execute(f"DELETE FROM {table};")
    print(f"Cleared data from {table}")

# Reset auto-increment counters
cur.execute("DELETE FROM sqlite_sequence;")

# Enable foreign keys again
cur.execute("PRAGMA foreign_keys = ON;")

conn.commit()
conn.close()

print("All table data cleared successfully. Tables are safe.")


