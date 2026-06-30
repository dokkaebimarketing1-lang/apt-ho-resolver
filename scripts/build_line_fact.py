"""전체 DB에 floorplan_infer 적용 -> line_fact (주기커밋+재개)"""
import sys, sqlite3, time
sys.path.insert(0, "D:/부동산호수알아내기")
from src.floorplan_infer import infer_floorplan

db = sqlite3.connect("D:/부동산호수알아내기/local.db")
db.execute("DELETE FROM line_fact")  # fresh start
done = set()
complexes = db.execute(
    "SELECT complex_id, count(*) FROM unit_master "
    "WHERE area_exclusive IS NOT NULL AND complex_id != '' "
    "GROUP BY complex_id ORDER BY count(*) DESC"
).fetchall()

print(f"Total complexes: {len(complexes)}")
t0 = time.time()
total_lines = 0

for i, (cid, cnt) in enumerate(complexes):
    if cid in done: continue
    # 한 번에 모든 동 데이터 가져오기
    rows = db.execute(
        "SELECT dong, ho, area_exclusive FROM unit_master "
        "WHERE complex_id=? AND area_exclusive IS NOT NULL", (cid,)
    ).fetchall()
    # 동별로 그룹화
    dong_units: dict[str, list[dict]] = {}
    for dong, ho, area in rows:
        fl = int(ho.zfill(4)[:2]) if ho and ho.zfill(4)[:2].isdigit() else 0
        dong_units.setdefault(dong, []).append({"ho":ho,"area_exclusive":area,"dong":dong,"floor":fl})
    
    for dong, units in dong_units.items():
        if len(units) < 2: continue
        result = infer_floorplan(units)
        if result is None: continue
        for r in result:
            db.execute("INSERT INTO line_fact (complex_id,dong,line,direction,area_type,confidence) VALUES (?,?,?,?,?,?)",
                       (cid, dong, r["line"], r["direction"], r["area_type"], 0.8))
            total_lines += 1
    if (i+1) % 500 == 0:
        db.commit()
        elapsed = time.time()-t0
        rate = (i+1)/elapsed if elapsed else 0
        eta = (len(complexes)-i-1)/rate/60 if rate else 0
        print(f"  {i+1}/{len(complexes)} ({cid[:20]}) {total_lines} lines | {elapsed:.0f}s | ETA {eta:.0f}min", flush=True)

db.commit()
print(f"\nDone: {total_lines} rows in {time.time()-t0:.0f}s")
db.close()
