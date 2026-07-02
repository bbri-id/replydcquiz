import discord
import asyncio
import random
import os
import re
import json
from google import genai
from flask import Flask, render_template_string, jsonify
from threading import Thread
from datetime import datetime, timedelta, timezone

# =========================================================
# 1. VARIABEL GLOBAL (STATE & TIMERS)
# =========================================================
START_TIME_UTC = datetime.now(timezone.utc)
last_activity_time = datetime.now(timezone.utc)
last_send_time = datetime.now(timezone.utc)

is_paused = False  
is_triggering_c = False
quiz_channel_id = None

# =========================================================
# 2. SETUP WEB SERVER MINI, REKAPAN HADIAH, & STATS DASHBOARD
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
    <title>Loot Kuis Logger</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #1e1e24; color: #fff; margin: 20px; }
        h2 { color: #5865F2; border-bottom: 2px solid #5865F2; padding-bottom: 10px; display: flex; justify-content: space-between; align-items: center; }
        .stats-box { background-color: #2f3136; padding: 20px; border-radius: 8px; margin-bottom: 20px; border-left: 4px solid #43b581; position: relative; }
        .stats-box p { margin: 8px 0; font-size: 0.95em; color: #dcddde; }
        .stats-box strong { color: #fff; }
        .highlight-xp { color: #faa61a; font-weight: bold; font-size: 1.1em; }
        
        /* Web Control Styles */
        .control-panel { margin-top: 15px; padding-top: 15px; border-top: 1px solid #4f545c; display: flex; align-items: center; justify-content: space-between; }
        .status-badge { font-weight: bold; padding: 5px 10px; border-radius: 5px; background-color: #202225; }
        .btn { border: none; padding: 10px 20px; border-radius: 5px; font-weight: bold; cursor: pointer; transition: 0.2s; font-size: 1em; box-shadow: 0 4px 6px rgba(0,0,0,0.2); }
        .btn-start { background-color: #43b581; color: white; }
        .btn-start:hover { background-color: #3ca374; }
        .btn-pause { background-color: #ed4245; color: white; }
        .btn-pause:hover { background-color: #d83c3e; }
        .btn:disabled { opacity: 0.6; cursor: not-allowed; }

        .table-container { overflow-x: auto; }
        table { width: 100%; border-collapse: collapse; margin-top: 15px; background-color: #2f3136; border-radius: 8px; overflow: hidden; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #202225; }
        th { background-color: #5865F2; color: white; }
        tr:hover { background-color: #35383e; }
        .timestamp { color: #b9bbbe; font-size: 0.85em; }
        .reward { color: #43b581; font-weight: bold; }
    </style>
</head>
<body>
    <h2>🏆 Rekapan Hadiah Kuis (User: msdn)</h2>
    
    <div class="stats-box">
        <p>🟢 <strong>Server Up since:</strong> {{ start_str }}</p>
        <p>⏱️ <strong>Bot running:</strong> {{ uptime_str }}</p>
        <p>✨ <strong>XP Gained (This Session):</strong> <span class="highlight-xp">{{ total_xp }} %</span></p>
        
        <div class="control-panel">
            <div>
                🤖 <strong>Bot Status:</strong> <span id="status-badge" class="status-badge">Loading...</span>
            </div>
            <button id="toggle-btn" class="btn" onclick="toggleBot()">⏳ Loading</button>
        </div>
    </div>

    <div class="table-container">
        <table>
            <thead>
                <tr><th>Waktu (WIB)</th><th>Jawaban</th><th>Hadiah / Reward</th></tr>
            </thead>
            <tbody>
                {% if loots %}
                    {% for loot in loots %}
                    <tr><td>{{ loot.time }}</td><td><code>{{ loot.answer }}</code></td><td class="reward">{{ loot.reward }}</td></tr>
                    {% endfor %}
                {% else %}
                    <tr><td colspan="3" style="text-align:center; padding:20px; color:#72767d;">Belum ada hadiah ter-log. Pantau Live Log Render!</td></tr>
                {% endif %}
            </tbody>
        </table>
    </div>

    <script>
        async function fetchStatus() {
            try {
                let res = await fetch('/api/state');
                let data = await res.json();
                updateUI(data.paused);
            } catch (error) {
                console.error("Gagal mengambil status bot:", error);
            }
        }

        async function toggleBot() {
            let btn = document.getElementById('toggle-btn');
            btn.disabled = true;
            btn.innerText = "⏳ Processing...";
            try {
                let res = await fetch('/api/toggle', { method: 'POST' });
                let data = await res.json();
                updateUI(data.paused);
            } catch (error) {
                console.error("Gagal mengubah status bot:", error);
                alert("Gagal menghubungi server!");
            }
            btn.disabled = false;
        }

        function updateUI(isPaused) {
            let badge = document.getElementById('status-badge');
            let btn = document.getElementById('toggle-btn');
            
            if (isPaused) {
                badge.innerHTML = "😴 PAUSED";
                badge.style.color = "#ed4245";
                btn.className = "btn btn-start";
                btn.innerHTML = "▶️ START BOT";
            } else {
                badge.innerHTML = "🚀 RUNNING";
                badge.style.color = "#43b581";
                btn.className = "btn btn-pause";
                btn.innerHTML = "⏸️ PAUSE BOT";
            }
        }

        // Panggil status pertama kali saat web diload
        fetchStatus();
        
        // Auto-refresh status setiap 10 detik (opsional, jika di-pause via discord chat)
        setInterval(fetchStatus, 10000);
    </script>
</body>
</html>
"""

@app.route('/')
def home():
    loots = load_loot_history()
    
    # 1. Hitung Uptime
    now_utc = datetime.now(timezone.utc)
    uptime_delta = now_utc - START_TIME_UTC
    hours, remainder = divmod(int(uptime_delta.total_seconds()), 3600)
    minutes, _ = divmod(remainder, 60)
    
    start_time_wib = START_TIME_UTC + timedelta(hours=7)
    start_str = start_time_wib.strftime('%d %B %Y %H.%M WIB')
    uptime_str = f"{hours} Hours {minutes} Minutes"
    
    # 2. Hitung Total XP khusus di sesi server saat ini
    total_xp = 0
    start_time_naive = start_time_wib.replace(tzinfo=None) 
    
    for loot in loots:
        try:
            loot_time = datetime.strptime(loot["time"], '%Y-%m-%d %H:%M:%S')
            if loot_time >= start_time_naive:
                match = re.search(r'(\d+)\s*(?:%|xp)', loot["reward"], re.IGNORECASE)
                if match:
                    total_xp += int(match.group(1))
        except: pass
            
    return render_template_string(HTML_TEMPLATE, loots=loots, start_str=start_str, uptime_str=uptime_str, total_xp=total_xp)

# --- API ROUTES UNTUK WEB CONTROL ---
@app.route('/api/state', methods=['GET'])
def get_state():
    global is_paused
    return jsonify({"paused": is_paused})

@app.route('/api/toggle', methods=['POST'])
def toggle_state():
    global is_paused, last_activity_time
    is_paused = not is_paused
    
    if not is_paused:
        # Jika dihidupkan via web, reset timer agar tidak langsung nembak !c bertubi-tubi
        last_activity_time = datetime.now(timezone.utc)
        print("[WEB CONTROL] Bot AKTIF kembali.")
    else:
        print("[WEB CONTROL] Bot memasuki mode PAUSE.")
        
    return jsonify({"paused": is_paused})

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

Thread(target=run_web_server).start()

# =========================================================
# 3. DICTIONARY CHEAT CODE LOGO BRAND
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

    # 100 - 199
    "logo_101": "chanel", "logo_107": "champion", "logo_108": "lv", "logo_110": "levis",
    "logo_111": "rolex", "logo_112": "dickies", "logo_114": "columbia", "logo_116": "hermes",
    "logo_117": "palace", "logo_118": "kappa", "logo_119": "burberry", "logo_120": "puma",
    "logo_121": "reebok", "logo_125": "diesel", "logo_126": "fila", "logo_127": "versace",
    "logo_129": "hollister", "logo_133": "nike", "logo_136": "ck", "logo_138": "fred perry",

    # 200 - 299
    "logo_201": "apple", "logo_202": "dolby", "logo_203": "philips", "logo_204": "alibaba",
    "logo_206": "cisco", "logo_207": "intel", "logo_208": "adobe", "logo_209": "alcatel",
    "logo_210": "amazon", "logo_211": "amd", "logo_212": "asus", "logo_214": "dell",
    "logo_215": "fitbit", "logo_216": "fujitsu", "logo_217": "airbnb", "logo_218": "huawei",
    "logo_219": "t_mobile", "logo_220": "lg", "logo_221": "microsoft", "logo_222": "motorola",
    "logo_223": "nvidia", "logo_224": "oneplus", "logo_225": "paypal", "logo_227": "samsung",
    "logo_228": "seagate", "logo_229": "ericsson", "logo_230": "beats", "logo_231": "xiaomi",
    "logo_232": "uber", "logo_233": "youtube", "logo_234": "twitter", "logo_235": "Blackberry",
    "logo_236": "dropbox", "logo_237": "facebook", "logo_238": "google", "logo_239": "snapchat",

    # 300 - 399
    "logo_301": "netflix", "logo_302": "nintendo", "logo_303": "universal", "logo_304": "walking dead",
    "logo_305": "gameloft", "logo_306": "game of thrones", "logo_307": "discovery", "logo_308": "monopoly",
    "logo_309": "konami", "logo_311": "bandai", "logo_313": "warner bros", "logo_314": "rockstar",
    "logo_315": "ff", "logo_317": "activision", "logo_319": "walt disney", "logo_321": "hbo max",
    "logo_323": "jurassic", "logo_324": "fox", "logo_326": "marvel", "logo_328": "paramount",
    "logo_329": "sega", "logo_330": "star wars", "logo_331": "tencent", "logo_332": "terminator",
    "logo_333": "tiktok", "logo_334": "titanic", "logo_335": "soundcloud", "logo_336": "ubisoft",
    "logo_337": "lego", "logo_338": "discord", "logo_339": "spotify",

    # 400 - 499
    "logo_402": "cadillac", "logo_403": "chevrolet", "logo_404": "mini", "logo_405": "porsche",
    "logo_406": "citroen", "logo_408": "infiniti", "logo_409": "jaguar", "logo_410": "volkswagen",
    "logo_411": "lexus", "logo_412": "peugeot", "logo_413": "mitsubishi", "logo_414": "suzuki",
    "logo_415": "aston martin", "logo_416": "bentley", "logo_417": "bugatti", "logo_418": "audi",
    "logo_420": "dodge", "logo_421": "ferrari", "logo_422": "fiat", "logo_423": "ford",
    "logo_424": "honda", "logo_425": "hyundai", "logo_426": "koenigsegg", "logo_430": "mazda",
    "logo_431": "nissan", "logo_432": "opel", "logo_433": "renault", "logo_435": "seat",
    "logo_437": "subaru", "logo_438": "volvo", "logo_439": "bmw",

    # 500+
    "logo_501": "harley", "logo_502": "nescafe"
}

# =========================================================
# 4. CORE CODE SELF-BOT DISCORD & GEMINI CONFIG
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
    async def on_ready(self):
        print(f'Self-bot aktif sebagai: {self.user}')
        print(f'=== WEB CONTROL & ANTI-SLOWMODE AKTIF: TARGET CHANNEL {TARGET_CHANNEL_ID} ===')
        self.loop.create_task(self.background_30s_loop())

    async def on_message(self, message):
        global is_paused, last_activity_time, is_triggering_c, last_send_time
        
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
            return

        # 🛑 FILTER ABSOLUT
        if message.channel.id != TARGET_CHANNEL_ID: return
        if message.author.id != TARGET_USER_ID: return

        # Reset global timer tiap ada aktivitas
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

        if message.content:
            full_text += "\n" + message.content

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
                            hasil_lokal = eval(expr_purified)
                            final_answer = str(int(round(hasil_lokal)))
                            success = True
                            print(f"[MATH LOCAL] Berhasil hitung: {final_answer}")
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
                time_since_last_send = (datetime.now(timezone.utc) - last_send_time).total_seconds()
                safe_buffer = 6.0 
                
                if time_since_last_send < safe_buffer:
                    delay = safe_buffer - time_since_last_send + random.uniform(0.1, 0.5)
                    await asyncio.sleep(delay)
                
                try:
                    await asyncio.sleep(random.uniform(0.5, 1.5))
                    await message.channel.send(final_answer)
                    last_send_time = datetime.now(timezone.utc)
                    print(f"[SPEED] Mengirim jawaban: '{final_answer}'")
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
                    str_answer = ans_match.group(1).strip() if ans_match else "Tidak terdeteksi"
                    str_reward = rew_match.group(1).strip() if rew_match else "Tidak terdeteksi"
                    if "sent to your main" in str_reward.lower():
                        str_reward = str_reward.split("Sent to your")[0].strip()

                    wib_time = datetime.now(timezone.utc) + timedelta(hours=7)
                    history = load_loot_history()
                    history.insert(0, {"time": wib_time.strftime('%Y-%m-%d %H:%M:%S'), "answer": str_answer, "reward": str_reward})
                    save_loot_history(history)
                except: pass

            if is_paused or is_triggering_c: return

            is_triggering_c = True
            
            time_since_last_send = (datetime.now(timezone.utc) - last_send_time).total_seconds()
            required_wait = random.uniform(7.0, 12.0) 
            
            if time_since_last_send < required_wait:
                wait_time = required_wait - time_since_last_send
                await asyncio.sleep(wait_time)
            
            target_channel = self.get_channel(TARGET_CHANNEL_ID)
            if target_channel:
                try:
                    await target_channel.send("!c")
                    last_activity_time = datetime.now(timezone.utc)
                    last_send_time = datetime.now(timezone.utc)
                    print("[FAST TRACK SUCCESS] !c berhasil dikirim dengan instan.")
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
            
            if is_paused or is_triggering_c:
                continue

            time_silent = (datetime.now(timezone.utc) - last_activity_time).total_seconds()
            
            if time_silent >= 90.0:
                is_triggering_c = True
                print(f"[BACKGROUND] Sepi selama {int(time_silent)} detik. Memancing !c baru...")
                
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
