# Удаление секретов из истории Git

GitHub заблокировал push из-за обнаружения OpenAI API ключа в файле `backend.env`.

## Решение

Файлы `backend.env` и `telegram.env` уже добавлены в `.gitignore`, но они были закоммичены ранее.

### Вариант 1: Использовать BFG Repo-Cleaner (рекомендуется)

1. Скачайте BFG: https://rtyley.github.io/bfg-repo-cleaner/
2. Выполните:
   ```bash
   java -jar bfg.jar --delete-files backend.env
   java -jar bfg.jar --delete-files telegram.env
   git reflog expire --expire=now --all
   git gc --prune=now --aggressive
   git push --force
   ```

### Вариант 2: Использовать git filter-repo

```bash
pip install git-filter-repo
git filter-repo --path backend.env --path telegram.env --invert-paths
git push --force
```

### Вариант 3: Создать новый репозиторий (если история не важна)

Если история коммитов не критична, можно:
1. Создать новый репозиторий
2. Скопировать файлы (кроме .env)
3. Сделать initial commit

## Важно

После удаления секретов из истории:
1. **Смените все API ключи и токены**, которые были в репозитории
2. OpenAI API ключ нужно отозвать и создать новый
3. Telegram Bot токен нужно отозвать и создать новый

## Файлы-примеры

Созданы файлы:
- `backend.env.example` - шаблон для backend.env
- `telegram.env.example` - шаблон для telegram.env

Эти файлы можно безопасно коммитить в репозиторий.

