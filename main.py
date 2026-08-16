import asyncio
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from apify_client import ApifyClient
from telegram import Bot, InputMediaPhoto, InputMediaVideo, Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TELEGRAM_BOT_TOKEN = "8960878764:AAGia67FIQH6foQvVsR7Uu2Hjswi674JC_A"
TELEGRAM_USER_ID = 1426255282
APIFY_API_TOKEN = "apify_api_EGmxew3AxVjwTE3IDRSK3fK6bw2aXs1jMXzG"

MONITORED_USERS = set()
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
    await update.message.reply_text(
        "👋 ইনস্টাগ্রাম ট্র্যাকার বট চালু আছে!\n\n"
        "- /add username : ইউজার যোগ করুন\n"
        "- /remove username : বাদ দিন\n"
        "- /list : মনিটরিং লিস্ট\n"
        "- /check username : ফোর্স চেক (শেষ ১০টি Post, Story ও Highlight গ্রুপ আকারে আসবে)"
    )

async def add_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ ইউজারনেম দিন। যেমন: /add username")
        return
    username = context.args[0].replace("@", "").strip().lower()
    if username not in MONITORED_USERS:
        MONITORED_USERS.add(username)
        await update.message.reply_text(f"✅ {username} মনিটরিং লিস্টে যোগ করা হয়েছে।")
    else:
        await update.message.reply_text(f"⚠️ {username} অলরেডি লিস্টে আছে।")

async def remove_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ ইউজারনেম দিন। যেমন: /remove username")
        return
    username = context.args[0].replace("@", "").strip().lower()
    if username in MONITORED_USERS:
        MONITORED_USERS.remove(username)
        await update.message.reply_text(f"❌ {username} লিস্ট থেকে বাদ দেওয়া হয়েছে।")
    else:
        await update.message.reply_text(f"⚠️ {username} লিস্টে পাওয়া যায়নি।")

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if MONITORED_USERS:
        user_list_text = "\n".join([f"- {u}" for u in MONITORED_USERS])
        await update.message.reply_text(f"📋 বর্তমান মনিটরিং লিস্ট ({len(MONITORED_USERS)}জন):\n{user_list_text}")
    else:
        await update.message.reply_text("📋 লিস্ট বর্তমানে খালি। /add দিয়ে ইউজার যোগ করুন।")

# ==========================================
# কোর স্ক্র্যাপিং ও টেলিগ্রাম গ্রুপ সেন্ডিং লজিক
# ==========================================
async def scrape_and_send(bot: Bot, username: str, limit: int = 10):
    apify_client = ApifyClient(APIFY_API_TOKEN)
    
    # ১. Posts ও Highlights স্ক্র্যাপার
    try:
        run_posts = apify_client.actor("apify/instagram-post-scraper").call(
            run_input={
                "username": [username],
                "resultsLimit": limit
            }
        )
        post_items = apify_client.dataset(run_posts["defaultDatasetId"]).list_items().items
    except Exception as e:
        print(f"Post error for {username}: {e}")
        post_items = []

    # ২. Stories স্ক্র্যাপার
    try:
        run_stories = apify_client.actor("apify/instagram-stories-scraper").call(
            run_input={
                "username": username
            }
        )
        story_items = apify_client.dataset(run_stories["defaultDatasetId"]).list_items().items
    except Exception as e:
        print(f"Story error for {username}: {e}")
        story_items = []

    all_items = post_items + story_items

    for item in all_items:
        media_id = item.get("id") or item.get("url")
        if not media_id or media_id in PROCESSED_IDS:
            continue

        media_group = []

        # অ্যালবামের জন্য (Carousel/Sidecar)
        if item.get("type") == "Sidecar" or "sidecarChildPosts" in item:
            for child in item.get("sidecarChildPosts", []):
                video_url = child.get("videoUrl")
                display_url = child.get("displayUrl")
                if child.get("type") == "GraphVideo" and video_url:
                    media_group.append(InputMediaVideo(media=video_url))
                elif display_url:
                    media_group.append(InputMediaPhoto(media=display_url))

        # সিঙ্গল ভিডিও বা স্টোরি ভিডিও
        elif item.get("type") in ["Video", "StoryVideo"] or item.get("isVideo"):
            video_url = item.get("videoUrl")
            if video_url:
                media_group.append(InputMediaVideo(media=video_url))

        # সিঙ্গল ফটো বা স্টোরি ফটো
        else:
            display_url = item.get("displayUrl") or item.get("url")
            if display_url:
                media_group.append(InputMediaPhoto(media=display_url))

        # টেলিগ্রামে ১০টি করে গ্রুপ মিডিয়া সেন্ড করা
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
                    PROCESSED_IDS.add(media_id)
                except Exception as send_err:
                    print(f"Send Error: {send_err}")

# ==========================================
# ৫. ম্যানুয়াল ফোর্স চেক কমান্ড
# ==========================================
async def force_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ ইউজারনেম দিন। যেমন: /check cristiano")
        return
    
    username = context.args[0].replace("@", "").strip().lower()
    await update.message.reply_text(f"🔎 <b>{username}</b>-এর শেষ ১০টি পোস্ট, স্টোরি ও হাইলাইটস চেকিং শুরু হচ্ছে...", parse_mode="HTML")
    
    bot = context.bot
    await scrape_and_send(bot, username, limit=10)
    
    await update.message.reply_text(f"✅ <b>{username}</b>-এর মিডিয়া প্রসেসিং সম্পন্ন হয়েছে!", parse_mode="HTML")

# ==========================================
# ৬. অটোমেটিক ব্যাকগ্রাউন্ড লুপ (২৪/৭)
# ==========================================
async def monitor_instagram(bot: Bot):
    while True:
        users_to_check = list(MONITORED_USERS)
        for username in users_to_check:
            await scrape_and_send(bot, username, limit=3)
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
        
