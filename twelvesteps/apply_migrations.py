"""Script to apply Alembic migrations"""
import asyncio
from alembic.config import Config
from alembic import command

if __name__ == "__main__":
    cfg = Config("alembic.ini")
    print("Applying migrations...")
    command.upgrade(cfg, "head")
    print("Migrations applied successfully!")

