import os
import requests
import time
from datetime import datetime, timezone, timedelta

RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY")

now_utc = datetime.now(timezone.utc)
local_offset = timedelta(hours=2) # CEST
today_str = now_utc.strftime("%Y-%m-%d")

headers = {
    "X-RapidAPI-Key": RAPIDAPI_KEY,
    "X-RapidAPI-Host": "api-football-v1.p.rapidapi.com"
}

def get_team_stats(team_id):
    if not RAPIDAPI_KEY:
        return None
    try:
        url = f"https://api-football-v1.p.rapidapi.com/v3/fixtures?team={team_id}&last=5"
        res = requests.get(url, headers=headers).json()
        fixtures = res.get("response", [])
        
        if not fixtures: return None
        
        total_goals = 0
        over_25_count = 0
        valid_games = 0
        
        for f in fixtures:
            hg = f["goals"]["home"]
            ag = f["goals"]["away"]
            if hg is not None and ag is not None:
                match_goals = hg + ag
                total_goals += match_goals
                if match_goals > 2.5:
                    over_25_count += 1
                valid_games += 1
                
        if valid_games == 0: return None
        
        avg_goals = round(total_goals / valid_games, 2)
        pct = int((over_25_count / valid_games) * 100)
        return {"avg": avg_goals, "pct": pct}
    except Exception as e:
        print(f"Greška tim {team_id}: {e}")
        return None

matches_dict = {}

if RAPIDAPI_KEY:
    print("Pretražujem današnje koeficijente za Over 2.5...")
    found_odds = {}
    page = 1
    total_pages = 1
    
    while page <= total_pages and page <= 3:
        odds_url = f"https://api-football-v1.p.rapidapi.com/v3/odds?date={today_str}&bet=5&page={page}"
        try:
            res = requests.get(odds_url, headers=headers).json()
            if "paging" in res:
                total_pages = res["paging"]["total"]
                
            for item in res.get("response", []):
                fix_id = item["fixture"]["id"]
                fixture_timestamp = item["fixture"]["timestamp"]
                commence_dt = datetime.fromtimestamp(fixture_timestamp, tz=timezone.utc)
                
                if commence_dt <= now_utc:
                    continue
                    
                for bm in item.get("bookmakers", []):
                    found_price = None
                    for bet in bm.get("bets", []):
                        if str(bet["id"]) == "5" or bet["name"] == "Goals Over/Under":
                            for val in bet["values"]:
                                if val["value"] == "Over 2.5":
                                    price = float(val["odd"])
                                    if 1.60 <= price <= 1.85:
                                        found_price = price
                                        break
                            break
                    if found_price:
                        found_odds[fix_id] = {
                            "price": found_price,
                            "timestamp": fixture_timestamp
                        }
                        break 
        except Exception as e:
            print(f"Greška na odds API-ju: {e}")
        
        page += 1

    sorted_fixtures = sorted(found_odds.items(), key=lambda x: x[1]['timestamp'])
    selected_items = sorted_fixtures[:10]
    
    if selected_items:
        print(f"Pronađeno {len(selected_items)} mečeva. Povlačim statistiku...")
        selected_ids = [str(item[0]) for item in selected_items]
        ids_str = "-".join(selected_ids)
        prices_map = {item[0]: item[1]["price"] for item in selected_items}
        
        time.sleep(6.5)
        
        fix_url = f"https://api-football-v1.p.rapidapi.com/v3/fixtures?ids={ids_str}"
        try:
            res = requests.get(fix_url, headers=headers).json()
            response_items = {str(item["fixture"]["id"]): item for item in res.get("response", [])}
            
            for fix_id_str in selected_ids:
                if fix_id_str not in response_items:
                    continue
                    
                item = response_items[fix_id_str]
                fix_id_int = int(fix_id_str)
                
                dt_utc = datetime.fromtimestamp(item["fixture"]["timestamp"], tz=timezone.utc)
                local_dt = dt_utc + local_offset
                formatted_time = local_dt.strftime("%d.%m. u %H:%M")
                
                league = item["league"]["name"]
                country = item["league"]["country"]
                home_team = item["teams"]["home"]["name"]
                home_id = item["teams"]["home"]["id"]
                away_team = item["teams"]["away"]["name"]
                away_id = item["teams"]["away"]["id"]
                
                price = prices_map[fix_id_int]
                target_cashout = round(price / 1.20, 2)
                
                time.sleep(6.5)
                home_stats = get_team_stats(home_id)
                time.sleep(6.5)
                away_stats = get_team_stats(away_id)
                
                match_key = f"{home_team} vs {away_team}"
                matches_dict[match_key] = {
                    "teams": match_key,
                    "home": home_team,
                    "away": away_team,
                    "time": formatted_time,
                    "league": f"{league} ({country})",
                    "odds": price,
                    "target": target_cashout,
                    "h_stats": home_stats,
                    "a_stats": away_stats
                }
        except Exception as e:
            print(f"Greška kod dohvaćanja detalja: {e}")

table_rows = ""
if matches_dict:
    for m in matches_dict.values():
        h_stats = m["h_stats"]
        a_stats = m["a_stats"]
        
        if h_stats and a_stats:
            combined_avg = round((h_stats["avg"] + a_stats["avg"]) / 2, 2)
            combined_pct = int((h_stats["pct"] + a_stats["pct"]) / 2)
            
            signal = "🟢 A+ Signal" if combined_pct >= 60 else "🟡 B Signal"
            signal_class = "badge-a" if "A+" in signal else "badge-b"
            
            stats_html = f"""
                <div><b>📊 Prosjek Golova (zadnjih 5):</b> {m['home']} ({h_stats['avg']}), {m['away']} ({a_stats['avg']}) | <b style="color:white">Zajednički: {combined_avg} gola</b></div>
                <div style="margin-top: 4px;"><b>🔥 Over 2.5 Prolaznost:</b> {m['home']} ({h_stats['pct']}%), {m['away']} ({a_stats['pct']}%) | <b style="color:white">Zajednički: {combined_pct}%</b></div>
                <div style="color: #38bdf8; margin-top: 6px;"><b>💡 Plan:</b> Ulazak na {m['odds']} — Ciljani Cash Out na {m['target']} čim padne 1. pogodak.</div>
            """
        else:
            signal = "🟡 B Signal"
            signal_class = "badge-b"
            stats_html = f"<div style='color:#cbd5e1;'>Podaci o rezultatu trenutno nedostupni. Ciljani Cash Out je {m['target']}.</div>"

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
            <td style="font-size: 13px; line-height: 1.5; color: #94a3b8;">{stats_html}</td>
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
    <title>Over 2.5 Verified Stats Dashboard</title>
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #0f172a; color: #f8fafc; padding: 20px; margin: 0; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: #1e293b; padding: 25px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.3); }}
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
        <h1>Over 2.5 Verified Stats Dashboard (Top 10)</h1>
        <p>In-Play signali izračunati na temelju <b>stvarnih službenih rezultata</b> iz zadnjih 5 utakmica svake ekipe.</p>
        <table>
            <thead>
                <tr>
                    <th style="width: 20%;">Utakmica & Vrijeme</th>
                    <th style="width: 15%;">Liga</th>
                    <th style="width: 10%;">Tečaj & Cilj</th>
                    <th style="width: 10%;">Signal</th>
                    <th style="width: 45%;">Provjereni Statistički Podaci (API-Football)</th>
                </tr>
            </thead>
            <tbody>
                {table_rows}
            </tbody>
        </table>
        <div class="footer">Zadnje automatsko osvježavanje: {update_timestamp} (CEST) | Izvor: API-Football</div>
    </div>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html_content)

print("Podaci uspješno izračunati!")
