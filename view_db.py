import sqlite3

conn = sqlite3.connect("meditrack.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print("\nTables in database:\n")

cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cur.fetchall()

for table in tables:
    print(table["name"])

print("\nMedicines table:\n")

cur.execute("SELECT * FROM medicines")
rows = cur.fetchall()

for row in rows:
    print(dict(row))

conn.close()
