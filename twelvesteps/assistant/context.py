#todo
#context builder with last_messages, relavant_blocks, relavant_frames, dynamic_prompt generation
from db.models import Message
from typing import List
class Context:
    def __init__(self, message, last_messages : List[Message], assistant):
        self.assistant = assistant
        self.last_messages = last_messages
        self.message = message
        self.relevant_frames= []