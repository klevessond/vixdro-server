from datetime import timedelta
from pathlib import Path

from decouple import Csv, config

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config("SECRET_KEY")
DEBUG = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Terceiros
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",  # permite logout de verdade
    "corsheaders",
    # Nossos apps
    "contas",
    "fornecedores",
    "produtos",
    "clientes",
    "projetos",
    "pedidos",
    "agenda",
    "financeiro",
    "estoque",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Produção usa PostgreSQL. DB_ENGINE existe para rodar os testes num SQLite
# (DB_ENGINE=django.db.backends.sqlite3 e DB_NAME=caminho do arquivo).
DATABASES = {
    "default": {
        "ENGINE": config("DB_ENGINE", default="django.db.backends.postgresql"),
        "NAME": config("DB_NAME"),
        "USER": config("DB_USER", default=""),
        "PASSWORD": config("DB_PASSWORD", default=""),
        "HOST": config("DB_HOST", default="localhost"),
        "PORT": config("DB_PORT", default="5432"),
    }
}

# Usuario customizado: precisa estar definido ANTES do primeiro migrate.
AUTH_USER_MODEL = "contas.Vidraceiro"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True


DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    # Tudo exige login, exceto o que for liberado explicitamente na view.
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    # Limite de tentativas: o servidor esta na internet, isso freia ataques de senha.
    "DEFAULT_THROTTLE_RATES": {
        "login": "10/min",        # por endereço (IP)
        "login_email": "20/hour",  # por conta, venha de onde vier
        "cadastro": "5/min",
    },
    # Quantos proxies há na frente do Django (o Nginx = 1). Sem isto, o limite
    # de tentativas usa o cabeçalho X-Forwarded-For inteiro, que quem ataca
    # escolhe: bastava mudar o cabeçalho a cada tentativa para nunca ser barrado.
    "NUM_PROXIES": config("NUM_PROXIES", default=1, cast=int),
    # Parâmetro inválido (um id que não é UUID, uma data errada) responde 400
    # com explicação, em vez de erro 500.
    "EXCEPTION_HANDLER": "config.erros.tratar_excecao",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

CORS_ALLOWED_ORIGINS = config("CORS_ALLOWED_ORIGINS", default="", cast=Csv())

DATA_UPLOAD_MAX_MEMORY_SIZE = 8 * 1024 * 1024

STATIC_URL = "static/"
MEDIA_URL = "media/"

# Pastas servidas pelo Nginx (fora do /root, que o Nginx não consegue ler).
STATIC_ROOT = config("STATIC_ROOT", default=str(BASE_DIR / "staticfiles"))
MEDIA_ROOT = config("MEDIA_ROOT", default=str(BASE_DIR / "media"))

# Login do admin pelo domínio (o Django exige a origem na lista).
CSRF_TRUSTED_ORIGINS = config("CSRF_TRUSTED_ORIGINS", default="", cast=Csv())

# Atrás do Nginx: confia no aviso de HTTPS que ele manda. Sem isto, os
# endereços das fotos e logomarcas sairiam com http:// mesmo no HTTPS.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Cookies do admin só por HTTPS. Vale sempre que DEBUG=False; num servidor de
# teste sem HTTPS, ponha COOKIES_SEGUROS=False no .env (senão o login do admin
# não funciona por http://).
COOKIES_SEGUROS = config("COOKIES_SEGUROS", default=not DEBUG, cast=bool)
SESSION_COOKIE_SECURE = COOKIES_SEGUROS
CSRF_COOKIE_SECURE = COOKIES_SEGUROS

# Opcionais, ligados pelo .env de produção (ver env.exemplo):
#   HSTS_SEGUNDOS: o navegador passa a recusar http:// neste domínio pelo tempo
#   informado. Comece com 3600 e só depois suba para 31536000 (1 ano).
#   REDIRECIONAR_HTTPS: o Django redireciona http:// para https://. Só ligue se
#   o Nginx envia o cabeçalho X-Forwarded-Proto (senão vira redirecionamento sem fim).
SECURE_HSTS_SECONDS = config("HSTS_SEGUNDOS", default=0, cast=int)
SECURE_SSL_REDIRECT = config("REDIRECIONAR_HTTPS", default=False, cast=bool)
