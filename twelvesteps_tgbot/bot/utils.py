"""Utility functions for Telegram bot."""

from typing import List, Optional, Union
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, ReplyKeyboardMarkup


def split_long_message(text: str, max_length: int = 4096) -> List[str]:
    """
    Split long message into chunks preserving context.
    Tries to split at sentence boundaries when possible.
    
    Args:
        text: Text to split
        max_length: Maximum length of each chunk (default 4096 for Telegram)
    
    Returns:
        List of text chunks
    """
    if len(text) <= max_length:
        return [text]
    
    chunks = []
    current_chunk = ""
    
    # Split by paragraphs first
    paragraphs = text.split('\n\n')
    
    for para in paragraphs:
        # If paragraph itself is too long, split by sentences
        if len(para) > max_length:
            sentences = para.split('. ')
            for i, sentence in enumerate(sentences):
                if i < len(sentences) - 1:
                    sentence += '. '
                
                if len(current_chunk) + len(sentence) > max_length:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                        current_chunk = sentence
                    else:
                        # Single sentence is too long, split by words
                        words = sentence.split()
                        for word in words:
                            if len(current_chunk) + len(word) + 1 > max_length:
                                if current_chunk:
                                    chunks.append(current_chunk.strip())
                                    current_chunk = word
                                else:
                                    # Single word is too long, force split
                                    chunks.append(word[:max_length])
                                    current_chunk = word[max_length:]
                            else:
                                current_chunk += (' ' if current_chunk else '') + word
                else:
                    current_chunk += sentence
        else:
            # Check if adding paragraph would exceed limit
            if len(current_chunk) + len(para) + 2 > max_length:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = para
                else:
                    chunks.append(para)
            else:
                current_chunk += ('\n\n' if current_chunk else '') + para
    
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    return chunks


async def send_long_message(
    message: Message,
    text: str,
    reply_markup: Optional[Union[ReplyKeyboardMarkup, InlineKeyboardMarkup]] = None,
    max_length: int = 4096
) -> None:
    """
    Send a message, automatically splitting it if it exceeds max_length.
    Only the first chunk will have the reply_markup.
    
    Args:
        message: Message object to reply to
        text: Text to send
        reply_markup: Optional keyboard markup (only added to first chunk)
        max_length: Maximum length per chunk
    """
    chunks = split_long_message(text, max_length)
    
    for i, chunk in enumerate(chunks):
        if i == 0:
            # First chunk gets the markup
            await message.answer(chunk, reply_markup=reply_markup)
        else:
            # Subsequent chunks without markup
            await message.answer(chunk)


async def edit_long_message(
    callback: CallbackQuery,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    max_length: int = 4096
) -> None:
    """
    Edit a message, automatically splitting it if it exceeds max_length.
    If message is too long, it will be split into multiple messages.
    
    Args:
        callback: CallbackQuery object
        text: Text to send
        reply_markup: Optional inline keyboard markup
        max_length: Maximum length per chunk
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        chunks = split_long_message(text, max_length)
        
        if len(chunks) == 1:
            # Single chunk - can use edit_text
            try:
                await callback.message.edit_text(chunks[0], reply_markup=reply_markup)
                logger.info(f"Successfully edited message for callback {callback.data}")
            except Exception as e:
                logger.error(f"Failed to edit message: {e}, trying to send new message instead")
                # If edit fails, try to send new message
                await callback.message.answer(chunks[0], reply_markup=reply_markup)
        else:
            # Multiple chunks - edit first, send others
            try:
                await callback.message.edit_text(chunks[0], reply_markup=reply_markup)
                logger.info(f"Successfully edited first chunk for callback {callback.data}")
            except Exception as e:
                logger.error(f"Failed to edit message: {e}, sending all chunks as new messages")
                # If edit fails, send all as new messages
                await callback.message.answer(chunks[0], reply_markup=reply_markup)
            
            for chunk in chunks[1:]:
                await callback.message.answer(chunk)
    except Exception as e:
        logger.exception(f"Error in edit_long_message for callback {callback.data}: {e}")
        # Fallback: just send as new message
        try:
            await callback.message.answer(text[:max_length], reply_markup=reply_markup)
        except Exception as e2:
            logger.exception(f"Failed to send fallback message: {e2}")
            raise


def is_question(text: str) -> bool:
    """
    Determines if the input text is a question.
    
    Checks for:
    - Question words at the start (что, как, где, когда, кто, почему, зачем, какой, какая, какие, сколько)
    - Question phrases (расскажи о себе, что ты умеешь, что ты делаешь, что ты можешь)
    - Question mark at the end
    
    Args:
        text: Text to check
        
    Returns:
        True if text appears to be a question, False otherwise
    """
    if not text or not text.strip():
        return False
    
    text_lower = text.strip().lower()
    
    # Check for question mark
    if text.strip().endswith('?'):
        return True
    
    # Russian question words at the start
    question_words = [
        'что', 'как', 'где', 'когда', 'кто', 'почему', 'зачем',
        'какой', 'какая', 'какие', 'какое', 'сколько', 'откуда',
        'куда', 'чем', 'кому', 'чему', 'каким', 'какой', 'какую'
    ]
    
    # Check if starts with question word
    words = text_lower.split()
    if words and words[0] in question_words:
        return True
    
    # Check for question phrases
    question_phrases = [
        'расскажи о себе',
        'что ты умеешь',
        'что ты делаешь',
        'что ты можешь',
        'что ты знаешь',
        'что ты',
        'расскажи про себя',
        'расскажи про',
        'что это',
        'как это',
        'что такое',
        'как работает',
        'что делает',
        'что может',
        'что умеет',
        'что знаешь',
        'что делаешь',
        'что можешь',
        'что умеешь'
    ]
    
    for phrase in question_phrases:
        if phrase in text_lower:
            return True
    
    return False
