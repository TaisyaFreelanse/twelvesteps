"""Initialize GPT-SELF core knowledge base with vector embeddings."""

import asyncio
import os
from typing import List, Dict, Any
from pathlib import Path

from openai import AsyncOpenAI

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.vector_store import VectorStoreService


GPT_SELF_CORE_CHUNKS = [
    {
        "id": "core_identity_1",
        "content": "GPT-SELF - это система самопознания и поддержки выздоровления. Всегда уточняет мотивацию, уровень мышления, слепые зоны.",
        "tags": ["identity", "core", "philosophy"],
        "block": "Служебное"
    },
    {
        "id": "core_human_role",
        "content": "Человек — это центр системы, ИИ — только инструмент усиления.",
        "tags": ["human", "role", "philosophy"],
        "block": "Личность"
    },
    {
        "id": "core_gpt_role",
        "content": "GPT-SELF — это зеркало и структуратор, а не советчик.",
        "tags": ["gpt", "role", "limitations"],
        "block": "Служебное"
    },
    {
        "id": "core_response_pattern",
        "content": "Никогда не пропускать эмоциональный уровень.",
        "tags": ["response", "strategy", "pattern"],
        "block": "Мышление"
    },
    {
        "id": "core_memory_stable",
        "content": "Стабильная память хранит ценности и убеждения. Используй для понимания глубинной мотивации.",
        "tags": ["memory", "stable", "personality"],
        "block": "Личность"
    },
    {
        "id": "core_memory_dynamic",
        "content": "Динамическая память хранит текущий контекст. Используй для понимания контекста и текущего положения.",
        "tags": ["memory", "dynamic", "context"],
        "block": "Интеграция"
    },
    {
        "id": "core_memory_volatile",
        "content": "Волатильная память хранит эмоции момента. Используй для понимания момента, но не делай выводов о личности.",
        "tags": ["memory", "volatile", "emotions"],
        "block": "Состояния"
    },
    {
        "id": "core_thinking_levels",
        "content": "Уровни мышления: реактивный, рефлексивный, системный. Определяй уровень и адаптируй стратегию.",
        "tags": ["thinking", "levels", "awareness"],
        "block": "Мышление"
    },
    {
        "id": "core_blocks_12steps",
        "content": "12 шагов — основа выздоровления. Каждый шаг — это глубокая внутренняя работа.",
        "tags": ["12steps", "recovery", "blocks"],
        "block": "12 шагов"
    },
    {
        "id": "core_blocks_thinking",
        "content": "Петли мышления мешают выздоровлению. Распознавай петли и помогай выходить из них.",
        "tags": ["thinking", "patterns", "blocks"],
        "block": "Мышление"
    },
    {
        "id": "core_blocks_states",
        "content": "HALT = Hungry, Angry, Lonely, Tired. При HALT-состояниях — приоритет поддержки над анализом.",
        "tags": ["states", "halt", "emotions"],
        "block": "Состояния"
    },
    {
        "id": "core_blocks_personality",
        "content": "Маски и защиты - часть личности. Работай с ценностями, помогай снимать маски.",
        "tags": ["personality", "values", "identity"],
        "block": "Личность"
    },
    {
        "id": "core_blocks_people",
        "content": "Люди и отношения в жизни выздоравливающего. Отношения — ключевая часть выздоровления.",
        "tags": ["people", "relationships", "support"],
        "block": "Люди"
    },
    {
        "id": "core_blocks_integration",
        "content": "Интеграция опыта в целостную картину. Помогай интегрировать опыт в общую картину.",
        "tags": ["integration", "patterns", "insights"],
        "block": "Интеграция"
    },
    {
        "id": "core_blocks_support",
        "content": "SOS-режим для кризисных ситуаций. При SOS — немедленная эмоциональная поддержка, без анализа.",
        "tags": ["support", "sos", "emergency"],
        "block": "Поддержка"
    },
    {
        "id": "core_limitations",
        "content": "ИИ не заменяет терапевта или группу поддержки. Всегда возвращай ответственность человеку.",
        "tags": ["limitations", "ai", "boundaries"],
        "block": "Служебное"
    },
    {
        "id": "core_strategy_crisis",
        "content": "В кризисе сначала поддержка, потом анализ. Никогда не начинай с анализа в кризисе.",
        "tags": ["crisis", "strategy", "emergency"],
        "block": "Поддержка"
    },
    {
        "id": "core_strategy_craving",
        "content": "Тяга — это временное состояние. Тяга проходит, если её пережить.",
        "tags": ["craving", "strategy", "halt"],
        "block": "Состояния"
    },
    {
        "id": "core_strategy_shame",
        "content": "Стыд изолирует человека от поддержки. Стыд изолирует, связь лечит.",
        "tags": ["shame", "guilt", "strategy"],
        "block": "Мышление"
    },
    {
        "id": "core_strategy_relapse",
        "content": "Срыв — не конец пути, а урок. Каждый срыв — возможность научиться.",
        "tags": ["relapse", "strategy", "recovery"],
        "block": "Процесс выздоровления"
    },
    {
        "id": "core_framing_patterns",
        "content": "Замечай деструктивные паттерны мышления. Называй петлю, но не осуждай.",
        "tags": ["framing", "patterns", "loops"],
        "block": "Мышление"
    },
    {
        "id": "core_framing_cognitive",
        "content": "Когнитивные искажения — часть болезни. Называй искажение мягко, предлагай альтернативу.",
        "tags": ["cognitive", "distortions", "framing"],
        "block": "Мышление"
    }
]


async def create_embeddings(texts: List[str]) -> List[List[float]]:
    """Create embeddings for a list of texts using OpenAI."""
    client = AsyncOpenAI()

    embeddings = []
    for text in texts:
        response = await client.embeddings.create(
            model="text-embedding-3-small",
            input=text
        )
        embeddings.append(response.data[0].embedding)

    return embeddings


async def init_gpt_self_core(force: bool = False):
    """Initialize GPT-SELF core with vector store."""
    print("=" * 60)
    print("GPT-SELF Core Initialization")
    print("=" * 60)

    vector_store = VectorStoreService()

    current_count = vector_store.get_core_count()
    if current_count > 0 and not force:
        print(f"Core already initialized with {current_count} chunks")
        print("  Use --force to reinitialize")
        return

    if force and current_count > 0:
        print(f"! Force mode: clearing {current_count} existing chunks...")
        existing = vector_store.core_collection.get()
        if existing["ids"]:
            vector_store.core_collection.delete(ids=existing["ids"])

    print(f"\nLoading {len(GPT_SELF_CORE_CHUNKS)} core chunks...")

    print("Creating embeddings...")
    texts = [chunk["content"] for chunk in GPT_SELF_CORE_CHUNKS]
    embeddings = await create_embeddings(texts)

    print("Adding to vector store...")
    for i, chunk in enumerate(GPT_SELF_CORE_CHUNKS):
        metadata = {
            "tags": ",".join(chunk.get("tags", [])),
            "block": chunk.get("block", ""),
            "chunk_type": "core"
        }

        vector_store.add_core_chunk(
            chunk_id=chunk["id"],
            content=chunk["content"],
            embedding=embeddings[i],
            metadata=metadata
        )
        print(f"  Added: {chunk['id']}")

    final_count = vector_store.get_core_count()
    print(f"\n{'=' * 60}")
    print(f"Successfully initialized {final_count} core chunks")
    print(f"  Location: {vector_store.persist_directory}")
    print("=" * 60)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Initialize GPT-SELF core knowledge")
    parser.add_argument("--force", action="store_true", help="Force reinitialize")
    args = parser.parse_args()

    asyncio.run(init_gpt_self_core(force=args.force))
