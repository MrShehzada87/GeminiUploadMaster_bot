import asyncio
import os
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from apify_client import ApifyClient
from telegram import Bot, InputMediaPhoto, InputMediaVideo, Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TELEGRAM_BOT_TOKEN = "8960878764:AAGia67FIQH6foQvVsR7Uu2Hjswi674JC_A"
TELEGRAM_USER_ID = 1426255282
APIFY_API_TOKEN = "apify_api_EGmxew3AxVjwTE3IDRSK3fK6bw2aXs1jMXzG"

UPSTASH_URL = "https://thorough-lion-149431.upstash.io"
UPSTASH_TOKEN = "gQAAAAAAAke3AAIgcDE3YWViMDExYWQwM2U0ZWM3OWI3YjI3ZDhjNTg5ZGZiMg"

# --- Redis Helper Functions ---
def redis_get_users():
    try:
        headers = {"Authorization": f"Bearer {UPSTASH_TOKEN}"}
        res = requests.get(f"{UPSTASH_URL}/smembers/monitored_users", headers=headers, timeout=5).json()
        result = res.get("result", [])
        return set(result) if isinstance(result, list) else set()
    except Exception: return set()

def redis_add_user(username):
    try:
        headers = {"Authorization": f"Bearer {UPSTASH_TOKEN}"}
        requests.get(f"{UPSTASH_URL}/sadd/monitored_users/{username}", headers=headers)
    except Exception: pass

def redis_remove_user(username):
    try:
        headers = {"Authorization": f"Bearer {UPSTASH_TOKEN}"}
        requests.get(f"{UPSTASH_URL}/srem/monitored_users/{username}", headers=headers)
    except Exception: pass

def is_post_sent(post_id):
    try:
        headers = {"Authorization": f"Bearer {UPSTASH_TOKEN}"}
        res = requests.get(f"{UPSTASH_URL}/sismember/sent_posts/{post_id}", headers=headers, timeout=5).json()
        return res.get("result") == 1
    except Exception: return False

def mark_post_sent(post_id):
    try:
        headers = {"Authorization": f"Bearer {UPSTASH_TOKEN}"}
        requests.get(f"{UPSTASH_URL}/sadd/sent_posts/{post_id}", headers=headers)
    except Exception: pass

# --- Web Server ---
class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is Running Alive 24/7!")

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    server.serve_forever()

# --- Scraper Core Logic ---
async def scrape_and_send(bot: Bot, username: str, limit: int = 10, is_force: bool = False):
    apify_client = ApifyClient(APIFY_API_TOKEN)
    try:
        run = apify_client.actor("apify/instagram-scraper").call(
            run_input={"directUrls": [f"https://www.instagram.com/{username}/"], "resultsLimit": limit}
        )
        dataset_id = run["defaultDatasetId"] if isinstance(run, dict) else run.default_dataset_id
        items = apify_client.dataset(dataset_id).list_items().items
        
        # Oldest to Newest অর্ডার
        items.reverse()
        
        if not items and is_force:
            await bot.send_message(chat_id=TELEGRAM_USER_ID, text="⚠️ কোনো পোস্ট পাওয়া যায়নি।")
            return

        sent_count = 0
        for item in items:
            post_id = item.get("id") or item.get("shortCode") or item.get("url")
            
            # Auto-monitoring মোডে থাকলে ডুপ্লিকেট চেকিং করবে, ম্যানুয়াল /check দিলে ফিল্টার ছাড়া ১০টিই পাঠাবে
            if not is_force and post_id and is_post_sent(post_id):
                continue
            
            post_type = item.get("type", "Post")
            if post_type == "GraphVideo": post_type = "Reel/Video"
            elif post_type == "GraphSidecar": post_type = "Carousel Post"
            
            caption = f"👤 User: @{username}\n📌 Type: {post_type}"
            sent_status = False

            # Media Extraction Logic
            media_group = []
            child_posts = item.get("childPosts", [])

            if item.get("isVideo") and item.get("videoUrl"):
                await bot.send_video(chat_id=TELEGRAM_USER_ID, video=item.get("videoUrl"), caption=caption)
                sent_status = True
            elif child_posts:
                for child in child_posts[:10]:
                    v_url = child.get("videoUrl")
                    d_url = child.get("displayUrl")
                    if v_url: media_group.append(InputMediaVideo(media=v_url))
                    elif d_url: media_group.append(InputMediaPhoto(media=d_url))
                if media_group:
                    media_group[0].caption = caption
                    await bot.send_media_group(chat_id=TELEGRAM_USER_ID, media=media_group)
                    sent_status = True
            else:
                img_url = item.get("displayUrl") or item.get("imageUrl")
                if img_url:
                    await bot.send_photo(chat_id=TELEGRAM_USER_ID, photo=img_url, caption=caption)
                    sent_status = True

            if sent_status:
                sent_count += 1
                if post_id:
                    mark_post_sent(post_id)

        if is_force and sent_count == 0:
            await bot.send_message(chat_id=TELEGRAM_USER_ID, text="ℹ️ কোনো নতুন মিডিয়া পাওয়া যায়নি।")

    except Exception as e:
        if is_force: 
            await bot.send_message(chat_id=TELEGRAM_USER_ID, text=f"❌ Error: {e}")

# --- Bot Commands ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 ইনস্টাগ্রাম বট প্রস্তুত!\n\n- /add username\n- /remove username\n- /list\n- /check username")

async def add_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ ইউজারনেম দিন। যেমন: /add username")
        return
    username = context.args[0].replace("@", "").strip().lower()
    redis_add_user(username)
    await update.message.reply_text(f"✅ {username} পারমানেন্ট মনিটরিং লিস্টে যোগ করা হয়েছে।")

async def remove_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ ইউজারনেম দিন। যেমন: /remove username")
        return
    username = context.args[0].replace("@", "").strip().lower()
    redis_remove_user(username)
    await update.message.reply_text(f"❌ {username} লিস্ট থেকে বাদ দেওয়া হয়েছে।")

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = redis_get_users()
    if users:
        user_list_text = "\n".join([f"- {u}" for u in users])
        await update.message.reply_text(f"📋 বর্তমান মনিটরিং লিস্ট ({len(users)}জন):\n{user_list_text}")
    else:
        await update.message.reply_text("📋 লিস্ট বর্তমানে খালি। /add দিয়ে ইউজার যোগ করুন।")

async def force_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ ইউজারনেম দিন। যেমন: /check username")
        return
    username = context.args[0].replace("@", "").strip().lower()
    await update.message.reply_text(f"🔎 <b>{username}</b>-এর সর্বশেষ ১০টি পোস্ট ম্যানুয়ালি চেক ও সেন্ড করা হচ্ছে...", parse_mode="HTML")
    await scrape_and_send(context.bot, username, limit=10, is_force=True)

async def monitor_instagram(bot: Bot):
    while True:
        users_to_check = list(redis_get_users())
        for username in users_to_check:
            # অটো মনিটরিংয়ে সর্বশেষ ৫টি চেক করবে এবং শুধু নতুনটা পাঠাবে
            await scrape_and_send(bot, username, limit=5, is_force=False)
        await asyncio.sleep(60)  # প্রতি ১ মিনিট পরপর নতুন পোস্ট দ্রুত পাওয়ার জন্য চেক করবে

async def main():
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("add", add_user))
    application.add_handler(CommandHandler("remove", remove_user))
    application.add_handler(CommandHandler("list", list_users))
    application.add_handler(CommandHandler("check", force_check))
    
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    asyncio.create_task(monitor_instagram(bot))
    
    async with application:
        await application.start()
        await application.updater.start_polling()
        while True:
            await asyncio.sleep(3600)

if __name__ == '__main__':
    threading.Thread(target=run_dummy_server, daemon=True).start()
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
