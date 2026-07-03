import discord
import asyncio
import random
import os
import re
import json
import logging
from google import genai
from flask import Flask, render_template_string, jsonify
from threading import Thread
from datetime import datetime, timedelta, timezone

# =========================================================
# 1. VARIABEL GLOBAL (STATE, TIMERS, & MODE)
# =========================================================
START_TIME_UTC = datetime.now(timezone.utc)
last_activity_time = datetime.now(timezone.utc)
last_send_time = datetime.now(timezone.utc)

is_paused = False  
is_triggering_c = False
quiz_channel_id = None
client = None  

# 🛑 FITUR BARU: Mode & Rate Limit Tracker
bot_mode = "fast" # Pilihan: "fast" atau "slow"
rate_limit_count = 0

# =========================================================
# 2. PENCEGAT LOG UNTUK MENGHITUNG RATE LIMIT (429)
# =========================================================
class RateLimitHandler(logging.Handler):
    def emit(self, record):
        global rate_limit_count
        if record.levelno >= logging.WARNING:
            msg = self.format(record).lower()
            if "rate limited" in msg or "429" in msg:
                rate_limit_count += 1

# Pasang "Penyadap" ke logger HTTP bawaan discord.py
rl_handler = RateLimitHandler()
logging.getLogger('discord.http').addHandler(rl_handler)
# Set logging minimal ke INFO agar tidak terlalu spam di console Render
logging.basicConfig(level=logging.INFO)


# =========================================================
# 3. SETUP WEB SERVER MINI, REKAPAN HADIAH, & DASHBOARD
# =========================================================
app = Flask('')
DB_FILE = "loot_history.json"

def load_loot_history():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f: return json.load(f)
        except: return []
    return []

def save_loot_history(data):
    try:
        with open(DB_FILE, "w") as f: json.dump(data, f, indent=4)
    except Exception as e: print(f"[ERROR DB] {e}")

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Loot Kuis Dashboard</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
            background-color: #1e1e24; color: #fff; margin: 0; padding: 20px; 
            height: 100vh; box-sizing: border-box; display: flex; flex-direction: column; overflow: hidden;
        }
        h2 { 
            color: #5865F2; border-bottom: 2px solid #5865F2; padding-bottom: 10px; margin-top: 0;
            display: flex; justify-content: space-between; align-items: center; flex-shrink: 0;
        }
        
        .stats-box { 
            background-color: #2f3136; padding: 15px; border-radius: 8px; 
            margin-bottom: 15px; border-left: 4px solid #43b581; flex-shrink: 0;
        }
        .stats-info p { margin: 5px 0; font-size: 0.95em; color: #dcddde; }
        .stats-info strong { color: #fff; }
        
        .stats-grid { 
            display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); 
            gap: 10px; margin-top: 15px; 
        }
        .stat-item { 
            background: #202225; padding: 10px; border-radius: 5px; 
            text-align: center; font-size: 0.9em; color: #b9bbbe; 
        }
        .stat-item span { display: block; font-size: 1.4em; font-weight: bold; color: #faa61a; margin-top: 5px; }

        .control-panel { 
            margin-top: 15px; padding-top: 15px; border-top: 1px solid #4f545c; 
            display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px;
        }
        .control-info { display: flex; flex-direction: column; gap: 5px; }
        .status-badge { font-weight: bold; padding: 3px 8px; border-radius: 5px; background-color: #202225; }
        .btn { border: none; padding: 10px 15px; border-radius: 5px; font-weight: bold; cursor: pointer; transition: 0.2s; font-size: 0.9em; }
        
        .btn-start { background-color: #43b581; color: white; }
        .btn-start:hover { background-color: #3ca374; }
        .btn-pause { background-color: #ed4245; color: white; }
        .btn-pause:hover { background-color: #d83c3e; }
        
        .btn-mode { background-color: #5865F2; color: white; }
        .btn-mode:hover { background-color: #4752c4; }
        
        .btn:disabled { opacity: 0.6; cursor: not-allowed; }

        .table-container { flex-grow: 1; overflow-y: auto; background-color: #2f3136; border-radius: 8px; position: relative; }
        table { width: 100%; border-collapse: collapse; }
        thead th { 
            position: sticky; top: 0; background-color: #5865F2; color: white; 
            z-index: 1; padding: 12px; text-align: left; box-shadow: 0 2px 2px -1px rgba(0,0,0,0.4);
        }
        tbody td { padding: 12px; text-align: left; border-bottom: 1px solid #202225; }
        tr:hover { background-color: #35383e; }
        .reward { color: #43b581; font-weight: bold; }
        
        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: #202225; border-radius: 8px; }
        ::-webkit-scrollbar-thumb { background: #4f545c; border-radius: 8px; }
        ::-webkit-scrollbar-thumb:hover { background: #72767d; }
    </style>
</head>
<body>
    <h2>🏆 Rekapan Hadiah Kuis</h2>
    
    <div class="stats-box">
        <div class="stats-info">
            <p>🟢 <strong>Server Up since:</strong> <span id="start-str">Loading...</span></p>
            <p>⏱️ <strong>Bot running:</strong> <span id="uptime-str">Loading...</span></p>
        </div>
        
        <div class="stats-grid">
            <div class="stat-item">XP Gained<span id="val-xp">0 %</span></div>
            <div class="stat-item">Gold Gained<span id="val-gold">0</span></div>
            <div class="stat-item">Token Gained<span id="val-token">0</span></div>
            <div class="stat-item">TP Gained<span id="val-tp">0</span></div>
            <div class="stat-item">Rare Reward<span id="val-rare">0x</span></div>
        </div>

        <div class="control-panel">
            <div class="control-info">
                <div>🤖 <strong>Status:</strong> <span id="status-badge" class="status-badge">Loading...</span></div>
                <div>⚡ <strong>Speed:</strong> <span id="mode-badge" class="status-badge">Loading...</span></div>
                <div>⚠️ <strong>Rate Limits Hit:</strong> <span id="rl-badge" class="status-badge" style="color:#ed4245;">0</span></div>
            </div>
            <div>
                <button id="toggle-mode-btn" class="btn btn-mode" onclick="toggleMode()">⚙️ CHANGE MODE</button>
                <button id="toggle-btn" class="btn" onclick="toggleBot()">⏳ Loading</button>
            </div>
        </div>
    </div>

    <div class="table-container">
        <table>
            <thead>
                <tr><th>Waktu (WIB)</th><th>Jawaban</th><th>Hadiah / Reward</th></tr>
            </thead>
            <tbody id="table-body">
                <tr><td colspan="3" style="text-align:center; padding:20px; color:#72767d;">Memuat data real-time...</td></tr>
            </tbody>
        </table>
    </div>

    <script>
        let currentLootCount = -1; 

        async function fetchAllData() {
            try {
                let res = await fetch('/api/data');
                let data = await res.json();
                
                document.getElementById('start-str').innerText = data.start_str;
                document.getElementById('uptime-str').innerText = data.uptime_str;
                
                document.getElementById('val-xp').innerText = data.total_xp + " %";
                document.getElementById('val-gold').innerText = data.total_gold;
                document.getElementById('val-token').innerText = data.total_token;
                document.getElementById('val-tp').innerText = data.total_tp;
                document.getElementById('val-rare').innerText = data.rare_count + "x";
                document.getElementById('rl-badge').innerText = data.rate_limit_count;

                updateUI(data.paused, data.mode);
                
                if (data.loots.length !== currentLootCount) {
                    let html = "";
                    if (data.loots.length === 0) {
                        html = "<tr><td colspan='3' style='text-align:center; color:#72767d; padding:20px;'>Belum ada hadiah ter-log.</td></tr>";
                    } else {
                        data.loots.forEach(loot => {
                            html += `<tr><td>${loot.time}</td><td><code>${loot.answer}</code></td><td class="reward">${loot.reward}</td></tr>`;
                        });
                    }
                    document.getElementById('table-body').innerHTML = html;
                    currentLootCount = data.loots.length;
                }
            } catch (error) {
                console.error("Gagal menarik data API:", error);
            }
        }

        async function toggleBot() {
            let btn = document.getElementById('toggle-btn');
            btn.disabled = true;
            try {
                let res = await fetch('/api/toggle', { method: 'POST' });
                let data = await res.json();
                updateUI(data.paused, data.mode);
            } catch (error) { alert("Gagal menghubungi server!"); }
            btn.disabled = false;
        }

        async function toggleMode() {
            let btn = document.getElementById('toggle-mode-btn');
            btn.disabled = true;
            try {
                let res = await fetch('/api/toggle_mode', { method: 'POST' });
                let data = await res.json();
                updateUI(data.paused, data.mode);
            } catch (error) { alert("Gagal mengubah mode!"); }
            btn.disabled = false;
        }

        function updateUI(isPaused, botMode) {
            let badgeStatus = document.getElementById('status-badge');
            let badgeMode = document.getElementById('mode-badge');
            let btn = document.getElementById('toggle-btn');
            
            if (isPaused) {
                badgeStatus.innerHTML = "😴 PAUSED"; badgeStatus.style.color = "#ed4245";
                btn.className = "btn btn-start"; btn.innerHTML = "▶️ START BOT";
            } else {
                badgeStatus.innerHTML = "🚀 RUNNING"; badgeStatus.style.color = "#43b581";
                btn.className = "btn btn-pause"; btn.innerHTML = "⏸️ PAUSE BOT";
            }

            if (botMode === "fast") {
                badgeMode.innerHTML = "🏎️ FAST MODE (0.5s - 5s)"; badgeMode.style.color = "#faa61a";
            } else {
                badgeMode.innerHTML = "🐢 SLOW MODE (6s - 12s)"; badgeMode.style.color = "#b9bbbe";
            }
        }

        fetchAllData();
        setInterval(fetchAllData, 5000);
    </script>
</body>
</html>
"""

@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/data', methods=['GET'])
def get_data():
    loots = load_loot_history()
    
    now_utc = datetime.now(timezone.utc)
    uptime_delta = now_utc - START_TIME_UTC
    hours, remainder = divmod(int(uptime_delta.total_seconds()), 3600)
    minutes, _ = divmod(remainder, 60)
    
    start_time_wib = START_TIME_UTC + timedelta(hours=7)
    start_str = start_time_wib.strftime('%d %B %Y %H.%M WIB')
    uptime_str = f"{hours} Hours {minutes} Minutes"
    
    total_xp = 0
    total_gold = 0
    total_token = 0
    total_tp = 0
    rare_count = 0
    
    start_time_naive = start_time_wib.replace(tzinfo=None) 
    
    for loot in loots:
        try:
            loot_time = datetime.strptime(loot["time"], '%Y-%m-%d %H:%M:%S')
            if loot_time >= start_time_naive:
                rew = loot["reward"].lower()
                def extract_val(pattern):
                    m = re.search(pattern, rew)
                    if m:
                        clean_str = m.group(1).replace(',', '').replace('.', '')
                        return int(clean_str)
                    return 0
                
                total_xp += extract_val(r'([\d,\.]+)\s*(?:%|xp)')
                total_gold += extract_val(r'([\d,\.]+)\s*gold')
                total_token += extract_val(r'([\d,\.]+)\s*token')
                total_tp += extract_val(r'([\d,\.]+)\s*tp')
                if "rare" in rew: rare_count += 1
        except: pass

    return jsonify({
        "start_str": start_str,
        "uptime_str": uptime_str,
        "total_xp": total_xp,
        "total_gold": total_gold,
        "total_token": total_token,
        "total_tp": total_tp,
        "rare_count": rare_count,
        "loots": loots,
        "paused": is_paused,
        "mode": bot_mode,
        "rate_limit_count": rate_limit_count
    })

@app.route('/api/toggle', methods=['POST'])
def toggle_state():
    global is_paused, last_activity_time, client
    is_paused = not is_paused
    if not is_paused:
        last_activity_time = datetime.now(timezone.utc)
        print("[WEB CONTROL] Bot AKTIF kembali.")
        if client and client.loop and client.is_ready():
            try: asyncio.run_coroutine_threadsafe(client.trigger_manual_c(), client.loop)
            except: pass
    else:
        print("[WEB CONTROL] Bot memasuki mode PAUSE.")
    return jsonify({"paused": is_paused, "mode": bot_mode})

@app.route('/api/toggle_mode', methods=['POST'])
def toggle_mode():
    global bot_mode
    bot_mode = "slow" if bot_mode == "fast" else "fast"
    print(f"[WEB CONTROL] Mode diubah menjadi: {bot_mode.upper()}")
    return jsonify({"paused": is_paused, "mode": bot_mode})

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

Thread(target=run_web_server).start()

# =========================================================
# 4. DICTIONARY CHEAT CODE LOGO BRAND
# =========================================================
LOGO_MAP = {
    # 1 - 99
    "logo_1": "evian", "logo_3": "kraft", "logo_4": "maggi", "logo_5": "burger king",
    "logo_6": "ben and jerrys", "logo_7": "chipotle", "logo_9": "dunkin", "logo_10": "fanta",
    "logo_11": "kitkat", "logo_12": "taco bell", "logo_13": "quaker", "logo_16": "kfc",
    "logo_17": "pringles", "logo_18": "redbull", "logo_19": "snickers", "logo_20": "sprite",
    "logo_21": "doritos", "logo_24": "lays", "logo_26": "cocacola", "logo_29": "dominos",
    "logo_32": "heineken", "logo_33": "pepsi", "logo_34": "mcdonalds", "logo_35": "starbucks",
    "logo_37": "monster", "logo_38": "pizza hut", "logo_39": "android", "logo_40": "adobe",
    "logo_41": "chrome", "logo_42": "gmail", "logo_44": "twitter", "logo_45": "starbucks",
    "logo_46": "xbox",
    "logo_101": "chanel", "logo_107": "champion", "logo_108": "lv", "logo_110": "levis",
    "logo_111": "rolex", "logo_112": "dickies", "logo_114": "columbia", "logo_116": "hermes",
    "logo_117": "palace", "logo_118": "kappa", "logo_119": "burberry", "logo_120": "puma",
    "logo_121": "reebok", "logo_125": "diesel", "logo_126": "fila", "logo_127": "versace",
    "logo_129": "hollister", "logo_133": "nike", "logo_136": "ck", "logo_138": "fred perry",
    "logo_201": "apple", "logo_202": "dolby", "logo_203": "philips", "logo_204": "alibaba",
    "logo_206": "cisco", "logo_207": "intel", "logo_208": "adobe", "logo_209": "alcatel",
    "logo_210": "amazon", "logo_211": "amd", "logo_212": "asus", "logo_214": "dell",
    "logo_215": "fitbit", "logo_216": "fujitsu", "logo_217": "airbnb", "logo_218": "huawei",
    "logo_219": "t_mobile", "logo_220": "lg", "logo_221": "microsoft", "logo_222": "motorola",
    "logo_223": "nvidia", "logo_224": "oneplus", "logo_225": "paypal", "logo_227": "samsung",
    "logo_228": "seagate", "logo_229": "ericsson", "logo_230": "beats", "logo_231": "xiaomi",
    "logo_232": "uber", "logo_233": "youtube", "logo_234": "twitter", "logo_235": "Blackberry",
    "logo_236": "dropbox", "logo_237": "facebook", "logo_238": "google", "logo_239": "snapchat",
    "logo_301": "netflix", "logo_302": "nintendo", "logo_303": "universal", "logo_304": "walking dead",
    "logo_305": "gameloft", "logo_306": "game of thrones", "logo_307": "discovery", "logo_308": "monopoly",
    "logo_309": "konami", "logo_311": "bandai", "logo_313": "warner bros", "logo_314": "rockstar",
    "logo_315": "ff", "logo_317": "activision", "logo_319": "walt disney", "logo_321": "hbo max",
    "logo_323": "jurassic", "logo_324": "fox", "logo_326": "marvel", "logo_328": "paramount",
    "logo_329": "sega", "logo_330": "star wars", "logo_331": "tencent", "logo_332": "terminator",
    "logo_333": "tiktok", "logo_334": "titanic", "logo_335": "soundcloud", "logo_336": "ubisoft",
    "logo_337": "lego", "logo_338": "discord", "logo_339": "spotify",
    "logo_402": "cadillac", "logo_403": "chevrolet", "logo_404": "mini", "logo_405": "porsche",
    "logo_406": "citroen", "logo_408": "infiniti", "logo_409": "jaguar", "logo_410": "volkswagen",
    "logo_411": "lexus", "logo_412": "peugeot", "logo_413": "mitsubishi", "logo_414": "suzuki",
    "logo_415": "aston martin", "logo_416": "bentley", "logo_417": "bugatti", "logo_418": "audi",
    "logo_420": "dodge", "logo_421": "ferrari", "logo_422": "fiat", "logo_423": "ford",
    "logo_424": "honda", "logo_425": "hyundai", "logo_426": "koenigsegg", "logo_430": "mazda",
    "logo_431": "nissan", "logo_432": "opel", "logo_433": "renault", "logo_435": "seat",
    "logo_437": "subaru", "logo_438": "volvo", "logo_439": "bmw",
    "logo_501": "harley", "logo_502": "nescafe"
}

# =========================================================
# 5. CORE CODE SELF-BOT DISCORD & GEMINI CONFIG
# =========================================================
TOKEN_DISCORD = os.getenv('DISCORD_TOKEN')
API_KEY_GEMINI = os.getenv('GEMINI_API_KEY')
TARGET_USER_ID = int(os.getenv('TARGET_USER_ID')) if os.getenv('TARGET_USER_ID') else None
TARGET_CHANNEL_ID = int(os.getenv('TARGET_CHANNEL_ID')) if os.getenv('TARGET_CHANNEL_ID') else None

if not TOKEN_DISCORD or not API_KEY_GEMINI or not TARGET_USER_ID or not TARGET_CHANNEL_ID:
    print("Error: Variabel lingkungan belum diisi lengkap! Pastikan TARGET_CHANNEL_ID sudah ditambahkan.")
    exit(1)

ai_client = genai.Client(api_key=API_KEY_GEMINI)

class MySelfBot(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.send_lock = None

    async def on_ready(self):
        global client
        client = self
        if self.send_lock is None:
            self.send_lock = asyncio.Lock()
            
        print(f'Self-bot aktif sebagai: {self.user}')
        print(f'=== MULTI-MODE & DASHBOARD AKTIF: TARGET CHANNEL {TARGET_CHANNEL_ID} ===')
        self.loop.create_task(self.background_30s_loop())

    async def trigger_manual_c(self):
        global last_activity_time, last_send_time
        if not self.is_ready() or is_paused: return
        async with self.send_lock:
            target_channel = self.get_channel(TARGET_CHANNEL_ID)
            if target_channel:
                try:
                    await target_channel.send("!c")
                    last_activity_time = datetime.now(timezone.utc)
                    last_send_time = datetime.now(timezone.utc)
                except Exception as e: print(f"[START ERROR] Gagal memicu !c: {e}")

    async def on_message(self, message):
        global is_paused, last_activity_time, is_triggering_c, last_send_time, bot_mode
        
        # --- SAKLAR REMOTE CONTROL (DISCORD CHAT) ---
        if message.author.id == self.user.id:
            msg_lower = message.content.lower()
            if "rame" in msg_lower and not is_paused:
                is_paused = True
                print("[REMOTE CONTROL] Terdeteksi 'rame'. Bot memasuki mode PAUSE.")
            elif "capek" in msg_lower and is_paused:
                is_paused = False
                print("[REMOTE CONTROL] Terdeteksi 'capek'. Bot AKTIF kembali.")
                last_activity_time = datetime.now(timezone.utc)
                self.loop.create_task(self.trigger_manual_c())
            return

        if message.channel.id != TARGET_CHANNEL_ID: return
        if message.author.id != TARGET_USER_ID: return
        
        # 🛑 FILTER ANTI BURST: Abaikan pesan lebih dari 15 detik yg lalu
        try:
            msg_date = message.created_at
            if msg_date.tzinfo is None: msg_date = msg_date.replace(tzinfo=timezone.utc)
            if (datetime.now(timezone.utc) - msg_date).total_seconds() > 15.0: return
        except: pass

        last_activity_time = datetime.now(timezone.utc)

        full_text = ""
        image_url = ""

        if message.embeds:
            for embed in message.embeds:
                if embed.title: full_text += embed.title + "\n"
                if embed.description: full_text += embed.description + "\n"
                if embed.fields:
                    for field in embed.fields: full_text += f"{field.name}: {field.value}\n"
                if embed.footer and embed.footer.text: full_text += embed.footer.text + "\n"
                if embed.image and embed.image.url: image_url = embed.image.url

        if message.content: full_text += "\n" + message.content

        content_lower = full_text.lower()

        # =========================================================
        # ALUR 1: MENJAWAB SOAL BARU
        # =========================================================
        if "60 seconds" in content_lower or "!char" in content_lower:
            if is_paused: return

            print(f"[LOG RENDER] Mendeteksi Quiz Baru dari {message.author.name}!")
            final_answer = ""
            success = False

            if "math" in content_lower:
                try:
                    lines = [l.strip() for l in full_text.split('\n') if l.strip()]
                    target_line = ""
                    for line in lines:
                        if line.startswith("##") or ('=' in line and '?' in line):
                            target_line = line
                            break
                    if target_line:
                        expr = target_line.replace('##', '').split('=')[0].strip()
                        expr_clean = expr.replace('×', '*').replace('x', '*').replace('X', '*')
                        expr_clean = expr_clean.replace('²', '**2').replace('^2', '**2')
                        expr_purified = "".join(re.findall(r'[\d\+\-\*\/\(\)\s]+', expr_clean)).strip()
                        if expr_purified:
                            final_answer = str(int(round(eval(expr_purified))))
                            success = True
                except Exception as math_err:
                    print(f"[MATH ERROR] Dialihkan ke Gemini: {math_err}")

            if not success and image_url:
                try:
                    if "challenge/flags/flag_" in image_url:
                        match = re.search(r'flag_([^.]+)\.png', image_url)
                        if match: final_answer = match.group(1).replace('_', ' ').title(); success = True
                    elif "challenge/animals/animal_" in image_url:
                        match = re.search(r'animal_([^.]+)\.jpg', image_url)
                        if match: final_answer = match.group(1).replace('_', ' ').title(); success = True
                    elif "challenge/logos/logo_" in image_url:
                        match = re.search(r'(logo_\d+)\.png', image_url)
                        if match:
                            logo_key = match.group(1)
                            if logo_key in LOGO_MAP: final_answer = LOGO_MAP[logo_key].replace('_', ' ').title(); success = True
                except: pass

            if not success:
                try:
                    cleaned_math_text = full_text.replace('×', '*').replace('²', '^2')
                    prompt = f"Kamu adalah mesin penjawab kuis otomatis. HANYA berikan jawaban bersih intinya saja.\n\nKuis:\n{cleaned_math_text}"
                    response = ai_client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                    if response and response.text:
                        final_answer = response.text.strip().replace('.', '')
                        if final_answer: success = True
                except: pass

            if final_answer and success:
                async with self.send_lock:
                    time_since_last_send = (datetime.now(timezone.utc) - last_send_time).total_seconds()
                    
                    if bot_mode == "slow":
                        safe_buffer = 6.0 
                        if time_since_last_send < safe_buffer:
                            delay = safe_buffer - time_since_last_send + random.uniform(0.1, 0.5)
                            print(f"[SLOWMODE GUARD] Menunda kirim jawaban selama {delay:.2f} detik...")
                            await asyncio.sleep(delay)
                        await asyncio.sleep(random.uniform(0.5, 1.5))
                    else:
                        # FAST MODE: Sangat agresif, jeda 0.5 - 1.0 detik setelah soal keluar
                        await asyncio.sleep(random.uniform(0.5, 1.0))
                    
                    try:
                        await message.channel.send(final_answer)
                        last_send_time = datetime.now(timezone.utc)
                        print(f"[SPEED] Mengirim jawaban ({bot_mode.upper()} mode): '{final_answer}'")
                    except Exception as e:
                        print(f"[ERROR SEND JAWABAN] {e}")
                return

        # =========================================================
        # ALUR 2: KUIS SELESAI / TIMEOUT -> TRIGGGER !C AMAN
        # =========================================================
        is_quiz_ended = "got it first!" in content_lower or "reward:" in content_lower or "challenge solved" in content_lower or "time's up!" in content_lower

        if is_quiz_ended:
            if "msdn" in content_lower:
                try:
                    ans_match = re.search(r'Answer:\s*([^\n\r]+)', full_text, re.IGNORECASE)
                    rew_match = re.search(r'Reward:\s*([^\n\r]+)', full_text, re.IGNORECASE)
                    str_answer = ans_match.group(1).strip().replace('**', '') if ans_match else "Tidak terdeteksi"
                    str_reward = rew_match.group(1).strip().replace('**', '') if rew_match else "Tidak terdeteksi"
                    if "sent to your main" in str_reward.lower():
                        str_reward = str_reward.split("Sent to your")[0].strip()

                    wib_time = datetime.now(timezone.utc) + timedelta(hours=7)
                    history = load_loot_history()
                    history.insert(0, {"time": wib_time.strftime('%Y-%m-%d %H:%M:%S'), "answer": str_answer, "reward": str_reward})
                    save_loot_history(history)
                except: pass

            if is_paused or is_triggering_c: return
            is_triggering_c = True
            
            async with self.send_lock:
                time_since_last_send = (datetime.now(timezone.utc) - last_send_time).total_seconds()
                
                if bot_mode == "slow":
                    required_wait = random.uniform(7.0, 12.0) 
                else:
                    # FAST MODE: Menunggu cooldown bot 5 detik
                    required_wait = random.uniform(5.1, 6.0)
                
                if time_since_last_send < required_wait:
                    wait_time = required_wait - time_since_last_send
                    await asyncio.sleep(wait_time)
                
                target_channel = self.get_channel(TARGET_CHANNEL_ID)
                if target_channel:
                    try:
                        await target_channel.send("!c")
                        last_activity_time = datetime.now(timezone.utc)
                        last_send_time = datetime.now(timezone.utc)
                        print(f"[FAST TRACK SUCCESS] !c dikirim via {bot_mode.upper()} mode.")
                    except Exception as e:
                        last_activity_time = datetime.now(timezone.utc)
                        print(f"[FAILED TO SEND !c] Terkena error: {e}")
                        
            is_triggering_c = False

    # =========================================================
    # BACKGROUND WORKER LOOP (Setiap 30 Detik)
    # =========================================================
    async def background_30s_loop(self):
        global is_paused, last_activity_time, is_triggering_c, last_send_time
        await self.wait_until_ready()
        
        while not self.is_closed():
            await asyncio.sleep(30)
            if is_paused or is_triggering_c: continue

            time_silent = (datetime.now(timezone.utc) - last_activity_time).total_seconds()
            if time_silent >= 90.0:
                is_triggering_c = True
                print(f"[BACKGROUND] Sepi {int(time_silent)} detik. Memancing !c ...")
                
                async with self.send_lock:
                    target_channel = self.get_channel(TARGET_CHANNEL_ID)
                    if target_channel:
                        try:
                            await target_channel.send("!c")
                            last_send_time = datetime.now(timezone.utc)
                        except Exception as e:
                            print(f"[BACKGROUND ERROR] {e}")
                
                last_activity_time = datetime.now(timezone.utc)
                is_triggering_c = False

client = MySelfBot()
client.run(TOKEN_DISCORD)
