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
local_offset = timedelta(hours=2) # CEST vremenska zona

# 1. Povlačenje i filtriranje koeficijenata
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
                                            "time": formatted_time,
                                            "league": league,
                                            "odds": price,
                                            "target": target_cashout
                                        }
                                        break
    except Exception as e:
        print(f"Greška Odds API: {e}")

# 2. Generiranje analize s ID-evima (Pouzdanije spajanje)
ai_analyses = {}
if GEMINI_API_KEY and matches_dict:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        
        match_prompt_lines = []
        id_to_key = {}
        for idx, (m_key, m_val) in enumerate(matches_dict.items(), 1):
            match_id = f"ID_{idx}"
            id_to_key[match_id] = m_key
            match_prompt_lines.append(f"- {match_id}: {m_key} (Liga: {m_val['league']})")
        
        prompt_text = "\n".join(match_prompt_lines)
        
        prompt = f"""
        Analiziraj ove utakmice za Over 2.5 In-Play trading:
        {prompt_text}

        Za SVAKU utakmicu vrati analizu u JSON formatu gdje je KLJUČ točan ID (npr. "ID_1", "ID_2"):
        {{
          "ID_1": {{
             "signal": "🟢 A+ Signal" ili "🟡 B Signal",
             "profil": "Prosjek golova i stil igre obje ekipe.",
             "tempo_1h": "Statistika i opasnost za gol u 1. poluvremenu.",
             "zakljucak": "Trgovački savjet za Cash Out."
          }}
        }}
        Vrati isključivo čisti JSON.
        """
        
        model = genai.GenerativeModel('gemini-1.5-flash', generation_config={"response_mime_type": "application/json"})
        res = model.generate_content(prompt)
        raw_json = json.loads(res.text)
        
        # Preslikavanje ID-a natrag na pravi naziv utakmice
        for m_id, a_data in raw_json.items():
            if m_id in id_to_key:
                ai_analyses[id_to_key[m_id]] = a_data
                
    except Exception as e:
        print(f"AI greška: {e}")

# 3. Sklapanje HTML Tablice
table_rows = ""
if matches_dict:
    for match_key, m in matches_dict.items():
        analysis_data = ai_analyses.get(match_key, {})
        
        signal = analysis_data.get("signal", "🟢 A+ Signal" if m["odds"] <= 1.72 else "🟡 B Signal")
        profil = analysis_data.get("profil", f"Statistički profil za {m['teams']} u ligi {m['league']}.")
        tempo = analysis_data.get("tempo_1h", "Očekuje se rano otvaranje i pritisak u prvih 30 minuta.")
        zakljucak = analysis_data.get("zakljucak", f"Ciljani Cash Out profil na {m['target']}.")
        
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
                <div><b>📊 Profil & Golovi:</b> {profil}</div>
                <div style="margin-top: 4px;"><b>⏱️ 1H Tempo:</b> {tempo}</div>
                <div style="color: #38bdf8; margin-top: 4px;"><b>💡 Zaključak:</b> {zakljucak}</div>
            </td>
        </tr>
        """
else:
    table_rows = "<tr><td colspan='5' style='text-align:center;'>Trenutno nema nadolazećih mečeva koji zadovoljavaju trgovačke kriterije (1.60 - 1.85).</td></tr>"

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
    </style>
</head>
<body>
    <div class="container">
        <h1>Over 2.5 Trading Dashboard</h1>
        <p>Aktivni In-Play signali za nadolazeće utakmice (1.60 - 1.85) s izračunom 20% Cash Out profita i AI analizom tempa 1. poluvremena.</p>
        <table>
            <thead>
                <tr>
                    <th>Utakmica & Vrijeme</th>
                    <th>Liga</th>
                    <th>Tečaj & Cilj</th>
                    <th>Signal</th>
                    <th>Napredna Trading Analiza</th>
                </tr>
            </thead>
            <tbody>
                {table_rows}
            </tbody>
        </table>
    </div>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html_content)

print("Dashboard uspješno kreiran!")
