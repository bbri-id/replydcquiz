import discord
import asyncio
import random
import os
from google import genai
from flask import Flask
from threading import Thread

# =========================================================
# 1. SETUP WEB SERVER MINI
# =========================================================
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive and running!"

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

Thread(target=run_web_server).start()

# =========================================================
# 2. CORE CODE SELF-BOT DISCORD & GEMINI
# =========================================================
TOKEN_DISCORD = os.getenv('DISCORD_TOKEN')
API_KEY_GEMINI = os.getenv('GEMINI_API_KEY')
# PASTIKAN TARGET_USER_ID DI RENDER ADALAH ID MILIK BOT "LionNSEX"
TARGET_USER_ID = int(os.getenv('TARGET_USER_ID')) if os.getenv('TARGET_USER_ID') else None

if not TOKEN_DISCORD or not API_KEY_GEMINI or not TARGET_USER_ID:
    print("Error: Variabel lingkungan (Environment Variables) belum diisi lengkap!")
    exit(1)

ai_client = genai.Client(api_key=API_KEY_GEMINI)

class MySelfBot(discord.Client):
    async def on_ready(self):
        print(f'Self-bot aktif sebagai: {self.user}')
        print('Menunggu Quiz Embed dari Bot LionNSEX...')

    async def on_message(self, message):
        # Abaikan chat dari diri sendiri
        if message.author.id == self.user.id:
            return

        # Pastikan hanya merespon BOT TARGET (LionNSEX)
        if message.author.id != TARGET_USER_ID:
            return

        full_text = ""

        # 1. Ambil teks jika kiriman berupa Embed (Kotak Quiz)
        if message.embeds:
            for embed in message.embeds:
                if embed.title:
                    full_text += embed.title + "\n"
                if embed.description:
                    full_text += embed.description + "\n"
                if embed.fields:
                    for field in embed.fields:
                        full_text += f"{field.name}: {field.value}\n"
                if embed.footer and embed.footer.text:
                    full_text += embed.footer.text + "\n"

        # 2. Gabungkan dengan teks biasa (jika ada tambahan teks di luar embed)
        if message.content:
            full_text += "\n" + message.content

        # Pengecekan kata kunci di dalam seluruh teks embed
        content_lower = full_text.lower()
        
        # Mencari unsur "60 seconds" ATAU kata kunci reward character
        if "60 seconds" in content_lower or "!char" in content_lower:
            print(f"Mendeteksi Quiz Baru dari {message.author.name}!")
            
            async with message.channel.typing():
                try:
                    # Instruksi ketat ke Gemini untuk langsung menjawab quiz target
                    prompt = (
                        f"Kamu adalah peserta kuis pintar di Discord. Pecahkan kuis di bawah ini "
                        f"dan berikan JAWABANNYA SAJA secara instan (tanpa penjelasan, tanpa kata pengantar, tanpa tanda baca tambahan). "
                        f"Jika kuis matematika, hitung hasilnya. Jika tebak gambar/bendera/logo, sebutkan nama entitasnya yang tepat.\n\n"
                        f"Isi Kuis:\n{full_text}\n"
                        f"Jawaban singkat:"
                    )

                    response = ai_client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=prompt,
                    )
                    
                    jawaban_ai = response.text.strip()
                    
                    # Beri jeda natural 2-4 detik agar tidak terlihat mencurigakan
                    await asyncio.sleep(random.uniform(2, 4))
                    
                    # Kirim jawaban ke channel (bukan reply agar langsung terbaca sistem quiz)
                    await message.channel.send(jawaban_ai)
                    print(f"Merespon Quiz dengan jawaban: {jawaban_ai}")

                except Exception as e:
                    print(f"Gagal memproses AI atau mengirim pesan: {e}")

intents = discord.intents.all()
client = MySelfBot(intents=intents)
client.run(TOKEN_DISCORD)
