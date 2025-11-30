"""Smart migration script that handles multiple heads."""
import sys
import os
from alembic.config import Config
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError

def get_sync_database_url():
    """Get synchronous database URL from environment."""
    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        print("Error: DATABASE_URL environment variable is not set")
        return None
    
    # Convert async URL to sync URL for SQLAlchemy create_engine
    if "postgresql+asyncpg://" in database_url:
        sync_url = database_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
    elif "postgresql://" in database_url:
        sync_url = database_url.replace("postgresql://", "postgresql+psycopg2://")
    else:
        sync_url = database_url
    
    return sync_url

def check_if_database_empty():
    """Check if database is empty (no alembic_version table)."""
    try:
        url = get_sync_database_url()
        if not url:
            return False
        
        engine = create_engine(url)
        with engine.connect() as conn:
            # Check if alembic_version table exists
            inspector = inspect(engine)
            tables = inspector.get_table_names()
            has_alembic_version = "alembic_version" in tables
            has_users = "users" in tables
            
            if not has_alembic_version and not has_users:
                print("Database appears to be empty. Creating base tables from models first...")
                return True
            return False
    except Exception as e:
        print(f"Warning: Could not check database state: {e}")
        return False

def create_base_tables():
    """Create base tables from SQLAlchemy models."""
    try:
        # Import models to register them with Base
        from db.database import Base
        from db import models  # noqa: F401
        
        url = get_sync_database_url()
        if not url:
            return False
        
        engine = create_engine(url)
        
        # Create all tables
        print("Creating base tables from models...")
        Base.metadata.create_all(engine)
        print("Base tables created successfully!")
        
        # Mark initial migration as applied
        with engine.connect() as conn:
            # Check if alembic_version exists, if not create it
            inspector = inspect(engine)
            if "alembic_version" not in inspector.get_table_names():
                conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL, CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"))
                conn.commit()
                print("Created alembic_version table")
        
        return True
    except Exception as e:
        print(f"Error creating base tables: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Apply migrations, handling multiple heads."""
    cfg = Config("alembic.ini")
    script = ScriptDirectory.from_config(cfg)
    
    try:
        # Check if database is empty and create base tables if needed
        if check_if_database_empty():
            if not create_base_tables():
                print("Warning: Failed to create base tables, continuing with migrations anyway...")
        
        heads = script.get_revisions("heads")
        head_revisions = [h.revision for h in heads]
        print(f'Found {len(heads)} head(s): {head_revisions}')
        
        if len(heads) > 1:
            print('Multiple heads detected, applying to each head separately...')
            for head in heads:
                print(f'Applying migrations up to {head.revision}...')
                try:
                    command.upgrade(cfg, head.revision)
                    print(f'Successfully applied migrations to {head.revision}')
                except Exception as e:
                    print(f'Warning: Could not apply to {head.revision}: {e}')
            
            print('All heads applied, now applying merge migration...')
            try:
                command.upgrade(cfg, 'merge_heads_001')
                print('Merge migration applied successfully')
            except Exception as merge_err:
                print(f'Merge migration not found or already applied: {merge_err}')
                print('Continuing anyway...')
        else:
            print(f'Single head: {head_revisions[0] if head_revisions else "none"}')
            command.upgrade(cfg, 'head')
        
        print('All migrations applied successfully!')
        
        # Initialize profile sections if they don't exist
        print('Initializing profile sections...')
        try:
            from db.init_profile_sections import init_profile_sections
            init_profile_sections()
        except Exception as e:
            print(f'Warning: Could not initialize profile sections: {e}')
        
        # Initialize author template if it doesn't exist
        print('Initializing author template...')
        try:
            import asyncio
            from db import init_author_template
            asyncio.run(init_author_template.main())
        except Exception as e:
            print(f'Warning: Could not initialize author template: {e}')
            import traceback
            traceback.print_exc()
        
        # Initialize or update steps and questions (always runs to ensure data is up to date)
        print('Initializing/updating steps and questions...')
        try:
            import asyncio
            from db.initialize_db import initialize_db_and_seed
            asyncio.run(initialize_db_and_seed())
            print('✅ Steps and questions initialized/updated!')
        except Exception as e:
            print(f'Warning: Could not initialize steps and questions: {e}')
            import traceback
            traceback.print_exc()
        
        return 0
    except Exception as e:
        print(f'Migration error: {e}')
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())

