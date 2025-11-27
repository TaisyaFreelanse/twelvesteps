from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import Block as BlockModel


class BlockRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def add_block(self, title: str) -> BlockModel:
        """
        Creates a block. NOTE: This does not check for duplicates.
        Use get_or_create_block instead.
        """
        # Ensure consistency: always lowercase and strip whitespace
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
        """
        Safely finds a block or creates it, handling unique constraint errors.
        """
        clean_title = title.lower().strip()

        # 1. Try to find it first
        block = await self.get_block_by_title(clean_title)
        if block is not None:
            return block

        # 2. If not found, try to create it safely
        try:
            # 'begin_nested()' creates a Savepoint. If the insert fails, 
            # only this specific operation is rolled back, not the whole chat request.
            async with self.db.begin_nested():
                return await self.add_block(clean_title)
        except IntegrityError:
            # 3. If we get here, it means the block was created by another request 
            # milliseconds ago. We simply fetch it again.
            block = await self.get_block_by_title(clean_title)
            if block:
                return block
            
            # If it's still None, something unexpected happened
            raise