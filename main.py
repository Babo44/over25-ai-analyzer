import os
import requests
import google.generativeai as genai

ODDS_API_KEY = os.environ.get("ODDS_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not ODDS_API_KEY or not GEMINI_API_KEY:
    print("Greška: API ključevi nisu pronađeni u Secrets!")
    exit(1)

genai.configure(api_key=GEMINI_API_KEY)

# 1. Povlačenje utakmica
try:
    url = f"https://api.the-odds-api.com/v4/sports/upcoming/odds/?apiKey={ODDS_API_KEY}&regions=eu&markets=totals"
    res = requests.get(url)
    data = res.json()
except Exception as e:
    print(f"Greška pri dohvaćanju s Odds API-ja: {e}")
    data = []

prompt = f"""
Ti si analitičar za trading na sportskim kladionicama.
Pregledaj ove utakmice: {data}

Izdvoji mečeve gdje je Over 2.5 koeficijent između 1.60 i 1.85.
Generiraj moderan i čist HTML kod s tablicom (Stupci: Utakmica, Liga, Početni koeficijent, Ciljani Cashout za 20% profita).
Ako nema odgovarajućih mečeva u ponudi, prikaži HTML poruku: "Trenutno nema mečeva s koeficijentom u rasponu 1.60 - 1.85."

Vrati ISKLJUČIVO čisti HTML kod bez markdown oznaka.
"""

# 2. Rotacija modela ako jedan vrati 404
model_names = ['gemini-2.0-flash', 'gemini-1.5-flash-latest', 'gemini-1.5-flash']
html_code = ""

for name in model_names:
    try:
        model = genai.GenerativeModel(name)
        response = model.generate_content(prompt)
        html_code = response.text.replace("```html", "").replace("```", "").strip()
        print(f"Uspješno iskorišten model: {name}")
        break
    except Exception as e:
        print(f"Model {name} nije uspio: {e}")

if not html_code:
    html_code = "<h2>Greška u generiranju analize. Provjerite API postavke.</h2>"

# 3. Spremanje u datoteku
with open("index.html", "w", encoding="utf-8") as f:
    f.write(html_code)

print("index.html je uspješno kreiran!")
