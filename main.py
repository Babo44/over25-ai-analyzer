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

if ODDS_API_KEY:
    url = f"https://api.the-odds-api.com/v4/sports/upcoming/odds/?apiKey={ODDS_API_KEY}&regions=eu&markets=totals"
    try:
        res = requests.get(url)
        data = res.json()
        
        if isinstance(data, list):
            for match in data:
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
                prompt_items.append(f"{match_id}: {m_val['home']} vs {m_val['away']} (Liga: {m_val['league']})")
            
            prompt_text = "\n".join(prompt_items)
            
            prompt = f"""
            Ti si profesionalni kladioničarski analitičar. Napiši bogatu i detaljnu analizu forme i golova za sljedeće parove:
            {prompt_text}

            Za SVAKI par vrati ODGOVOR ISKLJUČIVO u valjanom JSON formatu s ključevima M_1, M_2 itd.:
            {{
              "M_1": {{
                 "signal": "🟢 A+ Signal" (ako su jake šanse za golove) ili "🟡 B Signal",
                 "forma_i_golovi": "Kratak opis forme obje ekipe u zadnjih 5 mečeva, prosjek golova i % Over 2.5.",
                 "tempo_1h": "Procjena prolaznosti Over 0.5 HT i tempa u 1. poluvremenu.",
                 "zakljucak": "Trgovačka preporuka za In-Play ulazak i Cash Out."
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

table_rows = ""
if matches_dict:
    for match_key, m in matches_dict.items():
        analysis_data = ai_analyses.get(match_key)
        
        if analysis_data:
            signal = analysis_data.get("signal", "🟢 A+ Signal" if m["odds"] <= 1.72 else "🟡 B Signal")
            forma = analysis_data.get("forma_i_golovi", "Analiza forme u izradi.")
            tempo = analysis_data.get("tempo_1h", "Očekuje se otvoren početak.")
            zakljucak = analysis_data.get("zakljucak", f"Ciljani Cash Out na {m['target']}.")
        else:
            signal = "🟢 A+ Signal" if m["odds"] <= 1.72 else "🟡 B Signal"
            implied_prob = round((1 / m['odds']) * 100, 1)
            forma = f"Kladioničarska implicirana vjerojatnost iznosi {implied_prob}%."
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
