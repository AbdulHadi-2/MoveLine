# MoveLine Backend

MoveLine is a Django and Django REST Framework backend for a smart moving-service platform. It supports customers, drivers, workers, offices, vehicles, orders, AI item analysis, live tracking, chat, notifications, payments, ratings, and admin monitoring.

## Requirements

- Python 3.10+
- MySQL, PostgreSQL, or SQLite depending on local settings
- Redis for Celery and realtime infrastructure
- Docker optional, useful for Redis on Windows
- Firebase service account file for push notifications, kept out of Git

## Local Setup

1. Create and activate a virtual environment:

```powershell
python -m venv venv
venv\Scripts\activate
```

2. Install dependencies:

```powershell
pip install -r requirements.txt
```

3. Configure environment and local secrets:

Create a local `.env` file or update your local settings values. Do not commit secrets.

Important local values include:

```text
SECRET_KEY
DEBUG
DATABASE settings
EMAIL_HOST_USER
EMAIL_HOST_PASSWORD
STRIPE_SECRET_KEY
FIREBASE service account path
```

4. Run migrations:

```powershell
python manage.py makemigrations
python manage.py migrate
```

5. Create an admin user:

```powershell
python manage.py createsuperuser
```

6. Run the development server:

```powershell
python manage.py runserver
```

For WebSocket support with Channels, run Daphne:

```powershell
daphne -b 127.0.0.1 -p 8000 moveline.asgi:application
```

## Redis and Celery

Run Redis with Docker:

```powershell
docker run --name moveline-redis -p 6379:6379 -d redis:7
```

Run Celery worker on Windows:

```powershell
celery -A moveline worker -l info --pool=solo
```

Run Celery Beat:

```powershell
celery -A moveline beat -l info
```

## Windows Helper Scripts

```powershell
.\scripts\windows\start-redis.ps1
.\scripts\windows\start-daphne.ps1
.\scripts\windows\start-celery-worker.ps1
.\scripts\windows\start-celery-beat.ps1
.\scripts\windows\start-nginx.ps1
.\scripts\windows\reload-nginx.ps1
```

## Main API Areas

### Authentication

```text
POST /api/auth/token/
POST /api/auth/token/refresh/
POST /api/auth/email-verification/verify/
POST /api/auth/email-verification/resend/
POST /api/auth/password-reset/
POST /api/auth/password-reset/verify/
POST /api/auth/password-reset/confirm/
POST /api/auth/password-reset/complete/
POST /api/auth/password-change/
```

### Users and Applicants

```text
GET/POST /api/users/
GET/POST /api/customers/
GET/POST /api/drivers/
GET/POST /api/workers/
GET/POST /api/offices/
POST /api/applicants/drivers/register/
POST /api/applicants/workers/register/
PATCH /api/admin/applicants/{drivers|workers}/{id}/schedule-interview/
POST /api/admin/applicants/{drivers|workers}/{id}/approve/
POST /api/admin/applicants/{drivers|workers}/{id}/reject/
```

### Orders

```text
GET/POST /api/orders/
GET /api/orders/my-orders/
GET /api/orders/my-driver-orders/
GET /api/orders/my-worker-orders/
POST /api/orders/estimate-price/
POST /api/orders/{id}/mark-delivered/
POST /api/orders/{id}/mark-available/
POST /api/orders/{id}/send-assignment-notification/
```

### AI Analyze

```text
POST /api/ai/analyze/
```

Use multipart form-data with `image` or repeated `images` fields.

### Tracking

```text
GET/POST /api/tracking/
GET /api/tracking-alerts/
GET /api/tracking-alerts/summary/
POST /api/tracking-alerts/{id}/driver-response/
POST /api/tracking-alerts/{id}/resolve/
```

Tracking WebSocket:

```text
ws://127.0.0.1:8000/ws/tracking/{order_id}/
```

### Chat

```text
GET /api/chat/orders/{order_id}/messages/
```

Chat WebSocket:

```text
ws://127.0.0.1:8000/ws/chat/{order_id}/
```

### Notifications

```text
POST /api/notifications/register-device/
GET /api/notifications/
POST /api/notifications/test/
```

### Ratings and Performance

```text
GET/POST /api/ratings/
GET /api/ratings/order-targets/{order_id}/
POST /api/ratings/rate-order/
GET /api/ratings/admin-order-ratings/
GET /api/performance-alerts/
POST /api/performance-alerts/{id}/resolve/
```

### Payments

```text
GET/POST /api/payments/
POST /api/payments/stripe/create-checkout-session/
POST /api/payments/stripe/create-order-checkout/
POST /api/payments/stripe/confirm-order-checkout/
POST /api/payments/paymera/initiate/
POST /api/payments/paymera/callback/
POST /api/payments/paymera/verify/
```

## Important Notes

The following files are intentionally ignored and must not be committed:

```text
.env
db.sqlite3
media/
staticfiles/
venv/
firebase-service-account.json
firebase-service-account-*.json
celerybeat-schedule*
deploy/nginx/logs/
deploy/nginx/temp/
```

For a detailed project flow and API documentation, see:

```text
PROJECT_FLOW_AND_APIS.md
TECH_STACK_EXPLANATION.md
SMART_TRACKING_MONITORING.md
WORKER_COUNT_LOGIC.md
RUN_WINDOWS.md
```
