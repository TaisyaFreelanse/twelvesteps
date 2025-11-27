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