"""Apoio comum aos testes: contas, login e dados mínimos."""
from django.core.cache import cache
from rest_framework.test import APIClient, APITestCase

from clientes.models import Cliente
from contas.models import Vidraceiro

SENHA = "vidro-temperado-88"


def criar_vidraceiro(email, **extra):
    dados = dict(nome="Fulano", celular="84999990000", cpf_cnpj="12345678901", rua="Rua A", numero="1",
                 bairro="Centro", cidade="Caicó", estado="RN")
    dados.update(extra)
    return Vidraceiro.objects.create_user(email=email, password=SENHA, **dados)


def criar_cliente(vidraceiro, nome="Maria"):
    return Cliente.objects.create(vidraceiro=vidraceiro, nome=nome)


class TesteApi(APITestCase):
    """Dois vidraceiros (ana e beto), cada um com o seu cliente de API já logado."""

    def setUp(self):
        cache.clear()  # os limites de tentativas ficam no cache
        self.ana = criar_vidraceiro("ana@exemplo.com")
        self.beto = criar_vidraceiro("beto@exemplo.com")
        self.api_ana = self.logado(self.ana)
        self.api_beto = self.logado(self.beto)

    @staticmethod
    def logado(vidraceiro):
        # raise_request_exception=False: um erro 500 aparece como resposta 500,
        # do jeito que o app receberia.
        api = APIClient(raise_request_exception=False)
        api.force_authenticate(vidraceiro)
        return api
