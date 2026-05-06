import cloudscraper
from bs4 import BeautifulSoup
import sqlite3
import re
from datetime import datetime
from flask import Flask, render_template_string

app = Flask(__name__)
DB_NAME = 'glc_podaci.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS cars
                 (id TEXT PRIMARY KEY, title TEXT, link TEXT, 
                  current_price INTEGER, previous_price INTEGER, 
                  year INTEGER, mileage INTEGER, 
                  price_drop INTEGER, best_buy_score INTEGER, last_updated TEXT)''')
    conn.commit()
    conn.close()

def calculate_best_buy(price, year, mileage):
    if price == 0: return 0
    base_value = 36000
    year_bonus = (year - 2019) * 3500
    mileage_penalty = ((mileage - 100000) / 10000) * 900
    return int((base_value + year_bonus - mileage_penalty) - price)

def scrape_njuskalo():
    url = "https://www.njuskalo.hr/auti/mercedes-glc?price[max]=50000&yearManufactured[min]=2019&mileage[max]=180000&accountPurpose=private"
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
    
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Započinjem obradu...")
    
    try:
        response = scraper.get(url)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        items = soup.find_all('li', class_=re.compile(r'EntityList-item'))
        print(f"Pronađeno HTML elemenata (oglasa): {len(items)}")
        
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        
        uspjesno_spremljeno = 0
        
        for item in items:
            try:
                # 1. LINK I NASLOV (Tražimo bilo koji link koji u sebi ima riječ 'oglas')
                link_tag = item.find('a', href=re.compile(r'-oglas-\d+'))
                if not link_tag:
                    continue # Nije oglas (možda reklama ili naslov)
                    
                href = link_tag.get('href', '')
                link = "https://www.njuskalo.hr" + href if href.startswith('/') else href
                title = link_tag.text.strip()
                if not title: title = "Mercedes-Benz GLC"
                
                # 2. ID OGLASA (Vadimo broj iz samog linka)
                id_match = re.search(r'oglas-(\d+)', href)
                if not id_match:
                    print("-> Preskočeno: Ne mogu izvući ID iz linka.")
                    continue
                ad_id = id_match.group(1)
                
                # 3. CIJENA (Skenira cijeli tekst bloka i traži format '35.000 €' ili '35000 €')
                price_str = ""
                price_tag = item.find(class_=re.compile(r'price--eur|price'))
                if price_tag and '€' in price_tag.text:
                    price_str = price_tag.text.split(',')[0]
                else:
                    price_match = re.search(r'([\d\.]+)\s*€', item.text)
                    if price_match: price_str = price_match.group(1)
                
                if not price_str:
                    print(f"-> Preskočeno ({ad_id}): Nije pronađena cijena.")
                    continue
                    
                price = int(re.sub(r'\D', '', price_str))
                if price < 5000: # Osigurač (npr. rata leasinga umjesto cijene)
                    print(f"-> Preskočeno ({ad_id}): Cijena manja od 5000€ ({price}€).")
                    continue
                
                # 4. GODIŠTE I KILOMETRI (Skenira sav tekst unutar oglasa)
                desc_text = item.text.replace('\xa0', ' ')
                
                year = 2019 # Default
                year_match = re.search(r'Godište:\s*(\d{4})', desc_text) or re.search(r'(2019|202[0-5])\.', desc_text)
                if year_match: 
                    # Prilagodba hvatanja grupe ovisno o regex matchu
                    y_str = year_match.group(1) if len(year_match.groups()) > 0 else year_match.group(0).replace('.', '')
                    year = int(y_str)
                
                mileage = 100000 # Default
                mil_match = re.search(r'Kilometraža:\s*([\d\.]+)', desc_text) or re.search(r'([\d\.]+)\s*km', desc_text)
                if mil_match:
                    mil_str = mil_match.group(1).replace('.', '')
                    if mil_str.isdigit() and int(mil_str) > 1000:
                        mileage = int(mil_str)

                # 5. OBRADA U BAZI
                bb_score = calculate_best_buy(price, year, mileage)
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                c.execute("SELECT current_price, price_drop FROM cars WHERE id=?", (ad_id,))
                row = c.fetchone()
                
                if row:
                    old_price, old_drop = row[0], row[1]
                    new_drop = old_price - price if price < old_price else old_drop
                    c.execute('''UPDATE cars SET current_price=?, previous_price=?, price_drop=?, 
                                 best_buy_score=?, last_updated=?, title=?, year=?, mileage=? WHERE id=?''', 
                              (price, old_price, new_drop, bb_score, now, title, year, mileage, ad_id))
                else:
                    c.execute('''INSERT INTO cars (id, title, link, current_price, previous_price, 
                                 year, mileage, price_drop, best_buy_score, last_updated) 
                                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                              (ad_id, title, link, price, price, year, mileage, 0, bb_score, now))
                
                uspjesno_spremljeno += 1
                
            except Exception as e:
                print(f"-> Preskočeno oglas uslijed neočekivane greške: {e}")
                continue
                
        conn.commit()
        conn.close()
        print(f"Završeno! Uspješno spremljeno u bazu: {uspjesno_spremljeno} oglasa.")
    except Exception as e:
        print(f"Glavna greška pri spajanju: {e}")

HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: sans-serif; background: #eceff1; margin: 0; padding: 10px; }
        .card { background: white; margin-bottom: 15px; padding: 15px; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        .price { font-size: 20px; font-weight: bold; color: #2e7d32; }
        .drop { color: white; background: #d32f2f; padding: 2px 6px; border-radius: 4px; font-size: 12px; }
        .best-buy { color: white; background: #f9a825; padding: 2px 6px; border-radius: 4px; font-size: 12px; margin-left: 5px; }
        .info { font-size: 14px; color: #555; margin: 5px 0; }
        .ai-box { border-top: 1px solid #eee; margin-top: 10px; padding-top: 10px; font-size: 13px; font-style: italic; }
        a { text-decoration: none; color: #1565c0; font-weight: bold; }
        .btn { display: block; width: 90%; background: #333; color: white; text-align: center; padding: 12px; border-radius: 8px; text-decoration: none; margin: 0 auto 20px auto; font-weight: bold; }
    </style>
</head>
<body>
    <h2 style="text-align:center;">🚗 GLC Analitika</h2>
    <a href="/scrape" class="btn">🔄 OSVJEŽI PODATKE</a>
    
    {% if not cars %}
        <h4 style="text-align:center; color:#d32f2f;">Baza je i dalje prazna. Provjeri log u Termuxu!</h4>
    {% endif %}

    {% for car in cars %}
    <div class="card">
        <a href="{{ car[2] }}" target="_blank">{{ car[1] }}</a>
        <div class="info">📅 {{ car[5] }}. god | 🛣️ {{ "{:,}".format(car[6]) }} km</div>
        <div class="price">
            {{ "{:,}".format(car[3]) }} €
            {% if car[7] > 0 %}<span class="drop">↓ -{{ car[7] }}€</span>{% endif %}
            {% if car[8] > 2000 %}<span class="best-buy">🔥 BEST BUY</span>{% endif %}
        </div>
        <div class="ai-box">
            AI Score: {% if car[8] > 0 %} Cijena je {{ car[8] }}€ ispod prosjeka. {% else %} Skuplji {{ car[8]|abs }}€ od prosjeka. {% endif %}
        </div>
    </div>
    {% endfor %}
</body>
</html>
"""

@app.route('/')
def index():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT * FROM cars ORDER BY best_buy_score DESC")
    cars = c.fetchall()
    conn.close()
    return render_template_string(HTML, cars=cars)

@app.route('/scrape')
def run_scrape():
    scrape_njuskalo()
    return '<script>window.location.href="/";</script>'

if __name__ == '__main__':
    init_db()
    scrape_njuskalo()
    app.run(host='0.0.0.0', port=5000)
