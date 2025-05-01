import motor.motor_asyncio
from config import Config
from .utils import send_log
from datetime import datetime

class Database:
    def __init__(self, uri, database_name):
        self._client = motor.motor_asyncio.AsyncIOMotorClient(uri)
        self.madflixbotz = self._client[database_name]
        self.col = self.madflixbotz.user
        self.queue_col = self.madflixbotz.queue

    def new_user(self, id):
        return dict(
            _id=int(id),
            file_id=None,
            caption=None,
            format_template=None,
            autorename_format=None,
            media_type=None
        )

    async def add_user(self, b, m):
        u = m.from_user
        if not await self.is_user_exist(u.id):
            user = self.new_user(u.id)
            await self.col.insert_one(user)
            await send_log(b, u)

    async def is_user_exist(self, id):
        user = await self.col.find_one({'_id': int(id)})
        return bool(user)

    async def total_users_count(self):
        count = await self.col.count_documents({})
        return count

    async def get_all_users(self):
        all_users = self.col.find({})
        return all_users

    async def delete_user(self, user_id):
        await self.col.delete_many({'_id': int(user_id)})

    async def set_thumbnail(self, id, file_id):
        if not await self.is_user_exist(id):
            await self.col.insert_one(self.new_user(id))
        await self.col.update_one({'_id': int(id)}, {'$set': {'file_id': file_id}})

    async def get_thumbnail(self, id):
        user = await self.col.find_one({'_id': int(id)})
        return user.get('file_id', None) if user else None

    async def set_caption(self, id, caption):
        if not await self.is_user_exist(id):
            await self.col.insert_one(self.new_user(id))
        await self.col.update_one({'_id': int(id)}, {'$set': {'caption': caption}})

    async def get_caption(self, id):
        user = await self.col.find_one({'_id': int(id)})
        return user.get('caption', None) if user else None

    async def set_format_template(self, id, format_template):
        if not await self.is_user_exist(id):
            await self.col.insert_one(self.new_user(id))
        await self.col.update_one({'_id': int(id)}, {'$set': {'format_template': format_template}})

    async def get_format_template(self, id):
        user = await self.col.find_one({'_id': int(id)})
        return user.get('format_template', None) if user else None

    async def set_media_preference(self, id, media_type):
        if not await self.is_user_exist(id):
            await self.col.insert_one(self.new_user(id))
        await self.col.update_one({'_id': int(id)}, {'$set': {'media_type': media_type}})

    async def get_media_preference(self, id):
        user = await self.col.find_one({'_id': int(id)})
        return user.get('media_type', None) if user else None

    async def set_autorename_format(self, id, autorename_format):
        if not await self.is_user_exist(id):
            await self.col.insert_one(self.new_user(id))
        await self.col.update_one({'_id': int(id)}, {'$set': {'autorename_format': autorename_format}})

    async def get_autorename_format(self, id):
        user = await self.col.find_one({'_id': int(id)})
        return user.get('autorename_format', None) if user else None

    async def log_queue_task(self, task):
        serializable_task = {
            "handler": task["handler"],
            "message_id": task["message"].id,
            "chat_id": task["chat_id"],
            "file_id": task["file_id"],
            "file_name": task["file_name"],
            "new_file_name": task["new_file_name"],
            "media_type": task["media_type"],
            "file_size": task["file_size"],
            "format_template": task["format_template"],
            "timestamp": datetime.now()
        }
        await self.queue_col.insert_one(serializable_task)

    async def get_pending_queue_tasks(self):
        return self.queue_col.find({})

madflixbotz = Database(Config.DB_URL, Config.DB_NAME)
