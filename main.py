import os
import json
import re
import requests
from datetime import datetime, timezone, timedelta
import google.generativeai as genai

ODDS_API_KEY = os.environ.get("ODDS_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

matches_dict = {}
now_utc = datetime.now(timezone.utc)
local_offset = timedelta(hours=2) # CEST
update_timestamp = (now_utc + local_offset).strftime("%d.%m.%Y. u %H:%M:%S")

status_message = ""

if not ODDS_API_KEY:
    status_message = "⚠️ Nije postavljen ODDS_API_KEY u GitHub Secrets."
else:
    # Pretražujemo glavne nogometne lige direktno
    leagues = [
        "soccer_epl", "soccer_spain_la_liga", "soccer_germany_bundesliga",
        "soccer_italy_serie_a", "soccer_france_ligue_one", "soccer_netherlands_eredivisie",
        "soccer_portugal_primeira_liga", "soccer_turkey_super_league", "soccer_poland_ekstraklasa",
        "soccer_belgium_first_div", "soccer_germany_bundesliga2", "soccer_spain_segunda_division"
    ]
    
    for l_key in leagues:
        if len(matches_dict) >= 10:
            break
            
        url = f"https://api.the-odds-api.com/v4/sports/{l_key}/odds/?apiKey={ODDS_API_KEY}&regions=eu&markets=totals"
        try:
            res = requests.get(url)
            
            if res.status_code in [401, 429]:
                status_message = f"⚠️ PREKORAČEN JE BESPLATNI MJESEČNI LIMIT NA ODDS API-JU (Status {res.status_code})."
                break
                
            data = res.json()
            if isinstance(data, dict) and "message" in data:
                status_message = f"⚠️ Odds API poruka: {data['message']}"
                break

            if isinstance(data, list):
                for match in data:
                    if len(matches_dict) >= 10:
                        break
                        
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
                    
                    found_price = None
                    for bm in match.get("bookmakers", []):
                        for mkt in bm.get("markets", []):
                            if mkt.get("key") == "totals":
                                for outcome in mkt.get("outcomes", []):
                                    if outcome.get("name") == "Over" and outcome.get("point") == 2.5:
                                        price = outcome.get("price", 0)
                                        if 1.60 <= price <= 1.85:
                                            found_price = price
                                            break
                                    if found_price: break
                            if found_price: break
                        if found_price: break
                        
                    if found_price:
                        matches_dict[match_key] = {
                            "teams": match_key,
                            "home": home,
                            "away": away,
                            "time": formatted_time,
                            "league": league,
                            "odds": found_price,
                            "target": round(found_price / 1.20, 2)
                        }
        except Exception as e:
            print(f"Greška liga {l_key}: {e}")

ai_analyses = {}
if GEMINI_API_KEY and matches_dict:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-1.5-flash")
        
        prompt_items = []
        id_to_key = {}
        for idx, (m_key, m_val) in enumerate(matches_dict.items(), 1):
            match_id = f"M_{idx}"
            id_to_key[match_id] = m_key
            prompt_items.append(f"{match_id}: {m_val['home']} vs {m_val['away']} (Liga: {m_val['league']})")
        
        prompt_text = "\n".join(prompt_items)
        prompt = "Ti si profesionalni kladioničarski analitičar. Napiši detaljnu analizu forme i golova za sljedeće parove:\n" + prompt_text + "\n\nVrati ODGOVOR ISKLJUČIVO u JSON formatu s ključevima M_1, M_2 itd:\n{\n  \"M_1\": {\n     \"signal\": \"🟢 A+ Signal\",\n     \"forma_i_golovi\": \"Opis forme u zadnjih 5 mečeva i prosjek golova.\",\n     \"tempo_1h\": \"Procjena 1H tempa.\",\n     \"zakljucak\": \"Trgovački savjet.\"\n  }\n}"
        
        res = model.generate_content(prompt)
        json_match = re.search(r'\{.*\}', res.text, re.DOTALL)
        if json_match:
            parsed_json = json.loads(json_match.group(0))
            for match_id, analysis in parsed_json.items():
                if match_id in id_to_key:
                    ai_analyses[id_to_key[match_id]] = analysis
    except Exception as e:
        print(f"Error AI: {e}")

table_rows = ""
if status_message:
    table_rows = f"<tr><td colspan='5' style='text-align:center; color:#ef4444; font-weight:bold; padding:20px;'>{status_message}</td></tr>"
elif matches_dict:
    for match_key, m in matches_dict.items():
        analysis_data = ai_analyses.get(match_key, {})
        signal = analysis_data.get("signal", "🟢 A+ Signal" if m["odds"] <= 1.72 else "🟡 B Signal")
        forma = analysis_data.get("forma_i_golovi", f"Implicirana vjerojatnost iznosi {round((1/m['odds'])*100, 1)}%.")
        tempo = analysis_data.get("tempo_1h", "Preporučuje se praćenje In-Play statistike opasnih napada.")
        zakljucak = analysis_data.get("zakljucak", f"Ciljani Cash Out profil na {m['target']} (20% profita).")
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
    table_rows = "<tr><td colspan='5' style='text-align:center;'>Trenutno nema nadolazećih mečeva u rasponu 1.60 - 1.85 za odabrane lige.</td></tr>"

html_template = """<!DOCTYPE html>
<html lang="hr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Over 2.5 Trading Dashboard</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #0f172a; color: #f8fafc; padding: 20px; margin: 0; }
        .container { max-width: 1150px; margin: 0 auto; background: #1e293b; padding: 25px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.3); }
        h1 { color: #38bdf8; margin-top: 0; font-size: 24px; }
        p { color: #94a3b8; font-size: 14px; margin-bottom: 20px; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 14px; text-align: left; border-bottom: 1px solid #334155; vertical-align: top; }
        th { background-color: #334155; color: #38bdf8; font-weight: 600; }
        tr:hover { background-color: #243347; }
        .badge { padding: 6px 10px; border-radius: 6px; font-weight: bold; font-size: 12px; display: inline-block; whitespace: nowrap; }
        .badge-a { background-color: #065f46; color: #34d399; border: 1px solid #059669; }
        .badge-b { background-color: #78350f; color: #fbbf24; border: 1px solid #d97706; }
        .footer { margin-top: 25px; font-size: 12px; color: #64748b; text-align: right; }
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
                __TABLE_ROWS__
            </tbody>
        </table>
        <div class="footer">Zadnje automatsko osvježavanje: __TIMESTAMP__ (CEST)</div>
    </div>
</body>
</html>"""

html_content = html_template.replace("__TABLE_ROWS__", table_rows).replace("__TIMESTAMP__", update_timestamp)

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html_content)

print("Kraj izvršavanja skripte.")
