import sqlite3
from config import DATABASE

conn = sqlite3.connect(DATABASE)
cur = conn.cursor()

#cur.execute("INSERT OR IGNORE INTO medicines (name, price, stock) VALUES ('Paracetamol', 10, 100)")
#cur.execute("INSERT OR IGNORE INTO medicines (name, price, stock) VALUES ('Cetirizine', 5, 50)")
#cur.execute("INSERT OR IGNORE INTO medicines (name, price, stock) VALUES ('Amoxicillin', 20, 30)")
cur.execute("SELECT * FROM medicines ORDER BY name ASC")

conn.commit()
conn.close()

#print("Medicines added")
