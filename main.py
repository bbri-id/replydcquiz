import discord
import asyncio
import random
import os
import re
import json
from google import genai
from flask import Flask, render_template_string
from threading import Thread
from datetime import datetime, timedelta, timezone

# =========================================================
# 1. SETUP WEB SERVER MINI, REKAPAN HADIAH, & STATS DASHBOARD
# =========================================================
app = Flask('')
DB_FILE = "loot_history.json"

# Rekam waktu saat skrip/server pertama kali dijalankan
START_TIME_UTC = datetime.now(timezone.utc)

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
        h2 { color: #5865F2; border-bottom: 2px solid #5865F2; padding-bottom: 10px; }
        .stats-box { background-color: #2f3136; padding: 15px; border-radius: 8px; margin-bottom: 20px; border-left: 4px solid #43b581; }
        .stats-box p { margin: 5px 0; font-size: 0.95em; color: #dcddde; }
        .stats-box strong { color: #fff; }
        .highlight-xp { color: #faa61a; font-weight: bold; font-size: 1.1em; }
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
    start_time_naive = start_time_wib.replace(tzinfo=None) # Hilangkan timezone info untuk komparasi dengan string JSON
    
    for loot in loots:
        try:
            loot_time = datetime.strptime(loot["time"], '%Y-%m-%d %H:%M:%S')
            # Hanya hitung loot yang didapat setelah server ini menyala
            if loot_time >= start_time_naive:
                # Ekstrak angka yang menempel dengan "%" atau "XP" (Contoh: "15%", "15 XP", "15% XP")
                match = re.search(r'(\d+)\s*(?:%|xp)', loot["reward"], re.IGNORECASE)
                if match:
                    total_xp += int(match.group(1))
        except:
            pass
            
    return render_template_string(HTML_TEMPLATE, 
                                  loots=loots, 
                                  start_str=start_str, 
                                  uptime_str=uptime_str,
                                  total_xp=total_xp)

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

Thread(target=run_web_server).start()

# =========================================================
# 2. DICTIONARY CHEAT CODE LOGO BRAND
# =========================================================
LOGO_MAP = {
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
    "logo_309": "konami", "logo_311": "bandai", "choice_313": "warner bros", "logo_314": "rockstar",
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
# 3. CORE CODE SELF-BOT DISCORD & GEMINI CONFIG
# =========================================================
TOKEN_DISCORD = os.getenv('DISCORD_TOKEN')
API_KEY_GEMINI = os.getenv('GEMINI_API_KEY')
TARGET_USER_ID = int(os.getenv('TARGET_USER_ID')) if os.getenv('TARGET_USER_ID') else None
TARGET_CHANNEL_ID = int(os.getenv('TARGET_CHANNEL_ID')) if os.getenv('TARGET_CHANNEL_ID') else None

if not TOKEN_DISCORD or not API_KEY_GEMINI or not TARGET_USER_ID or not TARGET_CHANNEL_ID:
    print("Error: Variabel lingkungan belum diisi lengkap! Pastikan TARGET_CHANNEL_ID sudah ditambahkan.")
    exit(1)

ai_client = genai.Client(api_key=API_KEY_GEMINI)

is_paused = False  
is_triggering_c = False
last_activity_time = datetime.now(timezone.utc)
last_send_time = datetime.now(timezone.utc)

class MySelfBot(discord.Client):
    async def on_ready(self):
        print(f'Self-bot aktif sebagai: {self.user}')
        print(f'=== ANTI-SLOWMODE (5s) AKTIF: TARGET CHANNEL {TARGET_CHANNEL_ID} ===')
        self.loop.create_task(self.background_30s_loop())

    async def on_message(self, message):
        global is_paused, last_activity_time, is_triggering_c, last_send_time
        
        # --- SAKLAR REMOTE CONTROL ---
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

        # 🛑 FILTER ABSOLUT: Hanya dengarkan pesan di TARGET_CHANNEL_ID dari LionNSEX
        if message.channel.id != TARGET_CHANNEL_ID: return
        if message.author.id != TARGET_USER_ID: return

        # Reset global timer tiap ada aktivitas di channel target
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
                # PENYESUAIAN SLOWMODE 5 DETIK SAAT MENGIRIM JAWABAN
                time_since_last_send = (datetime.now(timezone.utc) - last_send_time).total_seconds()
                safe_buffer = 6.0 
                
                if time_since_last_send < safe_buffer:
                    delay = safe_buffer - time_since_last_send + random.uniform(0.1, 0.5)
                    print(f"[SLOWMODE GUARD] Menunda pengiriman jawaban selama {delay:.2f} detik...")
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
            
            # PENYESUAIAN SLOWMODE 5 DETIK UNTUK MENGIRIM !c
            time_since_last_send = (datetime.now(timezone.utc) - last_send_time).total_seconds()
            required_wait = random.uniform(7.0, 12.0) 
            
            if time_since_last_send < required_wait:
                wait_time = required_wait - time_since_last_send
                print(f"[COOLDOWN GUARD] Menunggu {wait_time:.2f} detik (Melewati Slowmode) sebelum !c berikutnya...")
                await asyncio.sleep(wait_time)
            
            target_channel = self.get_channel(TARGET_CHANNEL_ID)
            if target_channel:
                try:
                    print("[ACTION] Mencoba mengirim !c...")
                    await target_channel.send("!c")
                    last_activity_time = datetime.now(timezone.utc)
                    last_send_time = datetime.now(timezone.utc)
                    print("[FAST TRACK SUCCESS] !c berhasil dikirim dengan instan (bypass slowmode).")
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
