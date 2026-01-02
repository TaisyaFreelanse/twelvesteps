from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import Message as MessageModel, SenderRole
from sqlalchemy import select
class MessageRepository():
    def __init__(self, db : AsyncSession):
        self.db = db

    async def add_message(self, content, sender_role : SenderRole, user_id):
        message = MessageModel(content = content, sender_role = sender_role, user_id = user_id )
        self.db.add(message)
        await self.db.flush()
        return message

    async def get_last_messages(self, user_id, amount=100) -> List[MessageModel]:

        query = select(MessageModel).where(MessageModel.user_id == user_id).order_by(MessageModel.created_at.desc()).limit(amount)
        result = await self.db.execute(query)
        return list(result.scalars().all())

