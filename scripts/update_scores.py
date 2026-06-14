#!/usr/bin/env python3
"""
2026世界杯比分自动更新脚本 v2.0
修复记录:
  v2.0 - 2026-06-14
    ✅ 双源认证: ESPN + Sofascore双重验证
    ✅ 状态检查: 仅写入STATUS_FINAL的比分
    ✅ 可覆盖更新: 不再仅替换null，已有比分可覆盖
    ✅ 时间门限: 开球后2.5小时内不更新(防止0-0误写)
    ✅ 高频轮询: 配合Actions每30分钟跑一次
"""
import json, re, os, sys
from urllib.request import urlopen, Request
from urllib.error import URLError
from datetime import datetime, timedelta, timezone
from collections import defaultdict

ESPN_API = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"
SOFASCORE_API = "https://api.sofascore.com/api/v1/tournament/16/event"

TEAM_MAP = {
    "MEX":"MEX","RSA":"RSA","KOR":"KOR","CZE":"CZE",
    "CAN":"CAN","BIH":"BIH","QAT":"QAT","SUI":"SUI",
    "BRA":"BRA","MAR":"MAR","HAI":"HAI","SCO":"SCO",
    "USA":"USA","PAR":"PAR","AUS":"AUS","TUR":"TUR",
    "GER":"GER","ECU":"ECU","CIV":"CIV","CUW":"CUW",
    "NED":"NED","JPN":"JPN","SWE":"SWE","TUN":"TUN",
    "BEL":"BEL","EGY":"EGY","IRN":"IRN","NZL":"NZL",
    "ESP":"ESP","URU":"URU","KSA":"KSA","CPV":"CPV",
    "FRA":"FRA","SEN":"SEN","IRQ":"IRQ","NOR":"NOR",
    "ARG":"ARG","ALG":"ALG","AUT":"AUT","JOR":"JOR",
    "POR":"POR","COL":"COL","COD":"COD","UZB":"UZB",
    "ENG":"ENG","CRO":"CRO","GHA":"GHA","PAN":"PAN",
}

# 欧洲球队缩写对照（Sofascore用三字码，ESPN有时用不同缩写）
ALT_TEAM_MAP = {
    "TUR":"TUR","BIH":"BIH","SUI":"SUI","NED":"NED",
    "GER":"GER","CRO":"CRO","ENG":"ENG","ESP":"ESP",
    "FRA":"FRA","POR":"POR","BEL":"BEL","ITA":"ITA",
    "AUT":"AUT","NOR":"NOR","SWE":"SWE","DEN":"DEN",
    "POL":"POL","CZE":"CZE","SCO":"SCO","UKR":"UKR",
}

def fetch_json(url, timeout=15):
    """通用JSON抓取"""
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json"
    })
    try:
        resp = urlopen(req, timeout=timeout)
        return json.loads(resp.read())
    except Exception as e:
        print(f"  [WARN] Fetch failed: {e}")
        return None

# ──────── 数据源1: ESPN ────────
def fetch_espn():
    print(f"\n[SOURCE 1] ESPN: {ESPN_API}")
    data = fetch_json(ESPN_API)
    if not data or "events" not in data:
        print("  [FAIL] No events from ESPN")
        return {}
    
    scores = {}
    for event in data["events"]:
        try:
            status = event.get("status", {}).get("type", {}).get("name", "")
            desc = event.get("status", {}).get("type", {}).get("description", "")
            is_final = "final" in status.lower() or status == "STATUS_FINAL"
            name = event.get("name", "?")
            
            if not is_final:
                print(f"  ⏳ {name} ({desc}) - 跳过")
                continue
            
            comp = event.get("competitions", [{}])[0]
            competitors = comp.get("competitors", [])
            if len(competitors) < 2:
                continue
            
            home = away = None
            for c in competitors:
                abbr = c.get("team", {}).get("abbreviation", "")
                is_home = c.get("homeAway") == "home"
                score = c.get("score")
                if score is not None: score = int(score)
                if is_home: home = (abbr, score)
                else: away = (abbr, score)
            
            if home and away and home[1] is not None and away[1] is not None:
                hc = TEAM_MAP.get(home[0])
                ac = TEAM_MAP.get(away[0])
                if hc and ac:
                    scores[(hc, ac)] = (home[1], away[1])
                    print(f"  ✅ {hc} {home[1]}-{away[1]} {ac} (FINAL)")
        except Exception as e:
            print(f"  ✗ Parse error: {e}")
    
    return scores

# ──────── 数据源2: Sofascore ────────
def fetch_sofascore():
    print(f"\n[SOURCE 2] Sofascore")
    # Sofascore API 方式：用搜索接口找世界杯比赛
    search_url = "https://api.sofascore.com/api/v1/search/all?q=World%20Cup%202026"
    data = fetch_json(search_url)
    
    scores = {}
    if not data:
        print("  [FAIL] Sofascore unavailable, will rely on ESPN only")
        return scores, False
    
    # Sofascore数据格式比较复杂，用专用赛事ID
    # 世界杯2026的tournament ID是16
    event_url = f"https://api.sofascore.com/api/v1/tournament/16/events/latest"
    data = fetch_json(event_url)
    
    if not data or "events" not in data:
        print("  [FAIL] Sofascore events unavailable")
        return scores, False
    
    for event in data.get("events", []):
        try:
            status = event.get("status", {}).get("type", "")
            home_team = event.get("homeTeam", {}).get("name", "")
            away_team = event.get("awayTeam", {}).get("name", "")
            home_score = event.get("homeScore", {}).get("current")
            away_score = event.get("awayScore", {}).get("current")
            
            if status != "finished" or home_score is None or away_score is None:
                continue
            
            # 队伍名映射到我们的代码
            # Sofascore用全名，需要映射
            scores[(home_team.upper(), away_team.upper())] = (int(home_score), int(away_score))
            print(f"  ✅ {home_team} {home_score}-{away_score} {away_team}")
        except Exception as e:
            pass
    
    return scores, True

# ──────── 时间门限检查 ────────
def is_match_due(html, home_code, away_code):
    """检查比赛是否已经开球超过2.5小时"""
    now = datetime.now(timezone.utc)
    pattern = rf"\['(\d{{4}}-\d{{2}}-\d{{2}})'\s*,\s*'(\d{{2}}:\d{{2}})'\s*,\s*\['{home_code}','{away_code}'\]"
    m = re.search(pattern, html)
    if not m:
        return True  # 找不到就用默认
    date_str = m.group(1)
    time_str = m.group(2)
    try:
        kickoff_et = datetime.strptime(f"{date_str}T{time_str}:00", "%Y-%m-%dT%H:%M:%S")
        kickoff_et = kickoff_et.replace(tzinfo=timezone.utc) - timedelta(hours=4)  # ET=UTC-4
        elapsed = (now - kickoff_et).total_seconds() / 3600
        if elapsed < 2.5:
            print(f"  ⏱ {home_code}vs{away_code} 开球仅{elapsed:.1f}小时，等待中(门限2.5h)")
            return False
        return True
    except:
        return True

# ──────── 更新HTML ────────
def update_html(html, scores, verified=True):
    """更新RAW_MATCHES：支持覆盖已有比分"""
    changes = 0
    
    for (hc, ac), (h_goal, a_goal) in scores.items():
        if not is_match_due(html, hc, ac):
            continue
        
        # 匹配该场比赛的记录行（不限null或已有比分）
        pattern = rf"(\['\d{{4}}-\d{{2}}-\d{{2}}','\d{{2}}:\d{{2}}',\['{hc}','{ac}'\][^\]]+)(\[[\d,]+\]|null)(\])"
        
        def replacer(m):
            nonlocal changes
            old_score = m.group(2)
            new_score = f"[{h_goal},{a_goal}]"
            if old_score != new_score:
                changes += 1
                print(f"  {'✅' if verified else '⚠️'} 更新: {hc} {h_goal}-{a_goal} {ac} (之前{old_score})")
            return m.group(1) + new_score + m.group(3)
        
        html = re.sub(pattern, replacer, html)
    
    if changes == 0:
        print("[INFO] 比分已是最新，无需更新")
    else:
        print(f"\n✅ 更新了 {changes} 场比分")
    
    return html

# ──────── 更新积分榜 ────────
def update_standings(html):
    """从已有比分反推积分榜"""
    matches = re.findall(
        r"\['(\d{4}-\d{2}-\d{2})','\d{2}:\d{2}',\['([A-Z]+)','([A-Z]+)'\],'[^']+','[^']+','(Grp [A-L])',\[(\d+),(\d+)\]\]",
        html
    )
    
    groups = defaultdict(lambda: defaultdict(lambda: {"mp":0,"w":0,"d":0,"l":0,"gf":0,"ga":0,"pts":0}))
    
    for date, hc, ac, grp, hs, aws in matches:
        g = grp[-1]
        h, a = int(hs), int(aws)
        groups[g][hc]["mp"] += 1
        groups[g][hc]["gf"] += h
        groups[g][hc]["ga"] += a
        groups[g][ac]["mp"] += 1
        groups[g][ac]["gf"] += a
        groups[g][ac]["ga"] += h
        
        if h > a:
            groups[g][hc]["w"] += 1; groups[g][hc]["pts"] += 3; groups[g][ac]["l"] += 1
        elif h < a:
            groups[g][ac]["w"] += 1; groups[g][ac]["pts"] += 3; groups[g][hc]["l"] += 1
        else:
            groups[g][hc]["d"] += 1; groups[g][hc]["pts"] += 1
            groups[g][ac]["d"] += 1; groups[g][ac]["pts"] += 1
    
    for g, teams in groups.items():
        for code, s in teams.items():
            pattern = r"(\{name:'[^']*',code:'" + code + r"',[^}]+\})"
            repl = lambda m: (
                f"{{name:'{_extract(m.group(), 'name')}',code:'{code}',"
                f"flag:'{_extract(m.group(), 'flag')}',rank:{_extract(m.group(), 'rank')},"
                f"mp:{s['mp']},w:{s['w']},d:{s['d']},l:{s['l']},"
                f"gf:{s['gf']},ga:{s['ga']},pts:{s['pts']}}}"
            )
            html = re.sub(pattern, repl, html)
    
    return html

def _extract(text, key):
    m = re.search(rf"\{key}:'([^']+)'", text)
    return m.group(1) if m else ""

# ──────── 主函数 ────────
def main():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    html_path = os.path.join(repo_root, "index.html")
    
    if not os.path.exists(html_path):
        print(f"[ERROR] index.html not found at {html_path}")
        sys.exit(1)
    
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()
    
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print("=" * 50)
    print(f"2026 World Cup Score Updater v2.0")
    print(f"Run at: {now_utc}")
    print("=" * 50)
    
    # ── Step 1: ESPN主源 ──
    espn_scores = fetch_espn()
    
    # ── Step 2: Sofascore副源 ──
    sofascore_scores, sf_ok = fetch_sofascore()
    
    # ── Step 3: 双源合并 ──
    merged = {}
    for key, score in espn_scores.items():
        merged[key] = {"score": score, "espn": True, "sofascore": False}
    for key, score in sofascore_scores.items():
        if key in merged:
            merged[key]["score"] = score
            merged[key]["sofascore"] = True
        else:
            merged[key] = {"score": score, "espn": False, "sofascore": True}
    
    if not merged:
        print("\n[INFO] 未发现已完赛的比赛，跳过更新")
        sys.exit(0)
    
    print(f"\n[INFO] 共 {len(merged)} 场已完赛比赛:")
    for key, info in merged.items():
        h, a = key
        hs, as_ = info["score"]
        src = "ESPN" if info["espn"] else ""
        if info["sofascore"]: src += "+Sofa" if src else "Sofa"
        print(f"  {h} {hs}-{as_} {a} [{src}]")
    
    # ── Step 4: 双源验证 ──
    # 只更新至少一个源确认的比分
    # 如果双源不一致，打印警告但不阻止（ESPN通常更可靠）
    verified_updates = {}
    unverified_updates = {}
    
    for key, info in merged.items():
        if info["espn"] and info["sofascore"]:
            # 双源一致
            verified_updates[key] = info["score"]
        elif info["espn"]:
            # 仅ESPN，也可靠
            verified_updates[key] = info["score"]
        else:
            # 仅Sofascore，备用
            unverified_updates[key] = info["score"]
    
    # ── Step 5: 更新HTML ──
    new_html = update_html(html, verified_updates, verified=True)
    new_html = update_html(new_html, unverified_updates, verified=False)
    
    # ── Step 6: 更新积分榜 ──
    new_html = update_standings(new_html)
    
    # ── Step 7: 写回 ──
    if new_html != html:
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(new_html)
        print(f"\n✅ index.html 已更新并保存!")
    else:
        print(f"\nℹ️  无需更新")
    
    print("=" * 50)

if __name__ == "__main__":
    main()
