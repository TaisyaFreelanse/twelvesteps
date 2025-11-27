from assistant.context import Context
from llm.provider import Provider


class Bot:
    def __init__(self, provider: Provider):
        self.provider = provider

    async def chat(self, context: Context):
        return await self.provider.respond(context)
