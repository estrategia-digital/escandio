from pathlib import Path
from datetime import timedelta
from decouple import config
try:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
except ImportError:
    # Defensivo: si el server aun no instalo sentry-sdk (deploy sin pip install),
    # el backend NO debe caerse — Sentry simplemente queda desactivado.
    sentry_sdk = None
    DjangoIntegration = None

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/6.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-x)e8ci34g3_w6y6&p-=4lcnn2z@jnic9#4h(s8&8bhq_jz9mj!'

# Se apaga automaticamente en prod (ENV='prod' en el .env del server) y queda
# True en dev/test. Con DEBUG=True Django acumula connection.queries por la
# vida del worker -> fue la causa del OOM del backend el 2026-06-01.
DEBUG = config('ENV', default='dev') != 'prod'

# === Sentry (observabilidad de errores) ===
# DORMIDO si no hay SENTRY_DSN (dev/local no envia nada). Captura los 500 NO
# manejados con tag de `tenant` (ver escandioapp.middleware). PII: no manda
# usuario/cookies/auth ni el body del request. OJO: Sentry SI incluye variables
# locales en el traceback (pueden traer datos de clientes).
def _sentry_before_send(event, hint):
    """Descarta el ValueError de arranque de uvicorn+ASGI ("can only handle
    ASGI/HTTP connections, not lifespan"): es puro ruido de startup, no afecta
    peticiones. Solo ese mensaje exacto; cualquier otro ValueError pasa normal.
    """
    exc_info = (hint or {}).get('exc_info')
    if exc_info:
        exc_value = exc_info[1]
        if isinstance(exc_value, ValueError) and 'can only handle ASGI/HTTP connections' in str(exc_value):
            return None
    return event


SENTRY_DSN = config('SENTRY_DSN', default='')
if SENTRY_DSN and sentry_sdk is not None:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
        environment=config('ENV', default='dev'),
        traces_sample_rate=0.0,          # solo errores, sin performance (sin costo extra)
        send_default_pii=False,
        max_request_body_size='never',
        before_send=_sentry_before_send,
    )

ALLOWED_HOSTS = ['*']


# Application definition

SHARED_APPS = (
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.sites',
    'django.contrib.messages',
    'django.contrib.admin',
    'django_tenants',
    'drf_spectacular',
    'contenedor',
    'vertical',
    'movil',
)

TENANT_APPS = (
    'ruteo',
    'general',
    'mensajeria'
)

INSTALLED_APPS = [
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'channels',
    'rest_framework',
    'drf_spectacular',
    'django_tenants',
    "corsheaders",
    'contenedor',
    'vertical',
    'ruteo',
    'general',
    'mensajeria',
    'movil',
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    'django_tenants.middleware.main.TenantMainMiddleware',
    # Etiqueta los eventos de Sentry con el tenant (no-op sin SENTRY_DSN).
    'escandioapp.middleware.SentryTenantMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',    
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'movil.middleware.VersionAppMiddleware',
]

ROOT_URLCONF = 'escandioapp.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
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

WSGI_APPLICATION = 'escandioapp.wsgi.application'
ASGI_APPLICATION = 'escandioapp.asgi.application'

_REDIS_URL = config('REDIS_URL', default='')
if _REDIS_URL:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {'hosts': [_REDIS_URL]},
        },
    }
else:
    CHANNEL_LAYERS = {
        'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'},
    }


# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases

DATABASES = {
        'default': {
        'ENGINE': 'django_tenants.postgresql_backend',
        'NAME': config('DATABASE_NAME'),
        'USER': config('DATABASE_USER'),
        'PASSWORD': config('DATABASE_CLAVE'),
        'HOST': config('DATABASE_HOST'),
        'PORT': config('DATABASE_PORT'),
    }
}

DATABASE_ROUTERS = (
    'django_tenants.routers.TenantSyncRouter',
)


TENANT_MODEL = "contenedor.Contenedor"
TENANT_DOMAIN_MODEL = "contenedor.Dominio"

# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = 'es'

TIME_ZONE = 'America/Bogota'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_URL = 'static/'

REST_FRAMEWORK = {
    'DEFAULT_FILTER_BACKENDS': ['django_filters.rest_framework.DjangoFilterBackend'],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 30,  
    'COERCE_DECIMAL_TO_STRING': False,      
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'EXCEPTION_HANDLER': 'escandioapp.exceptions.custom_exception_handler',
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

# drf-spectacular: el schema solo cubre la API movil v2 (/api/v2/).
SPECTACULAR_SETTINGS = {
    'TITLE': 'Escandio API movil v2',
    'DESCRIPTION': 'Contrato de la API v2 consumida por la app movil berkelio. '
                   'Ver movil/contrato_v2.py.',
    'VERSION': '2.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
    'PREPROCESSING_HOOKS': ['movil.spectacular.solo_endpoints_v2'],
}

SIMPLE_JWT = {      
    'ACCESS_TOKEN_LIFETIME': timedelta(days=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,    
}

AUTH_USER_MODEL = 'contenedor.User'

CORS_ALLOWED_ORIGIN_REGEXES = [
    # Dev local: localhost, 127.0.0.1 e IPv6 [::1], en cualquier puerto (front
    # local -> back QA). Sin esto el preflight no devuelve Access-Control-Allow-Origin.
    r"^https?://localhost(:\d+)?$",
    r"^https?://127\.0\.0\.1(:\d+)?$",
    r"^https?://\[::1\](:\d+)?$",
    r"^https?://([a-z0-9-]+\.)*ruteoapi\.online$",
    r"^https?://([a-z0-9-]+\.)*ruteoapi\.co$",
    r"^https?://([a-z0-9-]+\.)*ruteo\.co$",
    r"^https?://([a-z0-9-]+\.)*ruteo\.online$",
]

CORS_ALLOW_METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS']

CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
    "x-api-key"
]