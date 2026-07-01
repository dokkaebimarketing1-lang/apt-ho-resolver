"""DB 인덱스 생성 — SQLite/Supabase 호환"""
import sqlite3, time
db = sqlite3.connect("D:/부동산호수알아내기/local.db", timeout=30)

idxs = [
    ("idx_cda", "CREATE INDEX idx_cda ON unit_master(complex_id, dong, area_exclusive)"),
    ("idx_cho", "CREATE INDEX idx_cho ON unit_master(complex_id, dong, ho)"),
    ("idx_flr", "CREATE INDEX idx_flr ON unit_master(floor)"),
]

for name, sql in idxs:
    t0 = time.time()
    try:
        db.execute(f"DROP INDEX IF EXISTS {name}")
        db.execute(sql)
        db.commit()
        print(f"  {name}: {time.time()-t0:.0f}s")
    except Exception as e:
        print(f"  {name}: ERROR - {e}")

print("DONE")
db.close()
