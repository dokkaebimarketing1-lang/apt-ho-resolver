"""공시가격 12.4M → dong+area 필터 → 원베일리 추론 (최적화)"""
import json, sys, sqlite3, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.matcher import match_ho
from src.domain import HoConclusion
from src.kpi import compute_precision_at_1, compute_single_confirm_coverage, compute_multi_prob_rate

listings_raw = json.load(open("참고자료/데이터샘플/listings_원베일리_full.json", encoding="utf-8"))
ledger_raw = json.load(open("참고자료/데이터샘플/ledger_원베일리.json", encoding="utf-8"))
labels = []
for dn, floors in ledger_raw["ledger"].items():
    dn = "".join(c for c in dn if c.isdigit())
    for _fk, hl in floors.items():
        for e in hl: labels.append({"id":f"{dn}_{e['ho']}","dong":dn,"ho":e["ho"]})

db = sqlite3.connect("local.db")
db.execute("CREATE INDEX IF NOT EXISTS idx_pp_dong_area ON unit_master(dong, area_exclusive)")
print("Index ready, starting inference...", flush=True)

results, matched = [], 0
t0 = time.time()
for i, l in enumerate(listings_raw):
    dong = "".join(c for c in str(l.get("buildingName","")) if c.isdigit())
    area = int(float(l.get("area2",0))*100)
    fs = str(l.get("floorInfo",""))
    floor = int(fs.split("/")[-1].strip()) if "/" in fs else (int(fs) if fs.isdigit() else None)
    area_type = str(l.get("areaName",""))
    
    units = []
    for r in db.execute(
        "SELECT dong,ho,area_exclusive,public_price FROM unit_master WHERE dong=? AND area_exclusive BETWEEN ? AND ?",
        (dong, area-500, area+500)
    ):
        units.append({"dong":r[0],"ho":r[1],"area_exclusive":r[2],"public_price":r[3],
                      "complex_id":"","area_type":"","direction":"","canonical_ho_id":"","floor":None})
    
    cand = match_ho([], units, complex_id="", dong=dong, area_cm2=area,
                    area_type=area_type if area_type else None,
                    floor_min=floor, floor_max=floor)
    ho = cand[0]["ho"] if cand else None
    if ho: matched += 1
    results.append(HoConclusion(complex_id="wonbailly",dong=dong,candidate_hos=cand,ho_final=ho))
    if (i+1)%200==0: print(f"  {i+1}/{len(listings_raw)} matched={matched} ({time.time()-t0:.0f}s)", flush=True)

p1 = compute_precision_at_1(results, labels)
cov = compute_single_confirm_coverage(results)
mr = compute_multi_prob_rate(results)
print(f"\n  precision@1: {p1:.4f}  single: {cov:.4f}  multi: {mr:.4f}  matched: {matched}/{len(listings_raw)}")
db.close()
