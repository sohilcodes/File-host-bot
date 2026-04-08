import os, telebot, subprocess, json, re, requests, time, random
from flask import Flask, request, jsonify
from threading import Thread
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

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
otp_store = {}
sessions = {}

# ===== TOKEN =====
def extract_token(path):
    code = open(path).read()
    patterns = [
        r'BOT_TOKEN\s*=\s*["\'](.+?)["\']',
        r'TOKEN\s*=\s*["\'](.+?)["\']'
    ]
    for p in patterns:
        m = re.search(p, code)
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
        bot.send_message(int(uid), f"🔐 Your OTP: {otp}")
    except:
        return "START_BOT_FIRST"

    return "SENT"

@app.route("/verify_otp", methods=["POST"])
def verify():
    uid = request.form.get("user_id")
    otp = request.form.get("otp")

    if uid in otp_store:
        real, t = otp_store[uid]

        if time.time() - t < 120 and otp == real:
            sessions[uid] = True

            try:
                bot.send_message(int(uid), "✅ Login Successful on Dashboard")
            except:
                pass

            del otp_store[uid]
            return "SUCCESS"

    return "FAIL"

# ===== LOGIN UI =====
@app.route("/login")
def login():
    return """
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Login</title>
<style>
body{background:#0f172a;color:white;font-family:sans-serif;display:flex;justify-content:center;align-items:center;height:100vh;}
.box{background:#1e293b;padding:25px;border-radius:15px;width:90%;max-width:350px;text-align:center;}
input{width:90%;padding:12px;margin:10px 0;border:none;border-radius:8px;}
button{width:95%;padding:12px;background:#22c55e;border:none;border-radius:8px;color:white;font-weight:bold;}
#otpBox{display:none;}
</style>
</head>
<body>
<div class="box">
<h2>🔐 Login</h2>

<input id="uid" placeholder="Telegram User ID">
<button onclick="sendOTP()">Send OTP</button>

<div id="otpBox">
<input id="otp" placeholder="Enter OTP">
<button onclick="verifyOTP()">Verify</button>
</div>

<p id="msg"></p>

</div>

<script>
function sendOTP(){
let uid=document.getElementById("uid").value;

fetch("/send_otp",{method:"POST",headers:{"Content-Type":"application/x-www-form-urlencoded"},body:"user_id="+uid})
.then(res=>res.text())
.then(d=>{
document.getElementById("msg").innerText="OTP Sent";
document.getElementById("otpBox").style.display="block";
});
}

function verifyOTP(){
let uid=document.getElementById("uid").value;
let otp=document.getElementById("otp").value;

fetch("/verify_otp",{method:"POST",headers:{"Content-Type":"application/x-www-form-urlencoded"},body:"user_id="+uid+"&otp="+otp})
.then(res=>res.text())
.then(d=>{
if(d=="SUCCESS"){
window.location="/dashboard?user_id="+uid;
}else{
document.getElementById("msg").innerText="Invalid OTP";
}
});
}
</script>

</body>
</html>
"""

# ===== DASHBOARD =====
@app.route("/dashboard")
def dash():
    uid = request.args.get("user_id")

    if uid not in sessions:
        return "Login Required"

    return f"""
    <h2>Dashboard</h2>
    Users: {len(data['users'])}<br>
    Bots: {sum(len(v) for v in data['users'].values())}<br>
    Running: {len(processes)}
    """

# ===== TRACK USERS =====
@app.route("/add_user", methods=["POST"])
def add_user():
    uid = int(request.form.get("user_id"))
    token = request.form.get("token")

    data["bot_users"].setdefault(token, [])
    if uid not in data["bot_users"][token]:
        data["bot_users"][token].append(uid)
        save()

    return jsonify({"ok": True})

# ===== TELEGRAM BOT =====
@bot.message_handler(commands=['start'])
def start(msg):
    uid = str(msg.from_user.id)
    data["users"].setdefault(uid, [])
    save()

    bot.send_message(msg.chat.id,
        "👋 Welcome\nUpload .py file\n/run file.py\n\n💰 Premium → @SohilCodes"
    )

# ===== UPLOAD =====
@bot.message_handler(content_types=['document'])
def upload(msg):
    uid = str(msg.from_user.id)
    file = msg.document

    if not file.file_name.endswith(".py"):
        return bot.reply_to(msg, "Only .py allowed")

    if uid not in data["premium"] and len(data["users"][uid]) >= 1:
        return bot.reply_to(msg, "Upgrade → @SohilCodes")

    f = bot.get_file(file.file_id)
    data_bytes = bot.download_file(f.file_path)

    path = os.path.join(UPLOAD_FOLDER, file.file_name)
    open(path, "wb").write(data_bytes)

    data["users"][uid].append(file.file_name)
    save()

    bot.reply_to(msg, f"Uploaded\n/run {file.file_name}")

# ===== RUN =====
@bot.message_handler(commands=['run'])
def run(msg):
    uid = str(msg.from_user.id)
    file = msg.text.split()[1]
    path = os.path.join(UPLOAD_FOLDER, file)

    if not is_safe_code(path):
        return bot.reply_to(msg, "Unsafe code")

    token = extract_token(path)
    if not token or not valid_token(token):
        return bot.reply_to(msg, "Invalid token")

    remove_webhook(token)

    p = subprocess.Popen(["python3", path])
    processes[uid] = p

    bot.reply_to(msg, "Started")

# ===== STOP =====
@bot.message_handler(commands=['stop'])
def stop(msg):
    uid = str(msg.from_user.id)
    if uid in processes:
        processes[uid].kill()
        del processes[uid]
        bot.reply_to(msg, "Stopped")

# ===== ADMIN PANEL =====
@bot.message_handler(commands=['admin'])
def admin(msg):
    if msg.from_user.id != ADMIN_ID:
        return

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("Users", callback_data="users"))
    kb.add(InlineKeyboardButton("Premium", callback_data="premium"))
    bot.send_message(msg.chat.id, "Admin Panel", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    if c.from_user.id != ADMIN_ID:
        return

    if c.data == "users":
        bot.answer_callback_query(c.id
