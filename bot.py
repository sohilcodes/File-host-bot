import os, telebot, subprocess, json, re, requests, time, random
from flask import Flask, request, jsonify
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

# ===== DATABASE =====
if os.path.exists(DATA_FILE):
    data = json.load(open(DATA_FILE))
else:
    data = {"users": {}, "premium": [], "bot_users": {}}

def save():
    json.dump(data, open(DATA_FILE, "w"))

processes = {}
running_tokens = {}

otp_store = {}
sessions = {}

# ===== TOKEN SYSTEM =====
def extract_token(path):
    content = open(path).read()
    patterns = [
        r'BOT_TOKEN\s*=\s*["\'](.+?)["\']',
        r'TOKEN\s*=\s*["\'](.+?)["\']'
    ]
    for p in patterns:
        m = re.search(p, content)
        if m:
            return m.group(1)
    return None

def valid_token(token):
    try:
        return requests.get(f"https://api.telegram.org/bot{token}/getMe").status_code == 200
    except:
        return False

def remove_webhook(token):
    try:
        requests.get(f"https://api.telegram.org/bot{token}/deleteWebhook")
    except:
        pass

# ===== SECURITY =====
def is_safe_code(path):
    bad = ["os.remove", "eval(", "exec(", "subprocess", "shutil"]
    code = open(path).read()
    return not any(b in code for b in bad)

# ===== OTP =====
def generate_otp():
    return str(random.randint(100000, 999999))

@app.route("/send_otp", methods=["POST"])
def send_otp():
    uid = request.form.get("user_id")
    otp = generate_otp()
    otp_store[uid] = (otp, time.time())

    try:
        bot.send_message(int(uid), f"🔐 OTP: {otp}")
    except:
        return "Start bot first"

    return "sent"

@app.route("/verify_otp", methods=["POST"])
def verify():
    uid = request.form.get("user_id")
    otp = request.form.get("otp")

    if uid in otp_store:
        real, t = otp_store[uid]
        if time.time() - t < 120 and otp == real:
            sessions[uid] = True
            return "SUCCESS"
    return "FAIL"

@app.route("/login")
def login():
    return '''
    <form action="/send_otp" method="post">
    <input name="user_id" placeholder="Telegram ID">
    <button>Send OTP</button>
    </form><br>
    <form action="/verify_otp" method="post">
    <input name="user_id"><input name="otp">
    <button>Verify</button>
    </form>
    '''

@app.route("/dashboard")
def dash():
    uid = request.args.get("user_id")
    if uid not in sessions:
        return "Login Required"

    return f"""
    Users: {len(data['users'])}<br>
    Bots: {sum(len(v) for v in data['users'].values())}<br>
    Running: {len(processes)}
    """

# ===== TRACK API =====
@app.route("/add_user", methods=["POST"])
def add_user():
    uid = int(request.form.get("user_id"))
    token = request.form.get("token")

    data["bot_users"].setdefault(token, [])
    if uid not in data["bot_users"][token]:
        data["bot_users"][token].append(uid)
        save()

    return jsonify({"ok": True})

# ===== START =====
@bot.message_handler(commands=['start'])
def start(msg):
    uid = str(msg.from_user.id)
    data["users"].setdefault(uid, [])
    save()

    bot.send_message(msg.chat.id,
        "👋 Welcome\n\nUpload .py\n/run file.py\n\n💰 Premium → @SohilCodes"
    )

# ===== UPLOAD =====
@bot.message_handler(content_types=['document'])
def upload(msg):
    uid = str(msg.from_user.id)
    file = msg.document

    if not file.file_name.endswith(".py"):
        return bot.reply_to(msg, "❌ Only .py")

    if uid not in data["premium"] and len(data["users"][uid]) >= 1:
        return bot.reply_to(msg, "💰 Upgrade @SohilCodes")

    info = bot.get_file(file.file_id)
    data_bytes = bot.download_file(info.file_path)

    path = os.path.join(UPLOAD_FOLDER, file.file_name)
    open(path, "wb").write(data_bytes)

    data["users"][uid].append(file.file_name)
    save()

    bot.reply_to(msg, f"✅ Uploaded\n/run {file.file_name}")

# ===== RUN =====
@bot.message_handler(commands=['run'])
def run(msg):
    uid = str(msg.from_user.id)
    file = msg.text.split()[1]
    path = os.path.join(UPLOAD_FOLDER, file)

    if not is_safe_code(path):
        return bot.reply_to(msg, "❌ Unsafe code")

    token = extract_token(path)
    if not token or not valid_token(token):
        return bot.reply_to(msg, "❌ Invalid token")

    remove_webhook(token)

    p = subprocess.Popen(["python3", path])
    processes[uid] = p

    bot.reply_to(msg, "🚀 Started")

# ===== STOP =====
@bot.message_handler(commands=['stop'])
def stop(msg):
    uid = str(msg.from_user.id)
    if uid in processes:
        processes[uid].kill()
        del processes[uid]
        bot.reply_to(msg, "🛑 Stopped")

# ===== BROADCAST =====
@bot.message_handler(commands=['broadcast'])
def bc(msg):
    if msg.from_user.id != ADMIN_ID:
        return

    text = msg.text.replace("/broadcast ", "")
    for token, users in data["bot_users"].items():
        for u in users:
            try:
                requests.get(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    params={"chat_id": u, "text": text}
                )
            except:
                pass

    bot.reply_to(msg, "✅ Sent")

# ===== ADMIN PANEL BUTTONS =====
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

@bot.message_handler(commands=['admin'])
def admin(msg):
    if msg.from_user.id != ADMIN_ID:
        return

    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("👥 Users", callback_data="users"),
        InlineKeyboardButton("💰 Premium", callback_data="premium")
    )
    kb.add(
        InlineKeyboardButton("➕ Add Premium", callback_data="addp"),
        InlineKeyboardButton("➖ Remove Premium", callback_data="remp")
    )

    bot.send_message(msg.chat.id, "👑 Admin Panel", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    if c.from_user.id != ADMIN_ID:
        return

    if c.data == "users":
        bot.answer_callback_query(c.id, f"Users: {len(data['users'])}")

    elif c.data == "premium":
        bot.answer_callback_query(c.id, str(data["premium"]))

    elif c.data == "addp":
        bot.send_message(c.message.chat.id, "Send: /addpremium ID")

    elif c.data == "remp":
        bot.send_message(c.message.chat.id, "Send: /removepremium ID")

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

# ===== RUN =====
def run_flask():
    app.run(host="0.0.0.0", port=5000)

if __name__ == "__main__":
    Thread(target=run_flask).start()
    print("🚀 Running")
    bot.infinity_polling()
