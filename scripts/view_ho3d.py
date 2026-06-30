"""호수 추론 3D 시각화 — V-World WebGL 3D (진짜 건물)

사용: python scripts/view_ho3d.py "서초푸르지오써밋" 104 17 74B 남동향
"""
import os, sys, json, webbrowser, sqlite3
from dotenv import load_dotenv
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv()
KEY = os.environ.get("VWORLD_API_KEY", "")

def query_db(complex_name: str, dong: str):
    db = sqlite3.connect(str(Path(__file__).parent.parent / "local.db"))
    lines = {}
    for r in db.execute("SELECT line,direction,area_type FROM line_fact WHERE complex_id=? AND dong=? ORDER BY line", (complex_name, dong)):
        lines[r[0]] = {"direction": r[1], "area_type": r[2]}
    units = db.execute("SELECT ho,floor,area_type,public_price FROM unit_master WHERE complex_id=? AND dong=? ORDER BY ho", (complex_name, dong)).fetchall()
    db.close()
    return lines, units

def build_html(complex_name: str, dong: str, floor: int, area_type: str, direction: str,
               lines_info: dict, units: list, coord: tuple) -> str:
    target_line, target_ho, evidence = None, None, []
    dir_map = {"남":"S","남동":"SE","남서":"SW","북":"N","북동":"NE","북서":"NW","동":"E","서":"W"}
    short_dir = dir_map.get(direction, direction)
    type_letter = "".join(c for c in area_type if c.isalpha())
    
    for line, info in lines_info.items():
        if info["area_type"] == type_letter or info["area_type"] == area_type:
            if not target_line: target_line = line
            evidence.append(f"면적 {area_type}(타입{type_letter}) = 라인{line}")
    for line, info in lines_info.items():
        inferred = info["direction"]
        compat = {"S":("S","SE","SW"),"N":("N","NE","NW"),"E":("E","NE","SE"),"W":("W","NW","SW")}
        if short_dir in compat.get(inferred,()) and info["area_type"] == type_letter:
            target_line = line
            evidence.append(f"향 {direction}({short_dir}) in {inferred} = 라인{line}")
    if target_line:
        ho_str = f"{floor:02d}{target_line}"
        for u in units:
            if u[0] == ho_str:
                target_ho = u[0]
                evidence.append(f"{floor}층 = {target_ho}호")
                if u[3]: evidence.append(f"공시가격 {u[3]//10000:,}만원")
    
    evidence_html = "<br>".join(f"✅ {e}" for e in evidence) if evidence else "❌ 매칭 실패"
    result_html = f'<span style="font-size:48px;color:#e94560;font-weight:bold">{target_ho}호</span>' if target_ho else '<span style="font-size:48px;color:#888">❓</span>'
    
    tags = ""
    for line, info in lines_info.items():
        hl = "hl" if line == target_line else ""
        tags += f'<span class="tag {hl}">{line}→{info["direction"]}({info["area_type"]})</span>'
    
    return f"""<!DOCTYPE html>
<html lang=ko><head><meta charset=utf-8>
<title>3D 호수 추론: {complex_name} {dong}동</title>
<script src="https://map.vworld.kr/js/webglMapInit.js.do?version=3.0&apiKey={KEY}"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:system-ui;display:flex;height:100vh;background:#000;overflow:hidden}}
#vmap{{flex:1;min-width:0}}
#panel{{width:380px;background:rgba(13,17,23,0.95);color:#c9d1d9;padding:20px;overflow-y:auto;border-left:2px solid #e94560;z-index:10;backdrop-filter:blur(10px)}}
h1{{font-size:18px;color:#e94560;margin-bottom:12px}}
h3{{color:#58a6ff;margin:15px 0 8px;font-size:14px}}
.tag{{display:inline-block;background:rgba(33,38,45,0.8);padding:4px 10px;border-radius:12px;margin:4px;font-size:13px;border:1px solid #30363d}}
.tag.hl{{border:2px solid #e94560;background:rgba(233,69,96,0.2);color:#ff7b72;font-weight:bold}}
.info-row{{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid rgba(48,54,61,0.5)}}
.info-row label{{color:#8b949e;font-size:12px}}
.info-row span{{font-weight:bold}}
.result{{background:rgba(22,27,34,0.9);border:2px solid #e94560;border-radius:12px;padding:20px;margin:15px 0;text-align:center}}
.evidence{{font-size:13px;line-height:2;color:#7ee787}}
.hint{{font-size:11px;color:#8b949e;margin-top:20px}}
</style></head>
<body>
<div id="vmap"></div>
<div id="panel">
  <h1>🏢 {complex_name}</h1>
  <div class="info-row"><label>동</label><span>{dong}동</span></div>
  <div class="info-row"><label>층</label><span>{floor}층</span></div>
  <div class="info-row"><label>평형</label><span>{area_type}㎡</span></div>
  <div class="info-row"><label>향</label><span>{direction}</span></div>
  <h3>📐 라인-방향 매핑</h3>{tags}
  <div class="result"><label style=color:#8b949e>추론 호수</label><br>{result_html}</div>
  <h3>📋 추론 근거</h3>
  <div class="evidence">{evidence_html}</div>
  <p class="hint">🖱 드래그=회전 | 우클릭=이동 | 휠=줌 | Shift+드래그=기울기</p>
</div>
<script>
var options = {{
    mapId: "vmap",
    initPosition: new vw.CameraPosition(
        new vw.CoordZ({coord[0]}, {coord[1]}, 600),
        new vw.Direction(45, -40, 0)
    ),
    navigation: true,
    terrain: {{visible: true}},
    building: {{visible: true, lod: 2}},
    satellite: {{visible: false}}
}};
var map = new vw.Map();
map.setOption(options);
map.start();
</script></body></html>"""

if __name__ == "__main__":
    if len(sys.argv) < 6:
        print("사용: python scripts/view_ho3d.py <단지명> <동> <층> <평형> <향>")
        sys.exit(1)
    complex_name, dong = sys.argv[1], sys.argv[2]
    floor, area_type, direction = int(sys.argv[3]), sys.argv[4], sys.argv[5]
    print(f"🔍 {complex_name} {dong}동 {floor}층 {area_type}㎡ {direction}")
    lines, units = query_db(complex_name, dong)
    coord = (127.0212, 37.5016)  # 서초푸르지오써밋 고정 좌표 (지오코더 이미 확인됨)
    print(f"  DB: {len(lines)} lines, {len(units)} units | 좌표: {coord[0]:.4f}, {coord[1]:.4f}")
    html = build_html(complex_name, dong, floor, area_type, direction, lines, units, coord)
    path = str(Path(__file__).parent / "view_ho3d.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  ✅ {path}")
    webbrowser.open(f"file://{path}")
