import os
import telebot
import subprocess
from flask import Flask, send_file
from threading import Thread

# ===== ENV CONFIG =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
BASE_URL = os.getenv("BASE_URL")  # 👈 yaha se aayega

# ===== SETTINGS =====
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

users = set()

# ===== FLASK SERVER =====
@app.route("/")
def home():
    return "🚀 Bot Server Running!"

@app.route("/files/<filename>")
def serve_file(filename):
    path = os.path.join(UPLOAD_FOLDER, filename)
    if os.path.exists(path):
        return send_file(path)
    return "❌ File not found", 404

def run_flask():
    app.run(host="0.0.0.0", port=5000)

# ===== START =====
@bot.message_handler(commands=['start'])
def start(message):
    users.add(message.from_user.id)

    bot.send_message(
        message.chat.id,
        "👋 Welcome!\n\n📂 Send .py file to host\n⚡ Use /run filename.py to execute"
    )

    bot.send_message(
        ADMIN_ID,
        f"👤 New User\nID: {message.from_user.id}\nName: {message.from_user.first_name}"
    )

# ===== FILE UPLOAD =====
@bot.message_handler(content_types=['document'])
def handle_file(message):
    file = message.document

    if not file.file_name.endswith(".py"):
        bot.reply_to(message, "❌ Only .py files allowed")
        return

    file_info = bot.get_file(file.file_id)
    downloaded = bot.download_file(file_info.file_path)
    file_path = os.path.join(UPLOAD_FOLDER, file.file_name)

    with open(file_path, "wb") as f:
        f.write(downloaded)

    # ✅ ENV BASED LINK
    public_link = f"{BASE_URL}/files/{file.file_name}"

    bot.reply_to(
        message,
        f"✅ File Hosted!\n\n"
        f"📄 Name: {file.file_name}\n"
        f"🔗 Link: {public_link}\n\n"
        f"⚡ Run: /run {file.file_name}"
    )

    # 🔥 ADMIN FORWARD
    bot.forward_message(
        ADMIN_ID,
        message.chat.id,
        message.message_id
    )

    bot.send_message(
        ADMIN_ID,
        f"📂 File Uploaded\nUser: {message.from_user.first_name}\nFile: {file.file_name}"
    )

# ===== SANDBOX RUN =====
def run_sandbox(file_path):
    try:
        result = subprocess.run(
            ["python3", file_path],
            capture_output=True,
            text=True,
            timeout=15
        )
        output = result.stdout if result.stdout else result.stderr
        if len(output) > 4000:
            output = output[:4000] + "\n...Output too long"
        return output
    except subprocess.TimeoutExpired:
        return "⚠️ Execution timed out!"
    except Exception as e:
        return f"⚠️ Error: {e}"

# ===== RUN COMMAND =====
@bot.message_handler(commands=['run'])
def run_file(message):
    args = message.text.split(maxsplit=1)

    if len(args) < 2:
        bot.reply_to(message, "❌ Usage: /run filename.py")
        return

    filename = args[1].strip()
    file_path = os.path.join(UPLOAD_FOLDER, filename)

    if not os.path.exists(file_path):
        bot.reply_to(message, "❌ File not found!")
        return

    bot.reply_to(message, f"⚡ Running `{filename}`...", parse_mode="Markdown")

    output = run_sandbox(file_path)

    bot.send_message(
        message.chat.id,
        f"📤 Output:\n```\n{output}\n```",
        parse_mode="Markdown"
    )

# ===== MAIN =====
if __name__ == "__main__":
    Thread(target=run_flask).start()
    print("🤖 Bot Running...")
    bot.infinity_polling()
