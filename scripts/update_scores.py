#!/usr/bin/env python3
"""
2026世界杯比分自动更新脚本 v2.1
- 移除Sofascore（403不可用），纯ESPN单源，更稳定
- ESPN API带日期查询，确保能拉到历史场次
- STATUS_FINAL检查 + 时间门限2.5h + 可覆盖更新
- 30分钟高频轮询
"""
import json, re, os, sys
from urllib.request import urlopen, Request
from urllib.error import URLError
from datetime import datetime, timedelta, timezone
from collections import defaultdict

ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"

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

def fetch_json(url, timeout=20):
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json"
    })
    try:
        resp = urlopen(req, timeout=timeout)
        return json.loads(resp.read())
    except Exception as e:
        print(f"  [WARN] {url[:60]}... -> {e}")
        return None

def fetch_espn_for_date(date_str=None):
    """某一日的ESPN数据，date_str格式 YYYYMMDD 或 None（当天）"""
    url = ESPN_BASE
    if date_str:
        url += f"?dates={date_str}"
    print(f"\n[ESPN] {url}")
    data = fetch_json(url)
    if not data or "events" not in data:
        print(f"  [FAIL] No data")
        return {}
    
    scores = {}
    for event in data["events"]:
        try:
            name = event.get("name", "?")
            status = event.get("status", {}).get("type", {}).get("name", "")
            desc = event.get("status", {}).get("type", {}).get("description", "")
            is_final = "final" in status.lower() or status == "STATUS_FINAL"
            
            if not is_final:
                print(f"  ⏳ {name} ({desc}) - 跳过")
                continue
            
            comp = event.get("competitions", [{}])[0]
            competitors = comp.get("competitors", [])
            if len(competitors) < 2: continue
            
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
                    print(f"  ✅ {hc} {home[1]}-{away[1]} {ac}")
        except Exception as e:
            print(f"  ✗ Parse error: {e}")
    
    return scores

def is_match_due(html, home_code, away_code):
    """时间门限：开球后2.5小时才写入"""
    pattern = rf"\['(\d{{4}}-\d{{2}}-\d{{2}})'\s*,\s*'(\d{{2}}:\d{{2}})'\s*,\s*\['{home_code}','{away_code}'\]"
    m = re.search(pattern, html)
    if not m: return True
    try:
        date_str, time_str = m.group(1), m.group(2)
        kickoff = datetime.strptime(f"{date_str}T{time_str}:00-04:00", "%Y-%m-%dT%H:%M:%S%z")
        now = datetime.now(timezone.utc).replace(tzinfo=timezone.utc)
        elapsed = (now - kickoff).total_seconds() / 3600
        if elapsed < 2.5:
            print(f"  ⏱ {home_code}vs{away_code} 开球{elapsed:.1f}h，未到2.5h门限")
            return False
        return True
    except:
        return True

def update_html(html, scores):
    """更新RAW_MATCHES，支持覆盖已有比分"""
    changes = 0
    for (hc, ac), (h_goal, a_goal) in scores.items():
        if not is_match_due(html, hc, ac):
            continue
        pattern = rf"(\['\d{{4}}-\d{{2}}-\d{{2}}','\d{{2}}:\d{{2}}',\['{hc}','{ac}'\][^\]]+)(\[[\d,]+\]|null)(\])"
        def replacer(m, hc=hc, ac=ac, hg=h_goal, ag=a_goal):
            nonlocal changes
            old = m.group(2)
            new = f"[{hg},{ag}]"
            if old != new:
                changes += 1
                print(f"  ✅ 更新: {hc} {hg}-{ag} {ac} (之前{old})")
            return m.group(1) + new + m.group(3)
        html = re.sub(pattern, replacer, html)
    if changes == 0:
        print("[INFO] 比分已最新")
    else:
        print(f"\n✅ 更新了 {changes} 场")
    return html

def update_standings(html):
    """从已有比分反推积分榜"""
    matches = re.findall(
        r"\['(\d{4}-\d{2}-\d{2})','\d{2}:\d{2}',\['([A-Z]+)','([A-Z]+)'\],'[^']+','[^']+','(Grp [A-L])',\[(\d+),(\d+)\]\]",
        html
    )
    groups = defaultdict(lambda: defaultdict(lambda: {"mp":0,"w":0,"d":0,"l":0,"gf":0,"ga":0,"pts":0}))
    for _, hc, ac, grp, hs, aws in matches:
        g = grp[-1]; h, a = int(hs), int(aws)
        groups[g][hc]["mp"]+=1; groups[g][hc]["gf"]+=h; groups[g][hc]["ga"]+=a
        groups[g][ac]["mp"]+=1; groups[g][ac]["gf"]+=a; groups[g][ac]["ga"]+=h
        if h>a: groups[g][hc]["w"]+=1; groups[g][hc]["pts"]+=3; groups[g][ac]["l"]+=1
        elif h<a: groups[g][ac]["w"]+=1; groups[g][ac]["pts"]+=3; groups[g][hc]["l"]+=1
        else: groups[g][hc]["d"]+=1; groups[g][hc]["pts"]+=1; groups[g][ac]["d"]+=1; groups[g][ac]["pts"]+=1
    for g, teams in groups.items():
        for code, s in teams.items():
            pattern = r"(\{name:'[^']*',code:'" + code + r"',[^}]+\})"
            repl = lambda m, s=s: (
                f"{{name:'{_extr(m.group(),'name')}',code:'{code}',"
                f"flag:'{_extr(m.group(),'flag')}',rank:{_extr(m.group(),'rank')},"
                f"mp:{s['mp']},w:{s['w']},d:{s['d']},l:{s['l']},"
                f"gf:{s['gf']},ga:{s['ga']},pts:{s['pts']}}}"
            )
            html = re.sub(pattern, repl, html)
    return html

def _extr(text, key):
    m = re.search(rf"\{key}:'([^']+)'", text)
    return m.group(1) if m else ""

def main():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    html_path = os.path.join(repo_root, "index.html")
    if not os.path.exists(html_path):
        print(f"[ERROR] index.html not found"); sys.exit(1)
    
    with open(html_path, "r", encoding="utf-8") as f: html = f.read()
    
    now = datetime.now(timezone.utc)
    print("="*50)
    print(f"2026 World Cup Updater v2.1")
    print(f"Run: {now.strftime('%Y-%m-%d %H:%M UTC')} = BJT {(now+timedelta(hours=8)).strftime('%Y-%m-%d %H:%M')}")
    print("="*50)
    
    # 查多日数据：当前-1天, -2天, -3天（覆盖最近3个比赛日）
    all_scores = {}
    for days_back in range(4):  # 当天 + 前3天
        d = (now - timedelta(days=days_back)).strftime("%Y%m%d")
        scores = fetch_espn_for_date(d)
        for k, v in scores.items():
            if k not in all_scores:  # 最近的日期优先
                all_scores[k] = v
    
    if not all_scores:
        print("\n[INFO] 未发现已完赛比赛")
        sys.exit(0)
    
    print(f"\n[INFO] 共 {len(all_scores)} 场已完赛")
    new_html = update_html(html, all_scores)
    new_html = update_standings(new_html)
    
    if new_html != html:
        with open(html_path, "w", encoding="utf-8") as f: f.write(new_html)
        print(f"\n✅ index.html 已更新!")
    else:
        print(f"\nℹ️ 无需更新")
    
    print("="*50)

if __name__ == "__main__":
    main()
