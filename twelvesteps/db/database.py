import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from dotenv import load_dotenv
import os




load_dotenv()

class Base(DeclarativeBase):

    def __repr__(self):
        cols = []
        for col in self.__table__.columns.keys():

            cols.append(f"{col}={getattr(self, col)}")
        return f"{self.__class__.__name__}(" + ", ".join(cols) + ")"
    pass


engine = create_async_engine(
    url = os.getenv("DATABASE_URL"),
    echo=True
)


async_session_factory = async_sessionmaker(
    engine, 
    class_ = AsyncSession, 
    expire_on_commit=False)




