# -*- coding: utf-8 -*-
"""
지하철 역사심도 웹지도 데이터 빌드 스크립트
-------------------------------------------------
상위 폴더(서울경기/대구/대전/부산/인천/국토부)에 있는 공공데이터 CSV 중
'가장 최신 날짜' 파일을 자동으로 골라 웹지도용 data/*.js 를 다시 만듭니다.

새 자료로 갱신하는 방법
  1) 공공데이터포털에서 받은 새 CSV를 해당 지역 폴더(하위 폴더 포함)에 넣기
     (파일명 끝의 _YYYYMMDD 날짜로 최신본을 판단합니다)
  2) '데이터갱신.bat' 더블클릭
  3) data/build_report.txt 에서 매칭 실패 역 확인

옵션
  --refresh-osm   OpenStreetMap 노선 형상을 다시 내려받기
  --refresh-elev  DEM 표고 캐시를 지우고 다시 조회
"""
import csv, io, os, re, sys, json, glob, math, time, datetime, urllib.request, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(HERE, 'data')
RAW = os.path.join(DATA, 'raw')
os.makedirs(RAW, exist_ok=True)

REPORT = []
def log(*a):
    s = ' '.join(str(x) for x in a)
    print(s)
    REPORT.append(s)

# ---------------------------------------------------------------- 파일 탐색
def read_csv(path):
    raw = open(path, 'rb').read()
    for enc in ('utf-8-sig', 'cp949'):
        try:
            txt = raw.decode(enc)
            break
        except UnicodeDecodeError:
            pass
    rows = list(csv.DictReader(io.StringIO(txt)))
    return [{(k or '').strip().strip('"'): (v or '').strip() for k, v in r.items()} for r in rows]

def file_date(path):
    m = re.findall(r'(20\d{6})', os.path.basename(path))
    return m[-1] if m else datetime.datetime.fromtimestamp(os.path.getmtime(path)).strftime('%Y%m%d')

def latest(folder, *keywords, exclude=('편집',)):
    pat = os.path.join(glob.escape(os.path.join(ROOT, folder)), '**', '*.csv')
    cands = [p for p in glob.glob(pat, recursive=True)
             if all(k in os.path.basename(p) for k in keywords)
             and not any(x in os.path.basename(p) for x in exclude)]
    if not cands:
        log('  [없음]', folder, keywords)
        return None
    cands.sort(key=lambda p: (file_date(p), os.path.getmtime(p)))
    p = cands[-1]
    log('  사용:', os.path.relpath(p, ROOT), '(기준일', file_date(p) + ')')
    return p

# ---------------------------------------------------------------- 이름/숫자 정규화
def norm(name):
    s = re.sub(r'\(.*?\)', '', name or '')
    s = re.sub(r'[\s·\.\-]', '', s)
    if s.endswith('역') and len(s) > 2:
        s = s[:-1]
    return s

def num(v):
    try:
        v = str(v).replace(',', '').strip()
        return float(v) if v not in ('', '-') else None
    except ValueError:
        return None

# ---------------------------------------------------------------- 노선 정의
# key: 웹지도에서 쓰는 노선 키, name: 표시명, color, region
LINES = [
    ('S1', '1호선', '#0052A4', '수도권'), ('S2', '2호선', '#00A84D', '수도권'),
    ('S3', '3호선', '#EF7C1C', '수도권'), ('S4', '4호선', '#00A5DE', '수도권'),
    ('S5', '5호선', '#996CAC', '수도권'), ('S6', '6호선', '#CD7C2F', '수도권'),
    ('S7', '7호선', '#747F00', '수도권'), ('S8', '8호선', '#E6186C', '수도권'),
    ('S9', '9호선', '#BDB092', '수도권'), ('SBD', '수인분당선', '#F5A200', '수도권'),
    ('SSB', '신분당선', '#D4003B', '수도권'), ('SGJ', '경의중앙선', '#77C4A3', '수도권'),
    ('SGC', '경춘선', '#0C8E72', '수도권'), ('SGG', '경강선', '#0054A6', '수도권'),
    ('SSH', '서해선', '#8FC31F', '수도권'), ('SAR', '공항철도', '#0090D2', '수도권'),
    ('SUI', '우이신설선', '#B7C452', '수도권'), ('SSL', '신림선', '#6789CA', '수도권'),
    ('SEV', '에버라인', '#56AD2D', '수도권'), ('SGP', '김포골드라인', '#A17800', '수도권'),
    ('SUL', '의정부경전철', '#FDA600', '수도권'), ('SGA', 'GTX-A', '#9A6292', '수도권'),
    ('I1', '인천1호선', '#7CA8D5', '수도권'), ('I2', '인천2호선', '#ED8B00', '수도권'),
    ('IM', '인천공항자기부상', '#FFCD12', '수도권'),
    ('B1', '부산1호선', '#F06A00', '부산'), ('B2', '부산2호선', '#81BF48', '부산'),
    ('B3', '부산3호선', '#BB8C00', '부산'), ('B4', '부산4호선', '#217DCB', '부산'),
    ('BGL', '부산김해경전철', '#8652A1', '부산'), ('BDH', '동해선', '#0054A6', '부산'),
    ('D1', '대구1호선', '#D93F5C', '대구'), ('D2', '대구2호선', '#00AA80', '대구'),
    ('D3', '대구3호선', '#FFB100', '대구'), ('DGK', '대경선', '#0054A6', '대구'),
    ('J1', '대전1호선', '#007448', '대전'), ('G1', '광주1호선', '#009088', '광주'),
]
LINE_BY_KEY = {k: dict(key=k, name=n, color=c, region=r) for k, n, c, r in LINES}

def national_line_key(code, name, op):
    n = name.replace(' ', '')
    table = [
        ('경인선', 'S1'), ('경부선', 'S1'), ('경원선', 'S1'), ('장항선', 'S1'),
        ('안산과천선', 'S4'), ('진접선', 'S4'), ('일산선', 'S3'),
        ('분당선', 'SBD'), ('수인선', 'SBD'), ('신분당선', 'SSB'), ('경의중앙선', 'SGJ'),
        ('경춘선', 'SGC'), ('경강선', 'SGG'), ('서해선', 'SSH'), ('인천국제공항선', 'SAR'),
        ('신림선', 'SSL'), ('우이신설선', 'SUI'), ('에버라인', 'SEV'), ('김포도시철도', 'SGP'),
        ('의정부', 'SUL'), ('자기부상철도', 'IM'), ('인천지하철1호선', 'I1'), ('인천지하철2호선', 'I2'),
        ('부산도시철도1호선', 'B1'), ('부산도시철도2호선', 'B2'), ('부산도시철도3호선', 'B3'),
        ('부산경량도시철도4호선', 'B4'), ('부산김해경전철', 'BGL'), ('동해선', 'BDH'),
        ('대구도시철도1호선', 'D1'), ('대구도시철도2호선', 'D2'), ('대구도시철도3호선', 'D3'),
        ('대경선', 'DGK'), ('대전도시철도1호선', 'J1'), ('광주도시철도1호선', 'G1'),
        ('도시철도7호선', 'S7'), ('수도권광역철도8호선', 'S8'),
    ]
    for k, v in table:
        if n == k:
            return v
    if '신림선' in n:
        return 'SSL'
    if '9호선' in n:
        return 'S9'
    m = re.fullmatch(r'(\d)호선', n)
    if m:
        return 'S' + m.group(1)
    return None

# ---------------------------------------------------------------- 1. 전국 역 위치(국토부)
log('== 데이터 파일 선택 ==')
p_nat = latest('국토부', '전체_도시철도역사정보')
stations = []           # 최종 레코드
by_line_name = {}       # (lineKey, norm) -> record
nat_date = ''
for r in read_csv(p_nat):
    lk = national_line_key(r['노선번호'], r['노선명'], r['운영기관명'])
    if not lk:
        log('  [노선 미정의]', r['노선명'], r['역사명'])
        continue
    nm = r['역사명']
    short = re.sub(r'\(.*?\)', '', nm).strip()
    rec = dict(name=short, fullName=nm, line=lk, lineName=r['노선명'], op=r['운영기관명'],
               lat=num(r['역위도']), lon=num(r['역경도']),
               transfer=r['환승노선명'] or '', src=[], depth=None)
    nat_date = r.get('데이터기준일자', nat_date)
    key = (lk, norm(r['역사명']))
    if key in by_line_name:
        continue
    by_line_name[key] = rec
    stations.append(rec)
log('  전국 역사(노선별):', len(stations))

# 서울시 보조 좌표 (국토부 목록에 없는 신규역 보완용)
extra_xy = {}
for p in [latest('서울경기', '역사마스터'), latest('서울경기', '역사 좌표')]:
    if not p:
        continue
    for r in read_csv(p):
        lat, lon = num(r.get('위도')), num(r.get('경도'))
        if lat and lon:
            extra_xy.setdefault(norm(r.get('역사명') or r.get('역명')), (lat, lon))

# 기관 자료와 국토부 자료의 역명이 다른 경우(개칭·약칭·오타)
ALIAS = {'을지3가': '을지로3가', '을지4가': '을지로4가', '애오게': '애오개', '동대문운동장': '동대문역사문화공원',
         'DMC': '디지털미디어시티', '당고개': '불암산', '이수': '총신대입구', '뚝섬유원지': '자양',
         '성서산단': '성서산업단지', '시립미술관': '벡스코', '성당못': '서부정류장'}
# 괄호 안 부역명으로도 찾기 (예: '총신대입구(이수)')
by_sub = {}
for (k, n), v in list(by_line_name.items()):
    for sub in re.findall(r'\((.*?)\)', v['fullName']):
        for part in re.split(r'[·,]', sub):
            by_sub.setdefault((k, norm(part)), v)

def find(lk, name):
    n = norm(name)
    n = ALIAS.get(n, n)
    rec = by_line_name.get((lk, n)) or by_sub.get((lk, n)) or by_sub.get((lk, norm(name)))
    if rec:
        return rec
    # 부분일치 (예: '대구역' vs '대구')
    cands = [v for (k, nn), v in by_line_name.items() if k == lk and (nn.startswith(n) or n.startswith(nn)) and min(len(n), len(nn)) >= 2]
    return cands[0] if len(cands) == 1 else None

def attach(lk, name, order, info, srcname):
    rec = find(lk, name)
    if not rec:
        xy = extra_xy.get(norm(name))
        if not xy:
            log('  [매칭실패]', LINE_BY_KEY[lk]['name'], name)
            return None
        rec = dict(name=norm(name), fullName=name, line=lk, lineName=LINE_BY_KEY[lk]['name'], op='',
                   lat=xy[0], lon=xy[1], transfer='', src=[], depth=None)
        by_line_name[(lk, norm(name))] = rec
        stations.append(rec)
        log('  [보조좌표로 추가]', LINE_BY_KEY[lk]['name'], name)
        rec['xyNote'] = '서울시 역사마스터 좌표 사용(국토부 목록에 없음)'
    rec.update({k: v for k, v in info.items() if v is not None})
    rec['order'] = order
    rec['src'].append(srcname)
    return rec

# ---------------------------------------------------------------- 2. 서울교통공사 심도
p = latest('서울경기', '서울교통공사_역사심도정보')
if p:
    d = file_date(p)
    for i, r in enumerate(read_csv(p)):
        lk = 'S' + r['호선']
        g, rl = num(r['지반고']), num(r['레일면고'])
        dr, dp = num(r['선로기준정거장깊이']), num(r['정거장깊이'])
        attach(lk, r['역명'], i, dict(
            floors=r['층수'], form=r['형식'], groundEL=g, railEL=rl,
            depth=dr, depthPlatform=dp, depthDef='선로(레일면) 기준 정거장 깊이',
            groundH=round(g - 100, 2) if g is not None else None,
            railH=round(rl - 100, 2) if rl is not None else None,
            note=r['비고'], hSrc='서울교통공사 지반고(EL)−100', dataDate=d), f'서울교통공사 역사심도정보({d})')

p = latest('서울경기', '9호선 2_3단계')
if p:
    d = file_date(p)
    for i, r in enumerate(read_csv(p)):
        g, rl = num(r['지반고']), num(r['레일면고'])
        attach('S9', r['정거장명'], 100 + i, dict(
            floors=r['정거장층수'], form=r['형식'], groundEL=g, railEL=rl,
            depth=num(r['선로기준 정거장 깊이(m)']), depthPlatform=num(r['승강장기준 정거장 깊이(m)']),
            depthDef='선로(레일면) 기준 정거장 깊이',
            groundH=round(g - 100, 2) if g is not None else None,
            railH=round(rl - 100, 2) if rl is not None else None,
            note=r['비고'], hSrc='서울교통공사 지반고(EL)−100', dataDate=d), f'서울교통공사 9호선 2·3단계 심도({d})')

p = latest('서울경기', '역사건축정보')
if p:
    for r in read_csv(p):
        rec = find('S' + r['호선'], r['역명'])
        if rec:
            rec.update(platformLen=num(r['길이(M)']), area=num(r['면적(㎡)']), built=r['준공년도'])
            rec.setdefault('floors', r['층수']); rec.setdefault('form', r['형식'])

# ---------------------------------------------------------------- 3. 지방 심도
def generic(folder, kw, linemap, namecol, depthcol, defn, extra=None):
    p = latest(folder, *kw)
    if not p:
        return
    d = file_date(p)
    org = os.path.basename(p).split('_')[0]
    for i, r in enumerate(read_csv(p)):
        lk = linemap(r)
        if not lk:
            continue
        raw = r[depthcol]
        dv = num(raw)
        info = dict(depth=dv, depthDef=defn, dataDate=d)
        if extra:
            info.update(extra(r, dv))
        if dv == 0 or raw == '지상':
            info['depth'] = None
            info['note'] = '지상역(심도 자료 없음)'
        attach(lk, r[namecol], i, info, f'{org}({d})')

generic('대구', ('역사심도',), lambda r: 'D' + r['호선'], '역 명',
        [c for c in ['역사심도(지상-도상바닥)_(단위_미터)'] if c][0], '지상~도상바닥 깊이')
generic('대전', ('역사깊이',), lambda r: 'J1', '역사명', '심도(m)', '역사 심도')
generic('부산', ('역사 건축현황',), lambda r: 'B' + r['호선'], '역명', '역사심도', '역사 심도',
        lambda r, dv: dict(floors=r['층수'], form=r['역형식'], area=num(r['역사면적']), built=r['준공년도']))

def inc_line(r):
    return {'1': 'I1', '2': 'I2', '7': 'S7'}.get(r['호선'])
def inc_extra(r, dv):
    if '지상' in (r.get('비고') or '') and dv:
        return dict(depth=-dv, note='지상(고가)역 — 값은 지상 높이')
    return {}
p_inc = latest('인천', '역사심도및높이')
if p_inc:
    cols = list(read_csv(p_inc)[0].keys())
    generic('인천', ('역사심도및높이',), inc_line, '역 명', [c for c in cols if c.startswith('심도')][0],
            '역사 심도(지상역은 높이)', inc_extra)

# ---------------------------------------------------------------- 4. DEM 표고 (Open-Meteo, Copernicus 90m)
def apply_dem():
  cache_path = os.path.join(RAW, 'elev_cache.json')
  cache = {} if '--refresh-elev' in sys.argv or not os.path.exists(cache_path) else json.load(open(cache_path, encoding='utf-8'))
  need = [s for s in stations if s['lat'] and f"{s['lat']:.5f},{s['lon']:.5f}" not in cache]
  log('== DEM 표고 조회:', len(need), '개 (캐시', len(cache), ')')
  for i in range(0, len(need), 100):
    chunk = need[i:i + 100]
    q = urllib.parse.urlencode(dict(latitude=','.join(f"{s['lat']:.5f}" for s in chunk),
                                    longitude=','.join(f"{s['lon']:.5f}" for s in chunk)))
    el = None
    for attempt in range(5):
        try:
            with urllib.request.urlopen('https://api.open-meteo.com/v1/elevation?' + q, timeout=60) as resp:
                el = json.load(resp)['elevation']
            break
        except Exception as e:
            log('  [DEM 재시도]', attempt + 1, e)
            time.sleep(20 * (attempt + 1))
    if el is None:
        log('  [DEM 조회 중단] 다음 실행 때 이어서 조회합니다')
        break
    for s, e in zip(chunk, el):
        cache[f"{s['lat']:.5f},{s['lon']:.5f}"] = e
    json.dump(cache, open(cache_path, 'w', encoding='utf-8'))
    time.sleep(8)
  json.dump(cache, open(cache_path, 'w', encoding='utf-8'))
  for s in stations:
    s['demH'] = cache.get(f"{s['lat']:.5f},{s['lon']:.5f}") if s['lat'] else None
    if s.get('hSrc', '').startswith('DEM') or (s.get('groundH') is None and s['demH'] is not None):
        s['groundH'] = s['demH']
        s['hSrc'] = 'DEM(Copernicus 90m) 추정'
        if s.get('depth') is not None and s['demH'] is not None:
            s['railH'] = round(s['demH'] - s['depth'], 1)

# ---------------------------------------------------------------- 5. 노선 형상 (OpenStreetMap)
osm_path = os.path.join(RAW, 'osm_routes.json')
OSM_Q = ('[out:json][timeout:400][bbox:33.0,124.5,38.7,131.0];'
         '(rel["route"~"^(subway|light_rail|monorail)$"];rel["route"="train"]["network"~"전철|도시철도|광역"];);out geom;')
if '--no-osm' not in sys.argv and ('--refresh-osm' in sys.argv or not os.path.exists(osm_path)):
    for url in ['https://overpass-api.de/api/interpreter', 'https://overpass.kumi.systems/api/interpreter',
                'https://overpass.private.coffee/api/interpreter']:
        try:
            log('== OSM 노선 다운로드:', url)
            req = urllib.request.Request(url, data=urllib.parse.urlencode({'data': OSM_Q}).encode(),
                                         headers={'User-Agent': 'subway-depth-map/1.0'})
            body = urllib.request.urlopen(req, timeout=600).read()
            json.loads(body)
            open(osm_path, 'wb').write(body)
            break
        except Exception as e:
            log('  실패:', e)

def osm_line_key(t):
    net, ref, name = t.get('network', ''), t.get('ref', ''), t.get('name', '')
    nm = name.replace(' ', '')
    rules = [('공항철도', 'SAR'), ('경의', 'SGJ'), ('중앙선', 'SGJ'), ('경춘', 'SGC'), ('경강', 'SGG'),
             ('서해선', 'SSH'), ('수인', 'SBD'), ('분당선', 'SBD'), ('신분당', 'SSB'), ('우이신설', 'SUI'),
             ('신림', 'SSL'), ('에버라인', 'SEV'), ('용인경전철', 'SEV'), ('김포', 'SGP'), ('의정부', 'SUL'),
             ('GTX-A', 'SGA'), ('광역급행', 'SGA'), ('자기부상', 'IM'), ('김해', 'BGL'), ('동해선', 'BDH'),
             ('대경선', 'DGK'), ('대구권광역', 'DGK')]
    for k, v in rules:
        if k in nm and not (k == '분당선' and '신분당' in nm):
            return v
    if '인천' in net or '인천' in nm:
        if ref in ('I1', '인천1') or '1호선' in nm: return 'I1'
        if ref in ('I2', '인천2') or '2호선' in nm: return 'I2'
    if '부산' in net or '부산' in nm:
        m = re.search(r'(\d)', ref or nm); return ('B' + m.group(1)) if m else None
    if '대구' in net or '대구' in nm:
        m = re.search(r'(\d)', ref or nm); return ('D' + m.group(1)) if m else None
    if '대전' in net or '대전' in nm: return 'J1'
    if '광주' in net or '광주' in nm: return 'G1'
    if ref in list('123456789'): return 'S' + ref
    m = re.search(r'(\d)호선', nm)
    return ('S' + m.group(1)) if m else None

def simplify(pts, tol):
    if len(pts) < 3: return pts
    a, b = pts[0], pts[-1]
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy) or 1e-12
    idx, dmax = 0, 0
    for i in range(1, len(pts) - 1):
        d = abs(dy * (pts[i][0] - a[0]) - dx * (pts[i][1] - a[1])) / L
        if d > dmax: idx, dmax = i, d
    if dmax <= tol: return [a, b]
    return simplify(pts[:idx + 1], tol)[:-1] + simplify(pts[idx:], tol)

features = []
stops = {}
if os.path.exists(osm_path):
    osm = json.load(open(osm_path, encoding='utf-8'))
    ways = {}
    unknown = set()
    for el in osm.get('elements', []):
        if el.get('type') != 'relation': continue
        lk = osm_line_key(el.get('tags', {}))
        if lk not in LINE_BY_KEY:
            unknown.add(el.get('tags', {}).get('name', '?')); continue
        for m in el.get('members', []):
            if m['type'] == 'node' and m.get('role', '').startswith('stop') and 'lat' in m:
                stops.setdefault(lk, {})[m['ref']] = (m['lat'], m['lon'])
            if m['type'] == 'way' and m.get('role', '') in ('', 'route') and m.get('geometry'):
                ways.setdefault(lk, {})[m['ref']] = [(g['lon'], g['lat']) for g in m['geometry']]
    for u in sorted(unknown):
        log('  [OSM 노선 미분류]', u)
    for lk, wd in ways.items():
        segs = [[[round(x, 5), round(y, 5)] for x, y in simplify(c, 0.00004)] for c in wd.values()]
        L = LINE_BY_KEY[lk]
        features.append(dict(type='Feature', properties=dict(key=lk, name=L['name'], color=L['color']),
                             geometry=dict(type='MultiLineString', coordinates=segs)))
    log('== OSM 노선:', len(features), '개 노선')
# ---------------------------------------------------------------- 5-1. 좌표 이상치 점검/보정
def km(a, b):
    return math.hypot((a[0] - b[0]) * 111.0, (a[1] - b[1]) * 111.0 * math.cos(math.radians(a[0])))

fix_path = os.path.join(HERE, '좌표보정.csv')
if not os.path.exists(fix_path):
    open(fix_path, 'w', encoding='utf-8-sig').write('노선,역명,위도,경도,메모\n')
for r in read_csv(fix_path):
    lk = next((k for k, L in LINE_BY_KEY.items() if L['name'] == r['노선']), None)
    rec = find(lk, r['역명']) if lk else None
    if rec and num(r['위도']) and num(r['경도']):
        rec['lat'], rec['lon'] = num(r['위도']), num(r['경도'])
        rec['xyNote'] = '좌표보정.csv 수동 보정'
        log('  [수동 좌표보정]', r['노선'], r['역명'])

for lk in LINE_BY_KEY:
    pts = [s for s in stations if s['line'] == lk and s.get('lat')]
    for s in pts:
        others = [km((s['lat'], s['lon']), (o['lat'], o['lon'])) for o in pts if o is not s]
        if not others or min(others) < 8:
            continue
        # 같은 노선의 다른 역과 8km 이상 떨어짐 → 원본 좌표 오류로 판단
        cand = None
        if 'order' in s:
            nb = [o for o in pts if 'order' in o and abs(o['order'] - s['order']) == 1]
            if nb:
                mid = (sum(o['lat'] for o in nb) / len(nb), sum(o['lon'] for o in nb) / len(nb))
                used = [(o['lat'], o['lon']) for o in pts if o is not s]
                free = [p for p in stops.get(lk, {}).values() if min(km(p, u) for u in used) > 0.3]
                if free:
                    cand = min(free, key=lambda p: km(p, mid))
                    if km(cand, mid) > 3:
                        cand = None
        how = 'OSM 정차위치'
        if not cand:
            # 같은 이름의 다른 노선 역 / 서울시 역사마스터 좌표 중 이 노선 근처(8km 이내)인 것
            n = norm(s['fullName'])
            alts = [(o['lat'], o['lon'], f"{LINE_BY_KEY[o['line']]['name']} {o['name']} 좌표") for o in stations
                    if o is not s and o['line'] != lk and norm(o['fullName']) == n and o.get('lat')]
            if n in extra_xy:
                alts.append((*extra_xy[n], '서울시 역사마스터 좌표'))
            alts = [a for a in alts if min(km(a[:2], (o['lat'], o['lon'])) for o in pts if o is not s) < 8]
            if alts:
                cand, how = alts[0][:2], alts[0][2]
        if cand:
            log(f"  [좌표 자동보정] {LINE_BY_KEY[lk]['name']} {s['name']}: ({s['lat']},{s['lon']}) → {how} ({cand[0]:.6f},{cand[1]:.6f})")
            s['xyNote'] = f"국토부 원본 좌표 오류({s['lat']}, {s['lon']}) → {how}로 보정"
            s['lat'], s['lon'] = round(cand[0], 6), round(cand[1], 6)
        elif min(others) > 30:
            s['xyNote'] = f"좌표 확인 필요: 같은 노선 다른 역과 {min(others):.0f}km 떨어져 있음(국토부 원본). 좌표보정.csv로 고칠 수 있습니다."
            log(f"  [좌표 확인 필요] {LINE_BY_KEY[lk]['name']} {s['name']} ({s['lat']},{s['lon']}) 가장 가까운 같은 노선 역 {min(others):.1f}km")
        else:
            log(f"  [좌표 확인 필요] {LINE_BY_KEY[lk]['name']} {s['name']} ({s['lat']},{s['lon']}) 가장 가까운 같은 노선 역 {min(others):.1f}km")

apply_dem()

have = {f['properties']['key'] for f in features}
for lk, L in LINE_BY_KEY.items():
    if lk in have:
        continue
    pts = [s for s in stations if s['line'] == lk and s.get('lat')]
    if len(pts) < 2:
        continue
    # OSM 형상이 없는 노선: 역 순서(원본 자료) 또는 최근접 연결로 직선 표시
    if sum(1 for s in pts if 'order' in s) >= len(pts) * 0.8:
        chain = sorted([s for s in pts if 'order' in s], key=lambda s: s['order'])
        segs, cur = [], [chain[0]]
        for a in chain[1:]:
            b = cur[-1]
            if math.hypot(a['lat'] - b['lat'], (a['lon'] - b['lon']) * 0.8) > 0.03:  # 약 3km 이상 점프 = 지선 시작
                segs.append(cur); cur = [a]
            else:
                cur.append(a)
        segs.append(cur)
    else:
        left = pts[:]
        start = max(left, key=lambda s: math.hypot(s['lat'] - sum(p['lat'] for p in pts) / len(pts),
                                                   s['lon'] - sum(p['lon'] for p in pts) / len(pts)))
        cur = [start]; left.remove(start)
        while left:
            b = cur[-1]
            a = min(left, key=lambda s: math.hypot(s['lat'] - b['lat'], s['lon'] - b['lon']))
            cur.append(a); left.remove(a)
        segs = [cur]
    coords = [[[round(s['lon'], 5), round(s['lat'], 5)] for s in seg] for seg in segs if len(seg) > 1]
    if coords:
        features.append(dict(type='Feature', properties=dict(key=lk, name=L['name'], color=L['color'], approx=True),
                             geometry=dict(type='MultiLineString', coordinates=coords)))
        log('  [직선 대체]', L['name'])

# ---------------------------------------------------------------- 6. 출력
for s in stations:
    s['src'] = ' / '.join(s['src']) or f'국토교통부 전체 도시철도역사정보({nat_date})'
    for k in list(s):
        if s[k] in (None, ''): del s[k]
stations = [s for s in stations if s.get('lat')]
meta = dict(built=datetime.datetime.now().strftime('%Y-%m-%d %H:%M'), nationalDate=nat_date,
            count=len(stations), withDepth=sum(1 for s in stations if 'depth' in s))
with open(os.path.join(DATA, 'stations.js'), 'w', encoding='utf-8') as f:
    f.write('window.META=' + json.dumps(meta, ensure_ascii=False) + ';\n')
    f.write('window.LINES=' + json.dumps(list(LINE_BY_KEY.values()), ensure_ascii=False) + ';\n')
    f.write('window.STATIONS=' + json.dumps(stations, ensure_ascii=False, separators=(',', ':')) + ';\n')
with open(os.path.join(DATA, 'routes.js'), 'w', encoding='utf-8') as f:
    f.write('window.ROUTES=' + json.dumps(dict(type='FeatureCollection', features=features),
                                          ensure_ascii=False, separators=(',', ':')) + ';\n')
log('== 완료: 역', meta['count'], '/ 심도자료', meta['withDepth'])
open(os.path.join(DATA, 'build_report.txt'), 'w', encoding='utf-8').write('\n'.join(REPORT))
