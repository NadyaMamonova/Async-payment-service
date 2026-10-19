# Асинхронный сервис обработки платежей

Микросервис принимает запросы на оплату, сохраняет платежи в PostgreSQL, асинхронно обрабатывает их через эмулятор платёжного шлюза и уведомляет клиента о результате через подписанный webhook.

Проект реализует:

- FastAPI и Pydantic v2;
- асинхронный SQLAlchemy 2.0;
- PostgreSQL;
- RabbitMQ и FastStream;
- Transactional Outbox;
- идемпотентное создание платежей;
- повторные попытки с exponential backoff и jitter;
- Dead Letter Queue;
- HMAC-подпись webhook;
- SSRF-защиту webhook URL;
- Alembic-миграции;
- Docker Compose;
- unit-тесты критичной бизнес-логики.


## Запуск

### Требования

- Docker Desktop
- Docker Compose v2

### Настройка окружения

Скопировать пример конфигурации:

```bash
cp .env.example .env
```

Для PowerShell:

```powershell
Copy-Item -LiteralPath ".env.example" -Destination ".env"
```

### Запуск сервисов

```bash
docker compose up --build -d
```

Проверка:

```bash
docker compose ps
```

Ожидаемые сервисы:

- `postgres` — healthy;
- `rabbitmq` — healthy;
- `migrate` — завершён с кодом `0`;
- `api` — healthy;
- `outbox-publisher` — запущен;
- `consumer` — запущен;
- `mock-webhook` — healthy.

Логи:

```bash
docker compose logs -f api outbox-publisher consumer mock-webhook
```

## Доступные интерфейсы

- API: http://localhost:8000
- Swagger UI: http://localhost:8000/docs
- OpenAPI: http://localhost:8000/openapi.json
- RabbitMQ Management: http://localhost:15672
- Mock webhook: http://localhost:8001/webhook

Учётные данные RabbitMQ задаются переменными:

```dotenv
RABBITMQ_DEFAULT_USER
RABBITMQ_DEFAULT_PASS
```

## Аутентификация

Платёжные эндпоинты требуют заголовок:

```text
X-API-Key: <API_KEY>
```

`API_KEY` задаётся в `.env`.

Health-check эндпоинты намеренно не требуют API-ключ: они для Docker и оркестраторов


## Архитектура

```text
Клиент
  │
  │ POST /api/v1/payments
  ▼
FastAPI
  │
  │ одна транзакция PostgreSQL
  ├── payments
  └── outbox
        │
        ▼
Outbox publisher
        │ publisher confirm
        ▼
RabbitMQ: payments.new
        │
        ▼
Consumer
  ├── эмулятор платёжного шлюза
  ├── обновление статуса в PostgreSQL
  └── HMAC webhook
        │
        ├── 2xx → ACK
        ├── временная ошибка → retry queue
        └── 3-я ошибка → payments.dlq
```

API не обращается к RabbitMQ в транзакции HTTP-запроса. Сначала платёж и outbox-событие атомарно сохраняются в PostgreSQL. Отдельный publisher доставляет событие в RabbitMQ.

Это исключает ситуацию, когда платёж записан в БД, но событие потеряно из-за недоступности брокера.

## Технологии

- Python 3.12
- FastAPI
- Pydantic v2
- SQLAlchemy 2.0 async
- asyncpg
- PostgreSQL 16
- RabbitMQ 3.13
- FastStream
- Alembic
- httpx
- Docker и Docker Compose
- pytest, Ruff, mypy


## Структура проекта

```text
app/
├── api/                    # HTTP-эндпоинты, middleware, обработчики ошибок
├── application/
│   ├── services/           # Прикладные сценарии
│   └── idempotency.py      # Канонизация и fingerprint запросов
├── core/                   # Конфигурация, enum, исключения, логирование
├── db/
│   ├── models/             # SQLAlchemy-модели
│   ├── repositories/       # Доступ к данным
│   └── session.py
├── messaging/              # RabbitMQ broker и topology
├── schemas/                # Pydantic-контракты
└── workers/
    ├── outbox_publisher.py
    └── payment_consumer.py

migrations/                 # Alembic-миграции
mock_webhook/               # Локальный HMAC webhook receiver
tests/                      # Unit-тесты и фикстуры
```

## API

### Создание платежа

```http
POST /api/v1/payments
```

Обязательные заголовки:

```text
X-API-Key
Idempotency-Key
Content-Type: application/json
```

Пример:

```bash
curl -i \
  -X POST http://localhost:8000/api/v1/payments \
  -H "X-API-Key: local-development-api-key-change-me" \
  -H "Idempotency-Key: order-42-payment-1" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": "1500.50",
    "currency": "RUB",
    "description": "Payment for order 42",
    "metadata": {
      "order_id": "42",
      "customer_id": "17"
    },
    "webhook_url": "http://mock-webhook:8001/webhook"
  }'
```

Ответ:

```http
HTTP/1.1 202 Accepted
```

```json
{
  "payment_id": "7e139644-cb3a-4e4e-a381-2c7b8245a010",
  "status": "pending",
  "created_at": "2026-10-19T13:36:54.041832Z"
}
```

Сумма принимается как JSON number или строка, проверяется через `Decimal` и ограничивается двумя знаками после запятой.

Поддерживаемые валюты:

- `RUB`
- `USD`
- `EUR`

### Получение платежа

```bash
curl \
  http://localhost:8000/api/v1/payments/7e139644-cb3a-4e4e-a381-2c7b8245a010 \
  -H "X-API-Key: local-development-api-key-change-me"
```

Пример ответа:

```json
{
  "payment_id": "7e139644-cb3a-4e4e-a381-2c7b8245a010",
  "amount": "1500.50",
  "currency": "RUB",
  "description": "Payment for order 42",
  "metadata": {
    "order_id": "42",
    "customer_id": "17"
  },
  "status": "succeeded",
  "webhook_url": "http://mock-webhook:8001/webhook",
  "created_at": "2026-10-19T13:36:54.041832Z",
  "updated_at": "2026-10-19T13:36:57.368487Z",
  "processed_at": "2026-10-19T13:36:57.340265Z",
  "webhook_delivered_at": "2026-10-19T13:36:57.368487Z"
}
```

Денежная сумма возвращается строкой, чтобы клиент не потерял точность при преобразовании JSON number в `float`

## Идемпотентность

`Idempotency-Key` глобально уникален

Для тела запроса вычисляется SHA-256 fingerprint канонического представления:

- сумма нормализуется до двух знаков
- enum преобразуются в строковые значения
- ключи JSON сортируются
- учитываются сумма, валюта, описание, metadata и webhook URL

Повтор с тем же ключом и эквивалентным телом:

- возвращает `202`
- возвращает тот же `payment_id`
- не создаёт второй платёж
- не создаёт второе outbox-событие

Тот же ключ с другим телом возвращает:

```http
HTTP/1.1 409 Conflict
```

```json
{
  "detail": {
    "code": "idempotency_conflict",
    "message": "Idempotency key was already used with a different request"
  }
}
```

Уникальное ограничение PostgreSQL защищает от конкурентных запросов с одинаковым ключом.

## Transactional Outbox

Платёж и событие `payment.created` создаются в одной транзакции PostgreSQL

Outbox publisher:

1. выбирает готовую пачку событий
2. использует lease с `claim_id` и `claimed_until`
3. применяет блокировку `FOR UPDATE SKIP LOCKED`
4. публикует события с publisher confirms
5. только после подтверждения RabbitMQ устанавливает `published_at`
6. при ошибке сохраняет её и назначает следующую попытку с backoff и jitter

Возможна повторная публикация, если процесс завершится после подтверждения RabbitMQ, но до обновления outbox. Поэтому система использует at-least-once, а consumer должен быть идемпотентным

## RabbitMQ topology

Основной exchange:

```text
payments.events
```

Основная очередь:

```text
payments.new
```

Dead-letter exchange:

```text
payments.dlx
```

Dead-letter queue:

```text
payments.dlq
```

Основная очередь и DLQ используют quorum queue

Retry реализован через отдельные durable classic queues с TTL:

```text
payments.retry.attempt-1.800ms
payments.retry.attempt-1.1000ms
payments.retry.attempt-1.1200ms

payments.retry.attempt-2.1600ms
payments.retry.attempt-2.2000ms
payments.retry.attempt-2.2400ms
```

После истечения TTL сообщение возвращается в `payments.new`

## Retry и jitter

Всего разрешено три попытки обработки.

Базовая задержка вычисляется как:

```text
base_delay × 2^(attempt - 1)
```

Jitter выбирает один из вариантов:

```text
-20%, без изменения, +20%
```

При базовой задержке `1 секунда` получаются:

- после первой ошибки: `0.8`, `1.0` или `1.2` секунды
- после второй ошибки: `1.6`, `2.0` или `2.4` секунды
- после третьей ошибки сообщение отправляется в `payments.dlq`

Jitter уменьшает одновременную повторную нагрузку на внешний сервис после его восстановления

Исходное сообщение подтверждается только после успешной публикации retry-сообщения с publisher confirm. Это предотвращает потерю события.

## Webhook

Пример payload:

```json
{
  "event_id": "46b1e6ec-56b1-5dc7-a804-623bd089ee42",
  "event": "payment.processed",
  "event_version": 1,
  "payment_id": "91d4cc65-cb78-4237-9f14-cee9afedbda9",
  "status": "succeeded",
  "amount": "2500.75",
  "currency": "EUR",
  "processed_at": "2026-10-19T13:45:13.625917Z",
  "metadata": {
    "scenario": "two-failures-then-success"
  }
}
```

Заголовки:

```text
X-Webhook-Id
X-Webhook-Timestamp
X-Webhook-Signature
```

Подпись:

```text
HMAC-SHA256(secret, timestamp + "." + raw_request_body)
```

Формат:

```text
X-Webhook-Signature: v1=<hex digest>
```

Получатель должен:

1. проверить допустимый возраст timestamp
2. вычислить HMAC по исходным байтам тела
3. сравнить подписи через constant-time comparison
4. проверить `event_id`
5. обрабатывать повторный `event_id` идемпотентно

`event_id` webhook формируется детерминированно, поэтому повторная доставка имеет тот же идентификатор

## Классификация webhook-ответов

Успех:

```text
любой HTTP 2xx
```

Временные ошибки:

```text
408, 425, 429, 5xx, timeout, network error, DNS error
```

Постоянные ошибки:

```text
остальные 4xx
```

Они сразу направляют сообщение в DLQ, потому что повтор без изменения запроса не устранит проблему

## SSRF-защита

Перед отправкой webhook сервис:

- разрешает только HTTP/HTTPS
- требует HTTPS для публичных адресов
- запрещает credentials в URL
- запрещает fragment
- запрещает нестандартный публичный порт
- разрешает DNS
- проверяет все полученные IP-адреса
- блокирует loopback, private, link-local и другие non-global адреса
- не следует HTTP redirects

`mock-webhook` включён в явный локальный allowlist только для Docker Compose

## Эмулятор платёжного шлюза

Эмулятор:

- ждёт от 2 до 5 секунд
- возвращает примерно 90% `succeeded`
- возвращает примерно 10% `failed`
- использует детерминированный результат по `payment_id`

Детерминированность важна при повторной доставке: один платёж не может сначала стать успешным, а при redelivery - неуспешным.

## Формат ошибок

API использует единый контракт:

```json
{
  "detail": {
    "code": "validation_error",
    "message": "Request validation failed",
    "details": []
  }
}
```

Основные коды:

- `authentication_failed`
- `validation_error`
- `payment_not_found`
- `idempotency_conflict`
- `dependency_unavailable`
- `internal_error`

## Health checks

Liveness:

```text
GET /health/live
```

Readiness с проверкой PostgreSQL:

```text
GET /health
```

## Миграции

Миграции автоматически выполняются сервисом `migrate`

Ручной запуск:

```bash
docker compose run --rm migrate
```

Текущая head-миграция:

```bash
alembic heads
```

## Тесты и статический анализ

Создание локального окружения:

```bash
python -m venv .venv
```

Установка:

```bash
python -m pip install -r requirements.txt
```

Проверки:

```bash
ruff check app mock_webhook tests
mypy app mock_webhook tests
pytest -m "not integration"
```

Тесты покрывают:

- нормализацию Decimal
- отклонение некорректных сумм
- канонический fingerprint
- детерминированность шлюза
- HMAC-подпись
- защиту от изменения подписанного тела
- timestamp webhook
- классификацию HTTP-ответов

## Демонстрация retry

В `.env`:

```dotenv
MOCK_WEBHOOK_FAILURES_BEFORE_SUCCESS=2
MOCK_WEBHOOK_FAILURE_STATUS=503
```

Применить:

```bash
docker compose up -d --force-recreate mock-webhook
```

Первые две доставки получат `503`, третья — `204`

Проверить:

```bash
docker compose logs -f consumer mock-webhook
```

## Демонстрация DLQ

В `.env`:

```dotenv
MOCK_WEBHOOK_FAILURES_BEFORE_SUCCESS=100
MOCK_WEBHOOK_FAILURE_STATUS=503
```

После трёх попыток:

```bash
docker compose exec -T rabbitmq \
  rabbitmqctl list_queues \
  name messages_ready messages_unacknowledged
```

В `payments.dlq` появится сообщение.

После демонстрации следует вернуть:

```dotenv
MOCK_WEBHOOK_FAILURES_BEFORE_SUCCESS=0
```

## Остановка

Остановить контейнеры:

```bash
docker compose down
```

Удалить контейнеры вместе с локальными данными:

```bash
docker compose down -v
```

`down -v` удаляет PostgreSQL и RabbitMQ volumes и должен применяться только тогда, когда локальные данные больше не нужны.

## Production-ограничения

Проект является тестовым сервисом. Для production дополнительно потребуются:

- secret manager вместо `.env`
- полноценная клиентская аутентификация и авторизация вместо статического ключа
- TLS между сервисами
- реальный платёжный провайдер
- метрики, tracing и alerting
- административный процесс анализа и повторной обработки DLQ
- ротация HMAC-секретов с идентификаторами ключей
- rate limiting
- централизованное хранилище логов
- отдельный deployment job для миграций
- горизонтальное масштабирование API, publisher и consumer
- разделение runtime- и development-зависимостей, например на
  `requirements.txt` и `requirements-dev.txt`, чтобы в production-образ
  не попадали `pytest`, `mypy`, `ruff` и другие инструменты разработки
- закрытие внешнего доступа к портам PostgreSQL и RabbitMQ: в production
  они должны быть доступны только из внутренней сети
- удаление `mock-webhook` из production-развёртывания
- независимые настройки ресурсов, реплик и политики перезапуска для API,
  Outbox publisher и consumer
- резервное копирование PostgreSQL и мониторинг размера outbox и DLQ