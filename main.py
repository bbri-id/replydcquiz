import discord
import asyncio
import random
import os
import re
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
TARGET_USER_ID = int(os.getenv('TARGET_USER_ID')) if os.getenv('TARGET_USER_ID') else None

if not TOKEN_DISCORD or not API_KEY_GEMINI or not TARGET_USER_ID:
    print("Error: Variabel lingkungan (Environment Variables) belum diisi lengkap!")
    exit(1)

ai_client = genai.Client(api_key=API_KEY_GEMINI)

class MySelfBot(discord.Client):
    async def on_ready(self):
        print(f'Self-bot aktif sebagai: {self.user}')
        print('Menunggu Quiz Embed dari Bot LionNSEX dengan Fitur Cheat Code Kapital...')

    async def on_message(self, message):
        if message.author.id == self.user.id:
            return

        if message.author.id != TARGET_USER_ID:
            return

        full_text = ""
        image_url = ""

        # 1. Ekstrak teks dan URL Gambar dari Embed Quiz
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
                
                # Cek apakah ada gambar di dalam embed
                if embed.image and embed.image.url:
                    image_url = embed.image.url

        if message.content:
            full_text += "\n" + message.content

        content_lower = full_text.lower()
        
        # Pemicu kuis aktif
        if "60 seconds" in content_lower or "!char" in content_lower:
            print(f"[LOG RENDER] Mendeteksi Quiz Baru dari {message.author.name}!")
            
            final_answer = ""
            used_cheat = False

            # =========================================================
            # STRATEGI 1: JALUR CHEAT CODE (NEGARA & HEWAN VIA URL)
            # =========================================================
            if image_url:
                print(f"[LOG RENDER] Menemukan URL Gambar: {image_url}")
                
                # A. Deteksi Kuis Negara (Flags)
                if "challenge/flags/flag_" in image_url:
                    match = re.search(r'flag_([^.]+)\.png', image_url)
                    if match:
                        raw_answer = match.group(1)
                        # Ganti _ jadi spasi & kapital di awal kata (contoh: Sierra Leone)
                        final_answer = raw_answer.replace('_', ' ').title()
                        used_cheat = True
                        print(f"[CHEAT CODE] Berhasil mengekstrak kuis Negara: {final_answer}")

                # B. Deteksi Kuis Hewan (Animals)
                elif "challenge/animals/animal_" in image_url:
                    match = re.search(r'animal_([^.]+)\.jpg', image_url)
                    if match:
                        raw_answer = match.group(1)
                        # Ganti _ jadi spasi & KAPITAL DI AWAL KATA (contoh: Hyena / Guppy)
                        final_answer = raw_answer.replace('_', ' ').title()
                        used_cheat = True
                        print(f"[CHEAT CODE] Berhasil mengekstrak kuis Hewan: {final_answer}")

            # =========================================================
            # STRATEGI 2: JALUR GEMINI AI (MATH CHALLENGE / LOGO / TEXT)
            # =========================================================
            if not used_cheat:
                print("[LOG RENDER] Tidak ada cheat URL yang cocok. Menggunakan Gemini AI...")
                try:
                    prompt = (
                        f"Kamu adalah mesin penjawab kuis otomatis. Tugasmu adalah memecahkan kuis di bawah ini "
                        f"dan HANYA memberikan satu atau dua kata jawaban intinya saja tanpa embel-embel, tanpa penjelasan, "
                        f"tanpa tanda baca titik, tanpa kalimat pengantar, dan tanpa Markdown. Pastikan gunakan huruf kapital di awal setiap kata jawaban.\n\n"
                        f"Aturan Khusus:\n"
                        f"- Jika kuis matematika (Math Challenge), berikan HASIL ANGKA NYA SAJA (contoh: 24).\n"
                        f"- Jika kuis tebak logo/brand (Guess the Logo), sebutkan NAMA BRAND NYA SAJA dengan kapital diawal (contoh: Chanel).\n\n"
                        f"Isi Kuis:\n{full_text}\n"
                        f"Jawaban bersih:"
                    )

                    response = ai_client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=prompt,
                    )
                    
                    final_answer = response.text.strip()
                    if final_answer.endswith('.'):
                        final_answer = final_answer[:-1]

                except Exception as e:
                    print(f"[ERROR LOG RENDER] Gagal memproses kuis via Gemini: {e}")
                    return

            # =========================================================
            # PROSES PENGIRIMAN JAWABAN (STERIL)
            # =========================================================
            if final_answer:
                # Jeda acak natural agar tidak dianggap bot spam ilegal oleh Discord
                await asyncio.sleep(random.uniform(2, 4))
                
                # Kirim hanya jawaban bersih ke channel kuis
                await message.channel.send(final_answer)
                print(f"[LOG RENDER] Berhasil mengirim jawaban ke Discord: '{final_answer}'")

# Jalankan bot
client = MySelfBot()
client.run(TOKEN_DISCORD)
