import sqlite3

conn = sqlite3.connect("meditrack.db")
cur = conn.cursor()

cur.execute("DELETE FROM medicines")
conn.commit()

print("All medicines deleted successfully.")

conn.close()
