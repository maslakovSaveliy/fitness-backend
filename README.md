### Зависимости и окружение

python3 -m venv venv

./venv/bin/pip install -r requirements.txt


### Запуск

source venv/bin/activate && python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000