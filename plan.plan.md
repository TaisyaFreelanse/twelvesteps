# План доработок: Улучшение фреймов + Vector Store (Фаза 1)

## Статус: ✅ ВЫПОЛНЕНО

## Цель

1. ✅ Расширить структуру Frame для поддержки расширенного фрейминга
2. ✅ Обновить классификацию для возврата расширенных полей
3. ✅ Начать интеграцию Vector Store для семантического поиска

---

## Часть 1: Улучшение структуры Frame

### 1.1 Создать миграцию Alembic для новых полей ✅

**Файл:** `twelvesteps/alembic/versions/j7a8b9c0d1e2_add_extended_frame_fields.py` ✅ СОЗДАН

**Новые поля в таблице `frames`:**

- `thinking_frame` (VARCHAR(255), nullable) - "импульс + петля", "самоосуждение"
- `level_of_mind` (INTEGER, nullable) - 40, 60, 50
- `memory_type` (VARCHAR(50), nullable) - "volatile", "dynamic", "stable"
- `target_block` (JSON, nullable) - {"main": "12 шагов", "sub": "Тяга"}
- `action` (VARCHAR(255), nullable) - "trigger_strategy", "activate_emergency"
- `strategy_hint` (TEXT, nullable) - "Предложить вернуться к шагу 1"

### 1.2 Обновить модель Frame ✅

**Файл:** `twelvesteps/db/models.py` ✅ ОБНОВЛЕН

Добавить новые поля в класс `Frame`:

```python
thinking_frame: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
level_of_mind: Mapped[Optional[int]] = mapped_column(nullable=True)
memory_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
target_block: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
action: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
strategy_hint: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
```

### 1.3 Обновить промпт классификации ✅

**Файл:** `twelvesteps/llm/prompts/classify.json` ✅ ОБНОВЛЕН

Расширить `output_schema` для возврата расширенных полей:

```json

{

"output_schema": {

"parts": [

{

"part": "string",

"blocks": ["string"],

"emotion": "string",

"importance": "integer",

"thinking_frame": "string (optional)",

"level_of_mind": "integer (optional, 0-100)",

"memory_type": "string (optional: volatile, dynamic, stable)",

"target_block": {

"main": "string (optional)",

"sub": "string (optional)"

},

"action": "string (optional)",

"strategy_hint": "string (optional)"

}

],

"metadata": {

"intention": "string (optional)",

"urgency": "string (optional: низкая, средняя, высокая)",

"cognitive_mode": "string (optional)",

"suggested_response_mode": "string (optional)"
}
}
```

**Задачи:**
- [x] Обновить `classify.json` с новыми полями ✅
- [x] Обновить `ClassificationResult` модель в `openai_provider.py` ✅
- [x] Обновить `FrameRepository.add_frame()` для сохранения новых полей ✅

### 1.4 Обновить модели данных ✅

**Файл:** `twelvesteps/llm/openai_provider.py` ✅ ОБНОВЛЕН

Обновить классы `Part` и `ClassificationResult`:
- [x] Добавлены новые поля в `Part` ✅
- [x] Создан класс `ClassificationMetadata` ✅
- [x] Обновлен `ClassificationResult` с полем `metadata` ✅

### 1.5 Обновить FrameRepository ✅

**Файл:** `twelvesteps/repositories/FrameRepository.py` ✅ ОБНОВЛЕН

- [x] Обновлен метод `add_frame()` для сохранения новых полей ✅
- [x] Добавлен метод `get_frames_by_ids()` для семантического поиска ✅

### 1.6 Обновить chat_service для использования новых полей ✅

**Файл:** `twelvesteps/core/chat_service.py` ✅ ОБНОВЛЕН

- [x] Обновлено сохранение frames с новыми полями ✅
- [x] Добавлено создание embeddings при сохранении frames ✅
- [x] Добавлен семантический поиск в `handle_chat()` ✅
- [x] Объединение результатов блок-поиска и семантического поиска ✅

---

## Часть 2: Vector Store интеграция (начало)

### 2.1 Добавить зависимость ChromaDB ✅

**Файл:** `twelvesteps/requirements.txt` ✅ ОБНОВЛЕН

- [x] Добавлен `chromadb>=0.4.0` ✅

### 2.2 Создать сервис VectorStore ✅

**Файл:** `twelvesteps/services/vector_store.py` ✅ СОЗДАН

- [x] Создан класс `VectorStoreService` ✅
- [x] Реализованы методы для работы с frames ✅
- [x] Реализованы методы для работы с GPT-SELF core ✅

### 2.3 Интегрировать embeddings в сохранение frames ✅

**Файл:** `twelvesteps/core/chat_service.py` ✅ ОБНОВЛЕН

- [x] Добавлено создание embeddings через OpenAI API ✅
- [x] Добавлено сохранение в vector store при создании frame ✅
- [x] Обработка ошибок при создании embeddings ✅

### 2.4 Добавить семантический поиск в handle_chat ✅

**Файл:** `twelvesteps/core/chat_service.py` ✅ ОБНОВЛЕН

- [x] Добавлен семантический поиск по сообщению пользователя ✅
- [x] Объединение результатов блок-поиска и семантического поиска ✅
- [x] Дедупликация и сортировка результатов ✅

---

## Статус выполнения

### Выполнено:
- ✅ Часть 1: Улучшение структуры Frame (все задачи)
- ✅ Часть 2: Vector Store интеграция (начало - все задачи)

### Осталось:
- [ ] Создать скрипт инициализации vector store для GPT-SELF core (опционально)
- [ ] Тестирование работы семантического поиска
- [ ] Применение миграции БД

---

## Следующие шаги

1. Применить миграцию: `alembic upgrade head`
2. Пересобрать контейнер backend
3. Протестировать создание frames с новыми полями
4. Протестировать семантический поиск