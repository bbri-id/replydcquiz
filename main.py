import discord
import asyncio
import random
import os
import re
import json
from flask import Flask, render_template_string
from threading import Thread
from datetime import datetime

# =========================================================
# 1. SETUP WEB SERVER MINI & REKAPAN HADIAH
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
        h2 { color: #5865F2; border-bottom: 2px solid #5865F2; padding-bottom: 10px; }
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
    <div class="table-container">
        <table>
            <thead>
                <tr><th>Waktu (UTC)</th><th>Jawaban</th><th>Hadiah / Reward</th></tr>
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
    return render_template_string(HTML_TEMPLATE, loots=load_loot_history())

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
# 3. CORE CODE SELF-BOT DISCORD & GEMINI
# =========================================================
TOKEN_DISCORD = os.getenv('DISCORD_TOKEN')
API_KEY_GEMINI = os.getenv('GEMINI_API_KEY')
TARGET_USER_ID = int(os.getenv('TARGET_USER_ID')) if os.getenv('TARGET_USER_ID') else None

if not TOKEN_DISCORD or not TARGET_USER_ID:
    print("Error: Variabel lingkungan belum diisi lengkap!")
    exit(1)

from google import genai
ai_client = genai.Client(api_key=API_KEY_GEMINI) if API_KEY_GEMINI else None

current_trigger_task = None
quiz_channel_id = None

class MySelfBot(discord.Client):
    async def on_ready(self):
        print(f'Self-bot aktif sebagai: {self.user}')
        print('=== ALL CHEAT CODES READY (MATH BY GEMINI, FLAGS/ANIMALS/LOGOS BY URL) ===')

    async def on_message(self, message):
        global current_trigger_task, quiz_channel_id
        
        if message.author.id == TARGET_USER_ID or message.content.strip() == "!c":
            quiz_channel_id = message.channel.id

        if current_trigger_task and not current_trigger_task.done():
            if message.content.strip() == "!c" or (message.author.id == TARGET_USER_ID and ("60 seconds" in message.content.lower() or message.embeds)):
                current_trigger_task.cancel()
                current_trigger_task = None

        if message.author.id == self.user.id:
            return

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

        if message.author.id == TARGET_USER_ID:
            print(f"\n[LIVE DEBUG LIONNSEX] Teks Masuk:\n{full_text}\n-----------------------")

        # =========================================================
        # ALUR A: MENJAWAB KUIS (DENGAN JEDA PENGAMAN DELAY SMART)
        # =========================================================
        if message.author.id == TARGET_USER_ID and ("60 seconds" in content_lower or "!char" in content_lower):
            final_answer = ""
            success = False

            if image_url:
                # 1. Jalur Cheat URL Negara (Flags)
                if "challenge/flags/flag_" in image_url:
                    match = re.search(r'flag_([^.]+)\.png', image_url)
                    if match:
                        final_answer = match.group(1).replace('_', ' ').title()
                        success = True
                
                # 2. Jalur Cheat URL Hewan (Animals)
                elif "challenge/animals/animal_" in image_url:
                    match = re.search(r'animal_([^.]+)\.jpg', image_url)
                    if match:
                        final_answer = match.group(1).replace('_', ' ').title()
                        success = True
                
                # 3. BARU: Jalur Cheat URL Logo Brand (Logos)
                elif "challenge/logos/logo_" in image_url:
                    match = re.search(r'(logo_\d+)\.png', image_url)
                    if match:
                        logo_key = match.group(1)
                        if logo_key in LOGO_MAP:
                            # Ambil jawaban dan rapikan format kapitalnya (.title())
                            final_answer = LOGO_MAP[logo_key].replace('_', ' ').title()
                            success = True
                            print(f"[CHEAT LOGO] Terdeteksi {logo_key} -> Jawab: {final_answer}")

            # 4. Jalur Matematika (Tetap mengandalkan Gemini AI)
            if not success and "math" in content_lower and ai_client:
                try:
                    prompt = (
                        f"Kamu adalah kalkulator kuis otomatis. Hitung atau selesaikan kuis matematika di bawah ini "
                        f"dan HANYA berikan HASIL ANGKA NYA SAJA tanpa penjelasan, tanpa kalimat pengantar, "
                        f"tanpa tanda titik di akhir, dan tanpa format Markdown.\n\nIsi Kuis:\n{full_text}\nJawaban bersih:"
                    )
                    response = ai_client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                    final_answer = response.text.strip()
                    if final_answer.endswith('.'): final_answer = final_answer[:-1]
                    if final_answer: success = True
                except Exception as e:
                    print(f"[ERROR GEMINI] {e}")

            # KIRIM JAWABAN DENGAN JEDA 0.1 - 1.0 DETIK (PENGAMAN 429)
            if final_answer and success:
                try:
                    answer_delay = random.uniform(0.1, 1.0)
                    await asyncio.sleep(answer_delay)
                    
                    await message.channel.send(final_answer)
                    print(f"[SPEED] Jawaban kuis '{final_answer}' terkirim setelah jeda {round(answer_delay, 2)}s.")
                except Exception as e:
                    print(f"[ERROR SEND] {e}")
                return

        # =========================================================
        # ALUR B: PENGECEKAN LOOT & SMART TIMER
        # =========================================================
        if message.author.id == TARGET_USER_ID and ("got it first!" in content_lower or "reward:" in content_lower):
            
            if "msdn" in content_lower and "got it first!" in content_lower:
                print("[🏆 DEBUG WINNER] Deteksi kemenangan msdn terpicu di script!")
                ans_match = re.search(r'Answer:\s*([^\n\r]+)', full_text, re.IGNORECASE)
                rew_match = re.search(r'Reward:\s*([^\n\r]+)', full_text, re.IGNORECASE)
                
                str_answer = ans_match.group(1).strip() if ans_match else "Tidak terdeteksi"
                str_reward = rew_match.group(1).strip() if rew_match else "Tidak terdeteksi"
                
                if "sent to your main" in str_reward.lower():
                    str_reward = str_reward.split("Sent to your")[0].strip()

                history = load_loot_history()
                history.insert(0, {
                    "time": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
                    "answer": str_answer,
                    "reward": str_reward
                })
                save_loot_history(history)
                print("[LOOT COMMITTED] Berhasil menyimpan data kemenangan msdn!")

            if quiz_channel_id:
                if current_trigger_task and not current_trigger_task.done():
                    current_trigger_task.cancel()
                current_trigger_task = asyncio.create_task(self.smart_trigger_sequence())

    async def smart_trigger_sequence(self):
        global quiz_channel_id
        try:
            wait_time = random.uniform(6, 10)
            await asyncio.sleep(wait_time)
            if quiz_channel_id:
                target_channel = self.get_channel(quiz_channel_id)
                if target_channel:
                    try: await target_channel.send("!c")
                    except: pass
        except asyncio.CancelledError:
            pass

client = MySelfBot()
client.run(TOKEN_DISCORD)
