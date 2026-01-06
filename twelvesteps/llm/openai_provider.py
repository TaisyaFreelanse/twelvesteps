import json
import aiofiles
from typing import List, Optional
from pydantic import BaseModel, Field

from assistant.context import Context
from assistant.response import Response
from llm.provider import Provider
from openai import AsyncOpenAI
from repositories import PromptRepository

class ProfileAnalysis(BaseModel):
    update_needed: bool = Field(..., description="True if the user message contains new psychological/identity info")
    extracted_info: Optional[str] = Field(None, description="The specific new details extracted")
    reason: Optional[str] = Field(None, description="Why the update is needed")

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

    def _format_profile_task(self, system_instruction: str, input_data: str) -> list[dict]:
        return [
            self._format_message("system", system_instruction),
            self._format_message("user", input_data)
        ]


    async def generate_sos_response(self, system_prompt: str, question: str, personalization: str) -> str:
        """Generate SOS response example for user."""
        config = await self.load_config("./llm/configs/openai_dynamic.json")
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

    async def analyze_profile(self, context: Context) -> ProfileAnalysis:
        """Analyze user message to extract profile information."""
        config = await self.load_config("./llm/configs/openai_dynamic.json")
        prompt_json = await PromptRepository.load_include_prompt()
        prompt_data = json.loads(prompt_json)
        system_prompt = prompt_data.get("prompt", "")
        
        user_input_block = f"User message: {context.message}\n\nCurrent profile: {context.assistant.personalized_prompt[:500] if context.assistant.personalized_prompt else 'Empty'}"

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
            return ProfileAnalysis(update_needed=False, extracted_info=None, reason="Error parsing")

    async def update_personalized_prompt(self, context: Context, new_info: str) -> str:
        """Update personalized prompt with new information."""
        config = await self.load_config("./llm/configs/openai_dynamic.json")
        prompt_json = await PromptRepository.load_update_prompt()
        prompt_data = json.loads(prompt_json)
        system_prompt = prompt_data.get("prompt", "")

        messages = self._format_profile_task(system_prompt, new_info)

        async with AsyncOpenAI() as client:
            response = await client.chat.completions.create(
                model=config.get("model", "gpt-4o"),
                messages=messages,
                temperature=config.get("temperature", 0.5),
                max_tokens=config.get("max_tokens", 600),
            )

        return response.choices[0].message.content.strip()


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