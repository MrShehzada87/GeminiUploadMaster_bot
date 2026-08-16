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

def redis_get_users():
    try:
        headers = {"Authorization": f"Bearer {UPSTASH_TOKEN}"}
        res = requests.get(f"{UPSTASH_URL}/smembers/monitored_users", headers=headers).json()
        return set(res.get("result", []))
    except Exception as e:
        print(f"Redis get error: {e}")
        return set()

def redis_add_user(username):
    try:
        headers = {"Authorization": f"Bearer {UPSTASH_TOKEN}"}
        requests.get(f"{UPSTASH_URL}/sadd/monitored_users/{username}", headers=headers)
    except Exception as e:
        print(f"Redis add error: {e}")

def redis_remove_user(username):
    try:
        headers = {"Authorization": f"Bearer {UPSTASH_TOKEN}"}
        requests.get(f"{UPSTASH_URL}/srem/monitored_users/{username}", headers=headers)
    except Exception as e:
        print(f"Redis remove error: {e}")

PROCESSED_IDS = set()

class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is Running Alive 24/7!")

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    server.serve_forever()

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 ইনস্টাগ্রাম ট্র্যাকার বট চালু আছে!\n\n- /add username\n- /remove username\n- /list\n- /check username")

async def add_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ ইউজারনেম দিন। যেমন: /add username")
        return
    username = context.args[0].replace("@", "").strip().lower()
    users = redis_get_users()
    if username not in users:
        redis_add_user(username)
        await update.message.reply_text(f"✅ {username} পারমানেন্ট মনিটরিং লিস্টে যোগ করা হয়েছে।")
    else:
        await update.message.reply_text(f"⚠️ {username} অলরেডি লিস্টে আছে।")

async def remove_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ ইউজারনেম দিন। যেমন: /remove username")
        return
    username = context.args[0].replace("@", "").strip().lower()
    users = redis_get_users()
    if username in users:
        redis_remove_user(username)
        await update.message.reply_text(f"❌ {username} লিস্ট থেকে বাদ দেওয়া হয়েছে।")
    else:
        await update.message.reply_text(f"⚠️ {username} লিস্টে পাওয়া যায়নি।")

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = redis_get_users()
    if users:
        user_list_text = "\n".join([f"- {u}" for u in users])
        await update.message.reply_text(f"📋 বর্তমান মনিটরিং লিস্ট ({len(users)}জন):\n{user_list_text}")
    else:
        await update.message.reply_text("📋 লিস্ট বর্তমানে খালি। /add দিয়ে ইউজার যোগ করুন।")

async def scrape_and_send(bot: Bot, username: str, limit: int = 10, is_force: bool = False):
    apify_client = ApifyClient(APIFY_API_TOKEN)
    
    try:
        run_posts = apify_client.actor("apify/instagram-scraper").call(
            run_input={
                "directUrls": [f"https://www.instagram.com/{username}/"],
                "resultsLimit": limit
            }
        )
        items = apify_client.dataset(run_posts["defaultDatasetId"]).list_items().items
    except Exception as e:
        print(f"Scrape error: {e}")
        items = []

    for item in items:
        media_id = item.get("id") or item.get("url")
        
        # ফোর্স চেক হলে আইডি স্কিপ করবে না
        if not is_force and media_id in PROCESSED_IDS:
            continue

        media_group = []

        # Album / Carousel Post
        if item.get("childPosts"):
            for child in item.get("childPosts", []):
                v_url = child.get("videoUrl")
                d_url = child.get("displayUrl")
                if v_url:
                    media_group.append(InputMediaVideo(media=v_url))
                elif d_url:
                    media_group.append(InputMediaPhoto(media=d_url))

        # Single Media
        else:
            v_url = item.get("videoUrl")
            d_url = item.get("displayUrl") or item.get("imageUrl") or item.get("url")
            
            if item.get("isVideo") and v_url:
                media_group.append(InputMediaVideo(media=v_url))
            elif d_url:
                media_group.append(InputMediaPhoto(media=d_url))

        # Telegram-এ মিডিয়া সেন্ড করা
        if media_group:
            chunks = [media_group[i:i + 10] for i in range(0, len(media_group), 10)]
            for chunk in chunks:
                try:
                    if len(chunk) > 1:
                        await bot.send_media_group(chat_id=TELEGRAM_USER_ID, media=chunk)
                    elif len(chunk) == 1:
                        if isinstance(chunk[0], InputMediaVideo):
                            await bot.send_video(chat_id=TELEGRAM_USER_ID, video=chunk[0].media)
                        else:
                            await bot.send_photo(chat_id=TELEGRAM_USER_ID, photo=chunk[0].media)
                    
                    if media_id:
                        PROCESSED_IDS.add(media_id)
                except Exception as send_err:
                    print(f"Send Error: {send_err}")

async def force_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ ইউজারনেম দিন। যেমন: /check cristiano")
        return
    username = context.args[0].replace("@", "").strip().lower()
    await update.message.reply_text(f"🔎 <b>{username}</b>-এর পোস্ট ও স্টোরি প্রসেস করা হচ্ছে...", parse_mode="HTML")
    await scrape_and_send(context.bot, username, limit=10, is_force=True)
    await update.message.reply_text(f"✅ <b>{username}</b>-এর প্রসেসিং শেষ!", parse_mode="HTML")

async def monitor_instagram(bot: Bot):
    while True:
        users_to_check = list(redis_get_users())
        for username in users_to_check:
            await scrape_and_send(bot, username, limit=3, is_force=False)
        await asyncio.sleep(300)

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
        
