import discord
import asyncio
import random
import os
import re
import json
import logging
import traceback
from google import genai
from flask import Flask, render_template_string, jsonify
from threading import Thread
from datetime import datetime, timedelta, timezone

# =========================================================
# 1. VARIABEL GLOBAL & TOKEN (SECURE)
# =========================================================
TOKEN_DISCORD = os.getenv('DISCORD_TOKEN')
API_KEY_GEMINI = os.getenv('GEMINI_API_KEY')
TARGET_USER_ID = int(os.getenv('TARGET_USER_ID')) if os.getenv('TARGET_USER_ID') else None
TARGET_CHANNEL_ID = int(os.getenv('TARGET_CHANNEL_ID')) if os.getenv('TARGET_CHANNEL_ID') else None
TOKEN_TUMBAL = os.getenv('DISCORD_TOKEN_TUMBAL')

if not TOKEN_DISCORD or not API_KEY_GEMINI or not TARGET_USER_ID or not TARGET_CHANNEL_ID or not TOKEN_TUMBAL:
    print("Error: Variabel lingkungan belum diisi lengkap! Pastikan TOKEN_TUMBAL juga sudah ditambahkan di .env/Render.")
    exit(1)

START_TIME_UTC = datetime.now(timezone.utc)
last_activity_time = datetime.now(timezone.utc)
last_send_time = datetime.now(timezone.utc)

last_player_chat_time = datetime.now(timezone.utc) - timedelta(minutes=10) 
last_admin_activity = datetime.now(timezone.utc) - timedelta(minutes=15) 
quiz_solved_time = datetime.now(timezone.utc) - timedelta(minutes=10)
last_tag_reply_time = datetime.now(timezone.utc) - timedelta(minutes=10)

is_paused = False  
bot_mode = "fast" 
rate_limit_count = 0

last_answered_msg_id = None
last_solved_msg_id = None
last_clicked_btn_msg_id = None 

session_total_xp = 0
session_total_gold = 0
session_total_token = 0
session_total_tp = 0
session_rare_count = 0

used_idle_chats = set()
quiz_solved_counter = 0
next_idle_chat_target = random.randint(5, 20)

consecutive_losses = 0
next_loss_target = random.randint(5, 7)

# =========================================================
# 2. PENCEGAT LOG & AI
# =========================================================
class RateLimitHandler(logging.Handler):
    def emit(self, record):
        global rate_limit_count
        if record.levelno >= logging.WARNING:
            msg = self.format(record).lower()
            if "rate limited" in msg or "429" in msg:
                rate_limit_count += 1

rl_handler = RateLimitHandler()
logging.getLogger('discord.http').addHandler(rl_handler)
logging.basicConfig(level=logging.INFO)

ai_client = genai.Client(api_key=API_KEY_GEMINI)

def apply_human_typing(text):
    ans = str(text)
    if ans.isdigit(): return ans 
    if random.random() < 0.50:
        if ' ' in ans or '-' in ans:
            ans = ans.replace(' ', '').replace('-', '')
        else:
            if len(ans) >= 4:
                idx = random.randint(2, len(ans)-2)
                ans = ans[:idx] + ' ' + ans[idx:]
    case_choice = random.random()
    if case_choice < 0.40: ans = ans.lower() 
    elif case_choice < 0.60:
        ans_list = list(ans.lower())
        num_upper = random.randint(1, max(1, len(ans_list)//2))
        for _ in range(num_upper):
            idx = random.randint(0, len(ans_list)-1)
            ans_list[idx] = ans_list[idx].upper()
        ans = "".join(ans_list)
    elif case_choice < 0.80:
        if len(ans) > 2: ans = ans[0].lower() + ans[1:].upper() 
        else: ans = ans.upper() 
    return ans

async def generate_gemini_text(prompt):
    def fetch():
        try:
            response = ai_client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
            return response.text.strip().replace('"', '')
        except: return ""
    return await asyncio.to_thread(fetch)

# =========================================================
# 3. SETUP WEB SERVER MINI
# =========================================================
app = Flask('')
DB_FILE = "loot_history.json"
CHAT_DB_FILE = "chat_history.json"

def load_json_db(file_name):
    if os.path.exists(file_name):
        try:
            with open(file_name, "r") as f: return json.load(f)
        except: return []
    return []

def save_json_db(file_name, data):
    try:
        with open(file_name, "w") as f: json.dump(data[:50], f, indent=4)
    except Exception as e: pass

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Loot Kuis Dashboard</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #1e1e24; color: #fff; margin: 0; padding: 20px; height: 100vh; box-sizing: border-box; display: flex; flex-direction: column; overflow: hidden; }
        h2 { color: #5865F2; border-bottom: 2px solid #5865F2; padding-bottom: 10px; margin-top: 0; display: flex; justify-content: space-between; align-items: center; flex-shrink: 0; font-size: 1.5em; }
        .stats-box { background-color: #2f3136; padding: 15px; border-radius: 8px; margin-bottom: 15px; border-left: 4px solid #43b581; flex-shrink: 0; }
        .stats-info p { margin: 5px 0; font-size: 0.95em; color: #dcddde; }
        .stats-info strong { color: #fff; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px; margin-top: 15px; }
        .stat-item { background: #202225; padding: 10px; border-radius: 5px; text-align: center; font-size: 0.9em; color: #b9bbbe; }
        .stat-item span { display: block; font-size: 1.4em; font-weight: bold; color: #faa61a; margin-top: 5px; }
        .control-panel { margin-top: 15px; padding-top: 15px; border-top: 1px solid #4f545c; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px; }
        .control-info { display: flex; flex-direction: column; gap: 5px; font-size: 0.9em; }
        .status-badge { font-weight: bold; padding: 3px 8px; border-radius: 5px; background-color: #202225; }
        .btn-wrapper { display: flex; gap: 10px; flex-wrap: wrap; justify-content: flex-end;}
        .btn { border: none; padding: 10px 15px; border-radius: 5px; font-weight: bold; cursor: pointer; transition: 0.2s; font-size: 0.9em; }
        .btn-start { background-color: #43b581; color: white; }
        .btn-start:hover { background-color: #3ca374; }
        .btn-pause { background-color: #ed4245; color: white; }
        .btn-pause:hover { background-color: #d83c3e; }
        .btn-mode { background-color: #5865F2; color: white; }
        .btn-mode:hover { background-color: #4752c4; }
        .btn-barbar { background-color: #ff4757; color: white; box-shadow: 0 0 10px #ff4757; animation: pulse 2s infinite; }
        .btn-barbar:hover { background-color: #ff6b81; }
        @keyframes pulse { 0% { box-shadow: 0 0 5px #ff4757; } 50% { box-shadow: 0 0 15px #ff4757; } 100% { box-shadow: 0 0 5px #ff4757; } }
        .btn:disabled { opacity: 0.6; cursor: not-allowed; }
        .tables-wrapper { display: grid; grid-template-columns: 2fr 1fr; gap: 15px; flex-grow: 1; min-height: 0; }
        .table-container { overflow-y: auto; background-color: #2f3136; border-radius: 8px; position: relative; border: 1px solid #202225; }
        .table-header { position: sticky; top: 0; z-index: 2; padding: 12px; margin: 0; text-align: center; color: white; font-weight: bold; font-size: 1.1em; box-shadow: 0 2px 2px -1px rgba(0,0,0,0.4); }
        .reward-header { background-color: #5865F2; }
        .chat-header { background-color: #faa61a; color: #1e1e24; }
        table { width: 100%; border-collapse: collapse; }
        tbody td { padding: 12px; text-align: left; border-bottom: 1px solid #202225; font-size: 0.9em; word-wrap: break-word; }
        tr:hover { background-color: #35383e; }
        .reward { color: #43b581; font-weight: bold; }
        .chat-author { color: #5865F2; font-weight: bold; display: block; margin-bottom: 2px;}
        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: #202225; border-radius: 8px; }
        ::-webkit-scrollbar-thumb { background: #4f545c; border-radius: 8px; }
        ::-webkit-scrollbar-thumb:hover { background: #72767d; }
        @media (max-width: 768px) {
            body { height: auto; overflow-y: auto; padding: 10px; }
            .stats-grid { grid-template-columns: repeat(2, 1fr); }
            .stat-item { padding: 8px; font-size: 0.8em; }
            .stat-item span { font-size: 1.2em; }
            .control-panel { flex-direction: column; align-items: stretch; }
            .btn-wrapper { width: 100%; margin-top: 10px; justify-content: space-between; }
            .btn { flex: 1 1 45%; padding: 12px 5px; font-size: 0.85em; text-align: center; } 
            #barbar-btn { flex: 1 1 100%; margin-top: 5px; font-size: 1em; }
            .tables-wrapper { display: flex; flex-direction: column; gap: 15px; }
            .table-container { height: 380px; }
            tbody td { padding: 8px; font-size: 0.85em; }
            .table-header { font-size: 1em; padding: 10px; }
        }
    </style>
</head>
<body>
    <h2>🏆 Rekapan Hadiah Kuis</h2>
    <div class="stats-box">
        <div class="stats-info">
            <p>🟢 <strong>Server Up since:</strong> <span id="start-str">Loading...</span></p>
            <p>⏱️ <strong>Bot running:</strong> <span id="uptime-str">Loading...</span></p>
            <p>👤 <strong>Stealth Tracker:</strong> <span id="stealth-str" style="font-weight:bold;">Aman</span></p>
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
            <div class="btn-wrapper">
                <button id="toggle-mode-btn" class="btn btn-mode" onclick="toggleMode()">⚙️ CHANGE MODE</button>
                <button id="toggle-btn" class="btn" onclick="toggleBot()">⏳ Loading</button>
                <button id="barbar-btn" class="btn btn-barbar" onclick="toggleBarbar()">🔥 BARBAR</button>
            </div>
        </div>
    </div>
    <div class="tables-wrapper">
        <div class="table-container">
            <div class="table-header reward-header">🎁 Reward Log</div>
            <table><tbody id="table-body"><tr><td colspan="3" style="text-align:center; padding:20px; color:#72767d;">Memuat data real-time...</td></tr></tbody></table>
        </div>
        <div class="table-container">
            <div class="table-header chat-header">💬 Player Chat Interceptor</div>
            <table><tbody id="chat-body"><tr><td style="text-align:center; padding:20px; color:#72767d;">Menunggu chat player...</td></tr></tbody></table>
        </div>
    </div>
    <script>
        let lastLootHash = ""; 
        let lastChatHash = "";
        async function fetchAllData() {
            try {
                let res = await fetch('/api/data?_=' + new Date().getTime());
                let data = await res.json();
                document.getElementById('start-str').innerText = data.start_str;
                document.getElementById('uptime-str').innerText = data.uptime_str;
                let stealthEl = document.getElementById('stealth-str');
                stealthEl.innerText = data.stealth_str;
                if(data.stealth_str.includes("ADMIN") || data.stealth_str.includes("OFF")) stealthEl.style.color = "#ed4245";
                else if(data.stealth_str.includes("Player")) stealthEl.style.color = "#faa61a";
                else stealthEl.style.color = "#43b581";
                document.getElementById('val-xp').innerText = data.total_xp + " %";
                document.getElementById('val-gold').innerText = data.total_gold;
                document.getElementById('val-token').innerText = data.total_token;
                document.getElementById('val-tp').innerText = data.total_tp;
                document.getElementById('val-rare').innerText = data.rare_count + "x";
                document.getElementById('rl-badge').innerText = data.rate_limit_count;
                updateUI(data.paused, data.mode);
                let newLootHash = data.loots.length > 0 ? JSON.stringify(data.loots[0]) : "empty";
                if (newLootHash !== lastLootHash) {
                    let html = "";
                    if (data.loots.length === 0) html = "<tr><td colspan='3' style='text-align:center; color:#72767d; padding:20px;'>Belum ada hadiah ter-log.</td></tr>";
                    else data.loots.forEach(loot => { html += `<tr><td style="width:25%">${loot.time}</td><td style="width:35%"><code>${loot.answer}</code></td><td class="reward">${loot.reward}</td></tr>`; });
                    document.getElementById('table-body').innerHTML = html;
                    lastLootHash = newLootHash;
                }
                let newChatHash = data.chats.length > 0 ? JSON.stringify(data.chats[0]) : "empty";
                if (newChatHash !== lastChatHash) {
                    let html = "";
                    if (data.chats.length === 0) html = "<tr><td style='text-align:center; color:#72767d; padding:20px;'>Room sepi. Belum ada chat player.</td></tr>";
                    else data.chats.forEach(chat => { html += `<tr><td><span class="chat-author">${chat.author}</span>${chat.content} <br><span style="font-size:0.8em; color:#72767d;">${chat.time}</span></td></tr>`; });
                    document.getElementById('chat-body').innerHTML = html;
                    lastChatHash = newChatHash;
                }
            } catch (error) { console.error(error); }
        }
        async function toggleBot() {
            let btn = document.getElementById('toggle-btn'); btn.disabled = true;
            try { let res = await fetch('/api/toggle', { method: 'POST' }); let data = await res.json(); updateUI(data.paused, data.mode); } catch (e) {} btn.disabled = false;
        }
        async function toggleMode() {
            let btn = document.getElementById('toggle-mode-btn'); btn.disabled = true;
            try { let res = await fetch('/api/toggle_mode', { method: 'POST' }); let data = await res.json(); updateUI(data.paused, data.mode); } catch (e) {} btn.disabled = false;
        }
        async function toggleBarbar() {
            let btn = document.getElementById('barbar-btn'); btn.disabled = true;
            try { let res = await fetch('/api/toggle_barbar', { method: 'POST' }); let data = await res.json(); updateUI(data.paused, data.mode); } catch (e) {} btn.disabled = false;
        }
        function updateUI(isPaused, botMode) {
            let badgeStatus = document.getElementById('status-badge'), badgeMode = document.getElementById('mode-badge'), btn = document.getElementById('toggle-btn');
            if (isPaused) {
                badgeStatus.innerHTML = "😴 PAUSED"; badgeStatus.style.color = "#ed4245";
                btn.className = "btn btn-start"; btn.innerHTML = "▶️ START BOT";
            } else {
                badgeStatus.innerHTML = "🚀 RUNNING"; badgeStatus.style.color = "#43b581";
                btn.className = "btn btn-pause"; btn.innerHTML = "⏸️ PAUSE BOT";
            }
            if (botMode === "barbar") { badgeMode.innerHTML = "🔥 BARBAR (No Rules!)"; badgeMode.style.color = "#ff4757"; }
            else if (botMode === "fast") { badgeMode.innerHTML = "🏎️ FAST MODE"; badgeMode.style.color = "#faa61a"; }
            else { badgeMode.innerHTML = "🐢 SLOW MODE (Stealth/Manual)"; badgeMode.style.color = "#b9bbbe"; }
        }
        fetchAllData();
        setInterval(fetchAllData, 2000); 
        document.addEventListener("visibilitychange", function() { if (!document.hidden) fetchAllData(); });
    </script>
</body>
</html>
"""

@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/data', methods=['GET'])
def get_data():
    loots = load_json_db(DB_FILE)
    chats = load_json_db(CHAT_DB_FILE)
    now_utc = datetime.now(timezone.utc)
    uptime_delta = now_utc - START_TIME_UTC
    hours, remainder = divmod(int(uptime_delta.total_seconds()), 3600)
    minutes, _ = divmod(remainder, 60)
    start_time_wib = START_TIME_UTC + timedelta(hours=7)
    time_since_admin = (now_utc - last_admin_activity).total_seconds()
    time_since_player = (now_utc - last_player_chat_time).total_seconds()
    
    if bot_mode == "barbar": stealth_str = "🔥 MODE BARBAR (Stealth OFF)"
    elif time_since_admin < 600.0: stealth_str = f"🚨 ADMIN ONLINE! Tiarap {int((600 - time_since_admin)/60)} Menit."
    elif time_since_player < 300.0: stealth_str = f"⚠️ Ada Player! Tiarap {int(300 - time_since_player)} Detik."
    else: stealth_str = "🟢 Aman (Sepi)"

    return jsonify({
        "start_str": start_time_wib.strftime('%d %B %Y %H.%M WIB'), "uptime_str": f"{hours} Hours {minutes} Minutes",
        "stealth_str": stealth_str, "total_xp": session_total_xp, "total_gold": session_total_gold,
        "total_token": session_total_token, "total_tp": session_total_tp, "rare_count": session_rare_count,
        "loots": loots, "chats": chats, "paused": is_paused, "mode": bot_mode, "rate_limit_count": rate_limit_count
    })

@app.route('/api/toggle', methods=['POST'])
def toggle_state():
    global is_paused, last_activity_time
    is_paused = not is_paused
    if not is_paused: last_activity_time = datetime.now(timezone.utc)
    return jsonify({"paused": is_paused, "mode": bot_mode})

@app.route('/api/toggle_mode', methods=['POST'])
def toggle_mode():
    global bot_mode
    bot_mode = "slow" if bot_mode == "fast" else "fast"
    return jsonify({"paused": is_paused, "mode": bot_mode})

@app.route('/api/toggle_barbar', methods=['POST'])
def toggle_barbar():
    global bot_mode
    bot_mode = "fast" if bot_mode == "barbar" else "barbar"
    return jsonify({"paused": is_paused, "mode": bot_mode})

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

Thread(target=run_web_server).start()

# =========================================================
# 4. DICTIONARY CHEAT CODE LOGO BRAND
# =========================================================
LOGO_MAP = {
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
# 5. TUMBAL BOT (AKUN KE-2) - INVISIBLE & BLIND CLICKER
# =========================================================
class TumbalBot(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def on_ready(self):
        print(f"[TUMBAL] Hadir sebagai Jari Tambahan: {self.user} (Invisible Mode)")

tumbal_client = TumbalBot(status=discord.Status.invisible)

async def trigger_tumbal_click(channel_id, message_id):
    await asyncio.sleep(random.uniform(1.0, 3.0))
    try:
        channel = tumbal_client.get_channel(channel_id)
        if not channel: channel = await tumbal_client.fetch_channel(channel_id)
        msg = await channel.fetch_message(message_id)
        
        target_btn = None
        if msg.components:
            for row in msg.components:
                for child in getattr(row, 'children', []):
                    if hasattr(child, 'click'):
                        target_btn = child
                        break
                if target_btn: break
        
        if target_btn and not getattr(target_btn, 'disabled', False):
            await target_btn.click()
            print("[TUMBAL BUTTON] Berhasil menyusul klik Start Challenge secara buta.")
    except Exception as e: 
        print(f"[TUMBAL BUTTON ERROR] {e}")


# =========================================================
# 6. MAIN BOT (AKUN UTAMA)
# =========================================================
class MySelfBot(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.send_lock = None

    async def on_ready(self):
        global client
        client = self
        if self.send_lock is None: self.send_lock = asyncio.Lock()
        print(f"[MAIN] Self-bot aktif sebagai: {self.user}")
        print(f"=== MULTI-MODE & DASHBOARD AKTIF: TARGET CHANNEL {TARGET_CHANNEL_ID} ===")

    async def send_idle_chat(self):
        history_str = ", ".join(list(used_idle_chats)[-10:]) if used_idle_chats else "belum ada"
        prompt = f"Buat 1 kalimat keluhan singkat ala gamer gen-Z Indonesia yang lagi pegel/bosen ngetik kuis Discord terus. Max 5 kata. Huruf kecil, typo dikit wajar atau 1 emot. DILARANG KERAS menggunakan kalimat yang mirip dengan ini: {history_str}. HANYA berikan output teksnya saja."
        msg = await generate_gemini_text(prompt)
        if msg:
            used_idle_chats.add(msg)
            await asyncio.sleep(random.uniform(2.0, 5.0))
            target = self.get_channel(TARGET_CHANNEL_ID)
            if target: 
                print(f"[AI CHAT] Mengeluh Pegel: {msg}")
                await target.send(msg)

    async def send_loss_streak_chat(self):
        history_str = ", ".join(list(used_idle_chats)[-10:]) if used_idle_chats else "belum ada"
        prompt = (f"Buat 1 keluhan singkat gamer gen-Z Indonesia yang kesel karena kesalip/kalah cepat jawab kuis Discord berkali-kali. "
                  f"Alasan bisa wifi lemot, lag, ngantuk, atau cape. Max 6 kata. Huruf kecil semua, boleh ada typo wajar atau 1 emot. "
                  f"DILARANG KERAS pakai kata 'udahan', 'off', 'berhenti', 'cabut', 'stop', 'tidur'. "
                  f"DILARANG KERAS pakai kalimat yang mirip dengan ini: {history_str}. HANYA berikan output teksnya saja.")
        msg = await generate_gemini_text(prompt)
        if msg:
            used_idle_chats.add(msg)
            await asyncio.sleep(random.uniform(3.0, 6.0))
            target = self.get_channel(TARGET_CHANNEL_ID)
            if target: 
                print(f"[AI CHAT] Kesalip Streak: {msg}")
                await target.send(msg)

    async def send_tag_reply(self, channel):
        prompt = "Ada player discord iseng ngetag/quote pesan kamu. Balas dengan santai ala gamer cowok. Sangat singkat, max 2 kata. Boleh pakai kata 'wkwk', 'kenapa', '?', atau 1 emot aja. Jangan kaku. HANYA berikan output teksnya saja."
        msg = await generate_gemini_text(prompt)
        if msg:
            await asyncio.sleep(random.uniform(2.0, 6.0))
            print(f"[AI CHAT] Membalas Tag: {msg}")
            await channel.send(msg)

    async def process_discord_event(self, message):
        global is_paused, last_activity_time, bot_mode
        global last_answered_msg_id, last_solved_msg_id, last_player_chat_time
        global quiz_solved_time, last_admin_activity, last_tag_reply_time
        global session_total_xp, session_total_gold, session_total_token, session_total_tp, session_rare_count
        global quiz_solved_counter, next_idle_chat_target
        global consecutive_losses, next_loss_target
        global last_clicked_btn_msg_id

        if message.channel.id != TARGET_CHANNEL_ID: return

        # ==========================================
        # 🛠️ DEBUG MODE: CETAK SEMUA PESAN DI RENDER
        # ==========================================
        print("\n--- [DEBUG MESSAGE RADAR] ---")
        print(f"Author: {message.author.name} (Bot: {message.author.bot})")
        print(f"Content: {message.content}")
        if message.embeds:
            print(f"Embeds: {len(message.embeds)}")
            for e in message.embeds: print(f" - Title: {e.title} | Desc: {e.description}")
        if message.components:
            print(f"Components found:")
            for row in message.components:
                for child in getattr(row, 'children', []):
                    print(f"  -> Type: {getattr(child, 'type', 'N/A')}, Label: {getattr(child, 'label', 'N/A')}, Custom ID: {getattr(child, 'custom_id', 'N/A')}")
        print("-----------------------------\n")

        # RADAR ADMIN
        author_name = message.author.name.lower()
        author_display = message.author.display_name.lower()
        if any(admin in author_name or admin in author_display for admin in ["ternate", "pandansex"]):
            last_admin_activity = datetime.now(timezone.utc)
            if bot_mode == "fast":
                bot_mode = "slow"
                print(f"[🚨 ADMIN ALERT] Admin beraktivitas! Kunci SLOW MODE 10 Menit.")

        # SAKLAR REMOTE CONTROL
        is_me = (message.author.id == self.user.id)
        if is_me:
            msg_lower = message.content.lower()
            if "rame" in msg_lower and not is_paused:
                is_paused = True
            elif "capek" in msg_lower and is_paused:
                is_paused = False
                last_activity_time = datetime.now(timezone.utc)
            return

        # INTERCEPTOR PLAYER (Abaikan Bot / App)
        if not is_me and not message.author.bot:
            if message.content and not message.content.startswith('!'):
                wib_time = datetime.now(timezone.utc) + timedelta(hours=7)
                chat_history = load_json_db(CHAT_DB_FILE)
                chat_history.insert(0, {"time": wib_time.strftime('%H:%M:%S WIB'), "author": message.author.name, "content": message.content})
                save_json_db(CHAT_DB_FILE, chat_history)

                last_player_chat_time = datetime.now(timezone.utc)
                if bot_mode == "fast":
                    bot_mode = "slow"
                    print(f"[STEALTH ALERT] Player {message.author.name} mengetik! Tiarap ke SLOW MODE.")

                is_mentioned = str(self.user.id) in message.content
                is_replied = message.reference and getattr(message.reference.resolved, 'author', None) and message.reference.resolved.author.id == self.user.id
                if is_mentioned or is_replied:
                    time_since_tag = (datetime.now(timezone.utc) - last_tag_reply_time).total_seconds()
                    if time_since_tag >= 120.0:
                        last_tag_reply_time = datetime.now(timezone.utc)
                        print(f"[TAG DETECTED] Di-tag oleh {message.author.name}. AI menyiapkan balasan...")
                        self.loop.create_task(self.send_tag_reply(message.channel))
            return 

        try:
            msg_date = message.created_at
            if msg_date.tzinfo is None: msg_date = msg_date.replace(tzinfo=timezone.utc)
            if (datetime.now(timezone.utc) - msg_date).total_seconds() > 60.0: return
        except: pass

        last_activity_time = datetime.now(timezone.utc)

        full_text = ""
        image_urls = []
        if message.embeds:
            for embed in message.embeds:
                if embed.title: full_text += embed.title + "\n"
                if embed.description: full_text += embed.description + "\n"
                if embed.fields:
                    for field in embed.fields: full_text += f"{field.name}: {field.value}\n"
                if embed.footer and embed.footer.text: full_text += embed.footer.text + "\n"
                if embed.image and embed.image.url: image_urls.append(embed.image.url)
                if embed.thumbnail and embed.thumbnail.url: image_urls.append(embed.thumbnail.url)

        if message.content: full_text += "\n" + message.content
        content_lower = full_text.lower()

        # =========================================================
        # ALUR 1: DETEKSI TOMBOL "START CHALLENGE" 🎮
        # =========================================================
        is_start_prompt = "start challenge" in content_lower or "needs" in content_lower or "players" in content_lower
        
        target_btn = None
        if is_start_prompt and message.components:
            for row in message.components:
                for child in getattr(row, 'children', []):
                    if hasattr(child, 'click'):
                        target_btn = child
                        break
                if target_btn: break
                
        if target_btn and message.id != last_clicked_btn_msg_id:
            if not is_paused:
                last_clicked_btn_msg_id = message.id
                
                if bot_mode == "slow": click_delay = random.uniform(2.0, 4.0)
                elif bot_mode == "fast": click_delay = random.uniform(1.0, 2.0)
                else: click_delay = random.uniform(0.3, 0.8) 
                    
                print(f"[MAIN BUTTON] Target klik buta ditemukan! Eksekusi dalam {click_delay:.2f}s")
                
                async def execute_main_click():
                    await asyncio.sleep(click_delay)
                    try:
                        await target_btn.click()
                        print("[MAIN BUTTON] Berhasil klik buta Start Challenge.")
                        self.loop.create_task(trigger_tumbal_click(message.channel.id, message.id))
                    except Exception as e:
                        print(f"[MAIN BUTTON ERROR] Gagal menekan tombol:")
                        traceback.print_exc() # MENCETAK AKAR ERROR SECARA DETAIL
                
                self.loop.create_task(execute_main_click())

        # =========================================================
        # ALUR 2: DETEKSI KUIS SELESAI & KALKULASI REWARD
        # =========================================================
        is_quiz_ended = "got it first!" in content_lower or "reward:" in content_lower or "challenge solved" in content_lower or "time's up!" in content_lower

        if is_quiz_ended:
            if message.id == last_solved_msg_id: return 
            last_solved_msg_id = message.id
            quiz_solved_time = datetime.now(timezone.utc) 

            if "msdn" in content_lower:
                consecutive_losses = 0 
                try:
                    ans_match = re.search(r'Answer:\s*([^\n\r]+)', full_text, re.IGNORECASE)
                    rew_match = re.search(r'Reward:\s*([^\n\r]+)', full_text, re.IGNORECASE)
                    str_answer = ans_match.group(1).strip().replace('**', '') if ans_match else "Tidak terdeteksi"
                    str_reward = rew_match.group(1).strip().replace('**', '') if rew_match else "Tidak terdeteksi"
                    if "sent to your main" in str_reward.lower(): str_reward = str_reward.split("Sent to your")[0].strip()

                    wib_time = datetime.now(timezone.utc) + timedelta(hours=7)
                    history = load_json_db(DB_FILE)
                    
                    is_duplicate = False
                    if len(history) > 0:
                        last_item = history[0]
                        if last_item.get("answer") == str_answer and last_item.get("reward") == str_reward:
                            is_duplicate = True

                    if not is_duplicate:
                        history.insert(0, {"time": wib_time.strftime('%Y-%m-%d %H:%M:%S'), "answer": str_answer, "reward": str_reward})
                        save_json_db(DB_FILE, history)
                        
                        rew_lower = str_reward.lower()
                        def extract_val(pattern, text):
                            m = re.search(pattern, text)
                            if m: return int(m.group(1).replace(',', '').replace('.', ''))
                            return 0
                        
                        session_total_xp += extract_val(r'([\d,\.]+)\s*(?:%|xp)', rew_lower)
                        session_total_gold += extract_val(r'([\d,\.]+)\s*gold', rew_lower)
                        session_total_token += extract_val(r'([\d,\.]+)\s*token', rew_lower)
                        session_total_tp += extract_val(r'([\d,\.]+)\s*tp', rew_lower)
                        if "rare" in rew_lower: session_rare_count += 1

                        quiz_solved_counter += 1
                        if quiz_solved_counter >= next_idle_chat_target:
                            quiz_solved_counter = 0
                            next_idle_chat_target = random.randint(5, 20)
                            self.loop.create_task(self.send_idle_chat())
                except: pass
            else:
                consecutive_losses += 1
                if consecutive_losses >= next_loss_target:
                    consecutive_losses = 0
                    next_loss_target = random.randint(5, 7)
                    self.loop.create_task(self.send_loss_streak_chat())
            return


        # =========================================================
        # ALUR 3: MENJAWAB SOAL BARU
        # =========================================================
        if "60 seconds" in content_lower or "!char" in content_lower:
            if message.id == last_answered_msg_id: return 
            last_answered_msg_id = message.id
            if is_paused: return

            current_quiz_start = datetime.now(timezone.utc)

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
                except: pass

            if not success and image_urls:
                try:
                    for img_url in image_urls:
                        if "flag_" in img_url:
                            match = re.search(r'flag_([^.\?]+)', img_url)
                            if match: final_answer = match.group(1).replace('_', ' ').title(); success = True; break
                        elif "animal_" in img_url:
                            match = re.search(r'animal_([^.\?]+)', img_url)
                            if match: final_answer = match.group(1).replace('_', ' ').title(); success = True; break
                        elif "logo_" in img_url:
                            match = re.search(r'(logo_\d+)', img_url)
                            if match:
                                logo_key = match.group(1)
                                if logo_key in LOGO_MAP: 
                                    final_answer = LOGO_MAP[logo_key].replace('_', ' ').title()
                                    success = True
                                    break
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
                final_answer = apply_human_typing(final_answer)
                char_count = len(final_answer)
                
                async with self.send_lock:
                    if bot_mode == "slow":
                        reaction_time = random.uniform(1.5, 3.0)
                        typing_speed = random.uniform(0.2, 0.3)
                    elif bot_mode == "fast":
                        reaction_time = random.uniform(0.5, 1.0)
                        typing_speed = random.uniform(0.10, 0.18)
                    else: # BARBAR MODE
                        reaction_time = random.uniform(0.1, 0.3)
                        typing_speed = random.uniform(0.05, 0.08)
                        
                    dynamic_delay = reaction_time + (char_count * typing_speed)
                    print(f"[TYPING] Mode {bot_mode.upper()} - Kata: {char_count} huruf. Delay: {dynamic_delay:.2f} detik.")
                    await asyncio.sleep(dynamic_delay)
                        
                    if quiz_solved_time > current_quiz_start:
                        if random.random() < 0.25: pass 
                        else: return 
                    
                    try:
                        await message.channel.send(final_answer)
                        last_send_time = datetime.now(timezone.utc)
                    except: pass

    async def on_message(self, message):
        await self.process_discord_event(message)

    async def on_message_edit(self, before, after):
        await self.process_discord_event(after)

main_client = MySelfBot()

# 🛑 START DUAL-CORE ENGINE
async def run_bots():
    await asyncio.gather(
        main_client.start(TOKEN_DISCORD),
        tumbal_client.start(TOKEN_TUMBAL)
    )

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(run_bots())
