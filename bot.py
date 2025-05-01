import asyncio
import logging
import logging.config
from datetime import datetime
from pytz import timezone
from pyrogram import Client, idle
from config import Config
import os

# Try to load logging configuration, fall back to basic config if it fails
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

# Global queue for tasks
queue = asyncio.Queue(maxsize=Config.QUEUE_MAXSIZE if hasattr(Config, 'QUEUE_MAXSIZE') else 100)

# Semaphore to limit concurrent tasks (e.g., 5 at a time)
SEMAPHORE = asyncio.Semaphore(5)

# Consumer coroutine to process queued tasks
async def process_queue(app):
    while True:
        task = await queue.get()
        async with SEMAPHORE:  # Limit concurrent processing
            try:
                logger.info(f"Processing task: {task}")
                if task["handler"] == "rename":
                    from plugins.file_rename import rename_file
                    await rename_file(app, task)
                queue.task_done()
            except Exception as e:
                logger.error(f"Error processing task {task}: {e}")
                queue.task_done()

class Bot(Client):
    def __init__(self):
        super().__init__(
            name="renamer",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.BOT_TOKEN,
            plugins={"root": "plugins"},
            workers=25  # As per your previous request
        )
        self.mention = None
        self.username = None
        self.uptime = Config.BOT_UPTIME

    async def start(self):
        # Attempt to connect with retries
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
                await asyncio.sleep(2 ** attempt)  # Exponential backoff

        me = await self.get_me()
        self.mention = f"[{me.first_name}](tg://user?id={me.id})"
        self.username = f"@{me.username}"
        logger.info(f"{me.first_name} Is Started.....✨️")

        # Start queue consumer
        asyncio.create_task(process_queue(self))

        # Notify admin and log channel
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
