from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import Block as BlockModel


class BlockRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def add_block(self, title: str) -> BlockModel:
        """Add a new block."""
        clean_title = title.lower().strip()

        block = BlockModel(title=clean_title)
        self.db.add(block)
        await self.db.flush()
        return block

    async def get_block_by_title(self, title: str) -> BlockModel | None:
        clean_title = title.lower().strip()
        query = select(BlockModel).where(BlockModel.title == clean_title)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_or_create_block(self, title: str) -> BlockModel:
        """Get existing block or create a new one."""
        clean_title = title.lower().strip()

        block = await self.get_block_by_title(clean_title)
        if block is not None:
            return block

        try:
            async with self.db.begin_nested():
                return await self.add_block(clean_title)
        except IntegrityError:
            block = await self.get_block_by_title(clean_title)
            if block:
                return block

            raise