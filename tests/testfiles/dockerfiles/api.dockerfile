FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi[standard] uvicorn

COPY api.py /app/api.py

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]