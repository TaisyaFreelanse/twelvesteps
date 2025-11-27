from __future__ import annotations

import secrets
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import User as UserModel, UserRole
from repositories.UserRepository import UserRepository


class UserService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = UserRepository(session)

    def _ensure_api_key(self, user: UserModel) -> None:
        if not user.api_key:
            user.api_key = secrets.token_hex(32)

    async def authenticate_telegram(
        self,
        telegram_id: str,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
    ) -> tuple[UserModel, bool]:
        telegram_id = str(telegram_id)
        user = await self.repo.get_by_telegram_id(telegram_id)
        is_new = user is None

        if is_new:
            user = await self.repo.add_user(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                display_name=first_name or username,
                user_role=UserRole.dependent,
            )
        else:
            if username and user.username != username:
                user.username = username
            if first_name and user.first_name != first_name:
                user.first_name = first_name
            if not user.display_name and (first_name or username):
                user.display_name = first_name or username

        self._ensure_api_key(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user, is_new

    async def update_profile(self, user: UserModel, updates: dict[str, Any]) -> UserModel:
        allowed_fields = {"display_name", "program_experience", "sobriety_date"}
        relevant_updates = {k: v for k, v in updates.items() if k in allowed_fields}
        if not relevant_updates:
            return user

        has_changes = False
        for field, value in relevant_updates.items():
            if getattr(user, field) != value:
                setattr(user, field, value)
                has_changes = True

        if has_changes:
            await self.session.commit()
            await self.session.refresh(user)

        return user
