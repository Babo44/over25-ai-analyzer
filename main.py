import os
import requests

ODDS_API_KEY = os.environ.get("ODDS_API_KEY")

matches_found = []

if ODDS_API_KEY:
    url = f"https://api.the-odds-api.com/v4/sports/upcoming/odds/?apiKey={ODDS_API_KEY}&regions=eu&markets=totals"
    try:
        res = requests.get(url)
        data = res.json()
        
        if isinstance(data, list):
            for match in data:
                # Filtriramo samo nogometne utakmice
                if not match.get("sport_key", "").startswith("soccer"):
                    continue
                    
                home = match.get("home_team", "")
                away = match.get("away_team", "")
                league = match.get("sport_title", "Nogomet")
                
                # Pretraga Over 2.5 koeficijenata
                for bm in match.get("bookmakers", []):
                    for mkt in bm.get("markets", []):
                        if mkt.get("key") == "totals":
                            for outcome in mkt.get("outcomes", []):
                                if outcome.get("name") == "Over" and outcome.get("point") == 2.5:
                                    price = outcome.get("price", 0)
                                    # Kriterij: Koeficijent između 1.60 i 1.85
                                    if 1.60 <= price <= 1.85:
                                        target_cashout = round(price / 1.20, 2)
                                        matches_found.append({
                                            "teams": f"{home} vs {away}",
                                            "league": league,
                                            "odds": price,
                                            "target": target_cashout
                                        })
    except Exception as e:
        print(f"Greška pri dohvaćanju: {e}")

# Izrada moderanog HTML sučelja
table_rows = ""
if matches_found:
    for m in matches_found:
        table_rows += f"""
        <tr>
            <td><b>{m['teams']}</b></td>
            <td>{m['league']}</td>
            <td><span class="badge odds">{m['odds']}</span></td>
            <td><span class="badge target">{m['target']}</span></td>
        </tr>
        """
else:
    table_rows = "<tr><td colspan='4' style='text-align:center;'>Trenutno nema utakmica u ponudi s Over 2.5 koeficijentom u rasponu 1.60 - 1.85.</td></tr>"

html_content = f"""
<!DOCTYPE html>
<html lang="hr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Over 2.5 Trading Analyzer</title>
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #0f172a; color: #f8fafc; padding: 20px; margin: 0; }}
        .container {{ max-width: 900px; margin: 0 auto; background: #1e293b; padding: 25px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.3); }}
        h1 {{ color: #38bdf8; margin-top: 0; font-size: 24px; }}
        p {{ color: #94a3b8; font-size: 14px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        th, td {{ padding: 12px 15px; text-align: left; border-bottom: 1px solid #334155; }}
        th {{ background-color: #334155; color: #38bdf8; font-weight: 600; }}
        tr:hover {{ background-color: #273549; }}
        .badge {{ padding: 6px 12px; border-radius: 6px; font-weight: bold; font-size: 14px; }}
        .odds {{ background-color: #0284c7; color: white; }}
        .target {{ background-color: #16a34a; color: white; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Over 2.5 Trading Analyzer</h1>
        <p>Filtrirane utakmice s početnim koeficijentom 1.60 - 1.85 i izračunatim ciljem za 20% profita (Cash Out).</p>
        <table>
            <thead>
                <tr>
                    <th>Utakmica</th>
                    <th>Liga</th>
                    <th>Početni Over 2.5</th>
                    <th>Ciljani Cashout (20% profit)</th>
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

print("Novi index.html je uspješno izgrađen!")
