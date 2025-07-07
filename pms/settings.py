import os
from pathlib import Path
import psycopg2.extensions
from decouple import config

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = config('SECRET_KEY','sdghtjykuyikjyhtgrfd')
DEBUG = config('DEBUG', default=False, cast=bool)
LOGS_DIR = os.path.join(BASE_DIR, 'logs')

if os.path.exists('/app'):
    # Docker environment
    LOGS_DIR = Path('/app/logs')
else:
    # Local development or CI
    LOGS_DIR = BASE_DIR / 'logs'

DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    'django_celery_beat',
    'django_filters',
    'djoser',
]

CELERY_BEAT_SCHEDULER='django_celery_beat.schedulers:DatabaseScheduler'

LOCAL_APPS = [
    'accounts',
    'properties',
    'bookings',
    'invitations',
    'trust_levels',
    'beds24_integration',
    'analytics',
    'health',
     'notifications',
    'upload',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'utils.middleware.DatabaseRoutingMiddleware',  # Custom routing middleware
    'utils.middleware.CacheHeadersMiddleware',     # Custom caching middleware
]

ROOT_URLCONF = 'pms.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'pms.wsgi.application'
AUTH_USER_MODEL = 'accounts.User'

# Optimized Database Configuration
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME', 'pms'),
        'USER': config('DB_USER', 'postgres'),
        'PASSWORD': config('DB_PASSWORD', 'postgres'),
        'HOST': config('DB_HOST', 'localhost'),
        'PORT': config('DB_PORT', default='5432'),
        'CONN_MAX_AGE': 300,  # 5 minutes connection pooling
        'OPTIONS': {
            'isolation_level': psycopg2.extensions.ISOLATION_LEVEL_READ_COMMITTED,
            'connect_timeout': 10,
            'application_name': 'oifyk_backend',
        },
        'TEST': {
            'NAME': 'test_pms_db',
        }
    }
}

# Read replica for better performance
if not DEBUG:
    DATABASES['replica'] = {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_REPLICA_NAME', config('DB_NAME', 'pms')),
        'USER': config('DB_REPLICA_USER', config('DB_USER', 'postgres')),
        'PASSWORD': config('DB_REPLICA_PASSWORD', config('DB_PASSWORD', 'postgres')),
        'HOST': config('DB_REPLICA_HOST', config('DB_HOST', 'localhost')),
        'PORT': config('DB_REPLICA_PORT', default='5432'),
        'CONN_MAX_AGE': 300,
        'OPTIONS': {
            'connect_timeout': 10,
            'application_name': 'oifyk_backend_replica',
        }
    }
DATABASE_ROUTERS = ['utils.db_router.DatabaseRouter']

# Redis Configuration - Optimized for High Traffic
REDIS_URL = config('REDIS_URL', default='redis://localhost:6379/0')

CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': REDIS_URL,
        'KEY_PREFIX': 'oifyk',
        'TIMEOUT': 300,
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'CONNECTION_POOL_KWARGS': {
                'max_connections': 100,
                'retry_on_timeout': True,
            },
          
            'PICKLE_VERSION': -1,
        }
    },
    # Separate cache for sessions
    'sessions': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': f"{REDIS_URL.replace('/0', '/1')}",
        'TIMEOUT': 86400,  # 24 hours
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        }
    }
}

# Use Redis for sessions
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'sessions'
SESSION_COOKIE_AGE = 86400  # 24 hours

# Celery Configuration - Optimized
CELERY_BROKER_URL = REDIS_URL.replace('/0', '/2')
CELERY_RESULT_BACKEND = REDIS_URL.replace('/0', '/3')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'
CELERY_TASK_ALWAYS_EAGER = DEBUG
CELERY_TASK_ROUTES = {
    'invitations.tasks.*': {'queue': 'invitations'},
    'properties.tasks.*': {'queue': 'properties'},
    'beds24_integration.tasks.*': {'queue': 'beds24'},
}

# REST Framework - Performance Optimized
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'utils.pagination.OptimizedPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'utils.throttling.AdminRateThrottle',
        'utils.throttling.OwnerRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
        'rest_framework.throttling.AnonRateThrottle'
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',
        'user': '1000/hour',
        'owner': '2000/hour',
        'admin': '5000/hour',
        'property_creation': '10/hour',
        'invitation': '50/hour',
    },
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ] if not DEBUG else [
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ]
}

# JWT Settings - Optimized for Security and Performance
from datetime import timedelta
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'VERIFYING_KEY': None,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',
}


ALLOWED_HOSTS = ['*']

# CORS Configuration
CORS_ALLOW_ALL_ORIGINS = DEBUG
cors_origins = config('CORS_ALLOWED_ORIGINS', default='')
if cors_origins:
    CORS_ALLOWED_ORIGINS = [origin.strip() for origin in cors_origins.split(',') if origin.strip()]
else:
    CORS_ALLOWED_ORIGINS = []

CORS_ALLOW_CREDENTIALS = True
CORS_PREFLIGHT_MAX_AGE = 86400

# File Storage - Production Optimized
USE_S3 = config('USE_S3', default=False, cast=bool)
if USE_S3:
    AWS_ACCESS_KEY_ID = config('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = config('AWS_SECRET_ACCESS_KEY')
    AWS_STORAGE_BUCKET_NAME = config('AWS_STORAGE_BUCKET_NAME')
    AWS_S3_REGION_NAME = config('AWS_S3_REGION_NAME', default='us-east-1')
    AWS_S3_CUSTOM_DOMAIN = f'{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com'
    AWS_DEFAULT_ACL = 'public-read'
    AWS_S3_OBJECT_PARAMETERS = {
        'CacheControl': 'max-age=86400',
    }
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
    STATICFILES_STORAGE = 'storages.backends.s3boto3.S3StaticStorage'
    MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/media/'
    STATIC_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/static/'
else:
    MEDIA_URL = '/media/'
    MEDIA_ROOT = BASE_DIR / 'media'
    STATIC_URL = '/static/'
    STATIC_ROOT = BASE_DIR / 'staticfiles'

# Email Configuration
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = config('EMAIL_HOST', default='smtp.sendgrid.net')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = True
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='apikey')
EMAIL_HOST_PASSWORD = config('SENDGRID_API_KEY', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='noreply@oifyk.com')

# Beds24 Configuration
BEDS24_API_URL = 'https://beds24.com/api/v2'
BEDS24_REFRESH_TOKEN = config('BEDS24_REFRESH_TOKEN', default='')

# Frontend URL for email links
FRONTEND_URL = config('FRONTEND_URL', default='http://localhost:3000')

# Security Settings for Production
# if not DEBUG:
#     SECURE_BROWSER_XSS_FILTER = True
#     SECURE_CONTENT_TYPE_NOSNIFF = True
#     SECURE_HSTS_INCLUDE_SUBDOMAINS = True
#     SECURE_HSTS_SECONDS = 86400
#     SECURE_REDIRECT_EXEMPT = []
#     SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=True, cast=bool)
#     SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
os.makedirs(LOGS_DIR, exist_ok=True)
# Logging Configuration - Production Optimized
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{levelname}] {asctime} {name} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '[{levelname}] {message}',
            'style': '{',
        },
    },
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse',
        },
        'require_debug_true': {
            '()': 'django.utils.log.RequireDebugTrue',
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'mail_admins': {
            'level': 'ERROR',
            'class': 'django.utils.log.AdminEmailHandler',
            'filters': ['require_debug_false'],
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['mail_admins', 'console'],
            'level': 'ERROR',
            'propagate': False,
        },
        'oifyk': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'celery': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
}

# Add file logging only in production (when not in CI and not DEBUG)
if not DEBUG and not os.environ.get('CI'):
    try:
        LOGGING['handlers']['file'] = {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(LOGS_DIR / 'django.log'),
            'maxBytes': 1024*1024*50,  # 50 MB
            'backupCount': 5,
            'formatter': 'verbose',
            'filters': ['require_debug_false'],
        }
        LOGGING['handlers']['debug_file'] = {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filename': str(LOGS_DIR / 'debug.log'),
            'formatter': 'verbose',
            'filters': ['require_debug_true'],
        }
        
        # Add file handlers to loggers
        for logger_name in ['django', 'django.request', 'oifyk', 'celery']:
            if logger_name in LOGGING['loggers']:
                LOGGING['loggers'][logger_name]['handlers'].append('file')
                
    except Exception as e:
        # If file logging fails, continue with console logging
        print(f"Warning: Could not configure file logging: {e}")
        pass

# Cache timeouts (in seconds)
CACHE_TIMEOUTS = {
    'USER_PROFILE': 3600,      # 1 hour
    'TRUST_NETWORK': 300,      # 5 minutes  
    'PROPERTY_LIST': 300,      # 5 minutes
    'PROPERTY_DETAIL': 1800,   # 30 minutes
    'ANALYTICS': 300,          # 5 minutes
    'BEDS24_TOKEN': 3300,      # 55 minutes (expires in 1 hour)
}

# Feature Flags
def str_to_bool(value):
    """Convert string to boolean, handling various formats"""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower().strip() in ('true', '1', 'yes', 'on')
    return bool(value)

# Feature Flags - More robust boolean parsing
FEATURES = {
    'BEDS24_INTEGRATION': str_to_bool(config('FEATURE_BEDS24', default='True')),
    'EMAIL_NOTIFICATIONS': str_to_bool(config('FEATURE_EMAIL', default='True')),
    'ANALYTICS_TRACKING': str_to_bool(config('FEATURE_ANALYTICS', default='True')),
    'RATE_LIMITING': str_to_bool(config('FEATURE_RATE_LIMITING', default='True')),
}

BEDS24_API_URL = 'https://beds24.com/api/v2'
SENDGRID_API_KEY = config('SENDGRID_API_KEY', default='')