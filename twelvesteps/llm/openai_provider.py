import json
import aiofiles
from typing import List, Optional
from pydantic import BaseModel, Field

from assistant.context import Context
from assistant.response import Response
from llm.provider import Provider
from openai import AsyncOpenAI
from repositories import PromptRepository

# --- New Pydantic Models for Analysis ---
class ProfileAnalysis(BaseModel):
    update_needed: bool = Field(..., description="True if the user message contains new psychological/identity info")
    extracted_info: Optional[str] = Field(None, description="The specific new details extracted")
    reason: Optional[str] = Field(None, description="Why the update is needed")

# --- Existing Models ---
class Part(BaseModel):
    part: str
    blocks: List[str]
    emotion: str
    importance: int
    thinking_frame: Optional[str] = None
    level_of_mind: Optional[int] = None
    memory_type: Optional[str] = None
    target_block: Optional[dict] = None
    action: Optional[str] = None
    strategy_hint: Optional[str] = None

class ClassificationMetadata(BaseModel):
    intention: Optional[str] = None
    urgency: Optional[str] = None
    cognitive_mode: Optional[str] = None
    suggested_response_mode: Optional[str] = None

class ClassificationResult(BaseModel):
    parts: List[Part]
    metadata: Optional[ClassificationMetadata] = None

class OpenAI(Provider):
    async def load_config(self, path: str):
        async with aiofiles.open(path, "r") as f:
            content = await f.read()
            return json.loads(content)

    def _format_message(self, role: str, content: str) -> dict:
        if not content:
            return None
        return {"role": role, "content": content}

    def _format_context(self, context: Context) -> list[dict]:
        messages = [
            self._format_message("system", context.assistant.system_prompt),
            self._format_message("system", context.assistant.personalized_prompt),
            self._format_message("system", context.assistant.helper_prompt),
        ]
        for msg in context.last_messages:
            try:
                messages.append(self._format_message(msg.sender_role.value, msg.content))
            except Exception as e:
                print(f"[OpenAI._format_context] Error formatting message: {e}")
        messages.append(self._format_message("user", context.message))
        return [m for m in messages if m and m["content"].strip()]

    def _format_context_classification(self, prompt: str, message: str) -> list[dict]:
        messages = [
            self._format_message("system", prompt),
            self._format_message("user", message)
        ]
        return [m for m in messages if m and m["content"].strip()]
    
    # --- NEW: Helper for Profile Tasks ---
    def _format_profile_task(self, system_instruction: str, input_data: str) -> list[dict]:
        return [
            self._format_message("system", system_instruction),
            self._format_message("user", input_data)
        ]


    async def generate_sos_response(self, system_prompt: str, question: str, personalization: str) -> str:
        config = await self.load_config("./llm/configs/openai_dynamic.json")
        """
        Generates an example answer based on the SOS context.
        """
        # Construct the messages payload
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user", 
                "content": (
                    f"Персонализация пользователя:\n{personalization}\n\n"
                    f"Последний вопрос бота:\n{question}\n\n"
                    "Напиши пример ответа для этого пользователя."
                )
            }
        ]

        async with AsyncOpenAI() as client:
            response = await client.chat.completions.create(
                model=config["model"],
                messages=messages,
                temperature=0.7,
            )

        return response.choices[0].message.content
    
    # --- NEW: Analyze Profile Function ---
# --- FIXED FUNCTION: Profile Analyzer ---
    async def analyze_profile(self, context: Context) -> ProfileAnalysis:
        """
        Determines if the user's message contains new information that requires 
        updating their personalization profile.
        """
        config = await self.load_config("./llm/configs/openai_dynamic.json")
        
        system_prompt = """
        You are a Clinical Profile Analyst.
        Compare the [CURRENT_PROFILE] with the [USER_MESSAGE].
        
        **Task:** 
        Determine if the message contains NEW relevant information about:
        1. Identity (Name, Age, Gender)
        2. Addiction Details (Substance, History)
        3. Status (Clean time, Relapse, Withdrawal symptoms)
        4. Psychology (Triggers, Coping mechanisms, Emotional state)
        
        **Output Format:**
        You MUST return a valid JSON object with exactly these fields:
        {
            "update_needed": true or false,
            "extracted_info": "A concise text summary of the new findings (or null if false)",
            "reason": "Short explanation of why this is relevant"
        }
        """

        user_input_block = f"""
        [CURRENT_PROFILE]:
        {context.assistant.personalized_prompt}

        [USER_MESSAGE]:
        {context.message}
        """

        messages = [
            self._format_message("system", system_prompt),
            self._format_message("user", user_input_block)
        ]

        async with AsyncOpenAI() as client:
            response = await client.chat.completions.create(
                model=config.get("model", "gpt-4o"),
                messages=messages,
                response_format={"type": "json_object"},
                temperature=config.get("temperature", 0.0),
                max_tokens=config.get("max_tokens", 300),
            )

        try:
            raw = response.choices[0].message.content
            data = json.loads(raw)
            return ProfileAnalysis(**data)
        except Exception as e:
            print(f"[OpenAI.analyze_profile] Error parsing analysis: {e} | Raw: {raw}")
            # Fallback so the bot doesn't crash
            return ProfileAnalysis(update_needed=False, extracted_info=None, reason="Error parsing")
        
    # --- NEW: Update Prompt Function ---
    async def update_personalized_prompt(self, context: Context, new_info: str) -> str:
        config = await self.load_config("./llm/configs/openai_dynamic.json")

        system_prompt = await PromptRepository.load_update_prompt()

        user_input_block = f"""
        [OLD_PROFILE]:
        {context.assistant.personalized_prompt}

        [NEW_FINDINGS]:
        {new_info}
        """

        messages = self._format_profile_task(system_prompt, user_input_block)

        async with AsyncOpenAI() as client:
            response = await client.chat.completions.create(
                model=config.get("model", "gpt-4o"),
                messages=messages,
                temperature=config.get("temperature", 0.5),
                max_tokens=config.get("max_tokens", 600),
            )

        return response.choices[0].message.content.strip()

    # --- Existing Methods ---

    async def plan(self, messages: list[dict]) -> str:
        prompt = await PromptRepository.load_dynamic_prompt()
        config = await self.load_config("./llm/configs/openai_dynamic.json")
        plan_messages = [{"role": "system", "content": prompt}] + messages

        async with AsyncOpenAI() as client:
            response = await client.chat.completions.create(
                model=config["model"],
                messages=plan_messages,
                max_tokens=config["max_tokens"],
            )
        return response.choices[0].message.content.strip()

    async def respond(self, context: Context) -> Response:
        messages = self._format_context(context)
        config = await self.load_config("./llm/configs/openai_system.json")

        plan = await self.plan(messages=messages)
        
        async with AsyncOpenAI() as client:
            response = await client.chat.completions.create(
                model=config["model"],
                messages=messages + [{"role": "system", "content": plan}],
                max_tokens=config["max_tokens"],
            )

        return Response(response.choices[0].message.content, plan=plan)

    async def classify(self, content: str) -> ClassificationResult:
        config = await self.load_config("./llm/configs/openai_classify.json")
        prompt = await PromptRepository.load_classify_prompt()
        
        messages = self._format_context_classification(prompt, content)

        async with AsyncOpenAI() as client:
            response = await client.chat.completions.create(
                model=config["model"],
                messages=messages,
                max_completion_tokens=config["max_tokens"],
            )

            raw = response.choices[0].message.content
            try:
                data = json.loads(raw)
                result = ClassificationResult(**data)
            except Exception as e:
                result = ClassificationResult(parts=[
                    Part(part=content, blocks=[], emotion="neutral", importance=0)
                ])
                print(f"[OpenAI.classify] JSON parse error: {e}\nRaw output: {raw}")

            return result