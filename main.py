import discord
import asyncio
import random
import os
import re
import json
import logging
import traceback
from google import genai
from flask import Flask, render_template_string, jsonify, request
from threading import Thread
from datetime import datetime, timedelta, timezone

# 🛑 MEMAKSA RENDER MENCETAK LOG SECARA REAL-TIME
logging.basicConfig(level=logging.WARNING, format='%(message)s')

# =========================================================
# 1. VARIABEL GLOBAL & TOKEN
# =========================================================
TOKEN_DISCORD = os.getenv('DISCORD_TOKEN')
API_KEY_GEMINI = os.getenv('GEMINI_API_KEY')
TARGET_USER_ID = int(os.getenv('TARGET_USER_ID')) if os.getenv('TARGET_USER_ID') else None
TARGET_CHANNEL_ID = int(os.getenv('TARGET_CHANNEL_ID')) if os.getenv('TARGET_CHANNEL_ID') else None
TOKEN_TUMBAL = os.getenv('DISCORD_TOKEN_TUMBAL')

if not TOKEN_DISCORD or not API_KEY_GEMINI or not TARGET_USER_ID or not TARGET_CHANNEL_ID or not TOKEN_TUMBAL:
    logging.warning("Error: Variabel lingkungan belum diisi lengkap!")
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
session_mail_count = 0  # 🛑 NEW: TRACKER MAILBOX

used_idle_chats = set()
quiz_solved_counter = 0
next_idle_chat_target = random.randint(5, 20)

consecutive_losses = 0
next_loss_target = random.randint(5, 7)

# Flag Psikologi Typo & Memory
session_last_answer_was_typo = False
last_typed_answer = ""

web_reply_queue = []

# =========================================================
# FUNGSI BYPASS API
# =========================================================
async def force_click_button(bot_client, message, button):
    try:
        session_id = getattr(bot_client.ws, 'session_id', None)
        app_id = getattr(message, 'application_id', None)
        if not app_id: app_id = message.author.id

        payload = {
            "type": 3, "nonce": str(discord.utils.time_snowflake(datetime.now(timezone.utc))),
            "guild_id": str(message.guild.id) if message.guild else None,
            "channel_id": str(message.channel.id), "message_flags": 0,
            "message_id": str(message.id), "application_id": str(app_id),
            "session_id": session_id,
            "data": { "component_type": 2, "custom_id": button.custom_id }
        }
        if payload["guild_id"] is None: del payload["guild_id"]
        route = discord.http.Route("POST", "/interactions")
        await bot_client.http.request(route, json=payload)
        return True
    except Exception as e:
        logging.warning(f"[BYPASS API ERROR]: {e}")
        return False

# =========================================================
# 2. PENCEGAT LOG & AI HUMANIZER
# =========================================================
class RateLimitHandler(logging.Handler):
    def emit(self, record):
        global rate_limit_count
        if record.levelno >= logging.WARNING:
            msg = self.format(record).lower()
            if "rate limited" in msg or "429" in msg:
                rate_limit_count += 1

logging.getLogger('discord.http').addHandler(RateLimitHandler())
ai_client = genai.Client(api_key=API_KEY_GEMINI)

def apply_human_typing(text):
    ans = str(text)
    is_typo = False
    if ans.isdigit(): return ans, False 
    
    if random.random() < 0.10:
        is_typo = True
        if ' ' in ans or '-' in ans: ans = ans.replace(' ', '').replace('-', '')
        else:
            if len(ans) >= 4:
                idx = random.randint(2, len(ans)-2)
                ans = ans[:idx] + ' ' + ans[idx:]
                
    case_choice = random.random()
    if case_choice < 0.85: ans = ans.lower() 
    elif case_choice < 0.95:
        ans_list = list(ans.lower())
        num_upper = random.randint(1, max(1, len(ans_list)//2))
        for _ in range(num_upper):
            idx = random.randint(0, len(ans_list)-1)
            ans_list[idx] = ans_list[idx].upper()
        ans = "".join(ans_list)
    else:
        if len(ans) > 2: ans = ans[0].lower() + ans[1:].upper() 
        else: ans = ans.upper() 
    return ans, is_typo

async def generate_gemini_text(prompt):
    def fetch():
        try:
            response = ai_client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
            return response.text.strip().replace('"', '')
        except: return ""
    return await asyncio.to_thread(fetch)

# =========================================================
# 3. SETUP WEB SERVER MINI (PWA READY)
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
    except: pass

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="id">
<head>
    <title>Dash</title>
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=0">
    <meta name="mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="theme-color" content="#1e1e24">
    <link rel="manifest" href="/manifest.json">
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #1e1e24; color: #dcddde; margin: 0; padding: 10px; box-sizing: border-box; display: flex; flex-direction: column; height: 100vh; overflow: hidden; font-size: 13px; }
        .stats-box { background-color: #2f3136; padding: 10px; border-radius: 6px; margin-bottom: 10px; border-left: 3px solid #43b581; flex-shrink: 0; }
        .top-info { display: flex; justify-content: space-between; flex-wrap: wrap; margin-bottom: 8px; font-size: 0.9em; }
        .top-info span { background: #202225; padding: 3px 6px; border-radius: 4px; margin-bottom: 3px;}
        .compact-stats { display: flex; flex-wrap: wrap; gap: 5px; align-items: center; border-top: 1px solid #4f545c; padding-top: 8px; font-size: 0.85em; }
        .stat-badge { background: #202225; padding: 3px 6px; border-radius: 4px; color: #b9bbbe; }
        .stat-badge b { color: #faa61a; }
        .btn-wrapper { display: flex; gap: 5px; flex-wrap: wrap; justify-content: flex-end; margin-top: 5px;}
        .btn { border: none; padding: 6px 10px; border-radius: 4px; font-weight: bold; cursor: pointer; font-size: 0.85em; }
        .btn-start { background-color: #43b581; color: white; }
        .btn-pause { background-color: #ed4245; color: white; }
        .btn-mode { background-color: #5865F2; color: white; }
        .btn-reset { background-color: #4f545c; color: white; }
        
        .tables-wrapper { display: flex; gap: 10px; flex-grow: 1; min-height: 0; flex-direction: column; }
        .table-container { background-color: #2f3136; border-radius: 6px; border: 1px solid #202225; display: flex; flex-direction: column; min-height: 0;}
        .chat-log { flex: 1; display: flex; flex-direction: column; }
        .reward-log { flex: 0 0 auto; display: flex; flex-direction: column; }
        
        .table-header { background: #202225; padding: 8px; text-align: center; color: #fff; font-weight: bold; font-size: 0.9em; flex-shrink: 0;}
        .table-body-wrapper { overflow-y: auto; flex-grow: 1; }
        table { width: 100%; border-collapse: collapse; }
        tbody td { padding: 6px 8px; border-bottom: 1px solid #202225; font-size: 0.9em; word-wrap: break-word; }
        .chat-author { color: #5865F2; font-weight: bold; }
        
        .reply-btn { background: transparent; border: 1px solid #5865F2; color: #5865F2; border-radius: 3px; cursor: pointer; padding: 2px 5px; font-size: 0.8em; margin-left: 5px; transition: 0.2s;}
        .reply-btn:hover { background: #5865F2; color: #fff; }
        .replied-badge { color: #43b581; font-size: 0.8em; margin-left: 5px; border: 1px solid #43b581; padding: 1px 4px; border-radius: 3px; }
        .jump-btn { background: transparent; border: 1px solid #faa61a; color: #faa61a; border-radius: 3px; cursor: pointer; padding: 2px 5px; font-size: 0.8em; margin-left: 5px; text-decoration: none; transition: 0.2s;}
        .jump-btn:hover { background: #faa61a; color: #1e1e24; }
        .action-group { display: inline-block; margin-top: 2px; }
        
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #4f545c; border-radius: 4px; }
        @media (max-width: 768px) {
            .tables-wrapper { flex-direction: column; }
            .chat-log { order: 1; flex: 1; }
            .reward-log { order: 2; flex: 0 0 auto; max-height: 40%; } 
            .top-info span { font-size: 0.8em; }
        }
        @media (min-width: 769px) {
            .tables-wrapper { flex-direction: row; }
            .chat-log { flex: 1.5; order: 1; }
            .reward-log { flex: 1; order: 2; max-height: none; }
        }
    </style>
</head>
<body>
    <div class="stats-box">
        <div class="top-info">
            <span>🟢 <b id="uptime-str">--:--</b></span>
            <span id="stealth-str" style="color:#43b581;">Aman</span>
            <span>🤖 <b id="status-badge">Run</b> | <b id="mode-badge">Fast</b></span>
            <span>⚠️ <b id="rl-badge" style="color:#ed4245;">0</b></span>
        </div>
        <div class="compact-stats">
            <span class="stat-badge">XP: <b id="val-xp">0%</b></span>
            <span class="stat-badge">G: <b id="val-gold">0</b></span>
            <span class="stat-badge">T: <b id="val-token">0</b></span>
            <span class="stat-badge">TP/SS: <b id="val-tp">0</b></span>
            <span class="stat-badge">Rare: <b id="val-rare">0</b></span>
            <span class="stat-badge">Mail: <b id="val-mail">0</b></span> <!-- 🛑 NEW TRACKER UI -->
        </div>
        <div class="btn-wrapper">
            <button class="btn btn-reset" onclick="requestNotif()" id="notif-btn">🔔 Notif</button>
            <button class="btn btn-reset" onclick="resetStats()">🔄 Reset</button>
            <button id="toggle-mode-btn" class="btn btn-mode" onclick="toggleMode()">⚙️ Mode</button>
            <button id="toggle-btn" class="btn btn-pause" onclick="toggleBot()">⏸️ Pause</button>
        </div>
    </div>
    <div class="tables-wrapper">
        <div class="table-container chat-log">
            <div class="table-header">💬 Chat Interceptor</div>
            <div class="table-body-wrapper">
                <table><tbody id="chat-body"></tbody></table>
            </div>
        </div>
        <div class="table-container reward-log">
            <div class="table-header">🎁 Log Reward (Max 5)</div>
            <div class="table-body-wrapper">
                <table style="table-layout: fixed;"><tbody id="table-body"></tbody></table>
            </div>
        </div>
    </div>

    <script>
        let lastLootHash = ""; let lastChatHash = "";
        
        document.addEventListener("DOMContentLoaded", () => {
            if ("Notification" in window && Notification.permission === "granted") {
                document.getElementById("notif-btn").innerText = "🔕 Notif On";
            }
        });

        function requestNotif() {
            if ("Notification" in window) {
                Notification.requestPermission().then(permission => {
                    if (permission === "granted") document.getElementById("notif-btn").innerText = "🔕 Notif On";
                });
            } else {
                alert("Browser tidak mendukung push notification.");
            }
        }

        async function fetchAllData() {
            try {
                let res = await fetch('/api/data?_=' + new Date().getTime()); let data = await res.json();
                document.getElementById('uptime-str').innerText = data.uptime_str;
                let stealthEl = document.getElementById('stealth-str'); stealthEl.innerText = data.stealth_str;
                stealthEl.style.color = (data.stealth_str.includes("ADMIN") || data.stealth_str.includes("OFF")) ? "#ed4245" : (data.stealth_str.includes("Player") ? "#faa61a" : "#43b581");
                
                document.getElementById('val-xp').innerText = data.total_xp + "%"; document.getElementById('val-gold').innerText = data.total_gold;
                document.getElementById('val-token').innerText = data.total_token; document.getElementById('val-tp').innerText = data.total_tp;
                document.getElementById('val-rare').innerText = data.rare_count; 
                document.getElementById('val-mail').innerText = data.mail_count; // 🛑 NEW DATA INJECTION
                document.getElementById('rl-badge').innerText = data.rate_limit_count;
                
                let modeBtn = document.getElementById('toggle-mode-btn');
                modeBtn.innerHTML = data.mode === "barbar" ? "🔥 Barbar" : (data.mode === "fast" ? "⚡ Fast" : "🐢 Slow");
                document.getElementById('mode-badge').innerText = data.mode;
                
                let toggleBtn = document.getElementById('toggle-btn');
                if (data.paused) { toggleBtn.className = "btn btn-start"; toggleBtn.innerHTML = "▶️ Start"; document.getElementById('status-badge').innerText = "Pause"; } 
                else { toggleBtn.className = "btn btn-pause"; toggleBtn.innerHTML = "⏸️ Pause"; document.getElementById('status-badge').innerText = "Run"; }

                let newLootHash = data.loots.length > 0 ? JSON.stringify(data.loots[0]) : "empty";
                if (newLootHash !== lastLootHash) {
                    let html = ""; data.loots.slice(0, 5).forEach(l => { 
                        let rewColor = "#fff";
                        let rewLower = l.reward.toLowerCase();
                        if (rewLower.includes("xp") || rewLower.includes("%")) rewColor = "#43b581"; 
                        else if (rewLower.includes("gold")) rewColor = "#faa61a"; 
                        else if (rewLower.includes("token")) rewColor = "#5865F2"; 
                        else if (rewLower.includes("tp") || rewLower.includes("ss") || rewLower.includes("rare")) rewColor = "#ed4245"; 
                        
                        let botAns = l.bot_answer || l.answer;
                        html += `<tr>
                            <td style="font-size:0.7em;color:#72767d;width:20%;">${l.time.split(' ')[1]}</td>
                            <td style="width:35%;"><code style="color:#dcddde;">${botAns}</code></td>
                            <td style="color:${rewColor}; font-weight:bold; font-size:0.85em; text-align:right;">${l.reward}</td>
                        </tr>`; 
                    });
                    document.getElementById('table-body').innerHTML = html; lastLootHash = newLootHash;
                }

                let newChatHash = data.chats.length > 0 ? JSON.stringify(data.chats[0]) : "empty";
                if (newChatHash !== lastChatHash) {
                    if (lastChatHash !== "" && lastChatHash !== "empty") {
                        let lastChatObj = JSON.parse(lastChatHash);
                        for (let c of data.chats) {
                            if (c.msg_id === lastChatObj.msg_id) break;
                            if (c.is_tag && ("Notification" in window) && Notification.permission === "granted") {
                                new Notification("🔔 Mention Kuis!", { body: c.author + ": " + c.content });
                            }
                        }
                    }

                    let html = ""; data.chats.forEach(c => { 
                        let gId = c.guild_id ? c.guild_id : "@me";
                        let cId = c.channel_id ? c.channel_id : data.target_channel_id;
                        let jumpUrl = `https://discord.com/channels/${gId}/${cId}/${c.msg_id}`;
                        
                        let actionBtns = "";
                        if (c.replied) {
                            actionBtns = `<span class="replied-badge">✅ Replied</span> <button class="reply-btn" onclick="replyMsg('${c.msg_id}', '${c.author}')">Balas (lagi)</button>`;
                        } else {
                            actionBtns = `<button class="reply-btn" onclick="replyMsg('${c.msg_id}', '${c.author}')">Balas</button>`;
                        }
                        actionBtns += ` <a href="${jumpUrl}" target="_blank" class="jump-btn">🔗 Go</a>`;
                        
                        let rowStyle = c.is_tag ? 'style="background-color: rgba(250, 166, 26, 0.1);"' : '';

                        html += `<tr ${rowStyle}><td><span style="font-size:0.7em;color:#72767d">${c.time.split(' ')[0]}</span> <span class="chat-author">${c.author}</span>: ${c.content} <div class="action-group">${actionBtns}</div></td></tr>`; 
                    });
                    document.getElementById('chat-body').innerHTML = html; lastChatHash = newChatHash;
                }
            } catch (e) {}
        }
        async function toggleBot() { await fetch('/api/toggle', {method: 'POST'}); fetchAllData(); }
        async function toggleMode() { await fetch('/api/toggle_mode', {method: 'POST'}); fetchAllData(); }
        async function resetStats() { await fetch('/api/reset', {method: 'POST'}); fetchAllData(); }
        async function replyMsg(msgId, author) {
            let txt = prompt(`Balas ke ${author}:`);
            if(txt) {
                await fetch('/api/reply', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({msg_id: msgId, content: txt})});
                fetchAllData(); 
            }
        }
        fetchAllData(); setInterval(fetchAllData, 2000);
    </script>
</body>
</html>
"""

@app.route('/')
def home(): return render_template_string(HTML_TEMPLATE)

@app.route('/manifest.json')
def manifest():
    return jsonify({
      "name": "Dash", "short_name": "Dash", "start_url": "/", "display": "standalone",
      "background_color": "#1e1e24", "theme_color": "#1e1e24"
    })

@app.route('/api/data', methods=['GET'])
def get_data():
    loots = load_json_db(DB_FILE)
    chats = load_json_db(CHAT_DB_FILE)
    now_utc = datetime.now(timezone.utc)
    uptime_delta = now_utc - START_TIME_UTC
    hours, remainder = divmod(int(uptime_delta.total_seconds()), 3600)
    minutes, _ = divmod(remainder, 60)
    
    time_since_admin = (now_utc - last_admin_activity).total_seconds()
    time_since_player = (now_utc - last_player_chat_time).total_seconds()
    
    if bot_mode == "barbar": stealth_str = "🔥 OFF"
    elif time_since_admin < 600.0: stealth_str = f"🚨 ADMIN ({int((600 - time_since_admin)/60)}m)"
    elif time_since_player < 300.0: stealth_str = f"⚠️ Player ({int(300 - time_since_player)}s)"
    else: stealth_str = "🟢 Aman"

    return jsonify({
        "uptime_str": f"{hours}h {minutes}m", "stealth_str": stealth_str, 
        "total_xp": session_total_xp, "total_gold": session_total_gold, "total_token": session_total_token, 
        "total_tp": session_total_tp, "rare_count": session_rare_count, "mail_count": session_mail_count,
        "loots": loots, "chats": chats, "paused": is_paused, "mode": bot_mode, "rate_limit_count": rate_limit_count,
        "target_channel_id": str(TARGET_CHANNEL_ID)
    })

@app.route('/api/toggle', methods=['POST'])
def toggle_state():
    global is_paused, last_activity_time
    is_paused = not is_paused
    if not is_paused: last_activity_time = datetime.now(timezone.utc)
    return jsonify({"status": "ok"})

@app.route('/api/toggle_mode', methods=['POST'])
def toggle_mode():
    global bot_mode
    if bot_mode == "slow": bot_mode = "fast"
    elif bot_mode == "fast": bot_mode = "barbar"
    else: bot_mode = "slow"
    return jsonify({"status": "ok"})

@app.route('/api/reset', methods=['POST'])
def reset_stats():
    global session_total_xp, session_total_gold, session_total_token, session_total_tp, session_rare_count, session_mail_count
    session_total_xp = session_total_gold = session_total_token = session_total_tp = session_rare_count = session_mail_count = 0
    return jsonify({"status": "ok"})

@app.route('/api/reply', methods=['POST'])
def web_reply():
    data = request.json
    if data and 'msg_id' in data and 'content' in data: 
        web_reply_queue.append(data)
        try:
            chats = load_json_db(CHAT_DB_FILE)
            for c in chats:
                if c.get("msg_id") == data["msg_id"]:
                    c["replied"] = True
                    break
            save_json_db(CHAT_DB_FILE, chats)
        except Exception as e: pass
    return jsonify({"status": "ok"})

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

Thread(target=run_web_server).start()

LOGO_MAP = {
    "logo_1": "evian", "logo_3": "kraft", "logo_4": "maggi", "logo_5": "burger king", "logo_6": "ben and jerrys", "logo_7": "chipotle", "logo_9": "dunkin", "logo_10": "fanta", "logo_11": "kitkat", "logo_12": "taco bell", "logo_13": "quaker", "logo_16": "kfc", "logo_17": "pringles", "logo_18": "redbull", "logo_19": "snickers", "logo_20": "sprite", "logo_21": "doritos", "logo_24": "lays", "logo_26": "cocacola", "logo_29": "dominos", "logo_32": "heineken", "logo_33": "pepsi", "logo_34": "mcdonalds", "logo_35": "starbucks", "logo_37": "monster", "logo_38": "pizza hut", "logo_39": "android", "logo_40": "adobe", "logo_41": "chrome", "logo_42": "gmail", "logo_44": "twitter", "logo_45": "starbucks", "logo_46": "xbox", "logo_101": "chanel", "logo_107": "champion", "logo_108": "lv", "logo_110": "levis", "logo_111": "rolex", "logo_112": "dickies", "logo_114": "columbia", "logo_116": "hermes", "logo_117": "palace", "logo_118": "kappa", "logo_119": "burberry", "logo_120": "puma", "logo_121": "reebok", "logo_125": "diesel", "logo_126": "fila", "logo_127": "versace", "logo_129": "hollister", "logo_133": "nike", "logo_136": "ck", "logo_138": "fred perry", "logo_201": "apple", "logo_202": "dolby", "logo_203": "philips", "logo_204": "alibaba", "logo_206": "cisco", "logo_207": "intel", "logo_208": "adobe", "logo_209": "alcatel", "logo_210": "amazon", "logo_211": "amd", "logo_212": "asus", "logo_214": "dell", "logo_215": "fitbit", "logo_216": "fujitsu", "logo_217": "airbnb", "logo_218": "huawei", "logo_219": "t_mobile", "logo_220": "lg", "logo_221": "microsoft", "logo_222": "motorola", "logo_223": "nvidia", "logo_224": "oneplus", "logo_225": "paypal", "logo_227": "samsung", "logo_228": "seagate", "logo_229": "ericsson", "logo_230": "beats", "logo_231": "xiaomi", "logo_232": "uber", "logo_233": "youtube", "logo_234": "twitter", "logo_235": "Blackberry", "logo_236": "dropbox", "logo_237": "facebook", "logo_238": "google", "logo_239": "snapchat", "logo_301": "netflix", "logo_302": "nintendo", "logo_303": "universal", "logo_304": "walking dead", "logo_305": "gameloft", "logo_306": "game of thrones", "logo_307": "discovery", "logo_308": "monopoly", "logo_309": "konami", "logo_311": "bandai", "logo_313": "warner bros", "logo_314": "rockstar", "logo_315": "ff", "logo_317": "activision", "logo_319": "walt disney", "logo_321": "hbo max", "logo_323": "jurassic", "logo_324": "fox", "logo_326": "marvel", "logo_328": "paramount", "logo_329": "sega", "logo_330": "star wars", "logo_331": "tencent", "logo_332": "terminator", "logo_333": "tiktok", "logo_334": "titanic", "logo_335": "soundcloud", "logo_336": "ubisoft", "logo_337": "lego", "logo_338": "discord", "logo_339": "spotify", "logo_402": "cadillac", "logo_403": "chevrolet", "logo_404": "mini", "logo_405": "porsche", "logo_406": "citroen", "logo_408": "infiniti", "logo_409": "jaguar", "logo_410": "volkswagen", "logo_411": "lexus", "logo_412": "peugeot", "logo_413": "mitsubishi", "logo_414": "suzuki", "logo_415": "aston martin", "logo_416": "bentley", "logo_417": "bugatti", "logo_418": "audi", "logo_420": "dodge", "logo_421": "ferrari", "logo_422": "fiat", "logo_423": "ford", "logo_424": "honda", "logo_425": "hyundai", "logo_426": "koenigsegg", "logo_430": "mazda", "logo_431": "nissan", "logo_432": "opel", "logo_433": "renault", "logo_435": "seat", "logo_437": "subaru", "logo_438": "volvo", "logo_439": "bmw", "logo_501": "harley", "logo_502": "nescafe"
}

# =========================================================
# 5. TUMBAL BOT (AKUN KE-2)
# =========================================================
class TumbalBot(discord.Client):
    def __init__(self, *args, **kwargs): super().__init__(*args, **kwargs)
    async def on_ready(self): logging.warning(f"[TUMBAL] Hadir: {self.user}")

tumbal_client = TumbalBot(status=discord.Status.invisible)

async def trigger_tumbal_click(channel_id, message_id):
    await asyncio.sleep(random.uniform(1.0, 3.0))
    try:
        channel = tumbal_client.get_channel(channel_id) or await tumbal_client.fetch_channel(channel_id)
        msg = await channel.fetch_message(message_id)
        target_btn = None
        if msg.components:
            for row in msg.components:
                for child in getattr(row, 'children', []):
                    if hasattr(child, 'click') and "pending" not in str(getattr(child, 'custom_id', '')).lower():
                        target_btn = child; break
                if target_btn: break
        if target_btn and not getattr(target_btn, 'disabled', False):
            if not await force_click_button(tumbal_client, msg, target_btn): await target_btn.click()
    except Exception: pass

# =========================================================
# 6. MAIN BOT (AKUN UTAMA)
# =========================================================
class MySelfBot(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.send_lock = asyncio.Lock()

    async def on_ready(self):
        global client; client = self
        logging.warning(f"[MAIN] Self-bot aktif: {self.user}")
        self.loop.create_task(self.process_web_queue())
        self.loop.create_task(self.background_30s_loop())

    async def background_30s_loop(self):
        global bot_mode
        await self.wait_until_ready()
        while not self.is_closed():
            await asyncio.sleep(30)
            time_since_admin = (datetime.now(timezone.utc) - last_admin_activity).total_seconds()
            time_since_player = (datetime.now(timezone.utc) - last_player_chat_time).total_seconds()
            
            if bot_mode == "slow" and time_since_player >= 300.0 and time_since_admin >= 600.0:
                bot_mode = "fast"
                logging.warning("[AUTO MODE] Kondisi aman (Sepi). Kembali ke FAST MODE.")

    async def process_web_queue(self):
        while not self.is_closed():
            if web_reply_queue:
                req = web_reply_queue.pop(0)
                channel = self.get_channel(TARGET_CHANNEL_ID)
                if channel:
                    try:
                        msg = await channel.fetch_message(int(req['msg_id']))
                        async with channel.typing():
                            await asyncio.sleep(1.5)
                            await msg.reply(req['content'])
                    except: pass
            await asyncio.sleep(0.5)

    async def send_random_sticker(self, channel):
        try:
            if channel.guild and channel.guild.stickers:
                stk = random.choice(channel.guild.stickers)
                await channel.send(stickers=[stk])
                logging.warning("[AI CHAT] Mengirim random sticker.")
        except: pass

    async def send_idle_chat(self):
        wib = (datetime.now(timezone.utc) + timedelta(hours=7)).strftime('%H:%M WIB')
        prompt = f"Waktu sekarang {wib}. Buat 1 keluhan singkat gamer gen-Z yang pegel ngetik kuis Discord terus. Max 5 kata. Huruf kecil. HANYA berikan output teksnya saja."
        msg = await generate_gemini_text(prompt)
        if msg:
            await asyncio.sleep(random.uniform(2.0, 5.0))
            channel = self.get_channel(TARGET_CHANNEL_ID)
            if channel:
                async with channel.typing():
                    await asyncio.sleep(2)
                    await channel.send(msg)

    async def send_loss_streak_chat(self):
        global session_last_answer_was_typo
        wib = (datetime.now(timezone.utc) + timedelta(hours=7)).strftime('%H:%M WIB')
        
        if session_last_answer_was_typo:
            prompt = f"Waktu {wib}. Buat 1 keluhan marah/kesal karena barusan ngetik kuisnya typo terus kesalip. Max 6 kata. Huruf kecil, no sensor."
            session_last_answer_was_typo = False
        else:
            prompt = f"Waktu {wib}. Buat 1 keluhan singkat gamer gen-Z karena kesalip jawab kuis Discord. Alasan lag/capek/waktu. Max 6 kata. Huruf kecil."
            
        msg = await generate_gemini_text(prompt)
        if msg:
            await asyncio.sleep(random.uniform(3.0, 6.0))
            channel = self.get_channel(TARGET_CHANNEL_ID)
            if channel:
                async with channel.typing():
                    await asyncio.sleep(2)
                    await channel.send(msg)

    async def send_tag_reply(self, channel):
        prompt = "Ada player discord ngetag kamu. Balas santai max 2 kata. Huruf kecil."
        msg = await generate_gemini_text(prompt)
        if msg:
            await asyncio.sleep(random.uniform(2.0, 6.0))
            async with channel.typing():
                await asyncio.sleep(1.5)
                await channel.send(msg)

    async def process_discord_event(self, message):
        global is_paused, last_activity_time, bot_mode, last_answered_msg_id, last_solved_msg_id, last_player_chat_time
        global quiz_solved_time, last_admin_activity, last_tag_reply_time, last_clicked_btn_msg_id
        global session_total_xp, session_total_gold, session_total_token, session_total_tp, session_rare_count, session_mail_count
        global quiz_solved_counter, next_idle_chat_target, consecutive_losses, next_loss_target
        global session_last_answer_was_typo, last_typed_answer

        if message.channel.id != TARGET_CHANNEL_ID: return

        # RADAR ADMIN
        author_name = message.author.name.lower()
        if any(admin in author_name for admin in ["ternate", "pandansex"]):
            last_admin_activity = datetime.now(timezone.utc)
            if bot_mode == "fast": bot_mode = "slow"

        # SAKLAR REMOTE CONTROL
        is_me = (message.author.id == self.user.id)
        if is_me:
            if "rame" in message.content.lower() and not is_paused: is_paused = True
            elif "capek" in message.content.lower() and is_paused: is_paused = False; last_activity_time = datetime.now(timezone.utc)
            return

        # INTERCEPTOR PLAYER 
        if not is_me and not message.author.bot:
            if message.content and not message.content.startswith('!'):
                wib_time = datetime.now(timezone.utc) + timedelta(hours=7)
                chat_history = load_json_db(CHAT_DB_FILE)
                
                guild_id = str(message.guild.id) if getattr(message, 'guild', None) else "@me"
                is_mentioned = str(self.user.id) in message.content
                is_replied = message.reference and getattr(message.reference.resolved, 'author', None) and message.reference.resolved.author.id == self.user.id
                is_tag = bool(is_mentioned or is_replied)
                
                chat_history.insert(0, {
                    "time": wib_time.strftime('%H:%M:%S WIB'), 
                    "author": message.author.name, 
                    "content": message.content, 
                    "msg_id": str(message.id), 
                    "guild_id": guild_id,
                    "channel_id": str(message.channel.id),
                    "replied": False,
                    "is_tag": is_tag
                })
                save_json_db(CHAT_DB_FILE, chat_history)

                last_player_chat_time = datetime.now(timezone.utc)
                if bot_mode == "fast": bot_mode = "slow"

                if is_tag:
                    if (datetime.now(timezone.utc) - last_tag_reply_time).total_seconds() >= 120.0:
                        last_tag_reply_time = datetime.now(timezone.utc)
                        self.loop.create_task(self.send_tag_reply(message.channel))
            return 

        try:
            if (datetime.now(timezone.utc) - (message.created_at.replace(tzinfo=timezone.utc) if message.created_at.tzinfo is None else message.created_at)).total_seconds() > 60.0: return
        except: pass

        last_activity_time = datetime.now(timezone.utc)

        full_text = message.content or ""
        image_urls = []
        if message.embeds:
            for e in message.embeds:
                if e.title: full_text += "\n" + e.title
                if e.description: full_text += "\n" + e.description
                if e.image and e.image.url: image_urls.append(e.image.url)
                if e.thumbnail and e.thumbnail.url: image_urls.append(e.thumbnail.url)
        content_lower = full_text.lower()

        # =========================================================
        # ALUR 1: DETEKSI TOMBOL "START CHALLENGE" 🎮
        # =========================================================
        if ("start challenge" in content_lower or "needs" in content_lower) and message.components:
            target_btn = None
            for row in message.components:
                for child in getattr(row, 'children', []):
                    if hasattr(child, 'click') and "pending" not in str(getattr(child, 'custom_id', '')).lower():
                        target_btn = child; break
                if target_btn: break
                
            if target_btn and message.id != last_clicked_btn_msg_id and not is_paused:
                last_clicked_btn_msg_id = message.id
                delay = random.uniform(2.0, 4.0) if bot_mode == "slow" else (random.uniform(1.0, 2.0) if bot_mode == "fast" else random.uniform(0.3, 0.8))
                
                async def execute_main_click():
                    await asyncio.sleep(delay)
                    try:
                        if not await force_click_button(self, message, target_btn): await target_btn.click()
                        self.loop.create_task(trigger_tumbal_click(message.channel.id, message.id))
                    except: pass
                self.loop.create_task(execute_main_click())

        # =========================================================
        # ALUR 2: KUIS SELESAI & KALKULASI
        # =========================================================
        if "got it first!" in content_lower or "challenge solved" in content_lower or "time's up!" in content_lower:
            if message.id == last_solved_msg_id: return 
            last_solved_msg_id = message.id
            quiz_solved_time = datetime.now(timezone.utc) 

            if "msdn" in content_lower:
                consecutive_losses = 0; session_last_answer_was_typo = False
                try:
                    ans_match = re.search(r'Answer:\s*([^\n\r]+)', full_text, re.IGNORECASE)
                    rew_match = re.search(r'Reward:\s*([^\n\r]+)', full_text, re.IGNORECASE)
                    
                    str_answer = ans_match.group(1).strip().replace('**', '') if ans_match else "N/A"
                    raw_reward = rew_match.group(1).strip().replace('**', '') if rew_match else "N/A"
                    
                    # 🛑 CEK MAILBOX DI SINI
                    is_mailed = "sent to" in raw_reward.lower() or "mailbox" in raw_reward.lower()
                    
                    str_reward = raw_reward.split("Sent to")[0].strip()

                    history = load_json_db(DB_FILE)
                    if not (len(history) > 0 and history[0].get("answer") == str_answer and history[0].get("reward") == str_reward):
                        history.insert(0, {"time": (datetime.now(timezone.utc) + timedelta(hours=7)).strftime('%Y-%m-%d %H:%M:%S'), "answer": str_answer, "bot_answer": last_typed_answer, "reward": str_reward})
                        save_json_db(DB_FILE, history)
                        
                        def ext_val(p, t): m = re.search(p, t); return int(m.group(1).replace(',', '').replace('.', '')) if m else 0
                        rl = str_reward.lower()
                        session_total_xp += ext_val(r'([\d,\.]+)\s*(?:%|xp)', rl)
                        session_total_gold += ext_val(r'([\d,\.]+)\s*gold', rl)
                        session_total_token += ext_val(r'([\d,\.]+)\s*token', rl)
                        session_total_tp += ext_val(r'([\d,\.]+)\s*tp', rl)
                        if "rare" in rl: session_rare_count += 1
                        if is_mailed: session_mail_count += 1 # 🛑 TAMBAHKAN KE COUNTER
                        
                        quiz_solved_counter += 1
                        if quiz_solved_counter >= next_idle_chat_target:
                            quiz_solved_counter = 0; next_idle_chat_target = random.randint(5, 20)
                            self.loop.create_task(self.send_idle_chat())
                except: pass
            else:
                try:
                    rew_match = re.search(r'Reward:\s*([^\n\r]+)', full_text, re.IGNORECASE)
                    if rew_match and "rare" in rew_match.group(1).lower() and random.random() < 0.3:
                        self.loop.create_task(self.send_random_sticker(message.channel))
                except: pass

                consecutive_losses += 1
                if consecutive_losses >= next_loss_target:
                    consecutive_losses = 0; next_loss_target = random.randint(5, 7)
                    self.loop.create_task(self.send_loss_streak_chat())
            return

        # =========================================================
        # ALUR 3: MENJAWAB KUIS
        # =========================================================
        if "60 seconds" in content_lower or "!char" in content_lower:
            if message.id == last_answered_msg_id or is_paused: return 
            last_answered_msg_id = message.id
            current_quiz_start = datetime.now(timezone.utc)
            final_answer, success = "", False

            if "math" in content_lower:
                try:
                    target_line = next((l for l in full_text.split('\n') if l.startswith("##") or '=' in l), "")
                    if target_line:
                        expr = "".join(re.findall(r'[\d\+\-\*\/\(\)\s]+', target_line.split('=')[0].replace('×', '*').replace('²', '**2')))
                        if expr: final_answer = str(int(round(eval(expr)))); success = True
                except: pass

            if not success and image_urls:
                for img_url in image_urls:
                    match = re.search(r'(flag|animal|logo)_([^.\?]+)', img_url)
                    if match:
                        cat, key = match.groups()
                        if cat == 'logo' and f"logo_{key}" in LOGO_MAP: final_answer = LOGO_MAP[f"logo_{key}"].replace('_', ' ').title(); success = True; break
                        elif cat in ['flag', 'animal']: final_answer = key.replace('_', ' ').title(); success = True; break

            if not success:
                try:
                    resp = ai_client.models.generate_content(model='gemini-2.5-flash', contents=f"Jawab inti kuis ini. HANYA JAWABAN SAJA:\n{full_text.replace('×', '*')}")
                    if resp and resp.text: final_answer = resp.text.strip().replace('.', ''); success = True
                except: pass

            if final_answer and success:
                final_answer, is_typo = apply_human_typing(final_answer)
                session_last_answer_was_typo = is_typo 
                last_typed_answer = final_answer 
                
                async with self.send_lock:
                    reaction_time = random.uniform(1.5, 3.0) if bot_mode == "slow" else (random.uniform(0.5, 1.0) if bot_mode == "fast" else random.uniform(0.1, 0.3))
                    typing_speed = random.uniform(0.2, 0.3) if bot_mode == "slow" else (random.uniform(0.10, 0.18) if bot_mode == "fast" else random.uniform(0.05, 0.08))
                    
                    delay = reaction_time + (len(final_answer) * typing_speed)
                    
                    async with message.channel.typing():
                        await asyncio.sleep(delay)
                        
                    if quiz_solved_time > current_quiz_start and random.random() >= 0.25: return 
                    try: await message.channel.send(final_answer)
                    except: pass

    async def on_message(self, message): await self.process_discord_event(message)
    async def on_message_edit(self, before, after): await self.process_discord_event(after)

# 🛑 START
async def run_bots(): await asyncio.gather(MySelfBot().start(TOKEN_DISCORD), tumbal_client.start(TOKEN_TUMBAL))

if __name__ == "__main__":
    loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
    try: loop.run_until_complete(run_bots())
    except KeyboardInterrupt: pass
