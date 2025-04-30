import asyncio
import logging
import logging.config
from datetime import datetime
from pytz import timezone
from telethon import TelegramClient, events
from config import Config

# Load logging configuration
logging.config.fileConfig('logging.conf')
logger = logging.getLogger(__name__)

# Global queue for tasks
queue = asyncio.Queue(maxsize=Config.QUEUE_MAXSIZE if hasattr(Config, 'QUEUE_MAXSIZE') else 100)

# Consumer coroutine to process queued tasks
async def process_queue(client):
    while True:
        task = await queue.get()
        try:
            logger.info(f"Processing task: {task}")
            if task["handler"] == "rename":
                from plugins.file_rename import rename_file
                await rename_file(client, task)
            # Add other handlers as needed (e.g., thumbnail, metadata)
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

        # Register plugin handlers
        from plugins.file_rename import rename_command, auto_rename_files
        from plugins.start import start_command  # Placeholder
        from plugins.metadata import metadata_command  # Placeholder
        from plugins.admin import admin_command  # Placeholder
        from plugins.thumb_cap import thumb_command  # Placeholder
        from plugins.forcesub import forcesub_check  # Placeholder

        self.add_event_handler(start_command, events.NewMessage(pattern="/start"))
        self.add_event_handler(rename_command, events.NewMessage(pattern="/rename"))
        self.add_event_handler(auto_rename_files, events.NewMessage(incoming=True, func=lambda e: e.is_private and (e.document or e.video or e.audio)))
        self.add_event_handler(metadata_command, events.NewMessage(pattern="/metadata"))
        self.add_event_handler(admin_command, events.NewMessage(pattern="/admin"))
        self.add_event_handler(thumb_command, events.NewMessage(pattern="/set_thumb"))
        self.add_event_handler(forcesub_check, events.NewMessage(incoming=True))

        # Start queue consumer
        self.loop.create_task(process_queue(self))

        # Notify admin and log channel
        for id in Config.ADMIN:
            try:
                await self.send_message(Config.LOG_CHANNEL, f"**{me.first_name} Is Started.....✨️**")
            except:
                logger.error(f"Failed to notify admin {id}")
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
