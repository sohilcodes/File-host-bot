import os
import telebot
import subprocess
import json
from flask import Flask, send_file
from threading import Thread
import time

# ===== ENV =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
BASE_URL = os.getenv("BASE_URL")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ===== DATABASE FILES =====
DATA_FILE = "data.json"

# ===== LOAD DATA =====
if os.path.exists(DATA_FILE):
    with open(DATA_FILE) as f:
        data = json.load(f)
else:
    data = {
        "users": {},
        "premium": []
    }

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump(data, f)

# ===== PROCESS STORE =====
processes = {}

# ===== FLASK =====
@app.route("/")
def home():
    return "🚀 Hosting Server Running"

@app.route("/files/<filename>")
def files(filename):
    return send_file(os.path.join(UPLOAD_FOLDER, filename))

def run_flask():
    app.run(host="0.0.0.0", port=5000)

# ===== START =====
@bot.message_handler(commands=['start'])
def start(message):
    uid = str(message.from_user.id)

    if uid not in data["users"]:
        data["users"][uid] = []
        save_data()

    bot.send_message(message.chat.id,
        "👋 Welcome!\n\n"
        "📂 Upload .py file to host\n"
        "⚡ /run filename.py\n"
        "🛑 /stop\n📊 /status"
    )

# ===== FILE UPLOAD =====
@bot.message_handler(content_types=['document'])
def upload(message):
    uid = str(message.from_user.id)
    file = message.document

    if not file.file_name.endswith(".py"):
        return bot.reply_to(message, "❌ Only .py allowed")

    # LIMIT SYSTEM
    if uid not in data["premium"] and len(data["users"][uid]) >= 1:
        return bot.reply_to(message,
            "💰 Free Plan Limit Reached!\n\n"
            "👉 Contact Admin to upgrade"
        )

    file_info = bot.get_file(file.file_id)
    downloaded = bot.download_file(file_info.file_path)

    path = os.path.join(UPLOAD_FOLDER, file.file_name)

    with open(path, "wb") as f:
        f.write(downloaded)

    data["users"][uid].append(file.file_name)
    save_data()

    link = f"{BASE_URL}/files/{file.file_name}"

    bot.reply_to(message,
        f"✅ Hosted!\n\n📄 {file.file_name}\n🔗 {link}"
    )

    # ADMIN FORWARD
    bot.forward_message(ADMIN_ID, message.chat.id, message.message_id)

# ===== RUN =====
@bot.message_handler(commands=['run'])
def run(message):
    uid = str(message.from_user.id)
    args = message.text.split(maxsplit=1)

    if len(args) < 2:
        return bot.reply_to(message, "Usage: /run file.py")

    filename = args[1]

    if filename not in data["users"].get(uid, []):
        return bot.reply_to(message, "❌ Not your file")

    if uid in processes:
        return bot.reply_to(message, "⚠️ Already running")

    process = subprocess.Popen(["python3", os.path.join(UPLOAD_FOLDER, filename)])
    processes[uid] = (process, filename)

    bot.reply_to(message, f"🚀 Started {filename}")

# ===== STOP =====
@bot.message_handler(commands=['stop'])
def stop(message):
    uid = str(message.from_user.id)

    if uid not in processes:
        return bot.reply_to(message, "❌ No running bot")

    process, _ = processes[uid]
    process.kill()
    del processes[uid]

    bot.reply_to(message, "🛑 Stopped")

# ===== STATUS =====
@bot.message_handler(commands=['status'])
def status(message):
    uid = str(message.from_user.id)

    if uid in processes:
        bot.reply_to(message, "🟢 Running")
    else:
        bot.reply_to(message, "🔴 Not running")

# ===== ADMIN PANEL =====
@bot.message_handler(commands=['addpremium'])
def addpremium(message):
    if message.from_user.id != ADMIN_ID:
        return

    uid = message.text.split()[1]

    if uid not in data["premium"]:
        data["premium"].append(uid)
        save_data()

    bot.reply_to(message, f"✅ {uid} is now Premium")

@bot.message_handler(commands=['removepremium'])
def removepremium(message):
    if message.from_user.id != ADMIN_ID:
        return

    uid = message.text.split()[1]

    if uid in data["premium"]:
        data["premium"].remove(uid)
        save_data()

    bot.reply_to(message, f"❌ {uid} removed from Premium")

# ===== AUTO RESTART SYSTEM =====
def monitor():
    while True:
        for uid, (proc, filename) in list(processes.items()):
            if proc.poll() is not None:  # stopped
                new_proc = subprocess.Popen(["python3", os.path.join(UPLOAD_FOLDER, filename)])
                processes[uid] = (new_proc, filename)
        time.sleep(5)

# ===== RUN =====
if __name__ == "__main__":
    Thread(target=run_flask).start()
    Thread(target=monitor).start()
    print("🚀 Hosting Bot Running")
    bot.infinity_polling()
