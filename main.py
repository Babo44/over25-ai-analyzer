import os
import requests
import google.generativeai as genai

ODDS_API_KEY = os.environ.get("ODDS_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

errors_list = []

if not ODDS_API_KEY:
    errors_list.append("ODDS_API_KEY nije pronađen u GitHub Secrets.")
if not GEMINI_API_KEY:
    errors_list.append("GEMINI_API_KEY nije pronađen u GitHub Secrets.")

html_code = ""

if ODDS_API_KEY and GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    
    # 1. Povlačenje utakmica
    try:
        url = f"https://api.the-odds-api.com/v4/sports/upcoming/odds/?apiKey={ODDS_API_KEY}&regions=eu&markets=totals"
        res = requests.get(url)
        data = res.json()
    except Exception as e:
        data = []
        errors_list.append(f"Odds API greška: {e}")

    prompt = f"""
    Ti si analitičar za trading na sportskim kladionicama.
    Pregledaj ove utakmice: {data}

    Izdvoji mečeve gdje je Over 2.5 koeficijent između 1.60 i 1.85.
    Generiraj moderan i čist HTML kod s tablicom (Stupci: Utakmica, Liga, Početni koeficijent, Ciljani Cashout za 20% profita).
    Ako nema odgovarajućih mečeva u ponudi, prikaži HTML poruku: "Trenutno nema mečeva s koeficijentom u rasponu 1.60 - 1.85."

    Vrati ISKLJUČIVO čisti HTML kod bez markdown oznaka.
    """

    # 2. Pokušaj generiranja s modelima
    for model_name in ['gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-2.0-flash-exp']:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            html_code = response.text.replace("```html", "").replace("```", "").strip()
            print(f"Uspješno iskorišten model: {model_name}")
            break
        except Exception as e:
            errors_list.append(f"Model {model_name} greška: {e}")

if not html_code:
    err_msg = "<br>".join(errors_list)
    html_code = f"<div style='font-family:sans-serif; padding:20px;'><h2>Došlo je do greške u analizi:</h2><p style='color:red;'>{err_msg}</p></div>"

# 3. Spremanje u index.html
with open("index.html", "w", encoding="utf-8") as f:
    f.write(html_code)
