## Fitness Mini App API

Backend API для фитнес-приложения в Telegram Mini App.

### Функционал

- **Аутентификация** через Telegram WebApp
- **Профиль пользователя** — анкета, настройки
- **Тренировки** — AI-генерация, история, оценки, статистика
- **Питание** — анализ фото еды, учёт КБЖУ, планы питания

### Требования

- Python 3.11+
- Supabase (PostgreSQL)
- OpenAI API
- Redis (опционально, для кэширования)

### Установка

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Переменные окружения

Создайте файл `.env`:

```env
# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-supabase-anon-key

# Telegram
TELEGRAM_BOT_TOKEN=your-bot-token

# JWT
JWT_SECRET_KEY=your-secret-key-min-32-chars
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=10080

# OpenAI
OPENAI_API_KEY=sk-your-openai-key

# Redis (опционально)
REDIS_URL=redis://localhost:6379/0

# Sentry (опционально)
SENTRY_DSN=https://your-sentry-dsn

# App
DEBUG=false
LOG_LEVEL=INFO
LOG_JSON=false

# Rate limiting
RATE_LIMIT_PER_MINUTE=60
RATE_LIMIT_AI_PER_MINUTE=10
```

### Запуск

```bash
source venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### API документация

После запуска доступна по адресу: http://localhost:8000/docs

### Эндпоинты

| Метод | Путь | Описание |
|-------|------|----------|
| POST | /auth/telegram | Авторизация через Telegram |
| GET | /users/me | Профиль пользователя |
| PATCH | /users/me/profile | Обновить профиль |
| GET | /workouts | Список тренировок |
| POST | /workouts/generate | Сгенерировать тренировку |
| GET | /nutrition/meals | Список приёмов пищи |
| POST | /nutrition/meals/analyze | Анализ фото еды |
| GET | /nutrition/recommendations | Рекомендации КБЖУ |

### Health Check

- `/health` — базовая проверка
- `/health/detailed` — проверка БД и Redis
