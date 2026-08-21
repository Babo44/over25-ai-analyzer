import os
import requests
from datetime import datetime, timezone, timedelta

ODDS_API_KEY = os.environ.get("ODDS_API_KEY")
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY")

matches_dict = {}
now_utc = datetime.now(timezone.utc)
local_offset = timedelta(hours=2) # CEST

def get_team_stats(team_name):
    """Povlači zadnjih 5 utakmica tima s API-Football i računa stvarne golove."""
    if not RAPIDAPI_KEY:
        return None
    
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": "api-football-v1.p.rapidapi.com"
    }
    
    try:
        # 1. Pronađi ID tima
        search_url = f"https://api-football-v1.p.rapidapi.com/v3/teams?search={team_name}"
        res = requests.get(search_url, headers=headers).json()
        
        if not res.get("response"):
            return None
            
        team_id = res["response"][0]["team"]["id"]
        
        # 2. Povuci zadnjih 5 završenih utakmica
        fixtures_url = f"https://api-football-v1.p.rapidapi.com/v3/fixtures?team={team_id}&last=5"
        f_res = requests.get(fixtures_url, headers=headers).json()
        
        fixtures = f_res.get("response", [])
        if not fixtures:
            return None
            
        total_goals = 0
        over_25_count = 0
        
        for f in fixtures:
            home_goals = f["goals"]["home"] or 0
            away_goals = f["goals"]["away"] or 0
            match_goals = home_goals + away_goals
            
            total_goals += match_goals
            if match_goals > 2.5:
                over_25_count += 1
                
        avg_goals = round(total_goals / len(fixtures), 2)
        over_25_pct = int((over_25_count / len(fixtures)) * 100)
        
        return {
            "avg": avg_goals,
            "pct": over_25_pct,
            "games": len(fixtures)
        }
    except Exception as e:
        print(f"Greška za tim {team_name}: {e}")
        return None

# 1. Povlačenje utakmica s Odds API-ja
if ODDS_API_KEY:
    url = f"https://api.the-odds-api.com/v4/sports/upcoming/odds/?apiKey={ODDS_API_KEY}&regions=eu&markets=totals"
    try:
        res = requests.get(url).json()
        if isinstance(res, list):
            for match in res:
                if not match.get("sport_key", "").startswith("soccer"):
                    continue
                
                commence_str = match.get("commence_time")
                if not commence_str:
                    continue
                
                commence_dt = datetime.fromisoformat(commence_str.replace("Z", "+00:00"))
                if commence_dt <= now_utc:
                    continue
                
                local_dt = commence_dt + local_offset
                formatted_time = local_dt.strftime("%d.%m. u %H:%M")
                    
                home = match.get("home_team", "")
                away = match.get("away_team", "")
                league = match.get("sport_title", "Nogomet")
                match_key = f"{home} vs {away}"
                
                if match_key in matches_dict:
                    continue
                
                for bm in match.get("bookmakers", []):
                    for mkt in bm.get("markets", []):
                        if mkt.get("key") == "totals":
                            for outcome in mkt.get("outcomes", []):
                                if outcome.get("name") == "Over" and outcome.get("point") == 2.5:
                                    price = outcome.get("price", 0)
                                    if 1.60 <= price <= 1.85:
                                        target_cashout = round(price / 1.20, 2)
                                        matches_dict[match_key] = {
                                            "teams": match_key,
                                            "home": home,
                                            "away": away,
                                            "time": formatted_time,
                                            "league": league,
                                            "odds": price,
                                            "target": target_cashout
                                        }
                                        break
    except Exception as e:
        print(f"Greška Odds API: {e}")

# 2. Sklapanje točnih i provjerenih podataka u HTML
table_rows = ""
if matches_dict:
    for match_key, m in matches_dict.items():
        home_stats = get_team_stats(m["home"])
        away_stats = get_team_stats(m["away"])
        
        if home_stats and away_stats:
            combined_avg = round((home_stats["avg"] + away_stats["avg"]) / 2, 2)
            combined_pct = int((home_stats["pct"] + away_stats["pct"]) / 2)
            
            signal = "🟢 A+ Signal" if combined_pct >= 60 else "🟡 B Signal"
            signal_class = "badge-a" if "A+" in signal else "badge-b"
            
            stats_html = f"""
                <div><b>📊 Prosjek Golova (Zadnjih 5 mečeva):</b> {m['home']} ({home_stats['avg']}), {m['away']} ({away_stats['avg']}) | <b>Zajednički: {combined_avg} gola/utakmici</b></div>
                <div style="margin-top: 4px;"><b>🔥 Over 2.5 Prolaznost:</b> {m['home']} ({home_stats['pct']}%), {m['away']} ({away_stats['pct']}%) | <b>Ukupni prosjek prolaza: {combined_pct}%</b></div>
                <div style="color: #38bdf8; margin-top: 4px;"><b>💡 Trading Plan:</b> Ulazak na tečaj {m['odds']} — Ciljani Cash Out na {m['target']} čim padne 1. pogodak.</div>
            """
        else:
            signal = "🟡 B Signal"
            signal_class = "badge-b"
            stats_html = f"""
                <div><b>📊 Profil Tečaja:</b> Implicirana kladioničarska vjerojatnost iznosi {round((1/m['odds'])*100, 1)}%.</div>
                <div style="color: #38bdf8; margin-top: 4px;"><b>💡 Trading Plan:</b> Pratiti utakmicu live i raditi Cash Out na metu {m['target']}.</div>
            """

        table_rows += f"""
        <tr>
            <td>
                <b>{m['teams']}</b><br>
                <small style="color: #94a3b8;">{m['time']}</small>
            </td>
            <td>{m['league']}</td>
            <td>
                <b>{m['odds']}</b><br>
                <small style="color: #10b981;">Cilj: {m['target']}</small>
            </td>
            <td><span class="badge {signal_class}">{signal}</span></td>
            <td style="font-size: 13px; line-height: 1.5;">{stats_html}</td>
        </tr>
        """
else:
    table_rows = "<tr><td colspan='5' style='text-align:center;'>Trenutno nema nadolazećih utakmica u rasponu 1.60 - 1.85.</td></tr>"

update_timestamp = (datetime.now(timezone.utc) + local_offset).strftime("%d.%m.%Y. u %H:%M:%S")

html_content = f"""
<!DOCTYPE html>
<html lang="hr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Over 2.5 Real Stats Trading Dashboard</title>
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #0f172a; color: #f8fafc; padding: 20px; margin: 0; }}
        .container {{ max-width: 1150px; margin: 0 auto; background: #1e293b; padding: 25px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.3); }}
        h1 {{ color: #38bdf8; margin-top: 0; font-size: 24px; }}
        p {{ color: #94a3b8; font-size: 14px; margin-bottom: 20px; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 14px; text-align: left; border-bottom: 1px solid #334155; vertical-align: top; }}
        th {{ background-color: #334155; color: #38bdf8; font-weight: 600; }}
        tr:hover {{ background-color: #243347; }}
        .badge {{ padding: 6px 10px; border-radius: 6px; font-weight: bold; font-size: 12px; display: inline-block; whitespace: nowrap; }}
        .badge-a {{ background-color: #065f46; color: #34d399; border: 1px solid #059669; }}
        .badge-b {{ background-color: #78350f; color: #fbbf24; border: 1px solid #d97706; }}
        .footer {{ margin-top: 25px; font-size: 12px; color: #64748b; text-align: right; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Over 2.5 Verified Stats Dashboard</h1>
        <p>In-Play signali izračunati na temelju <b>stvarnih rezultata zadnjih 5 utakmica</b> obje ekipe.</p>
        <table>
            <thead>
                <tr>
                    <th>Utakmica & Vrijeme</th>
                    <th>Liga</th>
                    <th>Tečaj & Cilj</th>
                    <th>Signal</th>
                    <th>Provjereni Statistički Podaci (API-Football)</th>
                </tr>
            </thead>
            <tbody>
                {table_rows}
            </tbody>
        </table>
        <div class="footer">Zadnje automatsko osvježavanje: {update_timestamp} (CEST)</div>
    </div>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html_content)

print("Podaci uspješno izračunati i zapisani!")
