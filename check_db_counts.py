import sqlite3

db = r"C:\Users\HP\Desktop\Mes Codes Recherche\BasesGeospatialeMultiModale\data\multimodal_base.sqlite"
conn = sqlite3.connect(db)
cur = conn.cursor()
rows = cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
for (name,) in rows:
    if name.startswith('sqlite'):
        continue
    count = cur.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
    print(f"{name}: {count}")
conn.close()
