import asyncio
import logging
import logging.config
from datetime import datetime
from pytz import timezone
from pyrogram import Client, idle
from config import Config
from helper.database import madflixbotz
import os
from collections import defaultdict

try:
    if os.path.exists('logging.conf'):
        logging.config.fileConfig('logging.conf')
    else:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler('bot.log')
            ]
        )
except Exception as e:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('bot.log')
        ]
    )
    logging.error(f"Failed to load logging.conf: {e}")

logger = logging.getLogger(__name__)

queue = asyncio.Queue(maxsize=Config.QUEUE_MAXSIZE if hasattr(Config, 'QUEUE_MAXSIZE') else 100)
user_semaphores = defaultdict(lambda: asyncio.Semaphore(4))  # Per-user limit: 4 tasks
MAX_CONCURRENT_TASKS = 50  # Global limit to prevent Heroku overload
global_semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)

async def process_queue(app):
    while True:
        try:
            task = await queue.get()
            user_id = task.get('user_id')
            if not user_id:
                logger.error(f"Task {task['file_id']} missing user_id")
                queue.task_done()
                continue

            async with global_semaphore:
                async with user_semaphores[user_id]:
                    max_retries = 3
                    for attempt in range(1, max_retries + 1):
                        try:
                            logger.info(f"Processing task for user {user_id}: {task['file_id']} - {task['new_file_name']}")
                            await app.send_message(
                                task['chat_id'],
                                "⚙️ Download Starting..."
                            )
                            if task["handler"] == "rename":
                                from plugins.file_rename import rename_file
                                await rename_file(app, task)
                            queue.task_done()
                            break
                        except Exception as e:
                            logger.error(f"Error processing task {task['file_id']} for user {user_id} on attempt {attempt}: {e}")
                            if attempt == max_retries:
                                logger.error(f"Max retries reached for task {task['file_id']}")
                                await app.send_message(
                                    task['chat_id'],
                                    f"Error processing file {task['new_file_name']}: {e}"
                                )
                                queue.task_done()
                            await asyncio.sleep(2 ** attempt)
        except Exception as e:
            logger.error(f"Queue worker error: {e}")
            await asyncio.sleep(5)

async def queue_health_check():
    while True:
        active_users = len(user_semaphores)
        logger.info(f"Queue status - Size: {queue.qsize()}, Full: {queue.full()}, Active users: {active_users}")
        await asyncio.sleep(120)  # Log every 2 minutes

class Bot(Client):
    def __init__(self):
        super().__init__(
            name="renamer",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.BOT_TOKEN,
            plugins={"root": "plugins"},
            workers=25
        )
        self.mention = None
        self.username = None
        self.uptime = Config.BOT_UPTIME

    async def start(self):
        max_retries = 5
        for attempt in range(1, max_retries + 1):
            try:
                await super().start()
                logger.info("Successfully connected to Telegram")
                break
            except Exception as e:
                logger.error(f"Connection attempt {attempt} failed: {e}")
                if attempt == max_retries:
                    logger.error("Max retries reached, exiting")
                    raise
                await asyncio.sleep(2 ** attempt)

        try:
            await madflixbotz.col.find_one()
            logger.info("MongoDB connected successfully")
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise

        me = await self.get_me()
        self.mention = f"[{me.first_name}](tg://user?id={me.id})"
        self.username = f"@{me.username}"
        logger.info(f"{me.first_name} Is Started.....✨️")

        asyncio.create_task(process_queue(self))
        asyncio.create_task(queue_health_check())

        for id in Config.ADMIN:
            try:
                await self.send_message(id, f"**{me.first_name} Is Started.....✨️**")
            except Exception as e:
                logger.error(f"Failed to notify admin {id}: {e}")

        if Config.LOG_CHANNEL:
            try:
                curr = datetime.now(timezone("Asia/Kolkata"))
                date = curr.strftime('%d %B, %Y')
                time = curr.strftime('%I:%M:%S %p')
                await self.send_message(
                    Config.LOG_CHANNEL,
                    f"**{self.mention} Is Restarted !!**\n\n📅 Date : `{date}`\n⏰ Time : `{time}`\n🌐 Timezone : `Asia/Kolkata`\n\n🉐 Version : `Pyrogram`"
                )
            except Exception as e:
                logger.error(f"Failed to send restart message to log channel: {e}")

    async def stop(self):
        await super().stop()
        logger.info("Bot stopped")

if __name__ == "__main__":
    bot = Bot()
    try:
        bot.run()
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
        raise
