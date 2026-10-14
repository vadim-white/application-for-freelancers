# Gateway Service (gateway-service)

1. Скопируйте .env.example -> .env и убедитесь, что SECRET_KEY совпадает с auth-service.
2. Установите зависимостии и запустите:

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

3. Подразумевается, что auth-service (8001), task-service (8002) и time-service (8003) уже запущены.
4. Health-check: GET http://127.0.0.1:8000/health
