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
logs = {}

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

# ===== ERROR MONITOR =====
def monitor(uid, process, log_file):
    process.wait()

    try:
        with open(log_file) as f:
            content = f.read()
    except:
        content = "No logs"

    if "Traceback" in content or "Error" in content:
        msg = "❌ Bot Crashed!\n\nLast Logs:\n" + content[-1000:]

        try:
            bot.send_message(int(uid), msg)
        except:
            pass

        try:
            bot.send_message(ADMIN_ID, f"🚨 User {uid} bot crashed\n\n{content[-1000:]}")
        except:
            pass

# ===== RUN BOT =====
def run_bot(uid, path):
    log_file = f"logs_{uid}.txt"

    with open(log_file, "w") as f:
        p = subprocess.Popen(
            ["python3", path],
            stdout=f,
            stderr=f
        )

    processes[uid] = p
    logs[uid] = log_file

    Thread(target=monitor, args=(uid, p, log_file)).start()

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
                bot.send_message(int(uid), "✅ Login Successful")
            except:
                pass

            del otp_store[uid]
            return "SUCCESS"

    return "FAIL"

# ===== LOGIN UI =====
@app.route("/login")
def login():
    return """
    <html>
    <body style="background:#0f172a;color:white;text-align:center;">
    <h2>🔐 Login</h2>

    <input id="uid" placeholder="Telegram ID"><br><br>
    <button onclick="sendOTP()">Send OTP</button><br><br>

    <div id="otpBox" style="display:none;">
        <input id="otp" placeholder="OTP"><br><br>
        <button onclick="verifyOTP()">Verify</button>
    </div>

    <p id="msg"></p>

    <script>
    function sendOTP(){
        let uid=document.getElementById("uid").value;

        fetch("/send_otp",{method:"POST",headers:{"Content-Type":"application/x-www-form-urlencoded"},body:"user_id="+uid})
        .then(()=>{document.getElementById("otpBox").style.display="block";});
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
    Users: {len(data['users'])}<br>
    Bots: {sum(len(v) for v in data['users'].values())}<br>
    Running: {len(processes)}
    """

# ===== BOT START =====
@bot.message_handler(commands=['start'])
def start(msg):
    uid = str(msg.from_user.id)
    data["users"].setdefault(uid, [])
    save()

    bot.send_message(msg.chat.id,
        "👋 Upload .py\n/run file.py\n/logs to view logs"
    )

# ===== UPLOAD =====
@bot.message_handler(content_types=['document'])
def upload(msg):
    uid = str(msg.from_user.id)
    file = msg.document

    if not file.file_name.endswith(".py"):
        return bot.reply_to(msg, "Only .py")

    if uid not in data["premium"] and len(data["users"][uid]) >= 1:
        return bot.reply_to(msg, "Upgrade required")

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
    run_bot(uid, path)

    bot.reply_to(msg, "Started with monitoring")

# ===== LOGS =====
@bot.message_handler(commands=['logs'])
def logs_cmd(msg):
    uid = str(msg.from_user.id)

    if uid not in logs:
        return bot.reply_to(msg, "No logs")

    with open(logs[uid]) as f:
        content = f.read()[-4000:]

    bot.reply_to(msg, content)

# ===== RUN =====
def run_flask():
    app.run(host="0.0.0.0", port=5000)

if __name__ == "__main__":
    Thread(target=run_flask).start()
    bot.infinity_polling()
