"""
Django settings for Move-Line project.
"""

import os
from pathlib import Path
from datetime import timedelta

from corsheaders.defaults import default_headers

BASE_DIR = Path(__file__).resolve().parent.parent


def load_env_file(path):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_file(BASE_DIR / ".env")

# -------------------------------------------------------------
# SECURITY
# -------------------------------------------------------------
SECRET_KEY = 'django-insecure-$$t0kv5ep8zxrhf^=%jev9g6*8ah_%jdeex)5(62zsb31n3k@%'
DEBUG = True
ALLOWED_HOSTS = ["*"]

# -------------------------------------------------------------
# APPLICATIONS
# -------------------------------------------------------------
INSTALLED_APPS = [
    # Django default apps
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party
    'rest_framework',
    'rest_framework.authtoken',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'channels',
    'corsheaders',

    # Local apps
    'users',
    'orders.apps.OrdersConfig',
    'vehicles',
    'payments',
    'tracking',
    'chat.apps.ChatConfig',
    'ai_analyze',
    'ratings',
    # 'notifications',  # optional
]

# -------------------------------------------------------------
# MIDDLEWARE
# -------------------------------------------------------------
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',

    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',

    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'moveline.urls'

# -------------------------------------------------------------
# TEMPLATES
# -------------------------------------------------------------
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'], 
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'moveline.wsgi.application'
ASGI_APPLICATION = 'moveline.asgi.application'  

# -------------------------------------------------------------
# REDIS / CELERY
# -------------------------------------------------------------
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", REDIS_URL)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE if "TIME_ZONE" in globals() else "Asia/Damascus"
CELERY_BEAT_SCHEDULE = {
    "check-stopped-trucks-every-minute": {
        "task": "tracking.tasks.check_stopped_trucks",
        "schedule": 60.0,
    },
}
 
# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.postgresql',
#         'NAME': 'moveline',
#         'USER': 'root',
#         'PASSWORD': 'bIQa1Hiyt5JDLXfjzFMRSpr0yKKfLK2y',
#         'HOST': 'dpg-d3tt00bipnbc738hirkg-a.oregon-postgres.render.com',
#         'PORT': '5432',
#         'OPTIONS': {
#             'sslmode': 'require',
#         }
#     }
# }
# try:
#     import dj_database_url  # type: ignore
# except ImportError:  # pragma: no cover - optional dependency in dev
#     dj_database_url = None

# DATABASE_URL = os.getenv('DATABASE_URL')

# if DATABASE_URL:
#     if dj_database_url is None:
#         raise ImportError("dj_database_url is required when DATABASE_URL is set")
#     DATABASES = {
#         'default': dj_database_url.parse(
#             DATABASE_URL,
#             conn_max_age=600,
#             ssl_require=True,
#         )
#     }
# else:
DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }


# }


# DATABASES = {
#     "default": {
#         "ENGINE": "django.db.backends.mysql",
#         "NAME": "moveline_db",
#         "USER": "admin",
#         "PASSWORD": "admin",
#         "HOST": "127.0.0.1",
#         "PORT": "3306",
#         "OPTIONS": {
#             "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
#         },
#     }
# }

# -------------------------------------------------------------
# PASSWORD VALIDATION
# -------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

AUTHENTICATION_BACKENDS = [
    "users.backends.EmailOrUsernameModelBackend",
]

# -------------------------------------------------------------
# INTERNATIONALIZATION
# -------------------------------------------------------------
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Damascus'
USE_I18N = True
USE_TZ = True

# -------------------------------------------------------------
# STATIC & MEDIA FILES
# -------------------------------------------------------------
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# -------------------------------------------------------------
# EMAIL (GMAIL SMTP)
# -------------------------------------------------------------
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = "hadi.tiger.2003h@gmail.com"
EMAIL_HOST_PASSWORD = "bgjb zagh ayiy mvjc"
DEFAULT_FROM_EMAIL = "MoveLine <hadi.tiger.2003h@gmail.com>"

# -------------------------------------------------------------
# FIREBASE (FCM)
# -------------------------------------------------------------
# Path to Firebase service account JSON
FIREBASE_CREDENTIALS_PATH = os.getenv(
    "FIREBASE_CREDENTIALS_PATH",
    str(BASE_DIR / "firebase-service-account.json"),
)

# -------------------------------------------------------------
# PAYMERA PAYMENT GATEWAY
# -------------------------------------------------------------
PAYMERA_BASE_URL = os.getenv("PAYMERA_BASE_URL", "")
PAYMERA_INITIATE_PATH = os.getenv("PAYMERA_INITIATE_PATH", "payment/initiate")
PAYMERA_MERCHANT_ID = os.getenv("PAYMERA_MERCHANT_ID", "")
PAYMERA_API_KEY = os.getenv("PAYMERA_API_KEY", "")
PAYMERA_WEBHOOK_SECRET = os.getenv("PAYMERA_WEBHOOK_SECRET", "")

# -------------------------------------------------------------
# STRIPE PAYMENT GATEWAY
# -------------------------------------------------------------
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_CURRENCY = os.getenv("STRIPE_CURRENCY", "usd")

# -------------------------------------------------------------
# REST FRAMEWORK
# -------------------------------------------------------------
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}

# -------------------------------------------------------------
# SIMPLE JWT CONFIGURATION
# -------------------------------------------------------------
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=3600000),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=2),
    'ROTATE_REFRESH_TOKENS': False,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# -------------------------------------------------------------
# CORS CONFIGURATION
# -------------------------------------------------------------
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",  # React
    "http://127.0.0.1:3000",
    "http://localhost:8080",  # Flutter Web
    "http://127.0.0.1:8080",
    "http://localhost:4200",  # Angular
]
CORS_ALLOW_HEADERS = list(default_headers) + [
    "ngrok-skip-browser-warning",
]
CSRF_TRUSTED_ORIGINS = [
    "https://trispermous-hamfistedly-douglas.ngrok-free.dev",
]

# -------------------------------------------------------------
# DEFAULTS
# -------------------------------------------------------------
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# -------------------------------------------------------------
# CUSTOM USER MODEL
# -------------------------------------------------------------
AUTH_USER_MODEL = 'users.User'
# APPEND_SLASH=False

# -------------------------------------------------------------
# CHANNELS
# -------------------------------------------------------------
CHANNEL_LAYER_BACKEND = os.getenv("CHANNEL_LAYER_BACKEND", "redis").lower()

if CHANNEL_LAYER_BACKEND == "memory":
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        }
    }
else:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {
                "hosts": [REDIS_URL],
            },
        }
    }

CSRF_TRUSTED_ORIGINS = [
    "https://trispermous-hamfistedly-douglas.ngrok-free.dev",
]
