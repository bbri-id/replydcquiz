import discord
import asyncio
import random
import os
import re
from flask import Flask, render_template_string
from threading import Thread
from datetime import datetime

# =========================================================
# 1. SETUP WEB SERVER MINI & REKAPAN HADIAH (HTML VIEW)
# =========================================================
app = Flask('')
loot_history = []

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
        .no-data { text-align: center; padding: 20px; color: #72767d; }
    </style>
</head>
<body>
    <h2>🏆 Rekapan Hadiah Kuis (User: msdn)</h2>
    <div class="table-container">
        <table>
            <thead>
                <tr>
                    <th>Waktu (UTC)</th>
                    <th>Jawaban</th>
                    <th>Hadiah / Reward</th>
                </tr>
            </thead>
            <tbody>
                {% if loots %}
                    {% for loot in loots %}
                    <tr>
                        <td class="timestamp">{{ loot.time }}</td>
                        <td><code>{{ loot.answer }}</code></td>
                        <td class="reward">{{ loot.reward }}</td>
                    </tr>
                    {% endfor %}
                {% else %}
                    <tr>
                        <td colspan="3" class="no-data">Belum ada hadiah yang tercatat. Kuis sedang berjalan...</td>
                    </tr>
                {% endif %}
            </tbody>
        </table>
    </div>
</body>
</html>
"""

@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE, loots=loot_history)

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

Thread(target=run_web_server).start()

# =========================================================
# 2. CORE CODE SELF-BOT DISCORD
# =========================================================
TOKEN_DISCORD = os.getenv('DISCORD_TOKEN')
TARGET_USER_ID = int(os.getenv('TARGET_USER_ID')) if os.getenv('TARGET_USER_ID') else None

if not TOKEN_DISCORD or not TARGET_USER_ID:
    print("Error: Variabel lingkungan belum diisi lengkap!")
    exit(1)

current_trigger_task = None
quiz_channel_id = None

class MySelfBot(discord.Client):
    async def on_ready(self):
        print(f'Self-bot aktif sebagai: {self.user}')
        print('Mode Kecepatan Penuh Steril Aktif. Siap memburu kuis.')

    async def on_message(self, message):
        global current_trigger_task, quiz_channel_id
        
        if message.author.id == TARGET_USER_ID or message.content.strip() == "!c":
            quiz_channel_id = message.channel.id

        # Batalkan timer !c kita jika kuis baru / perintah !c dari orang lain sudah muncul duluan
        if current_trigger_task and not current_trigger_task.done():
            if message.content.strip() == "!c" or (message.author.id == TARGET_USER_ID and ("60 seconds" in message.content.lower() or message.embeds)):
                current_trigger_task.cancel()
                current_trigger_task = None
                print("[SMART TIMER] Ada aktivitas kuis baru/!c dari user lain. Timer pemicu kita dibatalkan.")

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

        # =========================================================
        # ALUR A: MENJAWAB KUIS - INSTAN TANPA DELAY ⚡
        # =========================================================
        if message.author.id == TARGET_USER_ID and ("60 seconds" in content_lower or "!char" in content_lower):
            final_answer = ""
            success = False

            # 1. Jalur Cheat URL (Negara & Hewan)
            if image_url:
                if "challenge/flags/flag_" in image_url:
                    match = re.search(r'flag_([^.]+)\.png', image_url)
                    if match:
                        final_answer = match.group(1).replace('_', ' ').title()
                        success = True
                elif "challenge/animals/animal_" in image_url:
                    match = re.search(r'animal_([^.]+)\.jpg', image_url)
                    if match:
                        final_answer = match.group(1).replace('_', ' ').title()
                        success = True

            # 2. Jalur Matematika Lokal (PERBAIKAN TYPO OPERATOR PENGURANGAN)
            if not success and "math challenge" in content_lower:
                math_match = re.search(r'(\d+)\s*([\+\-\*\/])\s*(\d+)', full_text)
                if math_match:
                    angka1 = int(math_match.group(1))
                    operator = math_match.group(2)
                    angka2 = int(math_match.group(3))
                    
                    if operator == '+': hasil = angka1 + angka2
                    elif operator == '-': hasil = angka1 - angka2 # DIBAIKI DI SINI
                    elif operator == '*': hasil = angka1 * angka2
                    elif operator == '/': hasil = angka1 // angka2
                    
                    final_answer = str(hasil)
                    success = True

            # KIRIM INSTAN
            if final_answer and success:
                try:
                    await message.channel.send(final_answer)
                    print(f"[SPEED] Jawaban kuis dikirim instan: '{final_answer}'")
                except Exception as e:
                    print(f"[ERROR SEND] Gagal mengirim jawaban secara instan: {e}")
                return

        # =========================================================
        # ALUR B: REKAPAN HADIAH & SMART TIMER MAX 10 DETIK ⏱️
        # =========================================================
        if message.author.id == TARGET_USER_ID and ("got it first!" in content_lower or "reward:" in content_lower):
            
            if "msdn got it first!" in content_lower:
                print("[🏆 WINNER] Anda (msdn) menang!")
                ans_match = re.search(r'Answer:\s*([^\n\r]+)', full_text, re.IGNORECASE)
                rew_match = re.search(r'Reward:\s*([^\n\r]+)', full_text, re.IGNORECASE)
                
                str_answer = ans_match.group(1).strip() if ans_match else "Tidak terdeteksi"
                str_reward = rew_match.group(1).strip() if rew_match else "Tidak terdeteksi"
                
                if "sent to your main" in str_reward.lower():
                    str_reward = str_reward.split("Sent to your")[0].strip()

                loot_history.insert(0, {
                    "time": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
                    "answer": str_answer,
                    "reward": str_reward
                })

            if quiz_channel_id:
                if current_trigger_task and not current_trigger_task.done():
                    current_trigger_task.cancel()
                
                current_trigger_task = asyncio.create_task(self.smart_trigger_sequence())

    async def smart_trigger_sequence(self):
        global quiz_channel_id
        try:
            # Mengunci range tunggu aman di 6 - 10 detik
            wait_time = random.uniform(6, 10)
            print(f"[SMART TIMER] Mengatur waktu tunggu sepi: {round(wait_time, 2)} detik...")
            await asyncio.sleep(wait_time)
            
            if quiz_channel_id:
                target_channel = self.get_channel(quiz_channel_id)
                if target_channel:
                    try:
                        await target_channel.send("!c")
                        print("[SMART TIMER] Room sepi melebihi batas waktu! Mengirim !c...")
                    except Exception as e:
                        print(f"[ERROR TRIGGER] Gagal mengirim !c saat sepi: {e}")
        except asyncio.CancelledError:
            pass

client = MySelfBot()
client.run(TOKEN_DISCORD)
