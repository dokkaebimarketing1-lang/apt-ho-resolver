"""unit_master_v2 → line_fact 구축 (서울 전용, direction 빈칸)"""
import sys, sqlite3, time
sys.path.insert(0, "D:/부동산호수알아내기")
from src.floorplan_infer import infer_floorplan

db = sqlite3.connect("D:/부동산호수알아내기/local.db")

# line_fact 스키마 맞춰서 재생성
db.execute("DROP TABLE IF EXISTS line_fact")
db.execute("""
    CREATE TABLE line_fact (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        complex_name TEXT NOT NULL,
        dong TEXT NOT NULL,
        line TEXT NOT NULL,
        area_type TEXT,
        direction TEXT,        -- 실측값으로 교체 예정
        confidence REAL,
        UNIQUE(complex_name, dong, line)
    )
""")
db.commit()

# 서울 단지만 (sigungu_cd LIKE '11%')
done = set()
complexes = db.execute(
    """SELECT complex_name, bldg_pk, count(*)
       FROM unit_master_v2
       WHERE sigungu_cd LIKE '11%' AND complex_name != ''
       GROUP BY complex_name, bldg_pk
       ORDER BY count(*) DESC"""
).fetchall()

print(f"Seoul complexes (complex_name+bldg_pk): {len(complexes)}")
t0 = time.time()
total_lines = 0

for i, (cname, bldg_pk, cnt) in enumerate(complexes):
    key = f"{cname}|{bldg_pk}"
    if key in done:
        continue

    # 해당 건물의 모든 호 데이터
    rows = db.execute(
        """SELECT dong, ho, line, floor
           FROM unit_master_v2
           WHERE complex_name=? AND bldg_pk=?""",
        (cname, bldg_pk)
    ).fetchall()

    # 동별로 그룹화
    dong_units: dict[str, list[dict]] = {}
    for dong_str, ho_str, line_str, floor_val in rows:
        dong_units.setdefault(dong_str, []).append({
            "ho": ho_str,
            "dong": dong_str,
            "floor": floor_val,
        })

    for dong_str, units in dong_units.items():
        if len(units) < 2:
            continue
        result = infer_floorplan(units)
        if result is None:
            continue
        for r in result:
            db.execute(
                """INSERT OR IGNORE INTO line_fact
                   (complex_name, dong, line, area_type, direction, confidence)
                   VALUES (?,?,?,?,?,?)""",
                (cname, dong_str, r["line"], r["area_type"], "", 0.8)
            )
            total_lines += 1

    if (i + 1) % 500 == 0:
        db.commit()
        elapsed = time.time() - t0
        rate = (i + 1) / elapsed if elapsed else 0
        eta = (len(complexes) - i - 1) / rate / 60 if rate else 0
        print(f"  {i+1}/{len(complexes)} {cname[:30]:30s} {total_lines} lines | {elapsed:.0f}s | ETA {eta:.0f}min", flush=True)

db.commit()
print(f"\nDone: {total_lines} rows in {time.time()-t0:.0f}s")
print(f"Seoul line_fact rows: {db.execute('SELECT count(*) FROM line_fact').fetchone()[0]}")

# direction은 추측하지 않고 빈칸으로 — 나중에 실측값 채움
db.close()
