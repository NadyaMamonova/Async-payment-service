FROM python:3.12.10-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

COPY requirements.txt .

RUN python -m pip wheel \
    --wheel-dir=/wheels \
    --requirement=requirements.txt


FROM python:3.12.10-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN groupadd --system app \
    && useradd \
        --system \
        --gid app \
        --create-home \
        --home-dir /home/app \
        app

WORKDIR /app

COPY requirements.txt .
COPY --from=builder /wheels /wheels

RUN python -m pip install \
    --no-index \
    --find-links=/wheels \
    --requirement=requirements.txt \
    && rm -rf /wheels

COPY --chown=app:app . .

USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host=0.0.0.0", "--port=8000"]