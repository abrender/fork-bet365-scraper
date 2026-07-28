import re
import time
from datetime import datetime, timedelta
import pytz

from flask_cors import CORS
from flask import Flask, request, jsonify
app = Flask(__name__)


# languageId=1 → English (_1_3); others → _{languageId}_0 (e.g. 10 Chinese → _10_0)
DATA = {
    "_sports": {},
    "_by_oi": {},
    "_stats_by_oi": {},
}
SUFFIX = "_1_3"

# Soccer OVS1 / OVSF* tech stats (home,away). S0 may be absent in some packets.
SOCCER_STAT_FIELDS = {
    "S0": "Goal",
    "S1": "Corner",
    "S2": "YellowCard",
    "S3": "RedCard",
    "S4": "ThrowIn",
    "S5": "FreeKick",
    "S6": "GoalKick",
    "S7": "Penalty",
    "S8": "Substitution",
}


def empty_data_store():
    return {
        "_sports": {},
        "_by_oi": {},
        "_stats_by_oi": {},
    }


def apply_language_id(language_id):
    """Set SUFFIX from GamingContext.languageId; keep matching event buckets."""
    global DATA, SUFFIX
    try:
        lid = int(language_id)
    except (TypeError, ValueError):
        return
    # English ends with 3; all other languages end with 0
    tail = 3 if lid == 1 else 0
    new_suffix = f"_{lid}_{tail}"
    if new_suffix == SUFFIX:
        return
    old_data = DATA
    SUFFIX = new_suffix
    kept = empty_data_store()
    kept["_sports"] = old_data.get("_sports", {}) or {}
    kept["_stats_by_oi"] = old_data.get("_stats_by_oi", {}) or {}
    for key, val in old_data.items():
        if key in ("_sports", "_by_oi", "_stats_by_oi"):
            continue
        if isinstance(val, list) and key.endswith(f"A{SUFFIX}"):
            kept[key] = val
        elif isinstance(val, dict) and key.endswith(SUFFIX):
            kept[key] = val
            oi = val.get("OI")
            if oi:
                kept["_by_oi"][str(oi)] = key
    DATA = kept


def calculate_time_offset():
    """动态计算时差，冬令时为8小时，夏令时为7小时"""
    uk_tz = pytz.timezone("Europe/London")
    now = datetime.now(uk_tz)
    # 判断是否处于夏令时
    if now.dst() != timedelta(0):
        return 7 * 60 * 60  # 夏令时
    else:
        return 8 * 60 * 60  # 冬令时


def to_dit(txt):
    """
    Parse text data into dict format.
    将文本数据解析为字典格式。
    """
    dit = {}
    try:
        data = txt[:-1].split(';')
        for item in data:
            arr = item.split('=')
            if len(arr) > 1:
                dit[arr[0]] = arr[1]
    except Exception as e:
        print(f"Error in to_dit: {txt}")
    return dit


def parse_ev_it(it):
    """Return (sport_id, category_key) if IT is an in-play event for current SUFFIX."""
    if not it:
        return None, None
    m = re.search(rf"C(\d+)A{re.escape(SUFFIX)}$", it)
    if not m:
        return None, None
    sport_id = m.group(1)
    return sport_id, f"C{sport_id}A{SUFFIX}"


def ensure_category(category_key):
    if category_key not in DATA or not isinstance(DATA.get(category_key), list):
        DATA[category_key] = []
    return DATA[category_key]


def handle_insert(it, data_obj, category_key):
    """插入 EV 到分类列表，并登记 OI 索引。"""
    ensure_category(category_key)
    if "markets" not in data_obj or not isinstance(data_obj.get("markets"), list):
        data_obj["markets"] = []
    if it not in DATA[category_key]:
        DATA[category_key].append(it)
        print(f"insert {it}")
    if it not in DATA or not isinstance(DATA.get(it), dict):
        DATA[it] = data_obj
    else:
        # keep markets if re-insert
        markets = DATA[it].get("markets") if isinstance(DATA[it], dict) else None
        DATA[it].update(data_obj)
        if markets and not DATA[it].get("markets"):
            DATA[it]["markets"] = markets
    ev = DATA[it]
    # OVS1 uses fixture id (= OI / C3); index all known fixture keys
    for fid in (data_obj.get("OI"), data_obj.get("C3"), ev.get("OI"), ev.get("C3")):
        if fid:
            DATA.setdefault("_by_oi", {})[str(fid)] = it
    merge_pending_stats(ev, ev.get("OI") or data_obj.get("OI") or ev.get("C3") or data_obj.get("C3"))


def register_sport_from_cl(data_obj):
    sport_id = data_obj.get("CL") or data_obj.get("ID")
    if sport_id is None or sport_id == "":
        return
    sport_id = str(sport_id)
    sports = DATA.setdefault("_sports", {})
    sports[sport_id] = {
        "id": sport_id,
        "name": data_obj.get("NA") or sports.get(sport_id, {}).get("name") or "",
        "it": data_obj.get("IT") or sports.get(sport_id, {}).get("it") or "",
    }


def find_ev_by_oi(oi):
    if not oi:
        return None, None
    it = (DATA.get("_by_oi") or {}).get(str(oi))
    if it and isinstance(DATA.get(it), dict):
        return it, DATA[it]
    return None, None


def parse_home_away(val):
    """Parse 'home,away' (empty allowed) into {home, away} ints when possible."""
    if val is None or val == "":
        return {"home": None, "away": None}
    parts = str(val).split(",")
    home_raw = parts[0] if len(parts) > 0 else ""
    away_raw = parts[1] if len(parts) > 1 else ""

    def to_num(x):
        if x is None or x == "":
            return None
        try:
            return int(x)
        except ValueError:
            try:
                return float(x)
            except ValueError:
                return x

    return {"home": to_num(home_raw), "away": to_num(away_raw)}


def stats_from_dit(dit):
    stats = {}
    for sk, name in SOCCER_STAT_FIELDS.items():
        if sk in dit:
            stats[name] = parse_home_away(dit.get(sk))
    return stats


def ovsf_fixture_id(it_or_key, dit=None):
    """Resolve fixture OI from OVSF{id} IT / topic key / EV.ID."""
    text = str(it_or_key or "")
    m = re.search(r"OVSF(\d+)", text)
    if m:
        return m.group(1)
    if dit:
        it = dit.get("IT") or ""
        m = re.search(r"OVSF(\d+)", it)
        if m:
            return m.group(1)
        if dit.get("ID"):
            return str(dit.get("ID"))
    return None


def apply_soccer_stats(oi, dit, replace=False):
    """Store soccer stats by fixture id; attach to EV when present.

    `_stats_by_oi` is the source of truth and survives OVInPlay refreshes.
    """
    oi = str(oi or "")
    if not oi:
        return
    stats = stats_from_dit(dit)
    if not stats and not replace:
        return
    store = DATA.setdefault("_stats_by_oi", {})
    if replace:
        store[oi] = stats
    else:
        store.setdefault(oi, {}).update(stats)
    it, ev = find_ev_by_oi(oi)
    if ev is not None:
        ev["stats"] = dict(store[oi])
        DATA.setdefault("_by_oi", {})[oi] = it


def merge_pending_stats(ev, oi):
    """Copy durable stats onto a newly inserted / refreshed EV."""
    if not isinstance(ev, dict):
        return
    store = DATA.get("_stats_by_oi") or {}
    keys = []
    if oi:
        keys.append(str(oi))
    for k in (ev.get("OI"), ev.get("C3")):
        if k and str(k) not in keys:
            keys.append(str(k))
    merged = {}
    for k in keys:
        if k in store:
            merged.update(store[k])
    if merged:
        ev["stats"] = merged


def reattach_all_soccer_stats():
    """Re-bind durable stats onto current soccer EVs (after OVInPlay reset)."""
    store = DATA.get("_stats_by_oi") or {}
    if not store:
        return
    cat = f"C1A{SUFFIX}"
    for ev_it in (DATA.get(cat) or []):
        ev = DATA.get(ev_it)
        if not isinstance(ev, dict):
            continue
        merge_pending_stats(ev, ev.get("OI") or ev.get("C3"))


def init_ovs1(txt):
    """Full soccer tech-stats snapshot: OVS1 → EV;IT=OVSF{fixtureId};S1=h,a;..."""
    # Replace snapshot store, then clear EV.stats before re-apply
    DATA["_stats_by_oi"] = {}
    cat = f"C1A{SUFFIX}"
    for ev_it in (DATA.get(cat) or []):
        ev = DATA.get(ev_it)
        if isinstance(ev, dict):
            ev.pop("stats", None)
    for item in str(txt).split("|")[1:]:
        if not item or len(item) < 2:
            continue
        if item[:2] != "EV":
            continue
        dit = to_dit(item[3:] if len(item) > 3 else "")
        oi = ovsf_fixture_id(dit.get("IT"), dit)
        if oi:
            apply_soccer_stats(oi, dit, replace=True)


def attach_market(data_obj):
    oi = data_obj.get("FI")
    it, ev = find_ev_by_oi(oi)
    if not ev:
        return
    markets = ev.setdefault("markets", [])
    market = {
        "id": data_obj.get("ID") or data_obj.get("MA") or "",
        "ma": data_obj.get("MA") or data_obj.get("ID") or "",
        "name": data_obj.get("NA") or "",
        "it": data_obj.get("IT") or "",
        "su": data_obj.get("SU"),
        "odds": [],
    }
    markets.append(market)
    ev["_current_market_idx"] = len(markets) - 1


def attach_odds(data_obj):
    oi = data_obj.get("FI")
    it, ev = find_ev_by_oi(oi)
    if not ev:
        return
    markets = ev.get("markets") or []
    if not markets:
        return
    idx = ev.get("_current_market_idx")
    if idx is None or idx < 0 or idx >= len(markets):
        idx = len(markets) - 1
    markets[idx].setdefault("odds", []).append({
        "id": data_obj.get("ID") or "",
        "od": data_obj.get("OD") or "",
        "or": data_obj.get("OR"),
        "ha": data_obj.get("HA") or data_obj.get("HD") or "",
        "na": data_obj.get("NA") or "",
        "su": data_obj.get("SU"),
        "it": data_obj.get("IT") or "",
    })


def update_data(target_key, txt):
    """
    增量：U / I / D。EV 按 C{n}A{SUFFIX} 动态收录；I 也支持挂 MA/PA。
    """
    if "|" not in str(txt):
        return
    action_name, action_data = txt.split("|", 1)

    if action_name == "U":
        dit = to_dit(action_data)
        # Soccer tech stats: topic OVSF{fixtureId}
        oi = ovsf_fixture_id(target_key)
        if oi:
            apply_soccer_stats(oi, dit)
            return
        key = target_key
        if not (DATA.get(key) and isinstance(DATA.get(key), dict)):
            key = str(target_key).split("/")[-1]
        if isinstance(DATA.get(key), dict):
            # preserve markets / stats
            markets = DATA[key].get("markets")
            cur_idx = DATA[key].get("_current_market_idx")
            stats = DATA[key].get("stats")
            DATA[key].update(dit)
            if markets is not None and "markets" not in dit:
                DATA[key]["markets"] = markets
            if cur_idx is not None and "_current_market_idx" not in dit:
                DATA[key]["_current_market_idx"] = cur_idx
            if stats is not None and "stats" not in dit:
                DATA[key]["stats"] = stats
            oi = DATA[key].get("OI")
            if oi:
                DATA.setdefault("_by_oi", {})[str(oi)] = key

    elif action_name == "I":
        if len(action_data) < 2:
            return
        data_type = action_data[:2]
        dit = to_dit(action_data[3:] if len(action_data) > 3 else "")
        if data_type == "EV":
            it = dit.get("IT") or ""
            # Incremental soccer stats row
            oi = ovsf_fixture_id(it, dit)
            if oi and it.startswith("OVSF"):
                apply_soccer_stats(oi, dit, replace=True)
                return
            sport_id, category_key = parse_ev_it(it)
            if not it or not category_key:
                return
            dit["_sportId"] = sport_id
            handle_insert(it, dit, category_key)
        elif data_type == "CL":
            register_sport_from_cl(dit)
        elif data_type == "MA":
            attach_market(dit)
        elif data_type == "PA":
            attach_odds(dit)

    elif action_name == "D":
        it = str(target_key).split("/")[-1]
        sport_id, category_key = parse_ev_it(it)
        keys = []
        if category_key:
            keys.append(category_key)
        else:
            keys = [k for k, v in DATA.items() if isinstance(v, list) and k.startswith("C") and "A" in k]
        for key in keys:
            lst = DATA.get(key)
            if isinstance(lst, list) and it in lst:
                lst.remove(it)
        ev = DATA.get(it)
        if isinstance(ev, dict):
            oi = ev.get("OI")
            if oi and str(oi) in (DATA.get("_by_oi") or {}):
                del DATA["_by_oi"][str(oi)]
        if it in DATA:
            del DATA[it]


def init_data(txt):
    """
    全量快照：CL + 所有 C{n}A EV，并按流顺序挂 MA/PA。
    """
    lst = str(txt).split("|")[1:]
    current_ev_it = None

    for item in lst:
        if not item or len(item) < 2:
            continue
        data_type = item[:2]
        data_obj = to_dit(item[3:] if len(item) > 3 else "")

        if data_type == "CL":
            register_sport_from_cl(data_obj)
            continue

        it = data_obj.get("IT")
        if data_type == "EV":
            sport_id, category_key = parse_ev_it(it)
            if not it or not category_key:
                current_ev_it = None
                continue
            data_obj["_sportId"] = sport_id
            handle_insert(it, data_obj, category_key)
            current_ev_it = it
            continue

        if data_type == "MA":
            # Prefer FI→OI; fallback to current EV
            if data_obj.get("FI"):
                attach_market(data_obj)
            elif current_ev_it and isinstance(DATA.get(current_ev_it), dict):
                data_obj["FI"] = DATA[current_ev_it].get("OI")
                attach_market(data_obj)
            continue

        if data_type == "PA":
            if data_obj.get("FI"):
                attach_odds(data_obj)
            elif current_ev_it and isinstance(DATA.get(current_ev_it), dict):
                data_obj["FI"] = DATA[current_ev_it].get("OI")
                attach_odds(data_obj)
            continue


def data_parse(txt):
    """
    parses the data
    解析数据
    """
    if not txt or not txt.startswith(('\x15', '\x14')):
        return
    item_arr = txt.split('|\x08')
    for item in item_arr:
        item = item.strip()
        if not item:
            continue
        action_item = item[1:].split('\x01', 1)
        if len(action_item) < 2:
            continue
        action_key = action_item[0]
        action_val = action_item[1]

        if item.startswith('\x14OVInPlay_'):
            global DATA
            # Keep soccer stats across in-play full refresh
            preserved_stats = DATA.get("_stats_by_oi") or {}
            DATA = empty_data_store()
            DATA["_stats_by_oi"] = preserved_stats
            init_data(action_val)
            reattach_all_soccer_stats()
        elif item.startswith('\x14OVS1') or action_key.startswith('OVS1'):
            # Soccer tech-stats full snapshot (OVS1) or topic OVS1
            if item.startswith('\x14') or str(action_val).startswith('F|') or str(action_val).startswith('|'):
                init_ovs1(action_val)
            else:
                update_data(action_key, action_val)
        elif item.startswith('\x15'):
            update_data(action_key, action_val)


def _safe_int(val, default=0):
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def soccer_time_and_period(info):
    """原足球时间/阶段算法。"""
    TU = info.get("TU") or ""
    TT = _safe_int(info.get("TT"))
    TS = _safe_int(info.get("TS"))
    TM = _safe_int(info.get("TM"))
    MD = info.get("MD") or "0"
    league = info.get("CT") or ""

    if not TU:
        rel_time_set = f"{TM}:{str(TS).zfill(2)}"
    else:
        begin_ts = time.mktime(time.strptime(TU, "%Y%m%d%H%M%S"))
        now_ts = int(time.time()) - calculate_time_offset()
        if TM == 0 and TT == 0:
            rel_time_set = "00:00"
        else:
            if TT == 1:
                rel_time_set = str(int((now_ts - begin_ts) / 60.0) + TM) + \
                               ":" + str(int((now_ts - begin_ts) % 60.0)).zfill(2)
            else:
                rel_time_set = str(TM) + ":" + str(TS).zfill(2)

    if "Esoccer" in league and "mins play" in league:
        try:
            total_mins = int(league.split(" - ")[1].split(" ")[0])
        except Exception:
            total_mins = 90
    else:
        total_mins = 90

    if TM == total_mins / 2 and TS == 0 and TT == 0 and MD == "1":
        period = "HalfTime"
    elif TM == total_mins and TS == 0 and TT == 0 and MD == "1":
        period = "FullTime"
    elif TM == 0 and TS == 0 and TT == 0 and MD == "0":
        period = "ToStart"
    else:
        period = "FirstHalf" if MD == "0" else "SecondHalf"
    return rel_time_set, period


def basketball_time(info):
    """原篮球倒计时算法。"""
    TU = info.get("TU") or ""
    TT = _safe_int(info.get("TT"))
    TS = _safe_int(info.get("TS"))
    TM = _safe_int(info.get("TM"))
    try:
        begin_ts = int(time.mktime(time.strptime(TU, "%Y%m%d%H%M%S")))
        now_ts = int(time.time()) - calculate_time_offset()
        if TT == 1:
            if now_ts - begin_ts >= TS:
                return str(TM - 1).zfill(2) + ":" + str((60 + TS + begin_ts - now_ts)).zfill(2)
            return str(TM).zfill(2) + ":" + str((TS + begin_ts - now_ts)).zfill(2)
        return str(TM).zfill(2) + ":" + str(TS).zfill(2)
    except Exception:
        return str(TM).zfill(2) + ":" + str(TS).zfill(2)


def generic_time(info):
    TM = info.get("TM")
    TS = info.get("TS")
    if TM in (None, "") and TS in (None, ""):
        return ""
    try:
        return f"{int(TM)}:{str(int(TS)).zfill(2)}"
    except Exception:
        return f"{TM}:{TS}"


def format_live_event(ev_it, info, sport_id):
    """统一 /live 输出字段（兼容旧 id/event/league/time/score/period）。"""
    sports = DATA.get("_sports") or {}
    sport_meta = sports.get(str(sport_id), {})
    sport_name = sport_meta.get("name") or info.get("CL") or str(sport_id)

    period = info.get("CP") or ""
    rel_time = ""

    if str(sport_id) == "1":
        try:
            rel_time, period = soccer_time_and_period(info)
        except Exception as e:
            print(f"Error soccer time {ev_it}: {e}")
            rel_time = generic_time(info)
            period = period or info.get("MD") or ""
    elif str(sport_id) == "18":
        try:
            rel_time = basketball_time(info)
            period = info.get("CP") or period
        except Exception as e:
            print(f"Error basketball time {ev_it}: {e}")
            rel_time = generic_time(info)
    else:
        rel_time = generic_time(info)
        if not period:
            period = info.get("EX") or info.get("MD") or ""

    markets = []
    for m in (info.get("markets") or []):
        markets.append({
            "id": m.get("id"),
            "ma": m.get("ma"),
            "name": m.get("name"),
            "su": m.get("su"),
            "odds": m.get("odds") or [],
        })

    out = {
        "id": info.get("C2") or info.get("ID") or "",
        "fixtureId": info.get("OI") or "",
        "event": info.get("NA") or "",
        "shortName": info.get("N2") or info.get("N3") or "",
        "league": info.get("CT") or "",
        "sportId": str(sport_id),
        "sport": sport_name,
        "score": info.get("SS") or "",
        "period": period,
        "time": rel_time,
        "points": info.get("XP") or "",
        "phase": info.get("EX") or "",
        "serve": info.get("PI") or "",
        "markets": markets,
    }
    # Soccer: OVS1 tech stats (EV.stats, fallback durable store)
    if str(sport_id) == "1":
        out["stats"] = resolve_soccer_stats(info)
    return out


def resolve_soccer_stats(info):
    if not isinstance(info, dict):
        return {}
    if info.get("stats"):
        return info["stats"]
    store = DATA.get("_stats_by_oi") or {}
    for k in (info.get("OI"), info.get("C3")):
        if k and str(k) in store:
            return store[str(k)]
    return {}


def soccer_stats_list():
    """All soccer matches with stats only (for /soccer/stats)."""
    out = []
    category_key = f"C1A{SUFFIX}"
    for ev_it in (DATA.get(category_key) or []):
        info = DATA.get(ev_it)
        if not isinstance(info, dict):
            continue
        try:
            rel_time, period = soccer_time_and_period(info)
        except Exception:
            rel_time, period = generic_time(info), info.get("CP") or ""
        out.append({
            "fixtureId": info.get("OI") or info.get("C3") or "",
            "event": info.get("NA") or "",
            "league": info.get("CT") or "",
            "score": info.get("SS") or "",
            "time": rel_time,
            "period": period,
            "stats": resolve_soccer_stats(info),
        })
    return out


def live_events_for_sport(sport_id):
    category_key = f"C{sport_id}A{SUFFIX}"
    ev_lst = DATA.get(category_key) or []
    live_lst = []
    for ev_it in ev_lst:
        info = DATA.get(ev_it)
        if not isinstance(info, dict):
            continue
        try:
            live_lst.append(format_live_event(ev_it, info, sport_id))
        except Exception as e:
            print(f"Error parsing {ev_it} : {e}")
    return live_lst


def list_sport_ids():
    ids = set((DATA.get("_sports") or {}).keys())
    for key, val in DATA.items():
        if isinstance(val, list) and key.startswith("C") and f"A{SUFFIX}" in key:
            m = re.match(rf"C(\d+)A{re.escape(SUFFIX)}$", key)
            if m:
                ids.add(m.group(1))
    # numeric sort when possible
    def sort_key(x):
        try:
            return (0, int(x))
        except Exception:
            return (1, str(x))
    return sorted(ids, key=sort_key)


def soccer_data():
    return live_events_for_sport("1")


def basketball_data():
    return live_events_for_sport("18")


@app.route('/data', methods=['GET', 'POST'])
def handle_data():
    """
    Native data requests, including receiving POST data parsing and returning GET requests.
    原生数据请求，包括接收 POST 数据解析和返回 GET 请求。
    """
    if request.method == 'POST':
        data = request.json or {}
        try:
            apply_language_id(data.get("lang"))
            data_parse(data.get("data", ""))
        except Exception as e:
            print(f"Error parsing data: {e}")
        return "1"
    elif request.method == 'GET':
        return jsonify(DATA), 200


@app.route('/sports', methods=['GET'])
def sports_list():
    """当前已解析运动及场次数。"""
    sports = DATA.get("_sports") or {}
    out = []
    for sid in list_sport_ids():
        meta = sports.get(str(sid), {})
        cat = f"C{sid}A{SUFFIX}"
        out.append({
            "id": str(sid),
            "name": meta.get("name") or "",
            "count": len(DATA.get(cat) or []),
            "category": cat,
        })
    return jsonify(out), 200


@app.route('/live', methods=['GET'])
def live_event():
    """
    Visual and readable live data.
    可视易读的实时比赛列表数据.
    sport 缺省时返回全部运动。
    """
    sport = request.args.get("sport")
    if sport:
        live_lst = live_events_for_sport(str(sport))
    else:
        live_lst = []
        for sid in list_sport_ids():
            live_lst.extend(live_events_for_sport(sid))
    return jsonify(live_lst), 200


@app.route('/soccer/stats', methods=['GET'])
def soccer_stats_api():
    """仅返回所有足球比赛的技术统计（OVS1）。"""
    return jsonify(soccer_stats_list()), 200


if __name__ == '__main__':
    CORS(app)
    app.run(host='0.0.0.0', port=8485, threaded=True, debug=False)
