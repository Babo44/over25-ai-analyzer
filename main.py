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
local_now = now_utc + local_offset
local_today = local_now.date()
update_timestamp = local_now.strftime("%d.%m.%Y. u %H:%M:%S")

status_message = ""

if not ODDS_API_KEY:
    status_message = "⚠️ Nije postavljen ODDS_API_KEY u GitHub Secrets."
else:
    # 1. Povlačenje svih utakmica izravno, troši 1 kredit
    url = f"https://api.the-odds-api.com/v4/sports/upcoming/odds/?apiKey={ODDS_API_KEY}&regions=eu&markets=totals"
    try:
        res = requests.get(url)
        
        if res.status_code in [401, 429]:
            status_message = "⚠️ PREKORAČEN JE BESPLATNI MJESEČNI LIMIT NA ODDS API-JU (Quota Exceeded)."
        else:
            data = res.json()
            if isinstance(data, dict) and "message" in data:
                status_message = f"⚠️ API poruka: {data['message']}"
            elif isinstance(data, list):
                raw_matches = []
                for match in data:
                    sport_key = str(match.get("sport_key", ""))
                    if not (sport_key.startswith("soccer") or match.get("group") == "Soccer"):
                        continue
                        
                    commence_str = match.get("commence_time")
                    if not commence_str:
                        continue
                    
                    commence_dt = datetime.fromisoformat(commence_str.replace("Z", "+00:00"))
                    local_commence_dt = commence_dt + local_offset
                    
                    # STROGI FILTAR DATUMA: Samo utakmice koje se igraju DANAS i još nisu počele
                    if commence_dt <= now_utc or local_commence_dt.date() != local_today:
                        continue
                    
                    formatted_time = local_commence_dt.strftime("%d.%m. u %H:%M")
                    home = match.get("home_team", "")
                    away = match.get("away_team", "")
                    league = match.get("sport_title", "Nogomet")
                    match_key = f"{home} vs {away}"
                    
                    found_price = None
                    for bm in match.get("bookmakers", []):
                        for mkt in bm.get("markets", []):
                            if mkt.get("key") == "totals":
                                for outcome in mkt.get("outcomes", []):
                                    if outcome.get("name") == "Over" and outcome.get("point") == 2.5:
                                        price = outcome.get("price", 0)
                                        # Strogi filtar tečaja
                                        if 1.60 <= price <= 1.85:
                                            found_price = price
                                            break
                                if found_price: break
                        if found_price: break
                    
                    if found_price:
                        raw_matches.append({
                            "key": match_key,
                            "home": home,
                            "away": away,
                            "time": formatted_time,
                            "league": league,
                            "odds": found_price,
                            "target": round(found_price / 1.20, 2),
                            "timestamp": commence_dt.timestamp()
                        })

                # Sortiramo ih po vremenu početka, od onih koje kreću prve
                raw_matches.sort(key=lambda x: x["timestamp"])
                for m in raw_matches[:10]:
                    matches_dict[m["key"]] = m

    except Exception as e:
        status_message = f"⚠️ Greška pri dohvaćanju podataka: {e}"

# 2. Vraćanje na dokazano uspješni AI Prompt
ai_analyses = {}
if GEMINI_API_KEY and matches_dict and not status_message:
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
        
        # Puno precizniji i stroži prompt koji izričito zahtijeva detaljnu analizu
        prompt = f"""
        Ti si vrhunski nogometni analitičar za klađenje uživo. Napiši detaljnu, konkretnu i bogatu analizu očekivanih golova za sljedeće parove. Želim specifične podatke o formi, stilu igre i očekivanom tempu.

        Parovi:
        {prompt_text}

        MORAŠ vratiti odgovor ISKLJUČIVO u JSON formatu (ključevi moraju biti točni identifikatori poput M_1, M_2 itd.). Ne stavljaj nikakav tekst prije ni poslije JSON bloka. Koristi točno ovakvu strukturu:
        {{
          "M_1": {{
             "signal": "🟢 A+ Signal" (ako očekuješ puno golova i otvoren meč) ili "🟡 B Signal" (ako je malo opreznija utakmica),
             "forma_i_golovi": "Napiši konkretnu rečenicu o formi zadnjih 5 utakmica, ofenzivnoj snazi domačina i propusnosti obrane gosta. Spomeni % prolaza Over 2.5 ako imaš smisla za to.",
             "tempo_1h": "Detaljno procijeni kakav će biti tempo u 1. poluvremenu (npr. 'Gosti će krenuti ofenzivno, očekuje se brzi gol prije 30. minute').",
             "zakljucak": "Daj jasan trgovački savjet kada ući u okladu i gdje planirati Cash Out."
          }}
        }}
        """
        
        res = model.generate_content(prompt)
        # Pouzdano ekstrahiranje JSON-a iz teksta, ignorirajući eventualne markdown tagove (npr. ```json)
        json_match = re.search(r'\{.*\}', res.text, re.DOTALL)
        if json_match:
            parsed_json = json.loads(json_match.group(0))
            for match_id, analysis in parsed_json.items():
                if match_id in id_to_key:
                    ai_analyses[id_to_key[match_id]] = analysis
    except Exception as e:
        print(f"Error AI: {e}")

# 3. Slaganje HTML tablice
table_rows = ""
if status_message:
    table_rows = f"<tr><td colspan='5' style='text-align:center; color:#ef4444; font-weight:bold; padding:20px;'>{status_message}</td></tr>"
elif matches_dict:
    for match_key, m in matches_dict.items():
        analysis_data = ai_analyses.get(match_key)
        
        # Ako imamo bogatu analizu od AI-ja, koristi nju. Ako ne (jer je API pao), koristi rezervni tekst.
        if analysis_data and "forma_i_golovi" in analysis_data and "tempo_1h" in analysis_data:
            signal = analysis_data.get("signal", "🟢 A+ Signal" if m["odds"] <= 1.72 else "🟡 B Signal")
            forma = analysis_data["forma_i_golovi"]
            tempo = analysis_data["tempo_1h"]
            zakljucak = analysis_data.get("zakljucak", f"Ciljani Cash Out profil na {m['target']} (20% profita).")
        else:
            signal = "🟢 A+ Signal" if m["odds"] <= 1.72 else "🟡 B Signal"
            implied_prob = round((1 / m['odds']) * 100, 1)
            forma = f"Analiza trenutno nije dostupna. Kladioničarska implicirana vjerojatnost iznosi {implied_prob}%."
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
    table_rows = "<tr><td colspan='5' style='text-align:center;'>Trenutno nema današnjih utakmica u rasponu 1.60 - 1.85.</td></tr>"

# 4. Finalni HTML dokument
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
        <p>Aktivni In-Play signali za današnje utakmice (1.60 - 1.85) s izračunom 20% Cash Out profita i AI analizom forme.</p>
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
