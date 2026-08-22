import os
import json
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

api_limit_exceeded = False

if ODDS_API_KEY:
    try:
        sports_url = f"[https://api.the-odds-api.com/v4/sports/?apiKey=](https://api.the-odds-api.com/v4/sports/?apiKey=){ODDS_API_KEY}"
        sports_req = requests.get(sports_url)
        
        if sports_req.status_code in [401, 429]:
            api_limit_exceeded = True
        else:
            sports_res = sports_req.json()
            if isinstance(sports_res, dict) and "message" in sports_res:
                msg_lower = sports_res["message"].lower()
                if any(kw in msg_lower for kw in ["limit", "exceeded", "quota", "key"]):
                    api_limit_exceeded = True

            soccer_keys = []
            if isinstance(sports_res, list):
                for s in sports_res:
                    if s.get("active") and (s.get("group") == "Soccer" or s.get("key", "").startswith("soccer")):
                        soccer_keys.append(s.get("key"))
            
            if not soccer_keys and not api_limit_exceeded:
                soccer_keys = [
                    "soccer_epl", "soccer_spain_la_liga", "soccer_germany_bundesliga",
                    "soccer_italy_serie_a", "soccer_france_ligue_one", "soccer_netherlands_eredivisie",
                    "soccer_portugal_primeira_liga", "soccer_turkey_super_league", "soccer_poland_ekstraklasa",
                    "soccer_belgium_first_div", "soccer_germany_bundesliga2", "soccer_spain_segunda_division"
                ]

            raw_matches = []

            if not api_limit_exceeded:
                for s_key in soccer_keys:
                    odds_url = f"[https://api.the-odds-api.com/v4/sports/](https://api.the-odds-api.com/v4/sports/){s_key}/odds/?apiKey={ODDS_API_KEY}&regions=eu&markets=totals"
                    odds_req = requests.get(odds_url)
                    
                    if odds_req.status_code in [401, 429]:
                        api_limit_exceeded = True
                        break
                        
                    res = odds_req.json()
                    if isinstance(res, dict) and "message" in res:
                        msg_lower = res["message"].lower()
                        if any(kw in msg_lower for kw in ["limit", "exceeded", "quota"]):
                            api_limit_exceeded = True
                            break

                    if isinstance(res, list):
                        for match in res:
                            commence_str = match.get("commence_time")
                            if not commence_str:
                                continue
                            
                            commence_dt = datetime.fromisoformat(commence_str.replace("Z", "+00:00"))
                            local_commence_dt = commence_dt + local_offset
                            
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

                raw_matches.sort(key=lambda x: x["timestamp"])
                for m in raw_matches[:10]:
                    matches_dict[m["key"]] = m

    except Exception as e:
        print(f"Greška Odds API: {e}")

# Striktna JSON AI analiza pomoću response_mime_type
ai_analyses = {}

if GEMINI_API_KEY and matches_dict and not api_limit_exceeded:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        
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

        Vrati ODGOVOR ISKLJUČIVO kao čisti JSON objekt gdje su ključevi M_1, M_2 itd.:
        {{
          "M_1": {{
             "signal": "🟢 A+ Signal" (ako su jake šanse za golove) ili "🟡 B Signal",
             "forma_i_golovi": "Kratak detaljan opis forme obje ekipe u zadnjih 5 mečeva, prosjek golova i % Over 2.5.",
             "tempo_1h": "Procjena prolaznosti Over 0.5 HT i tempa u 1. poluvremenu.",
             "zakljucak": "Trgovačka preporuka za In-Play ulazak i Cash Out."
          }}
        }}
        """
        
        candidate_models = ["gemini-1.5-flash", "gemini-1.5-pro"]
        
        for model_name in candidate_models:
            try:
                # Prisiljavamo model da vraća striktni JSON
                model = genai.GenerativeModel(
                    model_name,
                    generation_config={"response_mime_type": "application/json"}
                )
                res = model.generate_content(prompt)
                
                parsed_json = json.loads(res.text)
                for match_id, analysis in parsed_json.items():
                    if match_id in id_to_key:
                        ai_analyses[id_to_key[match_id]] = analysis
                print(f"Uspješno generiran čisti JSON preko: {model_name}")
                break
            except Exception as mod_err:
                print(f"Model {model_name} greška: {mod_err}")
                
    except Exception as e:
        print(f"AI greška: {e}")

table_rows = ""

if api_limit_exceeded:
    table_rows = "<tr><td colspan='5' style='text-align:center; color: #ef4444; font-weight: bold; padding: 20px;'>⚠️ PREKORAČEN JE BESPLATNI MJESEČNI LIMIT NA ODDS API-JU (Quota Exceeded). Promijeni API ključ ili pričekaj obnovu kredita.</td></tr>"
elif matches_dict:
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
                <b>{m['home']} vs {m['away']}</b><br>
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
    table_rows = "<tr><td colspan='5' style='text-align:center;'>Trenutno nema nadolazećih današnjih mečeva u rasponu 1.60 - 1.85.</td></tr>"

update_timestamp = local_now.strftime("%d.%m.%Y. u %H:%M:%S")

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
        .footer {{ margin-top: 25px; font-size
