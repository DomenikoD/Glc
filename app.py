import cloudscraper
from bs4 import BeautifulSoup
import sqlite3
import re
from datetime import datetime
from flask import Flask, render_template_string, request, redirect, url_for

app = Flask(__name__)
DB_NAME = 'njuskalo_tracker.db'

# --- BAZA PODATAKA ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS filters
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, url TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS items
                 (ad_id TEXT, filter_id INTEGER, title TEXT, link TEXT, 
                  current_price INTEGER, previous_price INTEGER, 
                  price_drop INTEGER, description TEXT, last_updated TEXT,
                  PRIMARY KEY(ad_id, filter_id))''')
    
    c.execute("SELECT count(*) FROM filters")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO filters (name, url) VALUES (?, ?)",
                  ("Mercedes GLC", "https://www.njuskalo.hr/auti/mercedes-glc?price[max]=50000&yearManufactured[min]=2019&mileage[max]=180000&accountPurpose=private"))
    conn.commit()
    conn.close()

# --- UNIVERZALNI SCRAPER ---
def scrape_all_filters():
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    c.execute("SELECT id, name, url FROM filters")
    filters = c.fetchall()
    
    for f in filters:
        filter_id, f_name, url = f[0], f[1], f[2]
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Skeniram: {f_name}")
        
        try:
            response = scraper.get(url)
            soup = BeautifulSoup(response.content, 'html.parser')
            items = soup.find_all('li', class_=re.compile(r'EntityList-item'))
            print(f"Pronađeno {len(items)} potencijalnih elemenata.")
            
            uspjesno = 0
            for item in items:
                try:
                    link_tag = item.find('a', href=re.compile(r'-oglas-\d+'))
                    if not link_tag: continue
                    href = link_tag.get('href', '')
                    link = "https://www.njuskalo.hr" + href if href.startswith('/') else href
                    title = link_tag.text.strip()
                    
                    id_match = re.search(r'oglas-(\d+)', href)
                    if not id_match: continue
                    ad_id = id_match.group(1)
                    
                    price_str = ""
                    price_tag = item.find(class_=re.compile(r'price--eur|price'))
                    if price_tag and '€' in price_tag.text:
                        price_str = price_tag.text.split(',')[0]
                    else:
                        price_match = re.search(r'([\d\.]+)\s*€', item.text)
                        if price_match: price_str = price_match.group(1)
                    
                    if not price_str: continue
                    price = int(re.sub(r'\D', '', price_str))
                    
                    desc_tag = item.find('div', class_='entity-description-main')
                    desc_text = desc_tag.text.replace('\xa0', ' ').strip() if desc_tag else ""
                    if len(desc_text) > 80: desc_text = desc_text[:77] + "..."

                    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    c.execute("SELECT current_price, price_drop FROM items WHERE ad_id=? AND filter_id=?", (ad_id, filter_id))
                    row = c.fetchone()
                    
                    if row:
                        old_price, old_drop = row[0], row[1]
                        new_drop = old_price - price if price < old_price else old_drop
                        c.execute('''UPDATE items SET current_price=?, previous_price=?, price_drop=?, 
                                     description=?, last_updated=?, title=? WHERE ad_id=? AND filter_id=?''', 
                                  (price, old_price, new_drop, desc_text, now, title, ad_id, filter_id))
                    else:
                        c.execute('''INSERT INTO items (ad_id, filter_id, title, link, current_price, previous_price, 
                                     price_drop, description, last_updated) 
                                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                                  (ad_id, filter_id, title, link, price, price, 0, desc_text, now))
                    
                    uspjesno += 1
                except Exception as e:
                    continue
            
            print(f"Uspješno spremljeno: {uspjesno} oglasa za '{f_name}'.")
        except Exception as e:
            print(f"Greška na {f_name}: {e}")
            
    conn.commit()
    conn.close()

# --- WEB SUČELJE ---
HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Njuškalo Tracker</title>
    <style>
        body { font-family: -apple-system, sans-serif; background: #f0f2f5; margin: 0; padding: 0; }
        .header { background: #fff; padding: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); position: sticky; top: 0; z-index: 100; }
        .tabs { display: flex; overflow-x: auto; white-space: nowrap; gap: 10px; padding-bottom: 5px; scrollbar-width: none; }
        .tabs::-webkit-scrollbar { display: none; }
        .tab { background: #e4e6eb; color: #050505; text-decoration: none; padding: 8px 16px; border-radius: 20px; font-size: 14px; font-weight: 500; }
        .tab.active { background: #1a73e8; color: white; }
        .tab-add { background: #333; color: white; }
        
        .container { padding: 15px; }
        .actions { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }
        .btn-group { display: flex; gap: 8px; }
        .btn-refresh { background: #34a853; color: white; text-decoration: none; padding: 8px 12px; border-radius: 8px; font-weight: bold; font-size: 13px; }
        .btn-delete { background: #d32f2f; color: white; border: none; padding: 8px 12px; border-radius: 8px; font-weight: bold; font-size: 13px; cursor: pointer; }
        
        .card { background: white; margin-bottom: 12px; padding: 15px; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        .title { font-size: 16px; font-weight: bold; margin-bottom: 5px; display: block; color: #1a73e8; text-decoration: none; }
        .info { font-size: 13px; color: #65676b; margin-bottom: 8px; }
        .price { font-size: 18px; font-weight: bold; color: #1b5e20; }
        .drop { background: #e53935; color: white; padding: 3px 8px; border-radius: 6px; font-size: 12px; font-weight: bold; margin-left: 10px; vertical-align: text-bottom;}
        
        .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); z-index: 200; justify-content: center; align-items: center; }
        .modal-content { background: white; padding: 20px; border-radius: 12px; width: 90%; max-width: 400px; }
        .modal h3 { margin-top: 0; }
        .modal input { width: 100%; padding: 10px; margin-bottom: 15px; border: 1px solid #ccc; border-radius: 6px; box-sizing: border-box; }
        .modal button { background: #1a73e8; color: white; border: none; padding: 10px 15px; width: 100%; border-radius: 6px; font-weight: bold; font-size: 16px; }
        .close-btn { background: #ccc !important; color: black !important; margin-top: 10px; }
    </style>
</head>
<body>

    <div class="header">
        <div class="tabs">
            {% for f in filters %}
                <a href="/?f={{ f[0] }}" class="tab {% if current_filter == f[0] %}active{% endif %}">{{ f[1] }}</a>
            {% endfor %}
            <a href="#" class="tab tab-add" onclick="document.getElementById('addModal').style.display='flex'">+ Dodaj</a>
        </div>
    </div>

    <div class="container">
        <div class="actions">
            <h3 style="margin:0; color:#333;">Oglasi</h3>
            <div class="btn-group">
                <a href="/scrape?f={{ current_filter }}" class="btn-refresh">🔄 Osvježi</a>
                {% if current_filter %}
                <form action="/delete_filter/{{ current_filter }}" method="POST" onsubmit="return confirm('Jesi li siguran da želiš obrisati ovaj tab i sve njegove oglase?');" style="margin:0;">
                    <button type="submit" class="btn-delete">🗑️ Obriši</button>
                </form>
                {% endif %}
            </div>
        </div>
        
        {% if not items %}
            <div class="card" style="text-align:center; color:#666;">Nema pronađenih oglasa. Osvježi ili provjeri link.</div>
        {% endif %}

        {% for item in items %}
        <div class="card">
            <a href="{{ item[3] }}" target="_blank" class="title">{{ item[2] }}</a>
            <div class="info">{{ item[7] }}</div>
            <div class="price">
                {{ "{:,}".format(item[4]) }} €
                {% if item[6] > 0 %}
                    <span class="drop">↓ -{{ item[6] }}€</span>
                {% endif %}
            </div>
        </div>
        {% endfor %}
    </div>

    <div id="addModal" class="modal">
        <div class="modal-content">
            <h3>Novi Njuškalo Filter</h3>
            <form action="/add_filter" method="POST">
                <label style="font-size:12px; color:#555;">Kratki naziv (npr. Stanovi Trešnjevka)</label>
                <input type="text" name="name" required placeholder="Unesi ime taba...">
                
                <label style="font-size:12px; color:#555;">Kopirani URL iz Njuškala</label>
                <input type="url" name="url" required placeholder="https://www.njuskalo.hr/...">
                
                <button type="submit">Spremi i skeniraj</button>
                <button type="button" class="close-btn" onclick="document.getElementById('addModal').style.display='none'">Odustani</button>
            </form>
        </div>
    </div>

</body>
</html>
"""

@app.route('/')
def index():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, name FROM filters")
    filters = c.fetchall()
    
    current_filter = request.args.get('f', type=int)
    if not current_filter and filters:
        current_filter = filters[0][0]
        
    c.execute("SELECT * FROM items WHERE filter_id=? ORDER BY price_drop DESC, last_updated DESC", (current_filter,))
    items = c.fetchall()
    conn.close()
    
    return render_template_string(HTML, filters=filters, current_filter=current_filter, items=items)

@app.route('/add_filter', methods=['POST'])
def add_filter():
    name = request.form['name']
    url = request.form['url']
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO filters (name, url) VALUES (?, ?)", (name, url))
    new_id = c.lastrowid
    conn.commit()
    conn.close()
    scrape_all_filters()
    return redirect(url_for('index', f=new_id))

@app.route('/delete_filter/<int:filter_id>', methods=['POST'])
def delete_filter(filter_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Brišemo filter
    c.execute("DELETE FROM filters WHERE id=?", (filter_id,))
    # Brišemo i sve oglase koji pripadaju tom filteru kako ne bi ostali kao "smeće" u bazi
    c.execute("DELETE FROM items WHERE filter_id=?", (filter_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/scrape')
def run_scrape():
    f = request.args.get('f')
    scrape_all_filters()
    return redirect(url_for('index', f=f))

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000)
