import json
import aiofiles
from db.models import User as UserModel

class PromptRepository:

    @staticmethod
    async def load_system_prompt():
        async with aiofiles.open("./llm/prompts/system.json", "r", encoding="utf-8") as f:
            content = await f.read()
            return json.dumps(json.loads(content))

    @staticmethod
    async def load_classify_prompt():
        async with aiofiles.open("./llm/prompts/classify.json", "r", encoding="utf-8") as f:
            content = await f.read()
            return json.dumps(json.loads(content))

    @staticmethod
    async def load_dynamic_prompt():
        async with aiofiles.open("./llm/prompts/dynamic.json", "r", encoding="utf-8") as f:
            content = await f.read()
            return json.dumps(json.loads(content))

    @staticmethod
    async def load_include_prompt():
        async with aiofiles.open("./llm/prompts/include.json", "r", encoding="utf-8") as f:
            content = await f.read()
            return json.dumps(json.loads(content))

    @staticmethod
    async def load_update_prompt():
        async with aiofiles.open("./llm/prompts/include.json", "r", encoding="utf-8") as f:
            content = await f.read()
            return json.dumps(json.loads(content))

    @staticmethod
    async def load_sos_prompt():
        """
        try:
            async with aiofiles.open("./llm/prompts/sos.json", "r", encoding="utf-8") as f:
                content = await f.read()
                return json.dumps(json.loads(content))
        except FileNotFoundError:
            return "You are a helpful AA sponsor. Provide a brief, supportive hint."

    @staticmethod
    async def load_thanks_prompt():
        """
        try:
            async with aiofiles.open("./llm/prompts/thanks.json", "r", encoding="utf-8") as f:
                content = await f.read()
                return json.dumps(json.loads(content))
        except FileNotFoundError:
            return json.dumps({
                "role": "system",
                "content": "You are a supportive AA sponsor. Express genuine support and motivation when user uses /thanks."
            })

    @staticmethod
    async def load_day_prompt():
        """
        try:
            async with aiofiles.open("./llm/prompts/day.json", "r", encoding="utf-8") as f:
                content = await f.read()
                return json.dumps(json.loads(content))
        except FileNotFoundError:
            return json.dumps({
                "role": "system",
                "content": "You are a supportive AA sponsor. Help user analyze their current state when they use /day."
            })

    @staticmethod
    async def load_knowledge_base():
        """
        try:
            async with aiofiles.open("./llm/prompts/knowledge_base.json", "r", encoding="utf-8") as f:
                content = await f.read()
                return json.loads(content)
        except FileNotFoundError:
            return None

    @staticmethod
    async def get_step_knowledge(step_number: int) -> dict:
        """
        knowledge_base = await PromptRepository.load_knowledge_base()
        if knowledge_base and "steps" in knowledge_base:
            step_key = str(step_number)
            if step_key in knowledge_base["steps"]:
                return knowledge_base["steps"][step_key]
        return {
            "name": f"Шаг {step_number}",
            "essence": "",
            "keywords": [],
            "typical_situations": [],
            "guiding_areas": []
        }

    @staticmethod
    async def load_sos_memory_prompt():
        """
        try:
            async with aiofiles.open("./llm/prompts/sos_memory.json", "r", encoding="utf-8") as f:
                content = await f.read()
                return json.loads(content).get("prompt", "")
        except FileNotFoundError:
            return None

    @staticmethod
    async def load_sos_direction_prompt():
        """
        try:
            async with aiofiles.open("./llm/prompts/sos_direction.json", "r", encoding="utf-8") as f:
                content = await f.read()
                return json.loads(content).get("prompt", "")
        except FileNotFoundError:
            return None

    @staticmethod
    async def load_sos_question_prompt():
        """
        try:
            async with aiofiles.open("./llm/prompts/sos_question.json", "r", encoding="utf-8") as f:
                content = await f.read()
                return json.loads(content).get("prompt", "")
        except FileNotFoundError:
            return None

    @staticmethod
    async def load_sos_support_prompt():
        """
        try:
            async with aiofiles.open("./llm/prompts/sos_support.json", "r", encoding="utf-8") as f:
                content = await f.read()
                return json.loads(content).get("prompt", "")
        except FileNotFoundError:
            return None

    @staticmethod
    async def load_sos_examples_prompt():
        """
        try:
            async with aiofiles.open("./llm/prompts/sos_examples.json", "r", encoding="utf-8") as f:
                content = await f.read()
                return json.loads(content).get("prompt", "")
        except FileNotFoundError:
            return None

    @staticmethod
    async def load_profile_next_question_prompt():
        """
        try:
            async with aiofiles.open("./llm/prompts/profile_next_question.json", "r", encoding="utf-8") as f:
                content = await f.read()
                return json.loads(content).get("prompt", "")
        except FileNotFoundError:
            return None