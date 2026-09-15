import sqlite3, os, glob

for p in glob.glob("**/data.db", recursive=True):
    print(f"=== {p} ===")
    c = sqlite3.connect(p)
    cur = c.cursor()
    cur.execute("SELECT DISTINCT scope, COUNT(*) FROM tasks GROUP BY scope")
    print("  scope значения:", cur.fetchall())
    cur.execute("SELECT DISTINCT status, COUNT(*) FROM tasks GROUP BY status")
    print("  status значения:", cur.fetchall())
    c.close()

for p in glob.glob("**/auth.db", recursive=True):
    print(f"=== {p} (roles) ===")
    c = sqlite3.connect(p)
    cur = c.cursor()
    try:
        cur.execute("SELECT DISTINCT role FROM users")
        print("  role:", cur.fetchall())
    except Exception as e:
        print("  ", e)
    c.close()