import base64
import uuid
from io import BytesIO

from django.core.files.base import ContentFile
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle, SimpleRateThrottle

from projetos.fotos import FotoInvalida, abrir_imagem
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import Vidraceiro
from .planos import resumo_plano
from .serializers import (
    CadastroSerializer,
    LoginSerializer,
    PerfilSerializer,
    PrecosPadraoSerializer,
    VidraceiroSerializer,
)


def _resposta_com_tokens(vidraceiro, http_status):
    refresh = RefreshToken.for_user(vidraceiro)
    return Response(
        {
            "vidraceiro": VidraceiroSerializer(vidraceiro).data,
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        },
        status=http_status,
    )


class LimitePorEmail(SimpleRateThrottle):
    """Limite de tentativas de login por conta, venha de onde vier.
    O limite por endereço (IP) não segura quem testa senhas da mesma conta a
    partir de muitos endereços."""

    scope = "login_email"

    def get_cache_key(self, request, view):
        email = str(request.data.get("email", "")).strip().lower()[:254]
        if not email:
            return None
        return self.cache_format % {"scope": self.scope, "ident": email}


class LoginView(TokenObtainPairView):
    """POST /api/v1/auth/login/  {email, password}"""

    serializer_class = LoginSerializer
    throttle_classes = [ScopedRateThrottle, LimitePorEmail]
    throttle_scope = "login"


class CadastroView(generics.CreateAPIView):
    """POST /api/v1/vidraceiros/  (público)

    Idempotente: se a fila_sync do app reenviar um cadastro que já chegou
    (mesmo id, email e senha), responde 200 em vez de dar erro.
    """

    permission_classes = [AllowAny]
    serializer_class = CadastroSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "cadastro"

    def create(self, request, *args, **kwargs):
        existente = self._cadastro_ja_recebido(request.data)
        if existente is not None:
            return _resposta_com_tokens(existente, status.HTTP_200_OK)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vidraceiro = serializer.save()
        return _resposta_com_tokens(vidraceiro, status.HTTP_201_CREATED)

    @staticmethod
    def _cadastro_ja_recebido(dados):
        try:
            id_ = uuid.UUID(str(dados.get("id", "")))
        except ValueError:
            return None
        vidraceiro = Vidraceiro.objects.filter(pk=id_).first()
        if vidraceiro is None:
            return None
        email = str(dados.get("email", "")).strip().lower()
        senha = str(dados.get("password", ""))
        if vidraceiro.email == email and vidraceiro.check_password(senha):
            return vidraceiro
        return None


class MeView(generics.RetrieveUpdateAPIView):
    """GET   /api/v1/vidraceiros/me/  dados do vidraceiro logado
    PATCH /api/v1/vidraceiros/me/  edita os dados (o e-mail não muda: é o login)"""

    http_method_names = ["get", "patch", "head", "options"]

    def get_serializer_class(self):
        return PerfilSerializer if self.request.method == "PATCH" else VidraceiroSerializer

    def get_object(self):
        return self.request.user

    def update(self, request, *args, **kwargs):
        super().update(request, *args, **kwargs)
        # Devolve o vidraceiro completo, no mesmo formato do login.
        return Response(VidraceiroSerializer(request.user).data)


class PrecosPadraoView(generics.RetrieveUpdateAPIView):
    """GET / PATCH /api/v1/vidraceiros/me/precos/  (exige token)"""

    serializer_class = PrecosPadraoSerializer

    def get_object(self):
        return self.request.user


LOGO_LADO_MAXIMO = 800  # px: suficiente para a impressão, leve para guardar


class LogoView(APIView):
    """
    GET    /api/v1/vidraceiros/me/logo/   {"logo_url", "logo_data_uri"}
    POST   /api/v1/vidraceiros/me/logo/   {"imagem_base64": "..."}  (PNG ou JPEG)
    DELETE /api/v1/vidraceiros/me/logo/
    """

    def get(self, request):
        return Response(self._dados(request))

    def post(self, request):
        try:
            # Mesma conferência das fotos da medição: formato e tamanho.
            img = abrir_imagem(request.data.get("imagem_base64", ""))
        except FotoInvalida as e:
            raise ValidationError({"imagem_base64": str(e)})

        img.thumbnail((LOGO_LADO_MAXIMO, LOGO_LADO_MAXIMO))
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA")
        saida = BytesIO()
        img.save(saida, format="PNG", optimize=True)

        usuario = request.user
        if usuario.logo:
            usuario.logo.delete(save=False)  # a anterior sai do disco, não fica acumulando
        usuario.logo.save(f"logo-{usuario.pk}.png", ContentFile(saida.getvalue()), save=True)
        return Response(self._dados(request), status=status.HTTP_201_CREATED)

    def delete(self, request):
        if request.user.logo:
            request.user.logo.delete(save=False)
        request.user.logo = ""
        request.user.save(update_fields=["logo"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @staticmethod
    def _dados(request):
        logo = request.user.logo
        if not logo:
            return {"logo_url": None, "logo_data_uri": None}
        try:
            with logo.open("rb") as f:
                conteudo = base64.b64encode(f.read()).decode()
        except FileNotFoundError:
            # O arquivo sumiu do disco (ex: servidor restaurado sem a pasta media).
            return {"logo_url": None, "logo_data_uri": None}
        return {
            "logo_url": request.build_absolute_uri(logo.url),
            # Pronto para o PDF: a imagem vai dentro do documento.
            "logo_data_uri": f"data:image/png;base64,{conteudo}",
        }


class PlanoView(APIView):
    """GET /api/v1/vidraceiros/me/plano/  plano da conta e o que cada um inclui."""

    def get(self, request):
        return Response(resumo_plano(request.user))
