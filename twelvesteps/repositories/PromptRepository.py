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

    # --- ADD THIS METHOD ---
    @staticmethod
    async def load_sos_prompt():
        """
        Loads the system prompt for the SOS/Hint feature.
        """
        try:
            async with aiofiles.open("./llm/prompts/sos.json", "r", encoding="utf-8") as f:
                content = await f.read()
                # Validate JSON structure
                return json.dumps(json.loads(content))
        except FileNotFoundError:
            # Fallback string if file is missing, to prevent crash
            return "You are a helpful AA sponsor. Provide a brief, supportive hint."
    
    @staticmethod
    async def load_thanks_prompt():
        """
        Loads the system prompt for the /thanks command.
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
        Loads the system prompt for the /day command.
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
        Loads the knowledge base with 12 Steps information for SOS context.
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
        Get knowledge for a specific step.
        Returns dict with name, essence, keywords, typical_situations, guiding_areas.
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
        Loads the specialized SOS prompt for 'memory' help type.
        DEPRECATED: Use load_sos_direction_prompt instead.
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
        Loads the SOS prompt for 'direction' help type (Помоги понять куда смотреть).
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
        Loads the SOS prompt for 'question' help type (Не понимаю вопрос).
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
        Loads the SOS prompt for 'support' help type (Просто тяжело — нужна поддержка).
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
        Loads the SOS prompt for 'examples' help type (Нужны примеры).
        """
        try:
            async with aiofiles.open("./llm/prompts/sos_examples.json", "r", encoding="utf-8") as f:
                content = await f.read()
                return json.loads(content).get("prompt", "")
        except FileNotFoundError:
            return None