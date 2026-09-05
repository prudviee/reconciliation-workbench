FROM python:3.12.14-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements/runtime.lock requirements/runtime.lock
RUN python -m pip install --no-cache-dir -r requirements/runtime.lock

COPY . .

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
