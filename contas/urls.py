from django.urls import path
from rest_framework_simplejwt.views import TokenBlacklistView, TokenRefreshView

from .views import CadastroView, LogoView, LoginView, MeView, PlanoView, PrecosPadraoView

urlpatterns = [
    path("auth/login/", LoginView.as_view(), name="login"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("auth/logout/", TokenBlacklistView.as_view(), name="logout"),
    path("vidraceiros/", CadastroView.as_view(), name="cadastro"),
    path("vidraceiros/me/", MeView.as_view(), name="me"),
    path("vidraceiros/me/precos/", PrecosPadraoView.as_view(), name="precos-padrao"),
    path("vidraceiros/me/logo/", LogoView.as_view(), name="logo"),
    path("vidraceiros/me/plano/", PlanoView.as_view(), name="plano"),
]
