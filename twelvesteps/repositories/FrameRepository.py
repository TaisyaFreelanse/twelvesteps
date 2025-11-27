from typing import List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import Frame as FrameModel, Block as BlockModel
from repositories.BlockRepository import BlockRepository


class FrameRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def add_frame(
        self,
        content: str,
        emotion: str,
        weight: int,
        user_id: int,
        block_titles: List[str],
    ) -> FrameModel:
        frame = FrameModel(content=content, emotion=emotion, weight=weight, user_id=user_id)
        block_repo = BlockRepository(self.db)

        blocks: List[BlockModel] = []
        for title in block_titles:
            if not title:
                continue
            block = await block_repo.get_or_create_block(title)
            blocks.append(block)

        for block in blocks:
            frame.blocks.append(block)

        self.db.add(frame)
        await self.db.flush()
        return frame

    async def get_relevant_frames(
        self,
        user_id: int,
        block_titles: List[str],
        limit: int = 5,
    ) -> List[FrameModel]:
        if not block_titles:
            return []

        query = (
            select(FrameModel)
            .join(FrameModel.blocks)
            .where(FrameModel.user_id == user_id, BlockModel.title.in_(block_titles))
            .order_by(FrameModel.weight.desc(), FrameModel.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(query)
        return list(result.scalars().unique().all())
