"""Test database and API endpoints."""
import asyncio
import sys
import os
import aiohttp
import json

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from db.models import Step, Question, AnswerTemplate, TemplateType, User
from db.database import async_session_factory

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:password@postgres:5432/twelvesteps")

async def check_database():
    """Check database state."""
    print("=" * 60)
    print("🔍 CHECKING DATABASE")
    print("=" * 60)
    
    async with async_session_factory() as session:
        # Check steps
        result = await session.execute(select(Step))
        steps = result.scalars().all()
        print(f"📊 Steps: {len(steps)}")
        if steps:
            for step in steps[:5]:
                print(f"  - Step {step.index}: ID={step.id}, Title={step.title or 'N/A'}")
        else:
            print("  ❌ NO STEPS FOUND!")
        
        # Check questions
        result = await session.execute(select(Question))
        questions = result.scalars().all()
        print(f"📊 Questions: {len(questions)}")
        if questions:
            from collections import defaultdict
            by_step = defaultdict(int)
            for q in questions:
                by_step[q.step_id] += 1
            print(f"  Questions by step: {dict(sorted(by_step.items())[:5])}")
        else:
            print("  ❌ NO QUESTIONS FOUND!")
        
        # Check author template
        result = await session.execute(
            select(AnswerTemplate).where(AnswerTemplate.template_type == TemplateType.AUTHOR)
        )
        template = result.scalar_one_or_none()
        print(f"📊 Author template: {'✅ Found' if template else '❌ Missing'}")
        if template:
            print(f"  - ID={template.id}, Name={template.name}")
        
        # Check users
        result = await session.execute(select(User))
        users = result.scalars().all()
        print(f"📊 Users: {len(users)}")
        if users:
            for user in users[:3]:
                print(f"  - User ID={user.id}, Telegram ID={user.telegram_id}")
        
        return {
            "steps_count": len(steps),
            "questions_count": len(questions),
            "has_template": template is not None,
            "users_count": len(users)
        }

async def test_api():
    """Test API endpoints."""
    print("\n" + "=" * 60)
    print("🔍 TESTING API")
    print("=" * 60)
    
    # Get a test user token
    async with async_session_factory() as session:
        result = await session.execute(select(User).limit(1))
        user = result.scalar_one_or_none()
        if not user or not user.api_key:
            print("❌ No user with API key found for testing")
            return
        token = user.api_key
        print(f"✅ Using test user: ID={user.id}, Telegram ID={user.telegram_id}")
    
    base_url = "http://localhost:8000"
    headers = {"Authorization": f"Bearer {token}"}
    
    async with aiohttp.ClientSession() as session:
        # Test /steps/list
        try:
            async with session.get(f"{base_url}/steps/list", headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    print(f"✅ GET /steps/list: {len(data.get('steps', []))} steps")
                else:
                    print(f"❌ GET /steps/list: {resp.status}")
        except Exception as e:
            print(f"❌ GET /steps/list: {e}")
        
        # Test /steps/current
        try:
            async with session.get(f"{base_url}/steps/current", headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    print(f"✅ GET /steps/current: Step {data.get('step_number', 'N/A')}")
                elif resp.status == 404:
                    print(f"⚠️  GET /steps/current: No current step (user hasn't started)")
                else:
                    print(f"❌ GET /steps/current: {resp.status}")
        except Exception as e:
            print(f"❌ GET /steps/current: {e}")
        
        # Test /steps/next
        try:
            async with session.get(f"{base_url}/steps/next", headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    is_completed = data.get('is_completed', False)
                    message = data.get('message', '')
                    if is_completed:
                        print(f"✅ GET /steps/next: Program completed")
                    else:
                        print(f"✅ GET /steps/next: Question received ({len(message)} chars)")
                else:
                    print(f"❌ GET /steps/next: {resp.status}")
        except Exception as e:
            print(f"❌ GET /steps/next: {e}")

async def main():
    """Main function."""
    try:
        db_state = await check_database()
        await test_api()
        
        print("\n" + "=" * 60)
        print("📋 SUMMARY")
        print("=" * 60)
        print(f"Steps: {db_state['steps_count']} (expected: 12)")
        print(f"Questions: {db_state['questions_count']} (expected: ~100+)")
        print(f"Author template: {'✅' if db_state['has_template'] else '❌'}")
        print(f"Users: {db_state['users_count']}")
        
        if db_state['steps_count'] == 0:
            print("\n⚠️  CRITICAL: No steps found! Database initialization failed.")
            return 1
        if db_state['questions_count'] == 0:
            print("\n⚠️  CRITICAL: No questions found! Database initialization failed.")
            return 1
        
        print("\n✅ Database appears to be initialized correctly!")
        return 0
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

