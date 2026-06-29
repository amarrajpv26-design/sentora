"""
Django settings for sentora_core project.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
import cloudinary

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('SECRET_KEY')
DEBUG = True

ALLOWED_HOSTS = [
    "127.0.0.1",
    "localhost",
]
TIME_ZONE = 'Asia/Kolkata'
USE_TZ = True

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "cloudinary_storage",   # ← MUST be before staticfiles
    "django.contrib.staticfiles",
    "cloudinary",           # ← after staticfiles

    # custom
    "users",
    "admin_panel",
    "products",
    "shop",
    "cart",
    'checkout',
    'orders',
    'management',
    'coupons',
    'wallets.apps.WalletsConfig',
    'reviews',
    'offers',

    # google / allauth
    "django.contrib.sites",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
]

# Cloudinary credentials
CLOUDINARY_STORAGE = {
    'CLOUD_NAME': os.getenv('CLOUDINARY_CLOUD_NAME'),
    'API_KEY': os.getenv('CLOUDINARY_API_KEY'),
    'API_SECRET': os.getenv('CLOUDINARY_API_SECRET'),
}

cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET'),
)

# Storage — Django 4.2+ requires STORAGES dict (DEFAULT_FILE_STORAGE is ignored)
STORAGES = {
    "default": {
        "BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

SITE_ID = 1

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

CART_SESSION_ID = 'scentora_cart'

SOCIALACCOUNT_LOGIN_ON_GET = True
ACCOUNT_LOGOUT_ON_GET = False
SOCIALACCOUNT_ADAPTER = "admin_panel.adapter.ScentoraSocialAdapter"
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_QUERY_EMAIL = True

LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "admin_login"
ACCOUNT_USER_MODEL_USERNAME_FIELD = "username"
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_USERNAME_REQUIRED = True
ACCOUNT_EMAIL_VERIFICATION = "none"
ACCOUNT_AUTHENTICATION_METHOD = "username_email"
ACCOUNT_USER_MODEL_EMAIL_FIELD = "email"
ACCOUNT_LOGIN_METHODS = {"email", "username"}
ACCOUNT_SIGNUP_FIELDS = ["email", "username"]
SOCIALACCOUNT_UNIQUE_EMAIL = True

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

ROOT_URLCONF = "sentora_core.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [os.path.join(BASE_DIR, "templates")],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                'cart.context_processors.cart',
                'shop.context_processors.global_footer_categories',
            ],
        },
    },
]

WSGI_APPLICATION = "sentora_core.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME"),
        "USER": os.getenv("DB_USER"),
        "PASSWORD": os.getenv("DB_PASSWORD"),
        "HOST": "localhost",
        "PORT": "5432",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "users.validators.ScentoraComplexityValidator"},
]

LANGUAGE_CODE = "en-us"
USE_I18N = True

STATIC_URL = "static/"
STATICFILES_DIRS = [os.path.join(BASE_DIR, "static")]
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")

AUTH_USER_MODEL = "users.User"
LOGIN_URL = "user_login"

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD")
DEFAULT_FROM_EMAIL = f"Scentora <{EMAIL_HOST_USER}>"

PASSWORD_RESET_TIMEOUT = 14400

# MEDIA_ROOT is not needed — Cloudinary handles storage