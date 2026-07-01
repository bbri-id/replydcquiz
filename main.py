import discord
import asyncio
import random
import os
from google import genai
from flask import Flask
from threading import Thread

# =========================================================
# 1. SETUP WEB SERVER MINI (Agar Render Free Tier Tetap Hidup)
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
        # Abaikan jika pesan berasal dari diri sendiri
        if message.author.id == self.user.id:
            return

        # Pastikan hanya merespon BOT TARGET (LionNSEX)
        if message.author.id != TARGET_USER_ID:
            return

        full_text = ""

        # 1. Ekstrak teks dari kotak Embed Quiz
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

        # 2. Gabungkan dengan teks biasa jika ada
        if message.content:
            full_text += "\n" + message.content

        content_lower = full_text.lower()
        
        # Filter pemicu kuis: Mengandung "60 seconds" atau "!char"
        if "60 seconds" in content_lower or "!char" in content_lower:
            print(f"[LOG RENDER] Mendeteksi Quiz Baru dari {message.author.name}!")
            
            async with message.channel.typing():
                try:
                    # PROMPT SUPER KETAT: Memaksa Gemini hanya mengeluarkan jawaban murni
                    prompt = (
                        f"Kamu adalah mesin penjawab kuis otomatis. Tugasmu adalah memecahkan kuis di bawah ini "
                        f"dan HANYA memberikan satu atau dua kata jawaban intinya saja tanpa embel-embel, tanpa penjelasan, "
                        f"tanpa tanda baca titik, tanpa kalimat pengantar, dan tanpa Markdown (jangan gunakan bold/italic).\n\n"
                        f"Aturan Khusus:\n"
                        f"- Jika kuis matematika (Math Challenge), berikan HASIL ANGKA NYA SAJA (contoh: 24).\n"
                        f"- Jika kuis tebak logo/brand (Guess the Logo), sebutkan NAMA BRAND NYA SAJA (contoh: Chanel).\n"
                        f"- Jika kuis tebak negara/bendera (Guess the Country), sebutkan NAMA NEGARANYA SAJA (contoh: Switzerland).\n"
                        f"- Jika kuis tebak hewan (Guess the Animal), sebutkan NAMA HEWANNYA SAJA (contoh: Guppy).\n\n"
                        f"Isi Kuis:\n{full_text}\n"
                        f"Jawaban bersih:"
                    )

                    response = ai_client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=prompt,
                    )
                    
                    # Bersihkan spasi atau karakter newline yang tidak diinginkan
                    jawaban_ai = response.text.strip()
                    
                    # Pengaman tambahan: Jika AI tidak sengaja memberikan titik di akhir, kita hapus
                    if jawaban_ai.endswith('.'):
                        jawaban_ai = jawaban_ai[:-1]
                    
                    # Jeda acak natural sebelum mengirim (2-4 detik)
                    await asyncio.sleep(random.uniform(2, 4))
                    
                    # KIRIM JAWABAN MURNI (Bukan Reply, langsung teks biasa agar match-case sistem bot)
                    await message.channel.send(jawaban_ai)
                    print(f"[LOG RENDER] Berhasil menjawab kuis dengan teks: '{jawaban_ai}'")

                except Exception as e:
                    # PENTING: Jika error, pooling/tampilkan HANYA di log Render. Jangan kirim ke Discord!
                    print(f"[ERROR LOG RENDER] Gagal memproses kuis atau API bermasalah: {e}")

# Inisialisasi tanpa parameter intents eksternal (mengatasi AttributeError sebelumnya)
client = MySelfBot()
client.run(TOKEN_DISCORD)
