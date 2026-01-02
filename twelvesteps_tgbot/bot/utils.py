"""Utility functions for Telegram bot."""

from typing import List, Optional, Union
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, ReplyKeyboardMarkup


def split_long_message(text: str, max_length: int = 4096) -> List[str]:
    """Split a long message into chunks that fit Telegram's message limit."""
    if len(text) <= max_length:
        return [text]

    chunks = []
    current_chunk = ""

    paragraphs = text.split('\n\n')

    for para in paragraphs:
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
                        words = sentence.split()
                        for word in words:
                            if len(current_chunk) + len(word) + 1 > max_length:
                                if current_chunk:
                                    chunks.append(current_chunk.strip())
                                    current_chunk = word
                                else:
                                    chunks.append(word[:max_length])
                                    current_chunk = word[max_length:]
                            else:
                                current_chunk += (' ' if current_chunk else '') + word
                else:
                    current_chunk += sentence
        else:
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
    chunks = split_long_message(text, max_length)

    for i, chunk in enumerate(chunks):
        if i == 0:
            await message.answer(chunk, reply_markup=reply_markup)
        else:
            await message.answer(chunk)


async def edit_long_message(
    callback: CallbackQuery,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    max_length: int = 4096
) -> None:
    import logging
    from aiogram.exceptions import TelegramBadRequest

    logger = logging.getLogger(__name__)

    try:
        chunks = split_long_message(text, max_length)

        if len(chunks) == 1:
            try:
                await callback.message.edit_text(chunks[0], reply_markup=reply_markup)
                logger.info(f"Successfully edited message for callback {callback.data}")
            except TelegramBadRequest as e:
                error_message = str(e).lower()
                if "message is not modified" in error_message:
                    logger.debug(f"Message not modified (content unchanged) for callback {callback.data}: {e}")
                    if reply_markup is not None:
                        try:
                            await callback.message.edit_reply_markup(reply_markup=reply_markup)
                            logger.info(f"Updated reply markup for callback {callback.data}")
                        except Exception as markup_error:
                            logger.warning(f"Failed to update markup: {markup_error}, sending new message")
                            await callback.message.answer(chunks[0], reply_markup=reply_markup)
                else:
                    logger.error(f"TelegramBadRequest when editing message: {e}, trying to send new message instead")
                    await callback.message.answer(chunks[0], reply_markup=reply_markup)
            except Exception as e:
                logger.error(f"Failed to edit message: {e}, trying to send new message instead")
                await callback.message.answer(chunks[0], reply_markup=reply_markup)
        else:
            try:
                await callback.message.edit_text(chunks[0], reply_markup=reply_markup)
                logger.info(f"Successfully edited first chunk for callback {callback.data}")
            except TelegramBadRequest as e:
                error_message = str(e).lower()
                if "message is not modified" in error_message:
                    logger.debug(f"Message not modified (content unchanged) for callback {callback.data}: {e}")
                    if reply_markup is not None:
                        try:
                            await callback.message.edit_reply_markup(reply_markup=reply_markup)
                            logger.info(f"Updated reply markup for callback {callback.data}")
                        except Exception as markup_error:
                            logger.warning(f"Failed to update markup: {markup_error}, sending new message")
                            await callback.message.answer(chunks[0], reply_markup=reply_markup)
                else:
                    logger.error(f"TelegramBadRequest when editing message: {e}, sending all chunks as new messages")
                    await callback.message.answer(chunks[0], reply_markup=reply_markup)
            except Exception as e:
                logger.error(f"Failed to edit message: {e}, sending all chunks as new messages")
                await callback.message.answer(chunks[0], reply_markup=reply_markup)

            for chunk in chunks[1:]:
                await callback.message.answer(chunk)
    except Exception as e:
        logger.exception(f"Error in edit_long_message for callback {callback.data}: {e}")
        try:
            await callback.message.answer(text[:max_length], reply_markup=reply_markup)
        except Exception as e2:
            logger.exception(f"Failed to send fallback message: {e2}")
            raise


def is_question(text: str) -> bool:
    """Check if the text is a question."""
    if not text or not text.strip():
        return False

    text_lower = text.strip().lower()

    if text.strip().endswith('?'):
        return True

    question_words = [
        'что', 'как', 'где', 'когда', 'кто', 'почему', 'зачем',
        'какой', 'какая', 'какие', 'какое', 'сколько', 'откуда',
        'куда', 'чем', 'кому', 'чему', 'каким', 'какой', 'какую'
    ]

    words = text_lower.split()
    if words and words[0] in question_words:
        return True

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
