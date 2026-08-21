import os
import requests
import google.generativeai as genai

# Spajanje na API-je preko GitHub Secrets
ODDS_API_KEY = os.environ.get("ODDS_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)

# 1. Povlačenje utakmica s The-Odds-API (Pinnacle/Exchange koeficijenti)
url = f"https://api.the-odds-api.com/v4/sports/soccer/odds/?apiKey={ODDS_API_KEY}&regions=eu&markets=h2h,totals"
response = requests.get(url).json()

# 2. Slanje podataka Gemini AI-ju za filtriranje
prompt = f"""
Ti si profesionalni analitičar za trading na sportskim kladionicama.
Pregledaj ove utakmice: {response}

Izdvoji SAMO one utakmice gdje je Over 2.5 koeficijent između 1.60 i 1.85, 
i gdje timovi imaju visok potencijal za rani gol u prvih 15 minuta.
Generiraj jednostavan HTML kod s tablicom u kojoj su navedeni:
Utakmica, Liga, Početni koeficijent i Ciljani Cashout koeficijent za 20% profita.
Vrati ISKLJUČIVO čisti HTML kod bez dodatih opisa.
"""

model = genai.GenerativeModel('gemini-1.5-flash')
ai_response = model.generate_content(prompt)

# 3. Spremanje rezultata u index.html
with open("index.html", "w", encoding="utf-8") as f:
    f.write(ai_response.text)
