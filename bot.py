import os
import telebot
import subprocess
import json
import re
import requests
import time
from flask import Flask, send_file
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

# ===== LOAD DATA =====
if os.path.exists(DATA_FILE):
    with open(DATA_FILE) as f:
        data = json.load(f)
else:
    data = {"users": {}, "premium": []}

def save():
    with open(DATA_FILE, "w") as f:
        json.dump(data, f)

# ===== PROCESS STORE =====
processes = {}
running_tokens = {}

# ===== FLASK =====
@app.route("/")
def home():
    return "🚀 Hosting Live"

@app.route("/files/<filename>")
def files(filename):
    return send_file(os.path.join(UPLOAD_FOLDER, filename))

def run_flask():
    app.run(host="0.0.0.0", port=5000)

# ===== TOKEN EXTRACT =====
def extract_token(path):
    with open(path, "r") as f:
        content = f.read()
    match = re.search(r'BOT_TOKEN\s*=\s*["\'](.+?)["\']', content)
    return match.group(1) if match else None

def valid_token(token):
    try:
        r = requests.get(f"https://api.telegram.org/bot{token}/getMe")
        return r.status_code == 200
    except:
        return False

# ===== START =====
@bot.message_handler(commands=['start'])
def start(message):
    uid = str(message.from_user.id)

    if uid not in data["users"]:
        data["users"][uid] = []
        save()

    bot.send_message(message.chat.id,
        "👋 Welcome!\n\n"
        "📂 Upload .py file\n"
        "⚡ /run file.py\n🛑 /stop\n📊 /status"
    )

# ===== UPLOAD =====
@bot.message_handler(content_types=['document'])
def upload(message):
    uid = str(message.from_user.id)
    file = message.document

    if not file.file_name.endswith(".py"):
        return bot.reply_to(message, "❌ Only .py")

    # LIMIT
    if uid not in data["premium"] and len(data["users"][uid]) >= 1:
        return bot.reply_to(message, "💰 Upgrade to upload more files")

    info = bot.get_file(file.file_id)
    downloaded = bot.download_file(info.file_path)

    path = os.path.join(UPLOAD_FOLDER, file.file_name)

    with open(path, "wb") as f:
        f.write(downloaded)

    data["users"][uid].append(file.file_name)
    save()

    link = f"{BASE_URL}/files/{file.file_name}"

    bot.reply_to(message, f"✅ Hosted\n🔗 {link}")

    bot.forward_message(ADMIN_ID, message.chat.id, message.message_id)

# ===== RUN =====
@bot.message_handler(commands=['run'])
def run(message):
    uid = str(message.from_user.id)
    args = message.text.split(maxsplit=1)

    if len(args) < 2:
        return bot.reply_to(message, "Usage: /run file.py")

    filename = args[1]
    path = os.path.join(UPLOAD_FOLDER, filename)

    if filename not in data["users"].get(uid, []):
        return bot.reply_to(message, "❌ Not your file")

    if uid in processes:
        return bot.reply_to(message, "⚠️ Already running")

    token = extract_token(path)

    if not token:
        return bot.reply_to(message, "❌ BOT_TOKEN not found")

    if token == BOT_TOKEN:
        return bot.reply_to(message, "❌ Main token not allowed")

    if not valid_token(token):
        return bot.reply_to(message, "❌ Invalid token")

    if token in running_tokens:
        return bot.reply_to(message, "⚠️ Token already running")

    process = subprocess.Popen(["python3", path])
    processes[uid] = (process, filename, token)
    running_tokens[token] = uid

    bot.reply_to(message, f"🚀 Started {filename}")

# ===== STOP =====
@bot.message_handler(commands=['stop'])
def stop(message):
    uid = str(message.from_user.id)

    if uid not in processes:
        return bot.reply_to(message, "❌ No bot")

    process, _, token = processes[uid]
    process.kill()

    del processes[uid]
    if token in running_tokens:
        del running_tokens[token]

    bot.reply_to(message, "🛑 Stopped")

# ===== STATUS =====
@bot.message_handler(commands=['status'])
def status(message):
    uid = str(message.from_user.id)
    bot.reply_to(message, "🟢 Running" if uid in processes else "🔴 Stopped")

# ===== ADMIN =====
@bot.message_handler(commands=['addpremium'])
def addp(message):
    if message.from_user.id != ADMIN_ID:
        return
    uid = message.text.split()[1]
    data["premium"].append(uid)
    save()
    bot.reply_to(message, "✅ Premium added")

# ===== AUTO RESTART =====
def monitor():
    while True:
        for uid, (proc, file, token) in list(processes.items()):
            if proc.poll() is not None:
                new = subprocess.Popen(["python3", os.path.join(UPLOAD_FOLDER, file)])
                processes[uid] = (new, file, token)
        time.sleep(5)

# ===== RUN =====
if __name__ == "__main__":
    Thread(target=run_flask).start()
    Thread(target=monitor).start()
    print("🚀 Hosting Bot Running")
    bot.infinity_polling()
