from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from PIL import Image
from datetime import datetime
from hachoir.metadata import extractMetadata
from hachoir.parser import createParser
from helper.utils import progress_for_pyrogram, humanbytes, convert, log_queue_task
from helper.database import madflixbotz
from config import Config
import os
import time
import re
import asyncio
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

from bot import queue, user_semaphores, MAX_CONCURRENT_TASKS, global_semaphore

# Track active tasks per user
user_active_tasks = defaultdict(int)

# Regex patterns
pattern1 = re.compile(r'S(\d+)(?:E|EP)(\d+)', re.IGNORECASE)
pattern2 = re.compile(r'S(\d+)\s*(?:E|EP|-\s*EP)(\d+)', re.IGNORECASE)
pattern3 = re.compile(r'(?:[([<{]?\s*(?:E|EP)\s*(\d+)\s*[)\]>}]?)', re.IGNORECASE)
pattern3_2 = re.compile(r'(?:\s*-\s*(\d+)\s*)')
pattern4 = re.compile(r'S(\d+)[^\d]*(\d+)', re.IGNORECASE)
patternX = re.compile(r'(\d+)')
pattern_ch = re.compile(r'\[Ch-(\d+)\]', re.IGNORECASE)
pattern5 = re.compile(r'\b(?:.*?(\d{3,4}[^\dp]*p).*?|.*?(\d{3,4}p))\b', re.IGNORECASE)
pattern6 = re.compile(r'[([<{]?\s*4k\s*[)\]>}]?', re.IGNORECASE)
pattern7 = re.compile(r'[([<{]?\s*2k\s*[)\]>}]?', re.IGNORECASE)
pattern8 = re.compile(r'[([<{]?\s*HdRip\s*[)\]>}]?|\bHdRip\b', re.IGNORECASE)
pattern9 = re.compile(r'[([<{]?\s*4kX264\s*[)\]>}]?', re.IGNORECASE)
pattern10 = re.compile(r'[([<{]?\s*4kx265\s*[)\]>}]?', re.IGNORECASE)
pattern_season = re.compile(r'S(\d+)|Season\s*(\d+)', re.IGNORECASE)
pattern_chapter = re.compile(r'(?:Ch|Chapter)\s*(\d+)', re.IGNORECASE)
pattern_title = re.compile(r'^\[.*?\]\s*(.*?)\s*(?:\[S\d+|\[Ch-|\d{3,4}p|Season|Ch|$)', re.IGNORECASE)

def extract_title(filename):
    match = re.search(pattern_title, filename)
    if match:
        title = match.group(1).strip()
        logger.info(f"Extracted Title: {title}")
        return title
    return os.path.splitext(filename)[0]

def extract_season_number(filename):
    match = re.search(pattern_season, filename)
    if match:
        season = match.group(1) or match.group(2)
        logger.info(f"Extracted Season Number: {season}")
        return season.zfill(2)
    return "01"

def extract_quality(filename):
    for pattern in [pattern5, pattern6, pattern7, pattern8, pattern9, pattern10]:
        match = re.search(pattern, filename)
        if match:
            if pattern == pattern5:
                quality = match.group(1) or match.group(2)
            else:
                quality = match.group(0).strip('[](){} ')
            logger.info(f"Quality: {quality}")
            return quality
    return "Unknown"

def extract_episode_number(filename):
    for pattern in [pattern1, pattern2, pattern3, pattern3_2, pattern4, pattern_ch, patternX]:
        match = re.search(pattern, filename)
        if match:
            episode = match.group(2) if pattern in [pattern1, pattern2, pattern4] else match.group(1)
            logger.info(f"Extracted Episode: {episode}")
            return episode.zfill(2)
    return None

def extract_chapter_number(filename):
    match = re.search(pattern_chapter, filename) or re.search(pattern_ch, filename)
    if match:
        chapter = match.group(1)
        logger.info(f"Extracted Chapter: {chapter}")
        return chapter.zfill(2)
    return None

renaming_operations = {}

async def rename_file(app, task):
    message = task["message"]
    file_id = task["file_id"]
    file_name = task["file_name"]
    new_file_name = task["new_file_name"]
    media_type = task["media_type"]
    chat_id = task["chat_id"]
    file_size = task["file_size"]
    format_template = task["format_template"]
    user_id = task["user_id"]

    global user_active_tasks
    try:
        file_path = f"downloads/{new_file_name}"
        download_msg = await app.send_message(chat_id, "Trying To Download.....")
        path = await message.download(
            file_name=file_path,
            progress=progress_for_pyrogram,
            progress_args=("Download Started....", download_msg, time.time())
        )

        duration = 0
        try:
            metadata = extractMetadata(createParser(file_path))
            if metadata.has("duration"):
                duration = metadata.get('duration').seconds
        except Exception as e:
            logger.error(f"Error getting duration for {file_id}: {e}")

        upload_msg = await download_msg.edit("Trying To Uploading.....")
        ph_path = None
        c_caption = await madflixbotz.get_caption(chat_id)
        c_thumb = await madflixbotz.get_thumbnail(chat_id)

        caption = c_caption.format(filename=new_file_name, filesize=humanbytes(file_size), duration=convert(duration)) if c_caption else f"**{new_file_name}**"

        if c_thumb:
            ph_path = await app.download_media(c_thumb)
            logger.info(f"Thumbnail downloaded successfully for {file_id}: {ph_path}")
        elif media_type == "video" and message.video and message.video.thumbs:
            ph_path = await app.download_media(message.video.thumbs[0])

        if ph_path:
            Image.open(ph_path).convert("RGB").save(ph_path)
            img = Image.open(ph_path)
            img.resize((320, 320))
            img.save(ph_path, "JPEG")

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                if media_type == "document":
                    await app.send_document(
                        chat_id,
                        document=file_path,
                        thumb=ph_path,
                        caption=caption,
                        progress=progress_for_pyrogram,
                        progress_args=("Upload Started.....", upload_msg, time.time())
                    )
                elif media_type == "video":
                    await app.send_video(
                        chat_id,
                        video=file_path,
                        caption=caption,
                        thumb=ph_path,
                        duration=duration,
                        progress=progress_for_pyrogram,
                        progress_args=("Upload Started.....", upload_msg, time.time())
                    )
                elif media_type == "audio":
                    await app.send_audio(
                        chat_id,
                        audio=file_path,
                        caption=caption,
                        thumb=ph_path,
                        duration=duration,
                        progress=progress_for_pyrogram,
                        progress_args=("Upload Started.....", upload_msg, time.time())
                    )
                break
            except FloodWait as e:
                logger.error(f"Flood wait on attempt {attempt} for {file_id}: waiting {e.value} seconds")
                await asyncio.sleep(e.value)
            except Exception as e:
                logger.error(f"Upload error on attempt {attempt} for {file_id}: {e}")
                if attempt == max_retries:
                    os.remove(file_path)
                    if ph_path:
                        os.remove(ph_path)
                    await upload_msg.edit(f"Error: {e}")
                    return
                await asyncio.sleep(2)

        await download_msg.delete()
        os.remove(file_path)
        if ph_path:
            os.remove(ph_path)
        logger.info(f"File {new_file_name} processed successfully for {file_id}")
    except Exception as e:
        logger.error(f"Error in rename_file for {file_id}: {e}")
        await app.send_message(chat_id, f"Error processing file {new_file_name}: {e}")
    finally:
        user_active_tasks[user_id] -= 1
        if user_active_tasks[user_id] <= 0:
            del user_active_tasks[user_id]
        del renaming_operations[file_id]

@Client.on_message(filters.command("autorename"))
async def autorename_command(client, message):
    args = message.text.split(maxsplit=1)
    user_id = message.from_user.id
    if len(args) < 2:
        await message.reply(
            "Hᴇʀᴇ'ꜱ ʜᴏᴡ ᴛᴏ ᴜꜱᴇ ɪᴛ /autorename\n\n"
            "SETUP AUTO RENAME FORMAT\n\n"
            "Use These Keywords To Setup Custom File Name\n\n"
            "➝ {title} :- to replace anime or series title name\n"
            "➝ {season} :- to replace season number\n"
            "➝ {episode} :- to replace episode number\n"
            "➝ {quality} :- to replace video resolution\n"
            "➝ {chapter} :- to replace manga chapter number\n\n"
            "‣ Example: /format S{season} E{episode} - {title} [{quality}]\n"
            "‣ Manga: /format {title} {chapter} @index_Station"
        )
        logger.info(f"User {user_id} requested autorename help text")
        return
    autorename_format = args[1].strip()
    if not autorename_format:
        await message.reply("Please provide a valid autorename format")
        logger.warning(f"User {user_id} provided empty autorename format")
        return
    try:
        await madflixbotz.set_autorename_format(user_id, autorename_format)
        await message.reply(f"Autorename format set successfully! ✅\nFormat: `{autorename_format}`")
        logger.info(f"Autorename format set for {user_id}: {autorename_format}")
    except Exception as e:
        logger.error(f"Failed to set autorename format for {user_id}: {e}")
        await message.reply("Error setting autorename format. Please try again.")

@Client.on_message(filters.command("rename") & filters.user(Config.ADMIN))
async def rename_command(client, message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("Please provide a new name")
        return
    new_name = args[1]
    chat_id = message.chat.id
    user_id = message.from_user.id
    file_id = f"manual_{chat_id}_{int(time.time())}"
    task = {
        "handler": "rename",
        "message": message,
        "file_id": file_id,
        "file_name": "manual_file",
        "new_file_name": new_name,
        "media_type": "document",
        "chat_id": chat_id,
        "file_size": 0,
        "format_template": new_name,
        "user_id": user_id
    }
    try:
        await queue.put(task)
        await log_queue_task(task)
        await madflixbotz.log_queue_task(task)
        await message.reply("File added to rename queue")
    except asyncio.QueueFull:
        await message.reply("Queue is full, please try again later")

@Client.on_message(filters.command("queue_status") & filters.user(Config.ADMIN))
async def queue_status_command(client, message):
    pending_count = await madflixbotz.get_pending_queue_count()
    pending_tasks = await madflixbotz.get_pending_queue_tasks()
    tasks = []
    async for task in pending_tasks:
        tasks.append(task)
    queue_size = queue.qsize()
    if not tasks and queue_size == 0:
        await message.reply("Queue is empty")
    else:
        task_list = "\n".join([f"- User {task['user_id']}: {task['new_file_name']} (ID: {task['file_id']})" for task in tasks])
        active_users = "\n".join([f"User {uid}: {count} active tasks" for uid, count in user_active_tasks.items()])
        await message.reply(
            f"Queue Status:\n"
            f"Current queue size: {queue_size}\n"
            f"Pending tasks in DB: {pending_count}\n"
            f"Active users:\n{active_users or 'None'}\n"
            f"Tasks:\n{task_list}"
        )

@Client.on_message(filters.private & (filters.document | filters.video | filters.audio))
async def auto_rename_files(client, message):
    user_id = message.from_user.id
    try:
        autorename_format = await madflixbotz.get_autorename_format(user_id)
        if not autorename_format:
            await message.reply("Please set an auto rename format first using /autorename")
            logger.warning(f"No autorename format found for user {user_id}")
            return
    except Exception as e:
        logger.error(f"Error fetching autorename format for {user_id}: {e}")
        await message.reply("Error accessing autorename format. Please try setting it again with /autorename")
        return

    media_preference = await madflixbotz.get_media_preference(user_id)

    if message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name if message.document.file_name else "unknown"
        media_type = media_preference or "document"
        file_size = message.document.file_size
    elif message.video:
        file_id = message.video.file_id
        file_name = "video.mp4"
        media_type = media_preference or "video"
        file_size = message.video.file_size
    elif message.audio:
        file_id = message.audio.file_id
        file_name = "audio.mp3"
        media_type = media_preference or "audio"
        file_size = message.audio.file_size
    else:
        await message.reply("Unsupported file type")
        return

    logger.info(f"Original File Name for {user_id}: {file_name}")

    if file_id in renaming_operations:
        elapsed_time = (datetime.now() - renaming_operations[file_id]).seconds
        if elapsed_time < 10:
            logger.info(f"File {file_id} ignored: currently being renamed or recently renamed")
            return

    renaming_operations[file_id] = datetime.now()

    episode_number = extract_episode_number(file_name)
    season_number = extract_season_number(file_name)
    quality = extract_quality(file_name)
    chapter_number = extract_chapter_number(file_name)
    title = extract_title(file_name)

    if episode_number or chapter_number:
        format_template = autorename_format
        logger.info(f"Applying format template for {user_id}: {format_template}")
        format_template = format_template.replace("{title}", title or "Unknown", 1)
        format_template = format_template.replace("{season}", season_number, 1).replace("Season", season_number, 1).replace("SEASON", season_number, 1)
        format_template = format_template.replace("{episode}", episode_number or "00", 1).replace("Episode", episode_number or "00", 1).replace("EPISODE", episode_number or "00", 1)
        format_template = format_template.replace("{quality}", quality, 1).replace("Quality", quality, 1).replace("QUALITY", quality, 1)
        format_template = format_template.replace("{chapter}", chapter_number or "00", 1).replace("Chapter", chapter_number or "00", 1).replace("CHAPTER", chapter_number or "00", 1)

        _, file_extension = os.path.splitext(file_name)
        new_file_name = f"{format_template}{file_extension}"
        logger.info(f"Generated new file name for {user_id}: {new_file_name}")

        task = {
            "handler": "rename",
            "message": message,
            "file_id": file_id,
            "file_name": file_name,
            "new_file_name": new_file_name,
            "media_type": media_type,
            "chat_id": message.chat.id,
            "file_size": file_size,
            "format_template": format_template,
            "user_id": user_id
        }
        try:
            active_tasks = user_active_tasks[user_id]
            await queue.put(task)
            await log_queue_task(task)
            await madflixbotz.log_queue_task(task)
            user_active_tasks[user_id] += 1
            if active_tasks >= 4:
                await message.reply(f"⏳ Your file is in queue, please wait...")
            else:
                await message.reply(f"File added to rename queue, please wait...")
            logger.info(f"Task added to queue")
        except asyncio.QueueFull:
            await message.reply("Queue is full, please try again later")
            logger.warning(f"Queue full for user {user_id}")
    else:
        await message.reply("Could not extract episode or chapter number")
        logger.warning(f"Failed to extract episode/chapter for {user_id}: {file_name}")
        del renaming_operations[file_id]
