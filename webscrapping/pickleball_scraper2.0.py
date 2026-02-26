# Now we will extract statistics from the downloaded match reports.
# One issue with this dataset is the raw HTML structure changes frequently.
# We can solve this by building a scraper that checks for clean data before falling back to table parsing.
# This gives us reliable metrics to predict match outcomes.

from pathlib import Path
from bs4 import BeautifulSoup
import csv
import re
import math
import json

# Set folder path
REPORTS_DIR = Path(r"D:\PickleballReports2")

# Limit match count
MAX_MATCHES = None

MATCH_ID_RE = re.compile(r'(?i)\bM(\d+)\b')
DEF_RE = re.compile(r'^\s*(.*?)\s+(?:def\.|defeated|beat|d\.)\s+(.*?)\s*$', re.I)
VS_RE  = re.compile(r'^\s*(.*?)\s+(?:vs\.?|v\.?)\s+(.*?)\s*$', re.I)
SCORE_PAIR_RE = re.compile(r'(\d+)\s*[-–]\s*(\d+)')
TOTAL_RALLIES_RE = re.compile(r"Total Rallies\s*:\s*(\d+)", re.I)
AVG_SHOTS_RE = re.compile(r"\(([\d\.]+)\s*shots per rally\)", re.I)
RALLIES_WON_RE = re.compile(r"(.*?)\s+won\s+(\d+)\s+rallies\s*\(([\d\.]+)%\)", re.I)

def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="ignore")

def split_players(team_text: str) -> list[str]:
    return [x.strip() for x in team_text.split("&", 1)] if "&" in team_text else [team_text.strip(), ""]

def parse_header_lines(text: str):
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    idx = -1
    team_a_text = team_b_text = ""
    winning_team = None
    for i, ln in enumerate(lines):
        m = DEF_RE.match(ln)
        if m:
            team_a_text, team_b_text = m.group(1), m.group(2)
            winning_team = "TeamA"
            idx = i
            break
        m2 = VS_RE.match(ln)
        if m2:
            team_a_text, team_b_text = m2.group(1), m2.group(2)
            winning_team = None
            idx = i
            break
    match_name = lines[idx - 1] if idx > 0 else (lines[0] if lines else "")
    return match_name, team_a_text, team_b_text, winning_team

def parse_scores(text: str):
    paren_blocks = re.findall(r"\(([^)]*)\)", text)
    candidates = paren_blocks if paren_blocks else [text]
    for block in candidates:
        m = SCORE_PAIR_RE.search(block)
        if m:
            return int(m.group(1)), int(m.group(2))
    return None, None

def as_percent_0_100(x):
    if x is None:
        return None
    try:
        x = float(x)
    except Exception:
        return None
    return x * 100.0 if x <= 1.0 else x

# Parse rally lengths
def parse_rally_section(soup: BeautifulSoup, team_a_text: str, team_b_text: str):
    sec = soup.find(id="rally-lengths")
    if not sec:
        h3 = soup.find(lambda t: t.name in ("h2", "h3") and "rally lengths" in t.get_text(strip=True).lower())
        sec = h3.find_parent() if h3 else None

    out = {
        "TotalRallies": None,
        "AvgShotsPerRally": None,
        "TeamARalliesWon": None,
        "TeamBRalliesWon": None,
        "RallyPct_2ShotsOrLess": None,
        "RallyPct_3to5Shots": None,
        "RallyPct_6to12Shots": None,
        "RallyPct_13PlusShots": None,
    }
    if not sec:
        return out

    p_texts = [p.get_text(" ", strip=True) for p in sec.find_all("p")]
    joined = "\n".join(p_texts)
    m_tr = TOTAL_RALLIES_RE.search(joined)
    if m_tr:
        out["TotalRallies"] = int(m_tr.group(1))
    m_avg = AVG_SHOTS_RE.search(joined)
    if m_avg:
        try:
            out["AvgShotsPerRally"] = float(m_avg.group(1))
        except Exception:
            pass

    li_texts = [li.get_text(" ", strip=True) for li in sec.find_all("li")]
    a_won = b_won = None
    for t in li_texts:
        m = RALLIES_WON_RE.search(t)
        if not m:
            continue
        name, cnt = m.group(1).strip(), int(m.group(2))
        if team_a_text and team_a_text.lower() in name.lower():
            a_won = cnt
        elif team_b_text and team_b_text.lower() in name.lower():
            b_won = cnt
    if a_won is None or b_won is None:
        counts = []
        for t in li_texts:
            m = RALLIES_WON_RE.search(t)
            if m:
                counts.append(int(m.group(2)))
        if len(counts) >= 2:
            a_won = counts[0] if a_won is None else a_won
            b_won = counts[1] if b_won is None else b_won
    out["TeamARalliesWon"] = a_won
    out["TeamBRalliesWon"] = b_won

    bucket_vals = None
    for sc in sec.find_all("script", {"type": "application/json"}):
        try:
            data = json.loads(sc.string)
            d = data.get("x", {}).get("tag", {}).get("attribs", {}).get("data")
            if isinstance(d, dict) and all(k in d for k in ["<2_pct","3-5_pct","6-12_pct","13+_pct"]):
                bucket_vals = {
                    "RallyPct_2ShotsOrLess": as_percent_0_100(d["<2_pct"][0]),
                    "RallyPct_3to5Shots":     as_percent_0_100(d["3-5_pct"][0]),
                    "RallyPct_6to12Shots":    as_percent_0_100(d["6-12_pct"][0]),
                    "RallyPct_13PlusShots":   as_percent_0_100(d["13+_pct"][0]),
                }
                break
        except Exception:
            continue
    if bucket_vals is None:
        cells = [c.get_text(strip=True) for c in sec.select(".rt-td .rt-td-inner, .rt-td-inner")]
        perc = []
        for c in cells:
            m = re.search(r"([\d\.]+)\s*%", c)
            if m:
                perc.append(float(m.group(1)))
        if len(perc) >= 4:
            bucket_vals = {
                "RallyPct_2ShotsOrLess": perc[0],
                "RallyPct_3to5Shots":    perc[1],
                "RallyPct_6to12Shots":   perc[2],
                "RallyPct_13PlusShots":  perc[3],
            }
    if bucket_vals:
        out.update(bucket_vals)
    return out

# Parse shot counts
def norm_name(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())

def safe_int(s):
    if s is None:
        return None
    m = re.search(r"-?\d+", str(s).replace(",", ""))
    return int(m.group(0)) if m else None

def parse_shot_counts(soup: BeautifulSoup, team_a_text: str, team_b_text: str, a1: str, a2: str, b1: str, b2: str):
    # Define target keywords
    target_cols = {
        "team": ["team"],
        "player": ["player"],
        "unreturned": ["unreturned"],
        "assists": ["assist"],
        "errors": ["error"],
        "shots": ["shot", "total"]
    }

    tables = soup.select(".Reactable .rt-table")
    chosen = None
    col_idx = {}

    # Normalize header text
    def normalize(text):
        return re.sub(r"[^a-z]", "", text.lower())

    # Find matching table
    for t in tables:
        headers = [h.get_text(strip=True) for h in t.select(".rt-thead .rt-tr-header .rt-th .rt-text-content")]
        if not headers: continue
        
        tmp_idx = {}
        for i, h in enumerate(headers):
            h_clean = normalize(h)
            
            # Match keywords to headers
            for standard_key, substrings in target_cols.items():
                if any(sub in h_clean for sub in substrings):
                    tmp_idx[standard_key] = i
        
        # Verify valid table
        if "team" in tmp_idx and "player" in tmp_idx and "shots" in tmp_idx:
            chosen = t
            col_idx = tmp_idx
            break

    if chosen is None:
        return {}, {}

    # Extract table data
    body_rows = chosen.select(".rt-tbody .rt-tr")
    team_totals_raw = {}
    player_rows = {}

    for r in body_rows:
        cells = [c.get_text(strip=True) for c in r.select(".rt-td")]
        
        def get_val(key):
            idx = col_idx.get(key)
            if idx is not None and idx < len(cells):
                return safe_int(cells[idx])
            return None

        team_txt = cells[col_idx["team"]] if "team" in col_idx and col_idx["team"] < len(cells) else ""
        player_txt = cells[col_idx["player"]] if "player" in col_idx and col_idx["player"] < len(cells) else ""
        
        row_vals = {
            "unreturned": get_val("unreturned"),
            "assists":    get_val("assists"),
            "errors":     get_val("errors"),
            "shots":      get_val("shots"),
        }

        # Separate team and player rows
        if team_txt and not player_txt:
            team_totals_raw[team_txt] = row_vals
        elif player_txt:
            if player_txt not in player_rows:
                # Initialize missing values
                player_rows[player_txt] = {"unreturned": 0, "assists": 0, "errors": 0, "shots": 0}
            # Handle duplicate rows
            for k, v in row_vals.items():
                if v is not None:
                    player_rows[player_txt][k] += v

    # Format output
    out_team = {
        "TeamA_Unreturned": None, "TeamA_Assists": None, "TeamA_Errors": None, "TeamA_TotalShots": None,
        "TeamB_Unreturned": None, "TeamB_Assists": None, "TeamB_Errors": None, "TeamB_TotalShots": None,
    }

    # Assign team totals
    def assign_team_totals(team_label, dest_prefix):
        vals = team_totals_raw.get(team_label)
        if not vals: return False
        out_team[f"{dest_prefix}_Unreturned"] = vals["unreturned"]
        out_team[f"{dest_prefix}_Assists"]    = vals["assists"]
        out_team[f"{dest_prefix}_Errors"]     = vals["errors"]
        out_team[f"{dest_prefix}_TotalShots"] = vals["shots"]
        return True

    # Match team names
    matched_a = assign_team_totals(team_a_text, "TeamA")
    matched_b = assign_team_totals(team_b_text, "TeamB")

    # Calculate missing team totals
    player_to_team = {norm_name(a1): "TeamA", norm_name(a2): "TeamA", norm_name(b1): "TeamB", norm_name(b2): "TeamB"}
    
    if not matched_a or not matched_b:
        sums = {"TeamA": {"unreturned": 0, "assists": 0, "errors": 0, "shots": 0},
                "TeamB": {"unreturned": 0, "assists": 0, "errors": 0, "shots": 0}}
        
        for pname, stats in player_rows.items():
            tk = player_to_team.get(norm_name(pname))
            if tk:
                for k in sums[tk]:
                    if stats.get(k): sums[tk][k] += stats[k]

        if not matched_a:
            out_team["TeamA_Unreturned"] = sums["TeamA"]["unreturned"]
            out_team["TeamA_Assists"]    = sums["TeamA"]["assists"]
            out_team["TeamA_Errors"]     = sums["TeamA"]["errors"]
            out_team["TeamA_TotalShots"] = sums["TeamA"]["shots"]
        if not matched_b:
            out_team["TeamB_Unreturned"] = sums["TeamB"]["unreturned"]
            out_team["TeamB_Assists"]    = sums["TeamB"]["assists"]
            out_team["TeamB_Errors"]     = sums["TeamB"]["errors"]
            out_team["TeamB_TotalShots"] = sums["TeamB"]["shots"]

    # Map players
    def pluck(name):
        # Try exact match
        stats = player_rows.get(name) 
        if not stats:
            # Try fuzzy match
            n = norm_name(name)
            for k, v in player_rows.items():
                if norm_name(k) in n:
                    stats = v
                    break
        if not stats:
            return {"unreturned": None, "assists": None, "errors": None, "shots": None}
        return stats

    p1 = pluck(a1); p2 = pluck(a2); p3 = pluck(b1); p4 = pluck(b2)
    
    out_players = {
        "Player1_Unreturned": p1["unreturned"], "Player1_Assists": p1["assists"], "Player1_Errors": p1["errors"], "Player1_TotalShots": p1["shots"],
        "Player2_Unreturned": p2["unreturned"], "Player2_Assists": p2["assists"], "Player2_Errors": p2["errors"], "Player2_TotalShots": p2["shots"],
        "Player3_Unreturned": p3["unreturned"], "Player3_Assists": p3["assists"], "Player3_Errors": p3["errors"], "Player3_TotalShots": p3["shots"],
        "Player4_Unreturned": p4["unreturned"], "Player4_Assists": p4["assists"], "Player4_Errors": p4["errors"], "Player4_TotalShots": p4["shots"],
    }
    
    return out_team, out_players

# Parse shot frequencies
SHOTTYPE_CANON = {
    "transition zone": "TransitionZone",
    "dink": "Dink",
    "serve": "Serve",
    "return": "Return",
    "hand battle": "HandBattle",
    "3rd shot drop": "3rdShotDrop",
    "third shot drop": "3rdShotDrop",
    "3rd shot drive": "3rdShotDrive",
    "third shot drive": "3rdShotDrive",
    "lob": "Lob",
    "speed up": "SpeedUp",
    "reset": "Reset",
}
def canon_shottype(name: str) -> str | None:
    return SHOTTYPE_CANON.get((name or "").strip().lower())

def init_shottype_out():
    keys = ["TransitionZone","Dink","Serve","Return","HandBattle","3rdShotDrop","3rdShotDrive","Lob","SpeedUp","Reset"]
    out = {}
    for k in keys:
        out[f"ShotType_{k}_Freq"] = 0
        out[f"ShotType_{k}_Err%"] = 0.0
    return out

def parse_shot_type_frequencies(soup: BeautifulSoup):
    sec = soup.find(id="shot-type-frequencies")
    if not sec:
        h3 = soup.find(lambda t: t.name in ("h2", "h3") and "shot type frequencies" in t.get_text(strip=True).lower())
        sec = h3.find_parent() if h3 else None

    # Initialize default values
    out = init_shottype_out()
    if not sec:
        return out

    # Extract JSON data
    for sc in sec.find_all("script", {"type": "application/json"}):
        try:
            data = json.loads(sc.string)
            d = data.get("x", {}).get("tag", {}).get("attribs", {}).get("data")
            if isinstance(d, dict) and all(k in d for k in ["shot_type","cnt","unforced_pct"]):
                for name, cnt, err in zip(d["shot_type"], d["cnt"], d["unforced_pct"]):
                    ck = canon_shottype(name)
                    if not ck:
                        continue
                    # Handle missing counts
                    out[f"ShotType_{ck}_Freq"] = int(cnt) if cnt is not None else 0
                    # Handle missing percentages
                    val = as_percent_0_100(err)
                    out[f"ShotType_{ck}_Err%"] = val if val is not None else 0.0
                return out
        except Exception:
            continue

    header_map = {"shot type": "name", "frequency": "freq", "error %": "err"}
    table = sec.select_one(".Reactable .rt-table")
    if not table:
        return out
    heads = [h.get_text(strip=True).lower() for h in table.select(".rt-thead .rt-tr-header .rt-th .rt-text-content")]
    idx = {}
    for i, h in enumerate(heads):
        key = header_map.get(h)
        if key:
            idx[key] = i
    if not {"name","freq","err"}.issubset(idx.keys()):
        return out

    for row in table.select(".rt-tbody .rt-tr"):
        cells = [c.get_text(strip=True) for c in row.select(".rt-td")]
        if not cells:
            continue
        name = cells[idx["name"]] if idx["name"] < len(cells) else ""
        ck = canon_shottype(name)
        if not ck:
            continue
            
        freq_txt = cells[idx["freq"]] if idx["freq"] < len(cells) else ""
        err_txt  = cells[idx["err"]]  if idx["err"]  < len(cells) else ""
        
        # Set defaults on failure
        freq = safe_int(freq_txt)
        out[f"ShotType_{ck}_Freq"] = freq if freq is not None else 0
        
        m = re.search(r"([\d\.]+)\s*%", err_txt)
        err = float(m.group(1)) if m else 0.0
        out[f"ShotType_{ck}_Err%"] = err
        
    return out

# Parse third shot performance
def parse_third_shot_performance_agg(soup: BeautifulSoup, a1: str, a2: str, b1: str, b2: str):
    sec = soup.find(id="third-shot-performance")
    if not sec:
        h3 = soup.find(lambda t: t.name in ("h2","h3") and "third shot performance" in t.get_text(strip=True).lower())
        sec = h3.find_parent() if h3 else None

    players = [a1, a2, b1, b2]
    out = {}
    for i in range(4):
        out[f"Player{i+1}_3rdShot_Err%"] = None
        out[f"Player{i+1}_3rdShot_Win%"] = None
        out[f"Player{i+1}_3rdShot_OppError%"] = None
        out[f"Player{i+1}_3rdShot_LedToDinks%"] = None
    if not sec:
        return out

    rows_by_player = {norm_name(p): [] for p in players if p}

    # Extract JSON data
    used_json = False
    for sc in sec.find_all("script", {"type": "application/json"}):
        try:
            data = json.loads(sc.string)
            d = data.get("x", {}).get("tag", {}).get("attribs", {}).get("data")
            needed = ["player_nm","ts_type","cnt","error_pct","win_rally_pct","opp_fourth_error_pct","led_to_dinks_pct"]
            if isinstance(d, dict) and all(k in d for k in needed):
                for nm, cnt, err, win, opp, dinks in zip(
                    d["player_nm"], d["cnt"], d["error_pct"], d["win_rally_pct"], d["opp_fourth_error_pct"], d["led_to_dinks_pct"]
                ):
                    key = norm_name(nm)
                    if key in rows_by_player:
                        rows_by_player[key].append({
                            "cnt": int(cnt) if cnt is not None else 0,
                            "err": as_percent_0_100(err),
                            "win": as_percent_0_100(win),
                            "opp": as_percent_0_100(opp),
                            "dinks": as_percent_0_100(dinks),
                        })
                used_json = True
                break
        except Exception:
            continue

    # Extract HTML data
    if not used_json:
        header_map = {
            "player": "player", "shot": "shot", "frequency": "freq",
            "error %": "err", "win %": "win",
            "opp 4th error %": "opp", "led to dinks %": "dinks"
        }
        table = sec.select_one(".Reactable .rt-table")
        if table:
            heads = [h.get_text(strip=True).lower() for h in table.select(".rt-thead .rt-tr-header .rt-th .rt-text-content")]
            idx = {}
            for i, h in enumerate(heads):
                key = header_map.get(h)
                if key:
                    idx[key] = i
            for row in table.select(".rt-tbody .rt-tr"):
                cells = [c.get_text(" ", strip=True) for c in row.select(".rt-td")]
                if not cells or not {"player","freq"}.issubset(idx.keys()):
                    continue
                nm = cells[idx["player"]] if idx["player"] < len(cells) else ""
                key = norm_name(nm)
                if key not in rows_by_player:
                    continue
                cnt = safe_int(cells[idx["freq"]]) if idx["freq"] < len(cells) else 0
                def pick_pct(label):
                    if label not in idx or idx[label] >= len(cells):
                        return None
                    m = re.search(r"([\d\.]+)\s*%", cells[idx[label]])
                    return float(m.group(1)) if m else None
                rows_by_player[key].append({
                    "cnt": cnt or 0,
                    "err": pick_pct("err"),
                    "win": pick_pct("win"),
                    "opp": pick_pct("opp"),
                    "dinks": pick_pct("dinks"),
                })

    def wavg(items, key):
        vals = [(it[key], it["cnt"]) for it in items if it.get(key) is not None and it.get("cnt", 0) > 0]
        if not vals:
            return None
        num = sum(v * c for v, c in vals)
        den = sum(c for _, c in vals)
        return num / den if den else None

    # Format output
    for idx_p, pname in enumerate(players, start=1):
        key = norm_name(pname)
        items = rows_by_player.get(key, [])
        out[f"Player{idx_p}_3rdShot_Err%"] = wavg(items, "err")
        out[f"Player{idx_p}_3rdShot_Win%"] = wavg(items, "win")
        out[f"Player{idx_p}_3rdShot_OppError%"] = wavg(items, "opp")
        out[f"Player{idx_p}_3rdShot_LedToDinks%"] = wavg(items, "dinks")

    return out

# Parse dinking performance
def _norm_token(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())

def find_dink_anchor(soup: BeautifulSoup):
    # Now we will locate the anchor for the dinking section.
    # One issue with this dataset is the section names change often.
    # We solve this by matching exact keywords and variants.
    # This guarantees we target the correct metrics table.
    candidates = {
        "dink_performance", "dinking_performance",
        "dink performance", "dinking performance",
        "dinkperformance", "dinkingperformance",
    }
    # Match exact tokens
    for attr in ("name", "data-unique"):
        for div in soup.find_all("div", attrs={attr: True}):
            val = _norm_token(div.get(attr))
            if val in candidates:
                return div
    # Match combined words
    for attr in ("name", "data-unique"):
        for div in soup.find_all("div", attrs={attr: True}):
            v = (div.get(attr) or "").lower()
            if "dink" in v and "performance" in v:
                return div
    # Check heading
    hdr = soup.find(lambda t: t.name in ("h2","h3")
                    and "dink" in t.get_text(strip=True).lower()
                    and "performance" in t.get_text(strip=True).lower())
    return hdr 

def _header_key(raw: str) -> str | None:
    # Next let us normalize the header text.
    # The problem is that columns have different names across files.
    # We correct this by mapping them to standard dictionary keys.
    # This standardizes the column structure for modeling.
    s = (raw or "").strip().lower()
    s_norm = _norm_token(s)

    if "team" in s:
        return "team"
    if "player" in s:
        return "player"

    has_dink   = "dink" in s
    has_error  = "error" in s
    has_pct    = "%" in s or "percent" in s or "per" == s_norm[-3:] 

    # Check for dinks
    if has_dink and not has_error and not has_pct:
        return "dinks"

    # Check for errors
    if has_error and not has_pct:
        return "errors"

    # Check for error percentage
    if has_error and has_pct:
        return "err_pct"

    # Handle frequency column
    if "frequency" in s:
        return "dinks"

    return None

def _pick_pct(txt: str) -> float | None:
    m = re.search(r"([\d\.]+)\s*%", txt or "")
    return float(m.group(1)) if m else None

def parse_dinking_performance(soup: BeautifulSoup, a1: str, a2: str, b1: str, b2: str):
    players = [a1, a2, b1, b2]

    # Initialize outputs
    out = {}
    for i in range(1, 5):
        out[f"Player{i}_Dinks"] = None
        out[f"Player{i}_DinkErrors"] = None
        out[f"Player{i}_DinkError%"] = None

    # Find section anchor
    anchor = find_dink_anchor(soup)
    if not anchor:
        return out

    # Find react table
    table = None
    for el in anchor.find_all_next(True):
        # Stop at new section
        if el is not anchor and el.get("name") and "performance" in (el.get("name") or "").lower() and "dink" not in (el.get("name") or "").lower():
            break
        # Locate table class
        cls = el.get("class", [])
        if any("rt-table" == c or c.endswith("rt-table") for c in cls):
            table = el
            break
    if not table:
        # Use broader search
        table = anchor.find_next("div", class_=re.compile(r"\brt-table\b"))
    if not table:
        return out

    # Map column headers
    headers = []
    for th in table.select(".rt-thead .rt-tr-header .rt-th .rt-text-content"):
        headers.append(th.get_text(strip=True))

    # Build index map
    col_idx = {}
    for i, h in enumerate(headers):
        key = _header_key(h)
        if key and key not in col_idx:
            col_idx[key] = i

    # Check for player column
    if "player" not in col_idx:
        return out

    # Parse player rows
    groups = table.select(".rt-tbody .rt-tr-group")
    skip_positions = {0, 3}

    # Map player slots
    want = {norm_name(p): i+1 for i, p in enumerate(players) if p}

    # Read cell value
    def get_cell_text(cells, key):
        idx = col_idx.get(key)
        if idx is None or idx >= len(cells):
            return ""
        return cells[idx].get_text(" ", strip=True)

    for rpos, grp in enumerate(groups):
        if rpos in skip_positions:
            continue
        row = grp.select_one(".rt-tr")
        if not row:
            continue
        cells = row.select(".rt-td .rt-td-inner, .rt-td-inner")
        if not cells:
            continue

        # Find player name
        player_txt = get_cell_text(cells, "player")
        pid = norm_name(player_txt)
        slot = want.get(pid)
        if not slot:
            # Check for empty columns
            if not player_txt.strip():
                for ci, h in enumerate(headers):
                    if ci == col_idx.get("team"):
                        continue
                    txt = cells[ci].get_text(" ", strip=True) if ci < len(cells) else ""
                    if txt and not re.search(r"^\d+(\.\d+)?%?$", txt):
                        pid = norm_name(txt)
                        slot = want.get(pid)
                        if slot:
                            break
            if not slot:
                continue 

        # Parse column values
        dinks_txt   = get_cell_text(cells, "dinks") if "dinks" in col_idx else ""
        errors_txt  = get_cell_text(cells, "errors") if "errors" in col_idx else ""
        errpct_txt  = get_cell_text(cells, "err_pct") if "err_pct" in col_idx else ""

        dinks   = safe_int(dinks_txt)
        errors  = safe_int(errors_txt)
        err_pct = _pick_pct(errpct_txt)

        # Compute missing percentages
        if err_pct is None and dinks and dinks > 0 and errors is not None:
            err_pct = (errors * 100.0) / dinks

        out[f"Player{slot}_Dinks"] = dinks if (dinks is not None and dinks >= 0) else out[f"Player{slot}_Dinks"]
        out[f"Player{slot}_DinkErrors"] = errors if errors is not None else out[f"Player{slot}_DinkErrors"]
        out[f"Player{slot}_DinkError%"] = err_pct if err_pct is not None else out[f"Player{slot}_DinkError%"]

    return out

# Parse dink direction
def parse_dink_direction(soup: BeautifulSoup, a1: str, a2: str, b1: str, b2: str):
    sec = soup.find(id="dink-direction")
    if not sec:
        h3 = soup.find(lambda t: t.name in ("h2","h3") and "dink direction" in t.get_text(strip=True).lower())
        sec = h3.find_parent() if h3 else None

    players = [a1, a2, b1, b2]
    # Initialize aggregation
    agg = {
        norm_name(p): {
            "straight": 0,
            "across": 0,
            "sharp": 0,
            "straight_pct_fallback": None,
            "across_pct_fallback": None,
            "sharp_pct_fallback": None,
        }
        for p in players if p
    }

    out = {}
    for i in range(1, 5):
        out[f"Player{i}_StraightDinks"] = None
        out[f"Player{i}_Straight%"] = None
        out[f"Player{i}_AcrossDinks"] = None
        out[f"Player{i}_Across%"] = None
        out[f"Player{i}_SharpAcrossDinks"] = None
        out[f"Player{i}_SharpAcross%"] = None

    if not sec:
        return out

    # Try JSON extraction
    used_json = False
    for sc in sec.find_all("script", {"type": "application/json"}):
        try:
            data = json.loads(sc.string)
            d = data.get("x", {}).get("tag", {}).get("attribs", {}).get("data")
            need = [
                "player_nm",
                "straight_cnt", "straight_pct",
                "across_cnt", "across_pct",
                "sharp_across_cnt", "sharp_across_pct",
            ]
            if isinstance(d, dict) and all(k in d for k in need):
                for nm, scnt, spct, acnt, apct, shcnt, shpct in zip(
                    d["player_nm"],
                    d["straight_cnt"], d["straight_pct"],
                    d["across_cnt"], d["across_pct"],
                    d["sharp_across_cnt"], d["sharp_across_pct"],
                ):
                    pid = norm_name(nm)
                    if pid not in agg:
                        continue
                    # Parse counts
                    def to_int(v):
                        return int(v) if v is not None and str(v).strip().upper() != "NA" else 0
                    agg[pid]["straight"] += to_int(scnt)
                    agg[pid]["across"] += to_int(acnt)
                    agg[pid]["sharp"] += to_int(shcnt)
                    # Parse percentages
                    def to_pct(v):
                        return as_percent_0_100(v) if v is not None and str(v).strip().upper() != "NA" else None
                    sp = to_pct(spct)
                    ap = to_pct(apct)
                    shp = to_pct(shpct)
                    if sp is not None: agg[pid]["straight_pct_fallback"] = sp
                    if ap is not None: agg[pid]["across_pct_fallback"] = ap
                    if shp is not None: agg[pid]["sharp_pct_fallback"] = shp
                used_json = True
                break
        except Exception:
            continue

    # Fallback to HTML table
    if not used_json:
        table = sec.select_one(".Reactable .rt-table")
        if table:
            heads = [h.get_text(strip=True).lower() for h in table.select(".rt-thead .rt-tr-header .rt-th .rt-text-content")]
            idx = {}
            
            # Match headers
            for i, h in enumerate(heads):
                # Normalize header
                h_norm = re.sub(r"[^a-z%]", "", h)
                
                if "player" in h_norm:
                    idx["player"] = i
                # Check sharp column
                elif "sharp" in h_norm and "across" in h_norm:
                    if "%" in h_norm: idx["sharp_pct"] = i
                    else: idx["sharp_cnt"] = i
                elif "across" in h_norm:
                    if "%" in h_norm: idx["across_pct"] = i
                    else: idx["across_cnt"] = i
                elif "straight" in h_norm:
                    if "%" in h_norm: idx["straight_pct"] = i
                    else: idx["straight_cnt"] = i

            def pick_pct(txt):
                m = re.search(r"([\d\.]+)\s*%", txt or "")
                return float(m.group(1)) if m else None

            for row in table.select(".rt-tbody .rt-tr"):
                cells = [c.get_text(" ", strip=True) for c in row.select(".rt-td")]
                if not cells or "player" not in idx:
                    continue
                pid = norm_name(cells[idx["player"]])
                if pid not in agg:
                    continue

                # Parse counts
                if "straight_cnt" in idx:
                    v = safe_int(cells[idx["straight_cnt"]]); agg[pid]["straight"] += v if v is not None else 0
                if "across_cnt" in idx:
                    v = safe_int(cells[idx["across_cnt"]]); agg[pid]["across"] += v if v is not None else 0
                if "sharp_cnt" in idx:
                    v = safe_int(cells[idx["sharp_cnt"]]); agg[pid]["sharp"] += v if v is not None else 0

                # Handle missing percentages
                if "straight_pct" in idx:
                    v = pick_pct(cells[idx["straight_pct"]])
                    if v is not None: agg[pid]["straight_pct_fallback"] = v
                if "across_pct" in idx:
                    v = pick_pct(cells[idx["across_pct"]])
                    if v is not None: agg[pid]["across_pct_fallback"] = v
                if "sharp_pct" in idx:
                    v = pick_pct(cells[idx["sharp_pct"]])
                    if v is not None: agg[pid]["sharp_pct_fallback"] = v

    # Format player output
    def finalize(pid_norm):
        slot = agg.get(pid_norm)
        if not slot:
            return None, None, None, None, None, None
        s, a, sh = slot["straight"], slot["across"], slot["sharp"]
        total = s + a + sh
        if total > 0:
            sp = (s * 100.0) / total
            ap = (a * 100.0) / total
            shp = (sh * 100.0) / total
        else:
            sp = slot["straight_pct_fallback"]
            ap = slot["across_pct_fallback"]
            shp = slot["sharp_pct_fallback"]
        return s or None, sp, a or None, ap, sh or None, shp

    for i, pname in enumerate(players, start=1):
        pid = norm_name(pname) if pname else None
        s_cnt, s_pct, a_cnt, a_pct, sh_cnt, sh_pct = finalize(pid) if pid else (None, None, None, None, None, None)
        out[f"Player{i}_StraightDinks"] = s_cnt
        out[f"Player{i}_Straight%"]      = s_pct
        out[f"Player{i}_AcrossDinks"]    = a_cnt
        out[f"Player{i}_Across%"]        = a_pct
        out[f"Player{i}_SharpAcrossDinks"] = sh_cnt
        out[f"Player{i}_SharpAcross%"]     = sh_pct

    return out

# Parse error rates
def parse_error_rates_by_team_player(
    soup: BeautifulSoup, a1: str, a2: str, b1: str, b2: str
) -> dict:
    sec = soup.find(id="error-rates-by-team-player")
    if not sec:
        h3 = soup.find(lambda t: t.name in ("h2", "h3") and "error rates" in t.get_text(strip=True).lower())
        sec = h3.find_parent() if h3 else None

    players = [a1, a2, b1, b2]
    pnorms = [norm_name(p) if p else None for p in players]

    # Initialize outputs
    out = {
        "TeamA_Shots": None, "TeamA_Errors": None, "TeamA_Error%": None,
        "TeamA_UnforcedErrors": None, "TeamA_UnforcedError%": None,
        "TeamB_Shots": None, "TeamB_Errors": None, "TeamB_Error%": None,
        "TeamB_UnforcedErrors": None, "TeamB_UnforcedError%": None,
    }

    # Add players
    for i in range(1, 5):
        out[f"Player{i}_Shots"] = None
        out[f"Player{i}_Errors"] = None
        out[f"Player{i}_Error%"] = None
        out[f"Player{i}_UnforcedErrors"] = None
        out[f"Player{i}_UnforcedError%"] = None

    if not sec:
        return out

    # Create accumulator
    pdata = {pn: {"shots": 0, "errors": 0, "err_pct": None, "unf": 0, "unf_pct": None} for pn in pnorms if pn}

    def pct_from_str(s: str):
        if not s:
            return None
        m = re.search(r"([\d\.]+)\s*%", s)
        return float(m.group(1)) if m else None

    # Load JSON data
    used_json = False
    for sc in sec.find_all("script", {"type": "application/json"}):
        try:
            data = json.loads(sc.string)
        except Exception:
            continue
        d = data.get("x", {}).get("tag", {}).get("attribs", {}).get("data")
        need = {"player_nm", "shot_cnt", "error_cnt", "error_rate", "unforced_cnt", "unforced_rate"}
        if not isinstance(d, dict) or not need.issubset(d.keys()):
            continue
        for nm, shots, errs, erate, unf, urate in zip(
            d["player_nm"], d["shot_cnt"], d["error_cnt"], d["error_rate"], d["unforced_cnt"], d["unforced_rate"]
        ):
            pid = norm_name(nm)
            if pid not in pdata:
                continue
            shots_i = safe_int(shots) or 0
            errs_i = safe_int(errs) or 0
            unf_i = safe_int(unf) or 0
            pdata[pid]["shots"] += shots_i
            pdata[pid]["errors"] += errs_i
            pdata[pid]["unf"] += unf_i
            # Convert rates
            if erate is not None and str(erate).strip().upper() != "NA":
                pdata[pid]["err_pct"] = float(erate) * 100.0
            if urate is not None and str(urate).strip().upper() != "NA":
                pdata[pid]["unf_pct"] = float(urate) * 100.0
        used_json = True
        break

    # Load HTML data
    if not used_json:
        table = sec.select_one(".Reactable .rt-table")
        if table:
            heads = [h.get_text(strip=True).lower() for h in table.select(".rt-thead .rt-tr-header .rt-th .rt-text-content")]
            idx = {h: i for i, h in enumerate(heads)}
            # Normalize keys
            col = {
                "player": idx.get("player"),
                "shots": idx.get("shots*"),
                "errors": idx.get("errors"),
                "error%": idx.get("error %"),
                "unf": idx.get("unforced errors"),
                "unf%": idx.get("unforced  error %*"),
            }
            for row in table.select(".rt-tbody .rt-tr"):
                cells = [c.get_text(" ", strip=True) for c in row.select(".rt-td")]
                if not cells or col["player"] is None:
                    continue
                pname = cells[col["player"]]
                if not pname:
                    # Skip team rows
                    continue
                pid = norm_name(pname)
                if pid not in pdata:
                    continue
                if col["shots"] is not None:
                    v = safe_int(cells[col["shots"]]); pdata[pid]["shots"] += v or 0
                if col["errors"] is not None:
                    v = safe_int(cells[col["errors"]]); pdata[pid]["errors"] += v or 0
                if col["unf"] is not None:
                    v = safe_int(cells[col["unf"]]); pdata[pid]["unf"] += v or 0
                if col["error%"] is not None:
                    v = pct_from_str(cells[col["error%"]]); pdata[pid]["err_pct"] = v if v is not None else pdata[pid]["err_pct"]
                if col["unf%"] is not None:
                    v = pct_from_str(cells[col["unf%"]]); pdata[pid]["unf_pct"] = v if v is not None else pdata[pid]["unf_pct"]

    # Format player stats
    def finalize_player(pid):
        if not pid or pid not in pdata:
            return None, None, None, None, None
        shots = pdata[pid]["shots"] or 0
        errs = pdata[pid]["errors"] or 0
        unf = pdata[pid]["unf"] or 0
        err_pct = (errs * 100.0 / shots) if shots > 0 else pdata[pid]["err_pct"]
        unf_pct = (unf * 100.0 / shots) if shots > 0 else pdata[pid]["unf_pct"]
        return shots or None, errs or None, err_pct, unf or None, unf_pct

    pvals = [finalize_player(pn) for pn in pnorms]

    for i, vals in enumerate(pvals, start=1):
        shots, errs, err_pct, unf, unf_pct = vals
        out[f"Player{i}_Shots"] = shots
        out[f"Player{i}_Errors"] = errs
        out[f"Player{i}_Error%"] = err_pct
        out[f"Player{i}_UnforcedErrors"] = unf
        out[f"Player{i}_UnforcedError%"] = unf_pct

    # Calculate team totals
    def team_from_indices(idxs):
        s = sum((pvals[i][0] or 0) for i in idxs if pvals[i] is not None)
        e = sum((pvals[i][1] or 0) for i in idxs if pvals[i] is not None)
        u = sum((pvals[i][3] or 0) for i in idxs if pvals[i] is not None)
        err_pct = (e * 100.0 / s) if s > 0 else None
        unf_pct = (u * 100.0 / s) if s > 0 else None
        return s or None, e or None, err_pct, u or None, unf_pct

    ta = team_from_indices([0, 1])
    tb = team_from_indices([2, 3])

    out["TeamA_Shots"], out["TeamA_Errors"], out["TeamA_Error%"], out["TeamA_UnforcedErrors"], out["TeamA_UnforcedError%"] = ta
    out["TeamB_Shots"], out["TeamB_Errors"], out["TeamB_Error%"], out["TeamB_UnforcedErrors"], out["TeamB_UnforcedError%"] = tb

    return out

# Parse individual file
def parse_file(p: Path, metadata: dict) -> dict:
    html = read_text(p).replace("\u2013", "-").replace("\u2014", "-").replace("\u2212", "-")
    soup = BeautifulSoup(html, "lxml")
    
    # Extract match ID
    mid = p.stem 

    # Initialize default variables
    match_name = ""
    team_a_text, team_b_text = "UnknownA", "UnknownB"
    a_score, b_score = None, None
    total_rallies = None
    winning_team = None

    # Check metadata
    if mid in metadata:
        row = metadata[mid]
        # Extract trusted data
        team_a_text = row.get('TeamA')
        team_b_text = row.get('TeamB')
        
        # Extract scores
        a_score = int(row.get('TeamAScore')) if row.get('TeamAScore') else None
        b_score = int(row.get('TeamBScore')) if row.get('TeamBScore') else None
        total_rallies = int(row.get('Rallies')) if row.get('Rallies') else None 
        
        # Build match name
        skill = row.get('Skill Level', '')
        match_name = f"{skill} match (ID: {mid})"

        # Infer winning team
        if a_score is not None and b_score is not None:
            if a_score > b_score: winning_team = "TeamA"
            elif b_score > a_score: winning_team = "TeamB"

    else:
        # Scrape HTML data
        flat = soup.get_text(separator="\n", strip=True)
        match_name, team_a_text, team_b_text, winning_team = parse_header_lines(flat)
        a_score, b_score = parse_scores(flat)

    # Assign players
    a1, a2 = split_players(team_a_text)
    b1, b2 = split_players(team_b_text)

    team_label = f"{team_a_text} vs {team_b_text}" if team_a_text and team_b_text else ""

    rally = parse_rally_section(soup, team_a_text, team_b_text)
    if total_rallies is not None:
        rally["TotalRallies"] = total_rallies
    team_counts, player_counts = parse_shot_counts(soup, team_a_text, team_b_text, a1, a2, b1, b2)
    shot_types = parse_shot_type_frequencies(soup)
    third_shot_agg = parse_third_shot_performance_agg(soup, a1, a2, b1, b2)
    dinking_perf = parse_dinking_performance(soup, a1, a2, b1, b2)
    dink_dir = parse_dink_direction(soup, a1, a2, b1, b2)
    errors_tp = parse_error_rates_by_team_player(soup, a1, a2, b1, b2)

    return {
        "FileName": p.name,
        "MatchName": match_name,
        "Team": team_label,
        "TeamAPlayer1": a1, "TeamAPlayer2": a2,
        "TeamBPlayer1": b1, "TeamBPlayer2": b2,
        "TeamAScore": a_score, "TeamBScore": b_score,
        "WinningTeam": winning_team,
        "TotalRallies": rally["TotalRallies"],
        "AvgShotsPerRally": rally["AvgShotsPerRally"],
        "TeamARalliesWon": rally["TeamARalliesWon"],
        "TeamBRalliesWon": rally["TeamBRalliesWon"],
        "RallyPct_2ShotsOrLess": rally["RallyPct_2ShotsOrLess"],
        "RallyPct_3to5Shots": rally["RallyPct_3to5Shots"],
        "RallyPct_6to12Shots": rally["RallyPct_6to12Shots"],
        "RallyPct_13PlusShots": rally["RallyPct_13PlusShots"],
        **team_counts,
        **player_counts,
        **shot_types,
        **third_shot_agg,
        **dinking_perf,
        **dink_dir,
        **errors_tp,
    }


def numeric_id_for_sort(p: Path):
    m = MATCH_ID_RE.search(p.stem)
    return int(m.group(1)) if m else math.inf

def match_id_from_filename(p: Path) -> str:
    m = MATCH_ID_RE.search(p.stem)
    return f"M{int(m.group(1))}" if m else p.stem

def main():
    if not REPORTS_DIR.exists() or not REPORTS_DIR.is_dir():
        raise SystemExit(f"Folder not found: {REPORTS_DIR}")\
    
    csv_path = REPORTS_DIR / "matches4.0.csv"
    metadata = {}
    
    if csv_path.exists():
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Read match ID
                mid = row.get("MatchID") 
                if mid:
                    metadata[mid] = row
    print(f"Loaded metadata for {len(metadata)} matches.")

    files = sorted(
        list(REPORTS_DIR.rglob("*.html")) + list(REPORTS_DIR.rglob("*.htm")),
        key=numeric_id_for_sort
    )
    if not files:
        raise SystemExit("No HTML files found.")
    if MAX_MATCHES is not None:
        files = files[:MAX_MATCHES]
    csv_path = REPORTS_DIR / "matches4.0.csv"
    metadata = {}
    if csv_path.exists():
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                mid = row.get("MatchID")
                if mid:
                    metadata[mid] = row
    print(f"Loaded metadata for {len(metadata)} matches.")

    rows = []
    for f in files:
        try:
            row = parse_file(f, metadata)
            rows.append(row)
            mid = match_id_from_filename(f)
            score_txt = f"{row['TeamAScore']} to {row['TeamBScore']}" if row['TeamAScore'] is not None and row['TeamBScore'] is not None else "N/A"
            tr = row.get("TotalRallies")
            print(f"Finished scraping {mid} ({f.name}): {row['Team']} | Score {score_txt} | TotalRallies {tr}", flush=True)
        except Exception as e:
            print(f"[WARN] Failed {f}: {e}", flush=True)

    if not rows:
        raise SystemExit("No rows parsed.")

    out_csv = REPORTS_DIR / "matches_complete4.csv"
    with out_csv.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=[
    "FileName",
    "MatchName", "Team",
    "TeamAPlayer1", "TeamAPlayer2", "TeamBPlayer1", "TeamBPlayer2",
    "TeamAScore", "TeamBScore", "WinningTeam",
    "TotalRallies", "AvgShotsPerRally", "TeamARalliesWon", "TeamBRalliesWon",
    "RallyPct_2ShotsOrLess", "RallyPct_3to5Shots", "RallyPct_6to12Shots", "RallyPct_13PlusShots",

    "TeamA_Unreturned", "TeamA_Assists", "TeamA_Errors", "TeamA_TotalShots",
    "TeamB_Unreturned", "TeamB_Assists", "TeamB_Errors", "TeamB_TotalShots",

    "Player1_Unreturned", "Player1_Assists", "Player1_Errors", "Player1_TotalShots",
    "Player2_Unreturned", "Player2_Assists", "Player2_Errors", "Player2_TotalShots",
    "Player3_Unreturned", "Player3_Assists", "Player3_Errors", "Player3_TotalShots",
    "Player4_Unreturned", "Player4_Assists", "Player4_Errors", "Player4_TotalShots",

    "ShotType_TransitionZone_Freq", "ShotType_TransitionZone_Err%",
    "ShotType_Dink_Freq", "ShotType_Dink_Err%",
    "ShotType_Serve_Freq", "ShotType_Serve_Err%",
    "ShotType_Return_Freq", "ShotType_Return_Err%",
    "ShotType_HandBattle_Freq", "ShotType_HandBattle_Err%",
    "ShotType_3rdShotDrop_Freq", "ShotType_3rdShotDrop_Err%",
    "ShotType_3rdShotDrive_Freq", "ShotType_3rdShotDrive_Err%",
    "ShotType_Lob_Freq", "ShotType_Lob_Err%",
    "ShotType_SpeedUp_Freq", "ShotType_SpeedUp_Err%",
    "ShotType_Reset_Freq", "ShotType_Reset_Err%",

    "Player1_3rdShot_Err%", "Player1_3rdShot_Win%", "Player1_3rdShot_OppError%", "Player1_3rdShot_LedToDinks%",
    "Player2_3rdShot_Err%", "Player2_3rdShot_Win%", "Player2_3rdShot_OppError%", "Player2_3rdShot_LedToDinks%",
    "Player3_3rdShot_Err%", "Player3_3rdShot_Win%", "Player3_3rdShot_OppError%", "Player3_3rdShot_LedToDinks%",
    "Player4_3rdShot_Err%", "Player4_3rdShot_Win%", "Player4_3rdShot_OppError%", "Player4_3rdShot_LedToDinks%",

    "Player1_Dinks", "Player1_DinkErrors", "Player1_DinkError%",
    "Player2_Dinks", "Player2_DinkErrors", "Player2_DinkError%",
    "Player3_Dinks", "Player3_DinkErrors", "Player3_DinkError%",
    "Player4_Dinks", "Player4_DinkErrors", "Player4_DinkError%",

    "Player1_StraightDinks","Player1_Straight%","Player1_AcrossDinks","Player1_Across%","Player1_SharpAcrossDinks","Player1_SharpAcross%",
    "Player2_StraightDinks","Player2_Straight%","Player2_AcrossDinks","Player2_Across%","Player2_SharpAcrossDinks","Player2_SharpAcross%",
    "Player3_StraightDinks","Player3_Straight%","Player3_AcrossDinks","Player3_Across%","Player3_SharpAcrossDinks","Player3_SharpAcross%",
    "Player4_StraightDinks","Player4_Straight%","Player4_AcrossDinks","Player4_Across%","Player4_SharpAcrossDinks","Player4_SharpAcross%",

    "TeamA_Shots","TeamA_Errors","TeamA_Error%","TeamA_UnforcedErrors","TeamA_UnforcedError%",
    "TeamB_Shots","TeamB_Errors","TeamB_Error%","TeamB_UnforcedErrors","TeamB_UnforcedError%",
    "Player1_Shots","Player1_Errors","Player1_Error%","Player1_UnforcedErrors","Player1_UnforcedError%",
    "Player2_Shots","Player2_Errors","Player2_Error%","Player2_UnforcedErrors","Player2_UnforcedError%",
    "Player3_Shots","Player3_Errors","Player3_Error%","Player3_UnforcedErrors","Player3_UnforcedError%",
    "Player4_Shots","Player4_Errors","Player4_Error%","Player4_UnforcedErrors","Player4_UnforcedError%",
])
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {out_csv}")

if __name__ == "__main__":
    main()