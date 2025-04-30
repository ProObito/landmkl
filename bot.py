import asyncio
from datetime import datetime
from pytz import timezone
from telethon import TelegramClient, events
from config import Config
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global queue for tasks
queue = asyncio.Queue(maxsize=Config.QUEUE_MAXSIZE if hasattr(Config, 'QUEUE_MAXSIZE') else 100)

# Consumer coroutine to process queued tasks
async def process_queue(client):
    while True:
        task = await queue.get()
        try:
            logger.info(f"Processing task: {task}")
            # Example: task = {"handler": "rename", "event": event, "file_id": file_id, ...}
            if task["handler"] == "rename":
                from plugins.file_rename import rename_file
                await rename_file(client, task)
            queue.task_done()
        except Exception as e:
            logger.error(f"Error processing task {task}: {e}")
            queue.task_done()

class Bot(TelegramClient):
    def __init__(self):
        super().__init__(
            session="renamer",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
        )
        self.mention = None
        self.username = None
        self.uptime = Config.BOT_UPTIME

    async def start(self):
        await super().start(bot_token=Config.BOT_TOKEN)
        me = await self.get_me()
        self.mention = f"[{me.first_name}](tg://user?id={me.id})"
        self.username = f"@{me.username}"
        logger.info(f"{me.first_name} Is Started.....✨️")

        # Register plugins manually (Telethon doesn't use plugins dict)
        from plugins import file_rename  # Import other plugins as needed
        self.add_event_handler(file_rename.rename_command, events.NewMessage(pattern="/autorename"))
        # Add other plugin handlers here

        # Start queue consumer
        self.loop.create_task(process_queue(self))

        # Notify admin and log channel
        for id in Config.ADMIN:
            try:
                await self.send_message(Config.LOG_CHANNEL, f"**{me.first_name} Is Started.....✨️**")
            except:
                pass
        if Config.LOG_CHANNEL:
            try:
                curr = datetime.now(timezone("Asia/Kolkata"))
                date = curr.strftime('%d %B, %Y')
                time = curr.strftime('%I:%M:%S %p')
                await self.send_message(
                    Config.LOG_CHANNEL,
                    f"**{self.mention} Is Restarted !!**\n\n📅 Date : `{date}`\n⏰ Time : `{time}`\n🌐 Timezone : `Asia/Kolkata`\n\n🉐 Version : `Telethon`"
                )
            except:
                logger.error("Please make the bot admin in the log channel")

if __name__ == "__main__":
    bot = Bot()
    bot.run_until_disconnected()
