"""Script to check database state and fix initialization issues."""
import asyncio
import sys
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, text

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db.models import Step, Question, AnswerTemplate, TemplateType

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:password@postgres:5432/twelvesteps")

async def check_database():
    """Check database state."""
    engine = create_async_engine(DATABASE_URL)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    
    async with async_session() as session:
        # Check steps
        result = await session.execute(select(Step))
        steps = result.scalars().all()
        print(f"📊 Steps in database: {len(steps)}")
        if steps:
            for step in steps[:5]:  # Show first 5
                print(f"  - Step {step.index}: ID={step.id}, Title={step.title}")
        
        # Check questions
        result = await session.execute(select(Question))
        questions = result.scalars().all()
        print(f"📊 Questions in database: {len(questions)}")
        if questions:
            # Group by step
            from collections import defaultdict
            by_step = defaultdict(int)
            for q in questions:
                by_step[q.step_id] += 1
            print(f"  Questions by step: {dict(by_step)}")
        
        # Check author template
        result = await session.execute(
            select(AnswerTemplate).where(AnswerTemplate.template_type == TemplateType.AUTHOR)
        )
        template = result.scalar_one_or_none()
        print(f"📊 Author template: {'✅ Found' if template else '❌ Missing'}")
        if template:
            print(f"  - ID={template.id}, Name={template.name}")
        
        # Check profile sections
        from db.models import ProfileSection
        result = await session.execute(select(ProfileSection))
        sections = result.scalars().all()
        print(f"📊 Profile sections: {len(sections)}")
        
        return {
            "steps_count": len(steps),
            "questions_count": len(questions),
            "has_template": template is not None,
            "sections_count": len(sections)
        }

async def main():
    """Main function."""
    print("=" * 60)
    print("🔍 CHECKING DATABASE STATE")
    print("=" * 60)
    
    try:
        state = await check_database()
        
        print("\n" + "=" * 60)
        print("📋 SUMMARY")
        print("=" * 60)
        print(f"Steps: {state['steps_count']} (expected: 12)")
        print(f"Questions: {state['questions_count']} (expected: ~100+)")
        print(f"Author template: {'✅' if state['has_template'] else '❌'}")
        print(f"Profile sections: {state['sections_count']} (expected: 13+)")
        
        if state['steps_count'] == 0:
            print("\n⚠️  WARNING: No steps found! Initialization may have failed.")
            print("   Run: python -m db.initialize_db")
        if state['questions_count'] == 0:
            print("\n⚠️  WARNING: No questions found! Initialization may have failed.")
            print("   Run: python -m db.initialize_db")
        if not state['has_template']:
            print("\n⚠️  WARNING: Author template not found!")
            print("   Run: python -m db.init_author_template")
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

