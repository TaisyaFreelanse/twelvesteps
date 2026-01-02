from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from db.models import User as UserModel, UserRole
from typing import Optional

class UserRepository():
    def __init__(self, db : AsyncSession):
        self.db = db



    async def add_user(
        self,
        telegram_id,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        display_name: Optional[str] = None,
        user_role: UserRole = UserRole.dependent,
    ) -> UserModel:
        telegram_id = str(telegram_id)
        new_user = UserModel(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            display_name=display_name or first_name or username,
            user_role=user_role,
        )
        self.db.add(new_user)

        await self.db.flush()


        return new_user

    async def find_or_create_user_by_telegram_id(
        self,
        telegram_id,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
    ) -> UserModel:
        telegram_id = str(telegram_id)
        session = self.db
        user = await self.get_by_telegram_id(telegram_id)

        if user is None:
            print(f"Пользователь {telegram_id} не найден. Создаем нового.")
            user = await self.add_user(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                user_role=UserRole.dependent
            )
            user.last_active = datetime.now(timezone.utc)
            await session.commit()
            print("Новый пользователь сохранен.")
        else:
            updated = False
            if username and user.username != username:
                user.username = username
                updated = True
            if first_name and user.first_name != first_name:
                user.first_name = first_name
                updated = True

            user.last_active = datetime.now(timezone.utc)

            await session.flush()
            await session.commit()

        return user

    async def update_last_active(self, user_id: int) -> None:
        """Update last_active timestamp for a user."""
        stmt = update(UserModel).where(
            UserModel.id == user_id
        ).values(
            last_active=func.now()
        )
        await self.db.execute(stmt)
        await self.db.flush()

    async def get_personalized_prompt(self, user_id : int):
        query = select(UserModel).where(UserModel.id == user_id)
        result = await self.db.execute(query)

        user = result.scalar_one_or_none()
        if user and user.personal_prompt:
            return user.personal_prompt
        else:
            return None

    async def set_personalized_prompt(self, user_id : int, prompt_text : str) -> Optional[UserModel]:
        query = await select(UserModel).where(UserModel.id == user_id)
        result = await self.db.execute(query)

        user = result.scalar_one_or_none()
        if user:
            user.personal_prompt = prompt_text
            self.db.add(user)
            await self.db.flush()
            return user
        else:
            return None

    async def get_user_by_api_key(self, api_key: str) -> Optional[UserModel]:
        if not api_key:
            return None
        query = select(UserModel).where(UserModel.api_key == api_key)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_by_telegram_id(self, telegram_id) -> Optional[UserModel]:
        telegram_id = str(telegram_id)
        query = select(UserModel).where(UserModel.telegram_id == telegram_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> Optional[UserModel]:
        """Get user by ID"""
        query = select(UserModel).where(UserModel.id == user_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()