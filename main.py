import asyncio
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from apify_client import ApifyClient
from telegram import Bot, InputMediaPhoto, InputMediaVideo, Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ==========================================
# ১. ক্রেডেনশিয়ালস (আপনার তথ্যগুলো বসানো আছে)
# ==========================================
TELEGRAM_BOT_TOKEN = "8960878764:AAGia67FIQH6foQvVsR7Uu2Hjswi674JC_A"
TELEGRAM_USER_ID = 1426255282
APIFY_API_TOKEN = "apify_api_EGmxew3AxVjwTE3IDRSK3fK6bw2aXs1jMXzG"

# সার্ভার মেমোরিতে ইউজার লিস্ট জমা থাকবে (কখনো খালি হবে না)
MONITORED_USERS = set()

# ==========================================
# ২. Render Port Server (Render Deploy Failure এড়াতে)
# ==========================================
class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is Running Alive 24/7!")

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    server.serve_forever()

# ==========================================
# ৩. টেলিগ্রাম বটের কমান্ডসমূহ
# ==========================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 হেলো! ইনস্টাগ্রাম মনিটরিং বটে স্বাগতম।\n\n- ইউজার যোগ করতে: /add username\n- বাদ দিতে: /remove username\n- লিস্ট দেখতে: /list")

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
# ৪. ইনস্টাগ্রাম অটো-মনিটরিং লুপ (২৪/৭)
# ==========================================
async def monitor_instagram(bot: Bot):
    apify_client = ApifyClient(APIFY_API_TOKEN)
    posted_ids = set()
    
    while True:
        # মেমোরি থেকে লিস্ট নিয়ে চেক করবে
        users_to_check = list(MONITORED_USERS)
        for username in users_to_check:
            try:
                run = apify_client.actor("apify/instagram-scraper").call(
                    run_input={
                        "directUrls": [f"https://www.instagram.com/{username}/"], 
                        "resultsLimit": 1
                    }
                )
                items = apify_client.dataset(run["defaultDatasetId"]).list_items().items
                
                for item in items:
                    post_id = item.get("id")
                    if not post_id or post_id in posted_ids: 
                        continue
                    
                    media_group = []
                    if item.get("type") == "Sidecar":
                        for child in item.get("sidecarChildPosts", []):
                            if child.get("type") == "GraphVideo":
                                media_group.append(InputMediaVideo(media=child.get("videoUrl")))
                            else:
                                media_group.append(InputMediaPhoto(media=child.get("displayUrl")))
                    elif item.get("type") == "Video":
                        media_group.append(InputMediaVideo(media=item.get("videoUrl")))
                    else:
                        media_group.append(InputMediaPhoto(media=item.get("displayUrl")))

                    if media_group:
                        if len(media_group) > 1:
                            await bot.send_media_group(chat_id=TELEGRAM_USER_ID, media=media_group)
                        elif len(media_group) == 1:
                            if isinstance(media_group[0], InputMediaVideo):
                                await bot.send_video(chat_id=TELEGRAM_USER_ID, video=media_group[0].media)
                            else:
                                await bot.send_photo(chat_id=TELEGRAM_USER_ID, photo=media_group[0].media)
                        
                        posted_ids.add(post_id)
            except Exception as e:
                print(f"Error checking {username}: {e}")
        
        # ৩০০ সেকেন্ড (৫ মিনিট) পর পর নতুন পোস্ট চেক করবে
        await asyncio.sleep(300)

# ==========================================
# ৫. প্রধান সার্ভিস এক্সিকিউটর
# ==========================================
async def main():
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("add", add_user))
    application.add_handler(CommandHandler("remove", remove_user))
    application.add_handler(CommandHandler("list", list_users))
    
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
        
