import uuid

from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import Vidraceiro
from .serializers import CadastroSerializer, LoginSerializer, VidraceiroSerializer


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


class LoginView(TokenObtainPairView):
    """POST /api/v1/auth/login/  {email, password}"""

    serializer_class = LoginSerializer
    throttle_classes = [ScopedRateThrottle]
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


class MeView(generics.RetrieveAPIView):
    """GET /api/v1/vidraceiros/me/  (exige token)"""

    serializer_class = VidraceiroSerializer

    def get_object(self):
        return self.request.user
