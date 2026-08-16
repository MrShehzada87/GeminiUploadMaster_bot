import json
import asyncio
import os
from apify_client import ApifyClient
from telegram import Bot, InputMediaPhoto, InputMediaVideo, Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Configurations
TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"  # BotFather থেকে পাওয়া টোকেন
TELEGRAM_USER_ID = 123456789                    # আপনার টেলিগ্রাম আইডি
APIFY_API_TOKEN = "YOUR_APIFY_API_TOKEN"        # Apify থেকে পাওয়া টোকেন
USER_DB = "users.json"

def load_users():
    if not os.path.exists(USER_DB): return []
    with open(USER_DB, "r") as f: return json.load(f)

def save_users(users):
    with open(USER_DB, "w") as f: json.dump(users, f)

async def add_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ ইউজারনেম দিন। যেমন: /add username")
        return
    username = context.args[0]
    users = load_users()
    if username not in users:
        users.append(username)
        save_users(users)
        await update.message.reply_text(f"✅ {username} লিস্টে যোগ করা হয়েছে।")
    else:
        await update.message.reply_text(f"⚠️ {username} অলরেডি লিস্টে আছে।")

async def remove_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return
    username = context.args[0]
    users = load_users()
    if username in users:
        users.remove(username)
        save_users(users)
        await update.message.reply_text(f"❌ {username} লিস্ট থেকে বাদ দেওয়া হয়েছে।")

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = load_users()
    await update.message.reply_text(f"📋 বর্তমান মনিটরিং লিস্ট:\n{', '.join(users) if users else 'লিস্ট খালি।'}")

async def monitor_instagram(bot: Bot):
    apify_client = ApifyClient(APIFY_API_TOKEN)
    posted_ids = set()
    
    while True:
        users = load_users()
        for username in users:
            try:
                run = apify_client.actor("apify/instagram-scraper").call(run_input={"directUrls": [f"https://www.instagram.com/{username}/"], "resultsLimit": 1})
                items = apify_client.dataset(run["defaultDatasetId"]).list_items().items
                
                for item in items:
                    post_id = item.get("id")
                    if post_id in posted_ids: continue
                    
                    media_group = []
                    if item.get("type") == "Sidecar":
                        for child in item.get("sidecarChildPosts", []):
                            media_group.append(InputMediaVideo(media=child.get("videoUrl")) if child.get("type") == "GraphVideo" else InputMediaPhoto(media=child.get("displayUrl")))
                    elif item.get("type") == "Video":
                        media_group.append(InputMediaVideo(media=item.get("videoUrl")))
                    else:
                        media_group.append(InputMediaPhoto(media=item.get("displayUrl")))

                    if media_group:
                        await bot.send_media_group(chat_id=TELEGRAM_USER_ID, media=media_group)
                        posted_ids.add(post_id)
            except Exception as e:
                print(f"Error: {e}")
        await asyncio.sleep(180) # ৩ মিনিট পরপর চেক করবে

if __name__ == '__main__':
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("add", add_user))
    application.add_handler(CommandHandler("remove", remove_user))
    application.add_handler(CommandHandler("list", list_users))
    
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    loop = asyncio.get_event_loop()
    loop.create_task(monitor_instagram(bot))
    application.run_polling()
              
