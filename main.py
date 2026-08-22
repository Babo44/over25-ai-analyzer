import os
import json
import re
import requests
import time
from datetime import datetime, timezone, timedelta
import google.generativeai as genai

RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

now_utc = datetime.now(timezone.utc)
local_offset = timedelta(hours=2) # CEST
today_str = now_utc.strftime("%Y-%m-%d")
tomorrow_str = (now_utc + timedelta(days=1)).strftime("%Y-%m-%d")

headers = {
    "X-RapidAPI-Key": RAPIDAPI_KEY,
    "X-RapidAPI-Host": "api-football-v1.p.rapidapi.com"
}

EXCLUDE_LEAGUES = ["u19", "u21", "u20", "u23", "reserve", "oberliga", "amateur", "youth", "women", "žene"]

def is_valid_league(league_name):
    name_lower = league_name.lower()
    return not any(ex in name_lower for ex in EXCLUDE_LEAGUES)

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
                if match_goals > 2.5: over_25_count += 1
                valid_games += 1
        if valid_games == 0: return None
        return {
            "avg": round(total_goals / valid_games, 2),
            "pct": int((over_25_count / valid_games) * 100)
        }
    except Exception as e:
        print(f"Greška stat: {e}")
        return None

matches_dict = {}

# 1. Povlačenje ponude s API-Football (s pauzama od 14s)
if RAPIDAPI_KEY:
    print("Dohvaćam ponudu (pauze 14s za potpunu sigurnost)...")
    found_odds = {}
    
    for date_str in [today_str, tomorrow_str]:
        if len(found_odds) >= 15:
            break
        for page in range(1, 4):
            if len(found_odds) >= 15:
                break
            odds_url = f"https://api-football-v1.p.rapidapi.com/v3/odds?date={date_str}&bet=5&page={page}"
            try:
                res = requests.get(odds_url, headers=headers).json()
                for item in res.get("response", []):
                    fix_id = item["fixture"]["id"]
                    fixture_timestamp = item["fixture"]["timestamp"]
                    commence_dt = datetime.fromtimestamp(fixture_timestamp, tz=timezone.utc)
                    
                    if commence_dt <= now_utc:
                        continue
                        
                    league_name = item.get("league", {}).get("name", "")
                    if not is_valid_league(league_name):
                        continue
                        
                    found_price = None
                    for bm in item.get("bookmakers", []):
                        for bet in bm.get("bets", []):
                            if str(bet["id"]) == "5" or bet["name"] == "Goals Over/Under":
                                for val in bet["values"]:
                                    if val["value"] == "Over 2.5":
                                        price = float(val["odd"])
                                        if 1.60 <= price <= 1.85:
                                            found_price = price
                                            break
                                if found_price: break
                        if found_price:
                            found_odds[fix_id] = {
                                "price": found_price,
                                "timestamp": fixture_timestamp,
                                "league": league_name,
                                "country": item.get("league", {}).get("country", "")
                            }
                            break
            except Exception as e:
                print(f"Greška odds: {e}")
            
            time.sleep(14)

    # Sortiranje i odabir top 10
    sorted_fixtures = sorted(found_odds.items(), key=lambda x: x[1]['timestamp'])
    selected_items = sorted_fixtures[:10]
    
    if selected_items:
        selected_ids = [str(item[0]) for item in selected_items]
        ids_str = "-".join(selected_ids)
        
        time.sleep(14)
        fix_url = f"https://api-football-v1.p.rapidapi.com/v3/fixtures?ids={ids_str}"
        try:
            res = requests.get(fix_url, headers=headers).json()
            response_items = {str(item["fixture"]["id"]): item for item in res.get("response", [])}
            
            for fix_id_str in selected_ids:
                if fix_id_str not in response_items:
                    continue
                item = response_items[fix_id_str]
                fix_id_int = int(fix_id_str)
                info = found_odds[fix_id_int]
                
                dt_utc = datetime.fromtimestamp(item["fixture"]["timestamp"], tz=timezone.utc)
                local_dt = dt_utc + local_offset
                formatted_time = local_dt.strftime("%d.%m. u %H:%M")
                
                home_team = item["teams"]["home"]["name"]
                home_id = item["teams"]["home"]["id"]
                away_team = item["teams"]["away"]["name"]
                away_id = item["teams"]["away"]["id"]
                price = info["price"]
                
                time.sleep(14)
                home_stats = get_team_stats(home_id)
                time.sleep(14)
                away_stats = get_team_stats(away_id)
                
                match_key = f"{home_team} vs {away_team}"
                matches_dict[match_key] = {
                    "teams": match_key,
                    "home": home_team,
                    "away": away_team,
                    "time": formatted_time,
                    "league": f"{info['league']} ({info['country']})",
                    "odds": price,
                    "target": round(price / 1.20, 2),
                    "h_stats": home_stats,
                    "a_stats": away_stats
                }
        except Exception as e:
            print(f"Greška detalji: {e}")

# 2. Gemini AI Analiza
ai_analyses = {}
if GEMINI_API_KEY and matches_dict:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        active_model_name = None
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                active_model_name = m.name
                break
        
        if active_model_name:
            id_to_key = {}
            prompt_items = []
            for idx, (m_key, m_val) in enumerate(matches_dict.items(), 1):
                match_id = f"M_{idx}"
                id_to_key[match_id] = m_key
                h_st = m_val["h_stats"]
                a_st = m_val["a_stats"]
                st_info = f" [Statistika: {m_val['home']} avg {h_st['avg'] if h_st else 'N/A'}, {m_val['away']} avg {a_st['avg'] if a_st else 'N/A'}]" if h_st else ""
                prompt_items.append(f"{match_id}: {m_val['home']} vs {m_val['away']} (Liga: {m_val['league']}){st_info}")
            
            prompt_text = "\n".join(prompt_items)
            prompt = f"""
            Ti si profesionalni kladioničarski analitičar. Napiši bogatu analizu forme i 1H tempa za parove:
            {prompt_text}

            Za SVAKI par vrati ODGOVOR ISKLJUČIVO u valjanom JSON formatu s ključevima M_1, M_2 itd.:
            {{
              "M_1": {{
                 "signal": "🟢 A+ Signal" ili "🟡 B Signal",
                 "forma_i_golovi": "Kratak detaljan opis forme obje ekipe u zadnjih 5 mečeva, prosjek golova i % Over 2.5.",
                 "tempo_1h": "Procjena 1. poluvremena i Over 0.5 HT prolaza u %.",
                 "zakljucak": "Trgovačka preporuka za In-Play i Cash Out."
              }}
            }}
            """
            
            model = genai.GenerativeModel(active_model_name)
            res = model.generate_content(prompt)
            json_match = re.search(r'\{.*\}', res.text, re.DOTALL)
            if json_match:
                parsed_json = json.loads(json_match.group(0))
                for match_id, analysis in parsed_json.items():
                    if match_id in id_to_key:
                        ai_analyses[id_to_key[match_id]] = analysis
    except Exception as e:
        print(f"AI greška: {e}")

# 3. HTML Izrada
table_rows = ""
if matches_dict:
    for match_key, m in matches_dict.items():
        analysis_data = ai_analyses.get(match_key)
        
        if analysis_data:
            signal = analysis_data.get("signal", "🟢 A+ Signal" if m["odds"] <= 1.72 else "🟡 B Signal")
            forma = analysis_data.get("forma_i_golovi", "Analiza forme trenutno u izradi.")
            tempo = analysis_data.get("tempo_1h", "Očekuje se pritisak u ranim minutama.")
            zakljucak = analysis_data.get("zakljucak", f"Ciljani Cash Out na {m['target']}.")
        else:
            signal = "🟢 A+ Signal" if m["odds"] <= 1.72 else "🟡 B Signal"
            h_s = m["h_stats"]
            a_s = m["a_stats"]
            if h_s and a_s:
                forma = f"{m['home']} prosjek {h_s['avg']} gola ({h_s['pct']}% Over 2.5). {m['away']} prosjek {a_s['avg']} gola ({a_s['pct']}% Over 2.5)."
            else:
                forma = f"Implicirana kladioničarska vjerojatnost iznosi {round((1/m['odds'])*100, 1)}%."
            tempo = "Preporučuje se praćenje In-Play statistike opasnih napada."
            zakljucak = f"Ciljani Cash Out profil na {m['target']} (20% profita)."

        signal_class = "badge-a" if "A+" in signal else "badge-b"

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
            <td style="font-size: 13px; line-height: 1.5;">
                <div><b>📊 Stvarna Forma & Golovi:</b> {forma}</div>
                <div style="margin-top: 4px;"><b>⏱️ 1H Tempo:</b> {tempo}</div>
                <div style="color: #38bdf8; margin-top: 4px;"><b>💡 Trading Plan:</b> {zakljucak}</div>
            </td>
        </tr>
        """
else:
    table_rows = "<tr><td colspan='5' style='text-align:center;'>Trenutno nema nadolazećih mečeva u rasponu 1.60 - 1.85.</td></tr>"

update_timestamp = (datetime.now(timezone.utc) + local_offset).strftime("%d.%m.%Y. u %H:%M:%S")

html_content = f"""
<!DOCTYPE html>
<html lang="hr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Over 2.5 Trading Dashboard</title>
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
        <h1>Over 2.5 Trading Dashboard</h1>
        <p>Aktivni In-Play signali za nadolazeće utakmice (1.60 - 1.85) s izračunom 20% Cash Out profita i AI analizom forme.</p>
        <table>
            <thead>
                <tr>
                    <th>Utakmica & Vrijeme</th>
                    <th>Liga</th>
                    <th>Tečaj & Cilj</th>
                    <th>Signal</th>
                    <th>Stvarna Forma, Golovi & Trading Plan</th>
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

print("Kraj izvršavanja skripte.")
