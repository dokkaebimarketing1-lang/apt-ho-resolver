"""호수 추론 시각화 — 확정·참고 분리 출력"""
import os, sys, webbrowser, sqlite3
from dotenv import load_dotenv
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv()

def query_db(complex_name: str, dong: str):
    db = sqlite3.connect(str(Path(__file__).parent.parent / "local.db"))
    lines = {}
    for r in db.execute("SELECT line,direction,area_type,confidence FROM line_fact WHERE complex_id=? AND dong=? ORDER BY line", (complex_name, dong)):
        lines[r[0]] = {"direction": r[1], "area_type": r[2], "confidence": r[3] or 0.8}
    units = db.execute("SELECT ho,floor,area_exclusive,area_type,public_price FROM unit_master WHERE complex_id=? AND dong=? ORDER BY ho", (complex_name, dong)).fetchall()
    db.close()
    return lines, units

def build_html(complex_name, dong, floor, area_type, direction, lines_info, units, coord):
    dir_map = {"남":"S","남동":"SE","남서":"SW","북":"N","북동":"NE","북서":"NW","동":"E","서":"W"}
    short_dir = dir_map.get(direction, direction)
    type_letter = "".join(c for c in area_type if c.isalpha())
    compat = {"S":("S","SE","SW"),"N":("N","NE","NW"),"E":("E","NE","SE"),"W":("W","NW","SW")}
    
    # 1. 면적 매칭되는 라인 찾기
    area_lines = {line: info for line, info in lines_info.items() 
                  if info["area_type"] == type_letter or info["area_type"] == area_type}
    
    # 2. 층 매칭 — 확정 후보
    confirmed = []
    for line, info in area_lines.items():
        ho_str = f"{floor:02d}{line}"
        for u in units:
            ho = u[0]
            ho_floor = int(ho[:2]) if len(ho)>=2 and ho[:2].isdigit() else 0
            if ho_floor == floor and ho == ho_str:
                # 방향 확인
                dir_ok = short_dir in compat.get(info["direction"], ())
                conf_tag = "✅확정" if info["confidence"] >= 1.0 else "⚠️추정"
                dir_tag = f"→{direction}일치" if dir_ok else f"→{direction}불일치"
                confirmed.append({
                    "ho": ho, "line": line, "dir": info["direction"],
                    "conf": conf_tag, "dir_ok": dir_ok, "dir_tag": dir_tag,
                    "area": u[2], "price": u[4]
                })
    
    # 태그
    tags = "".join(
        f'<span class="tag {"hl" if l in area_lines else ""}">{l}→{i["direction"]}({i["area_type"]})</span>'
        for l,i in lines_info.items()
    )
    
    # 확정 영역
    conf_rows = ""
    for c in confirmed:
        cls = "dir-ok" if c["dir_ok"] else "dir-no"
        conf_rows += f'<div class="cand-row {cls}"><span class="ho">{c["ho"]}호</span><span class="meta">라인{c["line"]} {c["conf"]} {c["dir_tag"]}</span></div>'
    if not conf_rows:
        conf_rows = '<div class="cand-row"><span class="ho">❌</span><span class="meta">면적 범위 내 {0}층 유닛 없음</span></div>'.format(floor)
    
    return f"""<!DOCTYPE html>
<html><head><meta charset=utf-8><title>호수 추론: {complex_name}</title>
<link rel=stylesheet href=https://unpkg.com/leaflet@1.9.4/dist/leaflet.css>
<script src=https://unpkg.com/leaflet@1.9.4/dist/leaflet.js></script>
<style>
*{{margin:0;padding:0}} body{{font-family:system-ui;display:flex;height:100vh}}
#map{{flex:1}}
#panel{{width:380px;background:#0d1117;color:#c9d1d9;padding:20px;overflow-y:auto;border-left:2px solid #e94560}}
h1{{font-size:18px;color:#e94560;margin-bottom:12px}}
h3{{color:#58a6ff;margin:15px 0 8px;font-size:14px}}
.tag{{display:inline-block;background:#21262d;padding:3px 8px;border-radius:10px;margin:3px;font-size:12px;border:1px solid #30363d}}
.tag.hl{{border:2px solid #e94560;background:rgba(233,69,96,0.15)}}
.info-row{{display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid rgba(48,54,61,0.5)}}
.info-row label{{color:#8b949e;font-size:12px}}
.info-row span{{font-weight:bold}}
.cand-row{{display:flex;justify-content:space-between;align-items:center;padding:10px 12px;margin:6px 0;border-radius:8px;background:#161b22;border:1px solid #30363d}}
.cand-row.dir-ok{{border-color:#2ea043;background:rgba(46,160,67,0.1)}}
.cand-row .ho{{font-size:20px;font-weight:bold;color:#e6edf3}}
.cand-row .meta{{font-size:12px;color:#8b949e}}
.cand-row.dir-ok .meta{{color:#7ee787}}
.badge{{display:inline-block;padding:2px 8px;border-radius:8px;font-size:11px;margin-left:6px}}
.badge.confirmed{{background:rgba(46,160,67,0.2);color:#7ee787}}
.badge.estimate{{background:rgba(210,168,255,0.2);color:#d2a8ff}}
.result-box{{background:#161b22;border:2px solid #e94560;border-radius:12px;padding:15px;margin:15px 0;text-align:center}}
.result-box .main{{font-size:36px;color:#e94560;font-weight:bold}}
.hint{{font-size:11px;color:#8b949e;margin-top:15px}}
</style></head>
<body>
<div id=map></div>
<div id=panel>
  <h1>🏢 {complex_name}</h1>
  <div class="info-row"><label>동</label><span>{dong}동</span></div>
  <div class="info-row"><label>층</label><span>{floor}층</span></div>
  <div class="info-row"><label>평형</label><span>{area_type}㎡</span></div>
  <div class="info-row"><label>향</label><span>{direction}</span></div>
  
  <h3>📐 라인-방향 매핑</h3>{tags}
  
  <h3>🎯 확정 후보 (면적+층)</h3>
  {conf_rows}
  
  <p class="hint">✅확정: 면적+층=100% 일치<br>⚠️추정: 방향은 매물데이터로 교정 필요</p>
</div>
<script>
var map = L.map('map').setView([{coord[1]}, {coord[0]}], 17);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',{{maxZoom:20}}).addTo(map);
L.marker([{coord[1]}, {coord[0]}]).addTo(map).bindPopup('{complex_name}<br>{dong}동');
</script></body></html>"""

if __name__ == "__main__":
    if len(sys.argv) < 6:
        print("사용: python scripts/view_ho.py <단지명> <동> <층> <평형> <향>")
        sys.exit(1)
    complex_name, dong = sys.argv[1], sys.argv[2]
    floor, area_type, direction = int(sys.argv[3]), sys.argv[4], sys.argv[5]
    lines, units = query_db(complex_name, dong)
    coord = (127.0212, 37.5016)
    html = build_html(complex_name, dong, floor, area_type, direction, lines, units, coord)
    path = str(Path(__file__).parent / "view_ho.html")
    with open(path, "w", encoding="utf-8") as f: f.write(html)
    print(f"✅ {path}"); webbrowser.open(f"file://{path}")
