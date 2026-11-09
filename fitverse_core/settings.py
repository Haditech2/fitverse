"""
Django settings for fitverse_core project.
"""

from pathlib import Path
import os
import mimetypes

mimetypes.add_type('model/gltf-binary', '.glb')

BASE_DIR = Path(__file__).resolve().parent.parent

def _load_local_env():
    env_path = BASE_DIR / '.env'
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        name, value = line.split('=', 1)
        name = name.strip()
        value = value.strip().strip('"').strip("'")
        if name:
            os.environ.setdefault(name, value)

_load_local_env()

SECRET_KEY = 'django-insecure-gtu+k2%%x=3)wlzkaeds9crmkj4cqlg^_t_ixnws0ns%tm3mpj'

DEBUG = True

ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Fitverse Apps
    'fitverse_app',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'fitverse_core.urls'

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

WSGI_APPLICATION = 'fitverse_core.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

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

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Africa/Lagos'

USE_I18N = True

USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
DATA_UPLOAD_MAX_MEMORY_SIZE = 12 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 12 * 1024 * 1024

FASHN_VTON_SPACE = os.getenv('FASHN_VTON_SPACE', 'fashn-ai/fashn-vton-1.5')
HF_TOKEN = os.getenv('HF_TOKEN', '')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
GEMINI_TEXT_MODEL = os.getenv('GEMINI_TEXT_MODEL', 'gemini-3.6-flash')
GEMINI_IMAGE_MODEL = os.getenv('GEMINI_IMAGE_MODEL', 'gemini-3.1-flash-image')
GEMINI_TEXT_FALLBACKS = tuple(
    model.strip()
    for model in os.getenv('GEMINI_TEXT_FALLBACKS', 'gemini-3.5-flash,gemini-3.8-flash').split(',')
    if model.strip()
)
GEMINI_IMAGE_FALLBACKS = tuple(
    model.strip()
    for model in os.getenv('GEMINI_IMAGE_FALLBACKS', '').split(',')
    if model.strip()
)
AI_PROVIDER = os.getenv('AI_PROVIDER', 'gemini')

BODYGRAM_ORG_ID = os.getenv('BODYGRAM_ORG_ID', '')
BODYGRAM_API_KEY = os.getenv('BODYGRAM_API_KEY', '')
BODYGRAM_API_URL = os.getenv('BODYGRAM_API_URL', 'https://platform.bodygram.com/api/orgs')

LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'home'
LOGIN_URL = 'login'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
