#Abstract class for LLM to optimize adding different LLM providers
from abc import ABC, abstractmethod
class Provider(ABC):

    @abstractmethod
    async def respond(self):
        pass
    
    @abstractmethod
    async def classify(self, content : str):
        pass