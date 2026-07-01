import discord
import asyncio
import random
import os
from google import genai
from flask import Flask
from threading import Thread

# =========================================================
# 1. SETUP WEB SERVER MINI (Agar Render Free Tier Tidak Tidur)
# =========================================================
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive and running!"

def run_web_server():
    # Render mendeteksi aplikasi lewat port, defaultnya 10000 atau dari env PORT
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# Jalankan web server di thread terpisah sebelum bot Discord jalan
Thread(target=run_web_server).start()

# =========================================================
# 2. CORE CODE SELF-BOT DISCORD & GEMINI
# =========================================================
TOKEN_DISCORD = os.getenv('DISCORD_TOKEN')
API_KEY_GEMINI = os.getenv('GEMINI_API_KEY')
TARGET_USER_ID = int(os.getenv('TARGET_USER_ID')) if os.getenv('TARGET_USER_ID') else None

if not TOKEN_DISCORD or not API_KEY_GEMINI or not TARGET_USER_ID:
    print("Error: Variabel lingkungan (Environment Variables) belum diisi lengkap!")
    exit(1)

ai_client = genai.Client(api_key=API_KEY_GEMINI)

class MySelfBot(discord.Client):
    async def on_ready(self):
        print(f'Self-bot aktif sebagai: {self.user}')
        print('Menunggu chat dengan unsur "60 Seconds"...')

    async def on_message(self, message):
        if message.author.id == self.user.id:
            return

        if message.author.id == TARGET_USER_ID and "60 seconds" in message.content.lower():
            print(f"Menerima pesan dari {message.author.name}: '{message.content}'")
            
            async with message.channel.typing():
                try:
                    prompt = (
                        f"Kamu adalah saya (akun personal Discord). Balaslah chat dari teman saya berikut ini "
                        f"secara santai, singkat, dan natural menggunakan bahasa gaul/casual Indonesia. "
                        f"Chat dia membahas tentang '60 Seconds'.\n\n"
                        f"Chat teman: \"{message.content}\"\n"
                        f"Balasan pendek:"
                    )

                    response = ai_client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=prompt,
                    )
                    
                    jawaban_ai = response.text.strip()
                    await asyncio.sleep(random.uniform(3, 6))
                    await message.reply(jawaban_ai)
                    print(f"Berhasil membalas: {jawaban_ai}")

                except Exception as e:
                    print(f"Gagal memproses: {e}")

client = MySelfBot()
client.run(TOKEN_DISCORD)
