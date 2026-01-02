"""

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
Всегда уточняет мотивацию, уровень мышления, слепые зоны.""",
        "tags": ["identity", "core", "philosophy"],
        "block": "Служебное"
    },

    {
        "id": "core_human_role",
Человек — это центр системы, ИИ — только инструмент усиления.""",
        "tags": ["human", "role", "philosophy"],
        "block": "Личность"
    },

    {
        "id": "core_gpt_role",
GPT-SELF — это зеркало и структуратор, а не советчик.""",
        "tags": ["gpt", "role", "limitations"],
        "block": "Служебное"
    },

    {
        "id": "core_response_pattern",
Никогда не пропускать эмоциональный уровень.""",
        "tags": ["response", "strategy", "pattern"],
        "block": "Мышление"
    },

    {
        "id": "core_memory_stable",
Используй для понимания глубинной мотивации.""",
        "tags": ["memory", "stable", "personality"],
        "block": "Личность"
    },
    {
        "id": "core_memory_dynamic",
Используй для понимания контекста и текущего положения.""",
        "tags": ["memory", "dynamic", "context"],
        "block": "Интеграция"
    },
    {
        "id": "core_memory_volatile",
Используй для понимания момента, но не делай выводов о личности.""",
        "tags": ["memory", "volatile", "emotions"],
        "block": "Состояния"
    },

    {
        "id": "core_thinking_levels",
Определяй уровень и адаптируй стратегию.""",
        "tags": ["thinking", "levels", "awareness"],
        "block": "Мышление"
    },

    {
        "id": "core_blocks_12steps",
Каждый шаг — это глубокая внутренняя работа.""",
        "tags": ["12steps", "recovery", "blocks"],
        "block": "12 шагов"
    },
    {
        "id": "core_blocks_thinking",
Распознавай петли и помогай выходить из них.""",
        "tags": ["thinking", "patterns", "blocks"],
        "block": "Мышление"
    },
    {
        "id": "core_blocks_states",
При HALT-состояниях — приоритет поддержки над анализом.""",
        "tags": ["states", "halt", "emotions"],
        "block": "Состояния"
    },
    {
        "id": "core_blocks_personality",
Работай с ценностями, помогай снимать маски.""",
        "tags": ["personality", "values", "identity"],
        "block": "Личность"
    },
    {
        "id": "core_blocks_people",
Отношения — ключевая часть выздоровления.""",
        "tags": ["people", "relationships", "support"],
        "block": "Люди"
    },
    {
        "id": "core_blocks_integration",
Помогай интегрировать опыт в общую картину.""",
        "tags": ["integration", "patterns", "insights"],
        "block": "Интеграция"
    },
    {
        "id": "core_blocks_support",
При SOS — немедленная эмоциональная поддержка, без анализа.""",
        "tags": ["support", "sos", "emergency"],
        "block": "Поддержка"
    },

    {
        "id": "core_limitations",
Всегда возвращай ответственность человеку.""",
        "tags": ["limitations", "ai", "boundaries"],
        "block": "Служебное"
    },

    {
        "id": "core_strategy_crisis",
Никогда не начинай с анализа в кризисе.""",
        "tags": ["crisis", "strategy", "emergency"],
        "block": "Поддержка"
    },
    {
        "id": "core_strategy_craving",
Тяга проходит, если её пережить.""",
        "tags": ["craving", "strategy", "halt"],
        "block": "Состояния"
    },
    {
        "id": "core_strategy_shame",
Стыд изолирует, связь лечит.""",
        "tags": ["shame", "guilt", "strategy"],
        "block": "Мышление"
    },
    {
        "id": "core_strategy_relapse",
Каждый срыв — возможность научиться.""",
        "tags": ["relapse", "strategy", "recovery"],
        "block": "Процесс выздоровления"
    },

    {
        "id": "core_framing_patterns",
Называй петлю, но не осуждай.""",
        "tags": ["framing", "patterns", "loops"],
        "block": "Мышление"
    },
    {
        "id": "core_framing_cognitive",
Называй искажение мягко, предлагай альтернативу.""",
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
    """
    print("=" * 60)
    print("GPT-SELF Core Initialization")
    print("=" * 60)

    vector_store = VectorStoreService()

    current_count = vector_store.get_core_count()
    if current_count > 0 and not force:
        print(f"✓ Core already initialized with {current_count} chunks")
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
        print(f"  ✓ Added: {chunk['id']}")

    final_count = vector_store.get_core_count()
    print(f"\n{'=' * 60}")
    print(f"✓ Successfully initialized {final_count} core chunks")
    print(f"  Location: {vector_store.persist_directory}")
    print("=" * 60)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Initialize GPT-SELF core knowledge")
    parser.add_argument("--force", action="store_true", help="Force reinitialize")
    args = parser.parse_args()

    asyncio.run(init_gpt_self_core(force=args.force))

