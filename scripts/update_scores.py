#!/usr/bin/env python3
"""
2026世界杯比分自动更新脚本
在 GitHub Actions 中定时运行，从 ESPN 免费公开接口拉取真实比分，
自动更新 index.html 中的 RAW_MATCHES 数据。
零API费用，零外部依赖（只用 Python 标准库）。
"""
import json
import re
import os
import sys
from urllib.request import urlopen, Request
from urllib.error import URLError

# ESPN 免费公开接口（无需API Key）
ESPN_API = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"

# 队伍代码映射：ESPN的三字代码 → 我们的代码
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

def fetch_espn_data():
    """从ESPN获取世界杯实时数据"""
    print(f"[INFO] Fetching from ESPN: {ESPN_API}")
    req = Request(ESPN_API, headers={"User-Agent": "Mozilla/5.0"})
    try:
        resp = urlopen(req, timeout=15)
        data = json.loads(resp.read())
        print(f"[INFO] ESPN data received: {len(data.get('events', []))} events")
        return data
    except URLError as e:
        print(f"[WARN] ESPN fetch failed: {e}")
        return None

def parse_espn_scores(data):
    """从ESPN数据中解析比分，返回 dict: (home_code, away_code) -> (home_score, away_score)"""
    scores = {}
    if not data or "events" not in data:
        return scores
    
    for event in data["events"]:
        try:
            comp = event.get("competitions", [{}])[0]
            competitors = comp.get("competitors", [])
            if len(competitors) < 2:
                continue
            
            # 找到主客队
            home_team = away_team = None
            for c in competitors:
                team_abbr = c.get("team", {}).get("abbreviation", "")
                is_home = c.get("homeAway") == "home"
                score = c.get("score")
                if score is not None:
                    score = int(score)
                if is_home:
                    home_team = (team_abbr, score)
                else:
                    away_team = (team_abbr, score)
            
            if home_team and away_team and home_team[1] is not None and away_team[1] is not None:
                home_code = TEAM_MAP.get(home_team[0])
                away_code = TEAM_MAP.get(away_team[0])
                if home_code and away_code:
                    scores[(home_code, away_code)] = (home_team[1], away_team[1])
                    print(f"  ✓ {home_code} {home_team[1]}-{away_team[1]} {away_code}")
        except Exception as e:
            print(f"  ✗ Parse error for event: {e}")
    
    return scores

def update_html(html, scores):
    """更新HTML中的RAW_MATCHES数组，把null替换为真实比分"""
    # 匹配 RAW_MATCHES 数组内容
    # 模式: ['2026-06-11','16:00',['MEX','RSA'],...,null]
    # 要替换为: ['2026-06-11','16:00',['MEX','RSA'],...,[2,0]]
    
    def replace_match(match):
        full = match.group(0)
        # 提取队伍代码
        teams_match = re.search(r"\['([A-Z]+)','([A-Z]+)'\]", full)
        if not teams_match:
            return full
        
        home_code = teams_match.group(1)
        away_code = teams_match.group(2)
        key = (home_code, away_code)
        
        if key in scores:
            h, a = scores[key]
            # 替换最后一个 null（比分位置）
            new = re.sub(r',null\s*\]$', f',[{h},{a}]]', full)
            if new != full:
                print(f"  ✅ 更新: {home_code} vs {away_code} → {h}-{a}")
                return new
        
        return full
    
    # 匹配每条比赛记录
    new_html = re.sub(
        r"\['\d{4}-\d{2}-\d{2}','\d{2}:\d{2}',\[[^\]]+\],[^,]+,'[^']+','[^']+',null\]",
        replace_match,
        html
    )
    
    updated_count = sum(1 for key in scores 
                       if f",{scores[key][0]},{scores[key][1]}]" not in html 
                       and re.search(rf"\['{key[0]}','{key[1]}'\]", html))
    
    if new_html == html:
        print("[INFO] No new scores to update")
    else:
        print(f"[INFO] HTML updated")
    
    return new_html

def update_group_standings(html):
    """从比分数据反推小组积分榜"""
    # 提取所有已经有的比分
    matches = re.findall(
        r"\['(\d{4}-\d{2}-\d{2})','\d{2}:\d{2}',\['([A-Z]+)','([A-Z]+)'\],'[^']+','[^']+','(Grp [A-L])',\[(\d+),(\d+)\]\]",
        html
    )
    
    # 计算每组积分
    from collections import defaultdict
    groups = defaultdict(lambda: defaultdict(lambda: {"mp":0,"w":0,"d":0,"l":0,"gf":0,"ga":0,"pts":0}))
    
    for date, hc, ac, grp, hs, aws in matches:
        g = grp[-1]  # Grp A -> A
        h, a = int(hs), int(aws)
        
        groups[g][hc]["mp"] += 1
        groups[g][hc]["gf"] += h
        groups[g][hc]["ga"] += a
        groups[g][ac]["mp"] += 1
        groups[g][ac]["gf"] += a
        groups[g][ac]["ga"] += h
        
        if h > a:
            groups[g][hc]["w"] += 1
            groups[g][hc]["pts"] += 3
            groups[g][ac]["l"] += 1
        elif h < a:
            groups[g][ac]["w"] += 1
            groups[g][ac]["pts"] += 3
            groups[g][hc]["l"] += 1
        else:
            groups[g][hc]["d"] += 1
            groups[g][hc]["pts"] += 1
            groups[g][ac]["d"] += 1
            groups[g][ac]["pts"] += 1
    
    # 更新 GROUP_DATA
    for g, teams in groups.items():
        for code, stats in teams.items():
            # 在 GROUP_DATA 中查找匹配项
            # {name:'墨西哥',code:'MEX',flag:'🇲🇽',rank:15,mp:1,w:1,d:0,l:0,gf:2,ga:0,pts:3}
            pattern = r"(\{name:'[^']*',code:'" + code + r"',[^}]+\})"
            replacement = (
                f"{{name:'{_name_for_code(html, code)}',code:'{code}',"
                f"flag:'{_flag_for_code(html, code)}',rank:{_rank_for_code(html, code)},"
                f"mp:{stats['mp']},w:{stats['w']},d:{stats['d']},l:{stats['l']},"
                f"gf:{stats['gf']},ga:{stats['ga']},pts:{stats['pts']}}}"
            )
            html = re.sub(pattern, replacement, html)
    
    return html

_team_cache = {}
def _load_team_info(html):
    """从HTML中加载所有队伍信息"""
    if _team_cache:
        return
    # 解析 GROUP_DATA 获取每个队伍的名字、国旗、排名
    for m in re.finditer(
        r"\{name:'([^']+)',code:'([A-Z]+)',flag:'([^']+)',rank:(\d+),",
        html
    ):
        code = m.group(2)
        _team_cache[code] = {
            'name': m.group(1),
            'flag': m.group(3),
            'rank': int(m.group(4))
        }

def _name_for_code(html, code):
    _load_team_info(html)
    return _team_cache.get(code, {}).get('name', code)

def _flag_for_code(html, code):
    _load_team_info(html)
    return _team_cache.get(code, {}).get('flag', '🏳️')

def _rank_for_code(html, code):
    _load_team_info(html)
    return _team_cache.get(code, {}).get('rank', 50)

def main():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    html_path = os.path.join(repo_root, "index.html")
    
    if not os.path.exists(html_path):
        print(f"[ERROR] index.html not found at {html_path}")
        sys.exit(1)
    
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()
    
    print("=" * 50)
    print("2026 World Cup Score Updater")
    print("=" * 50)
    
    # 1. 从ESPN拉数据
    data = fetch_espn_data()
    if not data:
        print("[INFO] ESPN unavailable, no updates this run")
        sys.exit(0)
    
    # 2. 解析比分
    scores = parse_espn_scores(data)
    print(f"\n[INFO] Parsed {len(scores)} completed matches from ESPN")
    
    if not scores:
        print("[INFO] No completed matches found")
        sys.exit(0)
    
    # 3. 更新HTML
    new_html = update_html(html, scores)
    
    # 4. 更新小组积分榜
    new_html = update_group_standings(new_html)
    
    # 5. 写回文件
    if new_html != html:
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(new_html)
        print(f"\n✅ index.html updated and saved!")
    else:
        print(f"\nℹ️  No changes needed (scores already up to date)")

if __name__ == "__main__":
    main()
