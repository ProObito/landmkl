from telethon import TelegramClient, events
from telethon.tl.types import DocumentAttributeVideo, DocumentAttributeAudio
from telethon.errors import FloodWait
from PIL import Image
from datetime import datetime
from hachoir.metadata import extractMetadata
from hachoir.parser import createParser
from helper.utils import progress_for_telethon, humanbytes, convert, log_queue_task
from helper.database import madflixbotz
from config import Config
import os
import time
import re
import asyncio
import logging

logger = logging.getLogger(__name__)

# Global queue (imported from bot.py)
from bot import queue

# Regex patterns (unchanged)
pattern1 = re.compile(r'S(\d+)(?:E|EP)(\d+)')
pattern2 = re.compile(r'S(\d+)\s*(?:E|EP|-\s*EP)(\d+)')
pattern3 = re.compile(r'(?:[([<{]?\s*(?:E|EP)\s*(\d+)\s*[)\]>}]?)')
pattern3_2 = re.compile(r'(?:\s*-\s*(\d+)\s*)')
pattern4 = re.compile(r'S(\d+)[^\d]*(\d+)', re.IGNORECASE)
patternX = re.compile(r'(\d+)')
pattern5 = re.compile(r'\b(?:.*?(\d{3,4}[^\dp]*p).*?|.*?(\d{3,4}p))\b', re.IGNORECASE)
pattern6 = re.compile(r'[([<{]?\s*4k\s*[)\]>}]?', re.IGNORECASE)
pattern7 = re.compile(r'[([<{]?\s*2k\s*[)\]>}]?', re.IGNORECASE)
pattern8 = re.compile(r'[([<{]?\s*HdRip\s*[)\]>}]?|\bHdRip\b', re.IGNORECASE)
pattern9 = re.compile(r'[([<{]?\s*4kX264\s*[)\]>}]?', re.IGNORECASE)
pattern10 = re.compile(r'[([<{]?\s*4kx265\s*[)\]>}]?', re.IGNORECASE)

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
    match = re.search(pattern1, filename)
    if match:
        logger.info("Matched Pattern 1")
        return match.group(2)
    match = re.search(pattern2, filename)
    if match:
        logger.info("Matched Pattern 2")
        return match.group(2)
    match = re.search(pattern3, filename)
    if match:
        logger.info("Matched Pattern 3")
        return match.group(1)
    match = re.search(pattern3_2, filename)
    if match:
        logger.info("Matched Pattern 3_2")
        return match.group(1)
    match = re.search(pattern4, filename)
    if match:
        logger.info("Matched Pattern 4")
        return match.group(2)
    match = re.search(patternX, filename)
    if match:
        logger.info("Matched Pattern X")
        return match.group(1)
    return None

renaming_operations = {}

async def rename_file(client, task):
    """Process a rename task from the queue"""
    event = task["event"]
    file_id = task["file_id"]
    file_name = task["file_name"]
    new_file_name = task["new_file_name"]
    media_type = task["media_type"]
    chat_id = task["chat_id"]
    file_size = task["file_size"]
    format_template = task["format_template"]

    file_path = f"downloads/{new_file_name}"
    download_msg = await client.send_message(chat_id, "Trying To Download.....")
    try:
        path = await client.download_media(
            message=event.message,
            file=file_path,
            progress=progress_for_telethon,
            progress_args=("Download Started....", download_msg, time.time())
        )
    except Exception as e:
        logger.error(f"Download error: {e}")
        await download_msg.edit_text(f"Error: {e}")
        del renaming_operations[file_id]
        return

    duration = 0
    try:
        metadata = extractMetadata(createParser(file_path))
        if metadata.has("duration"):
            duration = metadata.get('duration').seconds
    except Exception as e:
        logger.error(f"Error getting duration: {e}")

    upload_msg = await download_msg.edit_text("Trying To Uploading.....")
    ph_path = None
    c_caption = await madflixbotz.get_caption(chat_id)
    c_thumb = await madflixbotz.get_thumbnail(chat_id)

    caption = c_caption.format(filename=new_file_name, filesize=humanbytes(file_size), duration=convert(duration)) if c_caption else f"**{new_file_name}**"

    if c_thumb:
        ph_path = await client.download_media(c_thumb)
        logger.info(f"Thumbnail downloaded successfully. Path: {ph_path}")
    elif media_type == "video" and event.message.video and event.message.video.thumbs:
        ph_path = await client.download_media(event.message.video.thumbs[0])

    if ph_path:
        Image.open(ph_path).convert("RGB").save(ph_path)
        img = Image.open(ph_path)
        img.resize((320, 320))
        img.save(ph_path, "JPEG")

    try:
        if media_type == "document":
            await client.send_document(
                chat_id,
                document=file_path,
                thumb=ph_path,
                caption=caption,
                progress=progress_for_telethon,
                progress_args=("Upload Started.....", upload_msg, time.time())
            )
        elif media_type == "video":
            await client.send_file(
                chat_id,
                file=file_path,
                caption=caption,
                thumb=ph_path,
                attributes=[DocumentAttributeVideo(duration=duration, w=0, h=0)],
                progress=progress_for_telethon,
                progress_args=("Upload Started.....", upload_msg, time.time())
            )
        elif media_type == "audio":
            await client.send_file(
                chat_id,
                file=file_path,
                caption=caption,
                thumb=ph_path,
                attributes=[DocumentAttributeAudio(duration=duration)],
                progress=progress_for_telethon,
                progress_args=("Upload Started.....", upload_msg, time.time())
            )
    except Exception as e:
        logger.error(f"Upload error: {e}")
        os.remove(file_path)
        if ph_path:
            os.remove(ph_path)
        await upload_msg.edit_text(f"Error: {e}")
        del renaming_operations[file_id]
        return

    await download_msg.delete()
    os.remove(file_path)
    if ph_path:
        os.remove(ph_path)
    del renaming_operations[file_id]
    logger.info(f"File {new_file_name} processed successfully")

@client.on(events.NewMessage(from_users=Config.ADMIN, pattern="/rename"))
async def rename_command(event):
    args = event.message.text.split(maxsplit=1)
    if len(args) < 2:
        await event.reply("Please provide a new name")
        return
    new_name = args[1]
    file_path = "some_file_path"  # Replace with actual logic
    chat_id = event.chat_id
    task = {
        "handler": "rename",
        "event": event,
        "file_id": f"manual_{chat_id}_{int(time.time())}",
        "file_name": file_path,
        "new_file_name": new_name,
        "media_type": "document",
        "chat_id": chat_id,
        "file_size": 0,
        "format_template": new_name
    }
    try:
        await queue.put(task)
        await log_queue_task(task)
        await madflixbotz.log_queue_task(task)  # Log to database
        await event.reply("File added to rename queue")
    except asyncio.QueueFull:
        await event.reply("Queue is full, please try again later")

@client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private and (e.document or e.video or e.audio)))
async def auto_rename_files(event):
    user_id = event.sender_id
    firstname = event.sender.first_name
    format_template = await madflixbotz.get_format_template(user_id)
    media_preference = await madflixbotz.get_media_preference(user_id)

    if not format_template:
        await event.reply("Please Set An Auto Rename Format First Using /autorename")
        return

    if event.document:
        file_id = event.document.id
        file_name = event.document.attributes[0].file_name if event.document.attributes else "unknown"
        media_type = media_preference or "document"
        file_size = event.document.size
    elif event.video:
        file_id = event.video.id
        file_name = "video.mp4"
        media_type = media_preference or "video"
        file_size = event.video.size
    elif event.audio:
        file_id = event.audio.id
        file_name = "audio.mp3"
        media_type = media_preference or "audio"
        file_size = event.audio.size
    else:
        await event.reply("Unsupported File Type")
        return

    logger.info(f"Original File Name: {file_name}")

    if file_id in renaming_operations:
        elapsed_time = (datetime.now() - renaming_operations[file_id]).seconds
        if elapsed_time < 10:
            logger.info("File is being ignored as it is currently being renamed or was renamed recently.")
            return

    renaming_operations[file_id] = datetime.now()

    episode_number = extract_episode_number(file_name)
    logger.info(f"Extracted Episode Number: {episode_number}")

    if episode_number:
        placeholders = ["episode", "Episode", "EPISODE", "{episode}"]
        for placeholder in placeholders:
            format_template = format_template.replace(placeholder, str(episode_number), 1)

        quality_placeholders = ["quality", "Quality", "QUALITY", "{quality}"]
        for quality_placeholder in quality_placeholders:
            if quality_placeholder in format_template:
                extracted_qualities = extract_quality(file_name)
                if extracted_qualities == "Unknown":
                    await event.reply("I Was Not Able To Extract The Quality Properly. Renaming As 'Unknown'...")
                    del renaming_operations[file_id]
                    return
                format_template = format_template.replace(quality_placeholder, "".join(extracted_qualities))

        _, file_extension = os.path.splitext(file_name)
        new_file_name = f"{format_template}{file_extension}"

        task = {
            "handler": "rename",
            "event": event,
            "file_id": file_id,
            "file_name": file_name,
            "new_file_name": new_file_name,
            "media_type": media_type,
            "chat_id": event.chat_id,
            "file_size": file_size,
            "format_template": format_template
        }
        try:
            await queue.put(task)
            await log_queue_task(task)
            await madflixbotz.log_queue_task(task)
            await event.reply("File added to rename queue")
        except asyncio.QueueFull:
            await event.reply("Queue is full, please try again later")
    else:
        await event.reply("Could not extract episode number")
        del renaming_operations[file_id]
