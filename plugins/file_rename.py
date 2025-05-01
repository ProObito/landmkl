from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from PIL import Image
from datetime import datetime
from hachoir.metadata import extractMetadata
from hachoir.parser import createParser
from helper.utils import progress_for_pyrogram, humanbytes, convert, log_queue_task
from helper.database import madflixbotz
from config import Config, Txt
import os
import time
import re
import asyncio
import logging

logger = logging.getLogger(__name__)

from bot import queue, SEMAPHORE

# Regex patterns (enhanced for season and more cases)
pattern1 = re.compile(r'S(\d+)(?:E|EP)(\d+)', re.IGNORECASE)
pattern2 = re.compile(r'S(\d+)\s*(?:E|EP|-\s*EP)(\d+)', re.IGNORECASE)
pattern3 = re.compile(r'(?:[([<{]?\s*(?:E|EP)\s*(\d+)\s*[)\]>}]?)', re.IGNORECASE)
pattern3_2 = re.compile(r'(?:\s*-\s*(\d+)\s*)')
pattern4 = re.compile(r'S(\d+)[^\d]*(\d+)', re.IGNORECASE)
patternX = re.compile(r'(\d+)')
pattern5 = re.compile(r'\b(?:.*?(\d{3,4}[^\dp]*p).*?|.*?(\d{3,4}p))\b', re.IGNORECASE)
pattern6 = re.compile(r'[([<{]?\s*4k\s*[)\]>}]?', re.IGNORECASE)
pattern7 = re.compile(r'[([<{]?\s*2k\s*[)\]>}]?', re.IGNORECASE)
pattern8 = re.compile(r'[([<{]?\s*HdRip\s*[)\]>}]?|\bHdRip\b', re.IGNORECASE)
pattern9 = re.compile(r'[([<{]?\s*4kX264\s*[)\]>}]?', re.IGNORECASE)
pattern10 = re.compile(r'[([<{]?\s*4kx265\s*[)\]>}]?', re.IGNORECASE)
pattern_season = re.compile(r'S(\d+)|Season\s*(\d+)', re.IGNORECASE)

def extract_season_number(filename):
    match = re.search(pattern_season, filename)
    if match:
        season = match.group(1) or match.group(2)
        logger.info(f"Extracted Season Number: {season}")
        return season
    return "01"  # Default to season 1 if not found

def extract_quality(filename):
    match5 = re.search(pattern5, filename)
    if match5:
        logger.info("Matched Pattern 5")
        quality5 = match5.group(1) or match5.group(2)
        logger.info(f"Quality: {quality5}")
        return quality5
    match6 = re.search(pattern6, filename)
    if match6:
        logger.info("Matched Pattern 6")
        quality6 = "4k"
        logger.info(f"Quality: {quality6}")
        return quality6
    match7 = re.search(pattern7, filename)
    if match7:
        logger.info("Matched Pattern 7")
        quality7 = "2k"
        logger.info(f"Quality: {quality7}")
        return quality7
    match8 = re.search(pattern8, filename)
    if match8:
        logger.info("Matched Pattern 8")
        quality8 = "HdRip"
        logger.info(f"Quality: {quality8}")
        return quality8
    match9 = re.search(pattern9, filename)
    if match9:
        logger.info("Matched Pattern 9")
        quality9 = "4kX264"
        logger.info(f"Quality: {quality9}")
        return quality9
    match10 = re.search(pattern10, filename)
    if match10:
        logger.info("Matched Pattern 10")
        quality10 = "4kx265"
        logger.info(f"Quality: {quality10}")
        return quality10
    unknown_quality = "Unknown"
    logger.info(f"Quality: {unknown_quality}")
    return unknown_quality

def extract_episode_number(filename):
    patterns = [pattern1, pattern2, pattern3, pattern3_2, pattern4, patternX]
    for pattern in patterns:
        match = re.search(pattern, filename)
        if match:
            episode = match.group(2) if pattern in [pattern1, pattern2, pattern4] else match.group(1)
            logger.info(f"Matched Pattern {pattern.__name__}, Episode: {episode}")
            return episode.zfill(2)  # Pad with zero
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

    file_path = f"downloads/{new_file_name}"
    download_msg = await app.send_message(chat_id, "Trying To Download.....")
    try:
        path = await message.download(
            file_name=file_path,
            progress=progress_for_pyrogram,
            progress_args=("Download Started....", download_msg, time.time())
        )
    except Exception as e:
        logger.error(f"Download error: {e}")
        await download_msg.edit(f"Error: {e}")
        del renaming_operations[file_id]
        return

    duration = 0
    try:
        metadata = extractMetadata(createParser(file_path))
        if metadata.has("duration"):
            duration = metadata.get('duration').seconds
    except Exception as e:
        logger.error(f"Error getting duration: {e}")

    upload_msg = await download_msg.edit("Trying To Uploading.....")
    ph_path = None
    c_caption = await madflixbotz.get_caption(chat_id)
    c_thumb = await madflixbotz.get_thumbnail(chat_id)

    caption = c_caption.format(filename=new_file_name, filesize=humanbytes(file_size), duration=convert(duration)) if c_caption else f"**{new_file_name}**"

    if c_thumb:
        ph_path = await app.download_media(c_thumb)
        logger.info(f"Thumbnail downloaded successfully. Path: {ph_path}")
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
            logger.error(f"Flood wait on attempt {attempt}: waiting {e.value} seconds")
            await asyncio.sleep(e.value)
        except Exception as e:
            logger.error(f"Upload error on attempt {attempt}: {e}")
            if attempt == max_retries:
                os.remove(file_path)
                if ph_path:
                    os.remove(ph_path)
                await upload_msg.edit(f"Error: {e}")
                del renaming_operations[file_id]
                return
            await asyncio.sleep(2)

    await download_msg.delete()
    os.remove(file_path)
    if ph_path:
        os.remove(ph_path)
    del renaming_operations[file_id]
    logger.info(f"File {new_file_name} processed successfully")

@Client.on_message(filters.command("autorename"))
async def autorename_command(client, message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply(Txt.FILE_NAME_TXT)
        return
    autorename_format = args[1]
    user_id = message.from_user.id
    await madflixbotz.set_autorename_format(user_id, autorename_format)
    logger.info(f"Autorename format set for {user_id}: {autorename_format}")
    await message.reply(f"Autorename format set to: `{autorename_format}`")

@Client.on_message(filters.command("rename") & filters.user(Config.ADMIN))
async def rename_command(client, message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("Please provide a new name")
        return
    new_name = args[1]
    chat_id = message.chat.id
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
        "format_template": new_name
    }
    try:
        await queue.put(task)
        await log_queue_task(task)
        await madflixbotz.log_queue_task(task)
        await message.reply("File added to rename queue")
    except asyncio.QueueFull:
        await message.reply("Queue is full, please try again later")

@Client.on_message(filters.private & (filters.document | filters.video | filters.audio))
async def auto_rename_files(client, message):
    user_id = message.from_user.id
    autorename_format = await madflixbotz.get_autorename_format(user_id)
    media_preference = await madflixbotz.get_media_preference(user_id)

    if not autorename_format:
        await message.reply("Please set an auto rename format first using /autorename")
        return

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

    logger.info(f"Original File Name: {file_name}")

    if file_id in renaming_operations:
        elapsed_time = (datetime.now() - renaming_operations[file_id]).seconds
        if elapsed_time < 10:
            logger.info("File is being ignored as it is currently being renamed or was renamed recently.")
            return

    renaming_operations[file_id] = datetime.now()

    episode_number = extract_episode_number(file_name)
    season_number = extract_season_number(file_name)
    quality = extract_quality(file_name)

    if episode_number:
        format_template = autorename_format
        # Replace variables
        format_template = format_template.replace("episode", episode_number, 1).replace("Episode", episode_number, 1).replace("EPISODE", episode_number, 1).replace("{episode}", episode_number, 1)
        format_template = format_template.replace("season", season_number, 1).replace("Season", season_number, 1).replace("SEASON", season_number, 1).replace("{season}", season_number, 1)
        format_template = format_template.replace("quality", quality, 1).replace("Quality", quality, 1).replace("QUALITY", quality, 1).replace("{quality}", quality, 1)

        _, file_extension = os.path.splitext(file_name)
        new_file_name = f"{format_template}{file_extension}"

        task = {
            "handler": "rename",
            "message": message,
            "file_id": file_id,
            "file_name": file_name,
            "new_file_name": new_file_name,
            "media_type": media_type,
            "chat_id": message.chat.id,
            "file_size": file_size,
            "format_template": format_template
        }
        try:
            await queue.put(task)
            await log_queue_task(task)
            await madflixbotz.log_queue_task(task)
            await message.reply(f"File added to rename queue with new name: `{new_file_name}`")
        except asyncio.QueueFull:
            await message.reply("Queue is full, please try again later")
    else:
        await message.reply("Could not extract episode number")
        del renaming_operations[file_id]
