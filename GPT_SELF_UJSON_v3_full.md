# ☁️ GPT-SELF DATA FRAME (UJSON v3.0 — Расширенный)
Структура данных состояния и смыслов пользователя в GPT-SELF без жёсткой привязки к ядру.

---

## 🧠 JSON-структура (UJSON)
```json
{
  "user": {
    "id": "string",
    "role": "dependent | sponsor | admin",
    "sobriety_date": "YYYY-MM-DD",
    "current_step": "1–12",
    "last_active": "ISO8601 timestamp",
    "sponsor_ids": ["user_id_1", "user_id_2"],
    "relapse_dates": ["YYYY-MM-DD"],
    "custom_fields": {
      "goals": ["string"],
      "important_people": ["string"],
      "support_format": "chat | video | audio | mixed"
    }
  },
  "state": {
    "recent_messages": [
      {
        "timestamp": "ISO8601",
        "text": "string",
        "tags": ["emotion", "trigger", "pattern"]
      }
    ],
    "daily_snapshot": {
      "emotions": ["guilt", "fear", "hope"],
      "triggers": ["conflict", "loneliness"],
      "actions": ["avoidance", "reflection"],
      "health": ["fatigue", "appetite_loss"]
    },
    "active_blocks": ["step_5", "craving", "thinking", "group", "evening"],
    "pending_topics": ["resentment", "shame_loop"],
    "group_signals": ["resistance", "alignment", "peer_pressure"]
  },
  "frames": {
    "confirmed": ["control", "isolation", "shame"],
    "candidates": ["lack_of_meaning", "abandonment"],
    "tracking": {
      "repetition_count": {
        "shame": 4,
        "abandonment": 2
      },
      "min_to_confirm": 3
    },
    "archetypes": ["victim", "rescuer", "judge"],
    "meta_flags": ["loop_detected", "frame_shift", "identity_conflict"]
  },
  "qa_status": {
    "last_prompt_included": true,
    "trace_ok": true,
    "open_threads": 0,
    "rebuild_required": true
  },
  "meta": {
    "metasloy_signals": ["disintegration_phase", "meaning_search"],
    "prompt_revision_history": 5,
    "time_zones": ["UTC+3"],
    "language": "ru",
    "data_flags": {
      "encrypted": true,
      "anonymized": true,
      "retention_days": 60
    }
  },
  "tracker_summary": {
    "thinking": ["loop", "rigidity", "self-blame"],
    "feeling": ["guilt", "anger", "gratitude"],
    "behavior": ["avoidance", "engagement"],
    "relationships": ["withdrawal", "dependence"],
    "health": ["insomnia", "headache"]
  }
}
```

---

## 📘 Краткое объяснение блоков

- `user`: расширенный профиль — включает ID, ролевую модель, даты рецидивов, цели и формат поддержки.
- `state`: оперативное состояние, включая эмоции, действия, сообщения, триггеры, групповые влияния.
- `frames`: автоматическое и пользовательское фрейм-отслеживание, архетипы, логика подтверждения.
- `qa_status`: статус соответствия внутренним проверкам и сборкам промпта.
- `meta`: системные поля, вкл. сигнал от MetaSloy, политику хранения, язык, зону.
- `tracker_summary`: композит дневного/недельного наблюдения для анализа динамики.

---

## 📂 Источники для сборки (без ядра)

1. `GPT-SELF Чистый ядро фреймы трекеры` — фреймы, трекеры, логика анализа.
2. `ТЗ MVP 12 шагов` — структура профиля, роли, шаги, память.
3. `QA-промпты и команды` — логика трассировки, незакрытых веток, rebuild.
4. `MetaSloy` — динамика фаз, кризисы, смена восприятия.
5. `Логика шагов и блоков` — структура активных блоков.
6. `Дополнительно`: принципы защиты данных, наблюдение, расширение профиля.

---

Готово для передачи в команду разработки и интеграции в backend. Подходит как формат хранения состояния, промптов, пользовательских тем, сигналов и трекеров.