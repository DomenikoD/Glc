import cloudscraper
from bs4 import BeautifulSoup
import sqlite3
import re
from datetime import datetime
from flask import Flask, render_template_string, request, redirect, url_for

app = Flask(__name__)
DB_NAME = 'njuskalo_tracker.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS filters (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, url TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS items
                 (ad_id TEXT, filter_id INTEGER, title TEXT, link TEXT, 
                  current_price INTEGER, previous_price INTEGER, 
                  price_drop INTEGER, description TEXT, last_updated TEXT, 
                  year INTEGER, mileage INTEGER,
                  PRIMARY KEY(ad_id, filter_id))''')
    
    # Automatska nadogradnja baze za novi parametar (Datum objave)
    try: c.execute("ALTER TABLE items ADD COLUMN publish_date TEXT DEFAULT ''")
    except: pass

    conn.commit()
    conn.close()

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
            uspjesno = 0
            for item in items:
                try:
                    link_tag = item.find('a', href=re.compile(r'-oglas-\d+'))
                    if not link_tag: continue
                    href = link_tag.get('href', '')
                    link = "https://www.njuskalo.hr" + href if href.startswith('/') else href
                    title = link_tag.text.strip()
                    ad_id = re.search(r'oglas-(\d+)', href).group(1)
                    
                    price_str = ""
                    price_tag = item.find(class_=re.compile(r'price--eur|price'))
                    if price_tag and '€' in price_tag.text: price_str = price_tag.text.split(',')[0]
                    else:
                        price_match = re.search(r'([\d\.]+)\s*€', item.text)
                        if price_match: price_str = price_match.group(1)
                    if not price_str: continue
                    price = int(re.sub(r'\D', '', price_str))
                    
                    desc_tag = item.find('div', class_='entity-description-main')
                    desc_text = desc_tag.text.replace('\xa0', ' ').strip() if desc_tag else ""
                    
                    year = 0
                    y_match = re.search(r'Godište:\s*(\d{4})', desc_text) or re.search(r'(201\d|202\d)\.', desc_text)
                    if y_match: year = int(y_match.group(1) if len(y_match.groups()) > 0 else y_match.group(0).replace('.',''))
                    
                    mileage = 0
                    m_match = re.search(r'Kilometraža:\s*([\d\.]+)', desc_text) or re.search(r'([\d\.]+)\s*km', desc_text)
                    if m_match: 
                        mil_str = m_match.group(1).replace('.', '')
                        if mil_str.isdigit(): mileage = int(mil_str)

                    if len(desc_text) > 80: desc_text = desc_text[:77] + "..."
                    
                    # Hvatanje datuma objave (iz <time> taga ili sličnih klasa na Njuškalu)
                    pub_date = ""
                    time_tag = item.find('time')
                    if time_tag: pub_date = time_tag.text.strip()
                    else:
                        date_elem = item.find(class_=re.compile(r'date'))
                        if date_elem: pub_date = date_elem.text.strip()
                    pub_date = pub_date.replace('Objavljen:', '').replace('Prikazan:', '').strip()

                    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    c.execute("SELECT current_price, price_drop FROM items WHERE ad_id=? AND filter_id=?", (ad_id, filter_id))
                    row = c.fetchone()
                    
                    if row:
                        old_price, old_drop = row[0], row[1]
                        if price < old_price: new_drop = old_drop + (old_price - price)
                        elif price > old_price: new_drop = 0
                        else: new_drop = old_drop

                        c.execute('''UPDATE items SET current_price=?, previous_price=?, price_drop=?, 
                                     description=?, last_updated=?, title=?, year=?, mileage=?, publish_date=? 
                                     WHERE ad_id=? AND filter_id=?''', 
                                  (price, old_price, new_drop, desc_text, now, title, year, mileage, pub_date, ad_id, filter_id))
                    else:
                        c.execute('''INSERT INTO items (ad_id, filter_id, title, link, current_price, previous_price, 
                                     price_drop, description, last_updated, year, mileage, publish_date) 
                                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                                  (ad_id, filter_id, title, link, price, price, 0, desc_text, now, year, mileage, pub_date))
                    uspjesno += 1
                except: continue
            print(f"Spremljeno {uspjesno} oglasa.")
        except Exception as e: print(f"Greška: {e}")
    conn.commit()
    conn.close()

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
        .toolbar { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 10px; margin-bottom: 15px; background: white; padding: 10px; border-radius: 8px; box-shadow: 0 1px 2px rgba(0,0,0,0.05); }
        .btn-group { display: flex; gap: 6px; }
        .btn { padding: 6px 12px; border-radius: 6px; font-size: 13px; font-weight: bold; text-decoration: none; border: none; cursor: pointer; }
        .btn-green { background: #34a853; color: white; }
        .btn-blue { background: #1a73e8; color: white; }
        .btn-red { background: #d32f2f; color: white; }
        select { padding: 6px; border-radius: 6px; border: 1px solid #ccc; font-size: 13px; background: white; }
        .card { background: white; margin-bottom: 12px; padding: 15px; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); border-left: 4px solid #1a73e8;}
        .title { font-size: 16px; font-weight: bold; margin-bottom: 8px; display: block; color: #1a73e8; text-decoration: none; line-height: 1.3;}
        .info-row { font-size: 13px; color: #444; margin-bottom: 8px; background: #f8f9fa; padding: 6px; border-radius: 6px; font-weight: 500;}
        .info-desc { font-size: 12px; color: #666; margin-bottom: 8px; }
        .price { font-size: 18px; font-weight: bold; color: #1b5e20; }
        .drop { background: #e53935; color: white; padding: 3px 8px; border-radius: 6px; font-size: 12px; font-weight: bold; margin-left: 10px; vertical-align: middle;}
        .ai-box { margin-top: 10px; padding-top: 8px; border-top: 1px dashed #ccc; font-size: 13px; }
        .ai-good { color: #2e7d32; font-weight: bold; }
        .ai-bad { color: #c62828; }
        .best-buy-badge { background: #f9a825; color: #000; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: bold; vertical-align: middle; margin-left: 5px;}
        .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); z-index: 200; justify-content: center; align-items: center; }
        .modal-content { background: white; padding: 20px; border-radius: 12px; width: 90%; max-width: 400px; }
        .modal input { width: 100%; padding: 10px; margin-bottom: 15px; border: 1px solid #ccc; border-radius: 6px; box-sizing: border-box; }
        .close-btn { background: #ccc !important; color: black !important; margin-top: 10px; }
    </style>
</head>
<body>
    <div class="header">
        <div class="tabs">
            {% for f in filters %}
                <a href="/?f={{ f['id'] }}" class="tab {% if current_filter == f['id'] %}active{% endif %}">{{ f['name'] }}</a>
            {% endfor %}
            <a href="#" class="tab tab-add" onclick="document.getElementById('addModal').style.display='flex'">+ Dodaj</a>
        </div>
    </div>
    <div class="container">
        <div class="toolbar">
            <div class="btn-group">
                <a href="/scrape?f={{ current_filter }}" class="btn btn-green">🔄 Osvježi</a>
                {% if filter_obj %}
                <button onclick="openEditModal('{{ filter_obj['name'] }}', '{{ filter_obj['url'] }}')" class="btn btn-blue">✏️</button>
                <form action="/delete_filter/{{ current_filter }}" method="POST" onsubmit="return confirm('Brisati tab?');" style="margin:0;">
                    <button type="submit" class="btn btn-red">🗑️</button>
                </form>
                {% endif %}
            </div>
            <form method="GET" style="margin:0;">
                <input type="hidden" name="f" value="{{ current_filter }}">
                <select name="sort" onchange="this.form.submit()">
                    <option value="default" {% if sort_by == 'default' %}selected{% endif %}>Zadano (Pad cijene)</option>
                    <option value="price_asc" {% if sort_by == 'price_asc' %}selected{% endif %}>Najjeftinije</option>
                    <option value="price_desc" {% if sort_by == 'price_desc' %}selected{% endif %}>Najskuplje</option>
                    <option value="newest" {% if sort_by == 'newest' %}selected{% endif %}>Najnovije (Zadnje ažurirano)</option>
                    {% if is_car %}
                    <option value="km_asc" {% if sort_by == 'km_asc' %}selected{% endif %}>Najmanje km</option>
                    <option value="best_buy" {% if sort_by == 'best_buy' %}selected{% endif %}>AI Best Buy</option>
                    {% endif %}
                </select>
            </form>
        </div>
        
        {% if not items %}<div class="card" style="text-align:center; color:#666;">Nema podataka. Probaj Osvježiti.</div>{% endif %}
        
        {% for item in items %}
        <div class="card">
            <a href="{{ item['link'] }}" target="_blank" class="title">{{ item['title'] }}</a>
            
            {% if is_car and item['year'] > 0 %}
                <div class="info-row">
                    📅 {{ item['year'] }}. god &nbsp;|&nbsp; 
                    🛣️ {{ "{:,}".format(item['mileage']).replace(',', '.') }} km 
                    {% if item.get('publish_date') %}&nbsp;|&nbsp; 🕒 {{ item['publish_date'] }}{% endif %}
                </div>
            {% else %}
                <div class="info-desc">{{ item['description'] }}</div>
                {% if item.get('publish_date') %}
                    <div class="info-desc" style="color:#888;">🕒 Objavljeno: {{ item['publish_date'] }}</div>
                {% endif %}
            {% endif %}

            <div class="price">
                {{ "{:,}".format(item['current_price']) }} €
                {% if item['price_drop'] > 0 %} <span class="drop">↓ -{{ item['price_drop'] }}€</span> {% endif %}
                {% if item.get('ai_score', 0) > 1500 %} <span class="best-buy-badge">🔥 TOP PRILIKA</span> {% endif %}
            </div>
            
            {% if is_car and item['year'] > 0 %}
            <div class="ai-box">
                <strong>AI Analiza:</strong> 
                {% if item.get('ai_score', 0) > 0 %}
                    <span class="ai-good">Cijena je {{ item['ai_score'] }}€ niža</span> za prosjek oglasa.
                {% else %}
                    <span class="ai-bad">Oko {{ item.get('ai_score', 0)|abs }}€ iznad tržišnog prosjeka.</span>
                {% endif %}
            </div>
            {% endif %}
        </div>
        {% endfor %}
    </div>

    <div id="addModal" class="modal">
        <div class="modal-content">
            <h3>Novi Filter</h3>
            <form action="/add_filter" method="POST">
                <input type="text" name="name" required placeholder="Ime (npr. Audi A4)">
                <input type="url" name="url" required placeholder="Njuškalo URL">
                <button type="submit" class="btn btn-blue" style="width:100%; padding:10px;">Spremi</button>
                <button type="button" class="btn close-btn" style="width:100%;" onclick="document.getElementById('addModal').style.display='none'">Odustani</button>
            </form>
        </div>
    </div>
    <div id="editModal" class="modal">
        <div class="modal-content">
            <h3>Uredi Filter</h3>
            <form action="/edit_filter/{{ current_filter }}" method="POST">
                <input type="text" id="edit_name" name="name" required>
                <input type="url" id="edit_url" name="url" required>
                <button type="submit" class="btn btn-blue" style="width:100%; padding:10px;">Spremi izmjene</button>
                <button type="button" class="btn close-btn" style="width:100%;" onclick="document.getElementById('editModal').style.display='none'">Odustani</button>
            </form>
        </div>
    </div>
    <script>
        function openEditModal(name, url) {
            document.getElementById('edit_name').value = name;
            document.getElementById('edit_url').value = url;
            document.getElementById('editModal').style.display = 'flex';
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM filters")
    filters = [dict(row) for row in c.fetchall()]
    current_filter = request.args.get('f', type=int)
    if not current_filter and filters: current_filter = filters[0]['id']
    filter_obj = next((f for f in filters if f['id'] == current_filter), None)
    is_car = filter_obj and ('auti' in filter_obj['url'].lower() or 'osobni-automobili' in filter_obj['url'].lower())
    sort_by = request.args.get('sort', 'default')
    
    order_clause = "ORDER BY price_drop DESC, last_updated DESC"
    if sort_by == 'price_asc': order_clause = "ORDER BY current_price ASC"
    elif sort_by == 'price_desc': order_clause = "ORDER BY current_price DESC"
    elif sort_by == 'newest': order_clause = "ORDER BY last_updated DESC"
    elif sort_by == 'km_asc': order_clause = "ORDER BY mileage ASC"
    
    c.execute(f"SELECT * FROM items WHERE filter_id=? {order_clause}", (current_filter,))
    items = [dict(row) for row in c.fetchall()]
    conn.close()

    if is_car and items:
        valid = [i for i in items if i['year'] > 0 and i['mileage'] > 0 and i['current_price'] > 0]
        if valid:
            avg_price = sum(i['current_price'] for i in valid) / len(valid)
            avg_year = sum(i['year'] for i in valid) / len(valid)
            avg_mil = sum(i['mileage'] for i in valid) / len(valid)
            for i in items:
                if i['year'] > 0:
                    y_diff = i['year'] - avg_year
                    m_diff = i['mileage'] - avg_mil
                    expected = avg_price + (y_diff * 1800) - (m_diff * 0.06)
                    i['ai_score'] = int(expected - i['current_price'])
        if sort_by == 'best_buy':
            items.sort(key=lambda x: x.get('ai_score', -99999), reverse=True)

    return render_template_string(HTML, filters=filters, current_filter=current_filter, filter_obj=filter_obj, items=items, is_car=is_car, sort_by=sort_by)

@app.route('/add_filter', methods=['POST'])
def add_filter():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO filters (name, url) VALUES (?, ?)", (request.form['name'], request.form['url']))
    new_id = c.lastrowid
    conn.commit()
    conn.close()
    return redirect(url_for('index', f=new_id))

@app.route('/edit_filter/<int:filter_id>', methods=['POST'])
def edit_filter(filter_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE filters SET name=?, url=? WHERE id=?", (request.form['name'], request.form['url'], filter_id))
    conn.commit()
    conn.close()
    return redirect(url_for('index', f=filter_id))

@app.route('/delete_filter/<int:filter_id>', methods=['POST'])
def delete_filter(filter_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM filters WHERE id=?", (filter_id,))
    c.execute("DELETE FROM items WHERE filter_id=?", (filter_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/scrape')
def run_scrape():
    scrape_all_filters()
    return redirect(url_for('index', f=request.args.get('f')))

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000)
