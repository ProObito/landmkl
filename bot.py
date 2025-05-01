# +++ Made By Obito [telegram username: @i_killed_my_clan] +++ #

import asyncio
import logging
import logging.config
from datetime import datetime
from pytz import timezone
from pyrogram import Client, idle
from config import Config
from helper.database import madflixbotz
import os

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
SEMAPHORE = asyncio.Semaphore(5)

async def process_queue(app):
    while True:
        try:
            task = await queue.get()
            async with SEMAPHORE:
                max_retries = 3
                for attempt in range(1, max_retries + 1):
                    try:
                        logger.info(f"Processing task: {task['file_id']} - {task['new_file_name']}")
                        if task["handler"] == "rename":
                            from plugins.file_rename import rename_file
                            await rename_file(app, task)
                        queue.task_done()
                        break
                    except Exception as e:
                        logger.error(f"Error processing task {task['file_id']} on attempt {attempt}: {e}")
                        if attempt == max_retries:
                            logger.error(f"Max retries reached for task {task['file_id']}")
                            queue.task_done()
                        await asyncio.sleep(2 ** attempt)
        except Exception as e:
            logger.error(f"Queue worker error: {e}")
            await asyncio.sleep(5)  # Prevent tight loop on failure

async def queue_health_check():
    while True:
        logger.info(f"Queue status - Size: {queue.qsize()}, Full: {queue.full()}")
        await asyncio.sleep(300)  # Log every 5 minutes

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


# +++ Made By Obito [telegram username: @i_killed_my_clan] +++ #
