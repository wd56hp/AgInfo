"""
Django settings for aginfo_django project.
"""
import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-change-me-in-production')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get('DJANGO_DEBUG', 'True').lower() == 'true'

ALLOWED_HOSTS = ['*']  # Configure appropriately for production

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.gis',  # GeoDjango
    'aginfo_django.aginfo',
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

ROOT_URLCONF = 'aginfo_django.urls'

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

WSGI_APPLICATION = 'aginfo_django.wsgi.application'

# Database
# https://docs.djangoproject.com/en/5.0/ref/settings/#databases
DATABASES = {
    'default': {
        'ENGINE': 'django.contrib.gis.db.backends.postgis',
        'NAME': os.environ.get('POSTGRES_DB', 'aginfo'),
        'USER': os.environ.get('POSTGRES_USER', 'agadmin'),
        'PASSWORD': os.environ.get('POSTGRES_PASSWORD', 'changeme'),
        'HOST': os.environ.get('POSTGRES_HOST', '172.28.0.10'),  # postgis container IP
        'PORT': os.environ.get('POSTGRES_PORT', '5432'),
    }
}

# Password validation
# https://docs.djangoproject.com/en/5.0/ref/settings/#auth-password-validators
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
# https://docs.djangoproject.com/en/5.0/topics/i18n/
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.0/howto/static-files/
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Default primary key field type
# https://docs.djangoproject.com/en/5.0/ref/settings/#default-auto-field
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# GeoDjango settings
# Auto-detect GDAL library path if not set or path doesn't exist
GDAL_LIBRARY_PATH = os.environ.get('GDAL_LIBRARY_PATH')
if not GDAL_LIBRARY_PATH or not os.path.exists(GDAL_LIBRARY_PATH):
    # Try common locations
    for path in ['/usr/lib/x86_64-linux-gnu/libgdal.so', '/usr/lib/libgdal.so']:
        if os.path.exists(path):
            GDAL_LIBRARY_PATH = path
            break
    else:
        GDAL_LIBRARY_PATH = None

GEOS_LIBRARY_PATH = os.environ.get('GEOS_LIBRARY_PATH')
if not GEOS_LIBRARY_PATH or not os.path.exists(GEOS_LIBRARY_PATH):
    # Try common locations
    for path in ['/usr/lib/x86_64-linux-gnu/libgeos_c.so', '/usr/lib/libgeos_c.so']:
        if os.path.exists(path):
            GEOS_LIBRARY_PATH = path
            break
    else:
        GEOS_LIBRARY_PATH = None

# Admin site customization
ADMIN_SITE_HEADER = 'AgInfo Administration'
ADMIN_SITE_TITLE = 'AgInfo Admin'
ADMIN_INDEX_TITLE = 'Welcome to AgInfo Administration'

