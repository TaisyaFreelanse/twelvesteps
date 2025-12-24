"""Test database connection to Render PostgreSQL"""
import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Set UTF-8 encoding for Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Load environment variables
env_path = Path(__file__).parent.parent / "backend.env"
if env_path.exists():
    load_dotenv(env_path)
    print(f"[OK] Loaded .env from: {env_path}")
else:
    print(f"[ERROR] .env file not found at: {env_path}")
    sys.exit(1)

database_url = os.getenv("DATABASE_URL")
if not database_url:
    print("[ERROR] DATABASE_URL not found in environment")
    sys.exit(1)

print(f"[OK] DATABASE_URL loaded: {database_url[:50]}...")
print()

# Test connection
async def test_connection():
    try:
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy import text
        
        print("[INFO] Connecting to database...")
        engine = create_async_engine(database_url, echo=False)
        
        async with engine.begin() as conn:
            # Test basic query
            result = await conn.execute(text("SELECT version()"))
            version = result.scalar()
            print(f"[OK] Connected successfully!")
            print(f"[INFO] PostgreSQL version: {version[:50]}...")
            print()
            
            # Check if alembic_version table exists (migrations applied)
            result = await conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'alembic_version'
                )
            """))
            has_migrations = result.scalar()
            
            if has_migrations:
                result = await conn.execute(text("SELECT version_num FROM alembic_version ORDER BY version_num DESC LIMIT 1"))
                latest_migration = result.scalar()
                print(f"[OK] Migrations applied. Latest: {latest_migration}")
            else:
                print("[WARNING] No migrations found. You may need to run: alembic upgrade head")
            print()
            
            # Check if new columns exist in profile_section_data
            result = await conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'profile_section_data' 
                AND column_name IN ('subblock_name', 'entity_type', 'importance', 'is_core_personality', 'tags')
                ORDER BY column_name
            """))
            new_columns = [row[0] for row in result.fetchall()]
            
            if new_columns:
                print(f"[OK] New columns found: {', '.join(new_columns)}")
            else:
                print("[WARNING] New columns not found. Migration m9n0o1p2q3r4 may not be applied.")
                print("   Run: cd twelvesteps && alembic upgrade head")
            print()
            
            # Count tables
            result = await conn.execute(text("""
                SELECT COUNT(*) 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
            """))
            table_count = result.scalar()
            print(f"[INFO] Total tables in database: {table_count}")
            
        await engine.dispose()
        print()
        print("[OK] Database connection test completed successfully!")
        
    except Exception as e:
        print(f"[ERROR] Error connecting to database: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(test_connection())

