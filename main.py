# আগের সব কোডের জায়গায় এটি পেস্ট করুন
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

# ... (আগের ফাংশনগুলো যেমন redis_get_users, redis_add_user সব একই থাকবে) ...

# শুধুমাত্র scrape_and_send ফাংশনটি নিচে দেওয়া হলো, এটি বদলান:

async def scrape_and_send(bot: Bot, username: str, limit: int = 5, is_force: bool = False):
    apify_client = ApifyClient(APIFY_API_TOKEN)
    
    try:
        run = apify_client.actor("apify/instagram-scraper").call(
            run_input={
                "directUrls": [f"https://www.instagram.com/{username}/"],
                "resultsLimit": limit
            }
        )
        items = apify_client.dataset(run["defaultDatasetId"]).list_items().items
        
        # ডিবাগ লগ: কয়টি আইটেম পেল
        count = len(items)
        if is_force:
            await bot.send_message(chat_id=TELEGRAM_USER_ID, text=f"📊 ডিবাগ: {username} এর প্রোফাইল থেকে {count} টি পোস্ট পাওয়া গেছে।")
        
        if count == 0:
            return

    except Exception as e:
        if is_force:
            await bot.send_message(chat_id=TELEGRAM_USER_ID, text=f"❌ Error: {e}")
        return

    for item in items:
        # মিডিয়া পাঠানোর লজিক আগের মতোই থাকবে (নিচে পুরোটা কপি করবেন)
        media_group = []
        child_posts = item.get("childPosts", [])
        images = item.get("images", [])
        
        if child_posts:
            for child in child_posts:
                v_url = child.get("videoUrl")
                d_url = child.get("displayUrl")
                if v_url: media_group.append(InputMediaVideo(media=v_url))
                elif d_url: media_group.append(InputMediaPhoto(media=d_url))
        elif images:
            for img_url in images[:10]: media_group.append(InputMediaPhoto(media=img_url))
        else:
            v_url = item.get("videoUrl")
            d_url = item.get("displayUrl") or item.get("imageUrl") or item.get("url")
            if item.get("isVideo") and v_url: media_group.append(InputMediaVideo(media=v_url))
            elif d_url: media_group.append(InputMediaPhoto(media=d_url))

        if media_group:
            try:
                if len(media_group) > 1: await bot.send_media_group(chat_id=TELEGRAM_USER_ID, media=media_group[:10])
                elif len(media_group) == 1:
                    if isinstance(media_group[0], InputMediaVideo): await bot.send_video(chat_id=TELEGRAM_USER_ID, video=media_group[0].media)
                    else: await bot.send_photo(chat_id=TELEGRAM_USER_ID, photo=media_group[0].media)
            except Exception as e:
                print(f"Send Error: {e}")
                
