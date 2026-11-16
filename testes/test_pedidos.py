from unittest import mock

from django.utils import timezone

from fornecedores.models import Fornecedor, ItemFornecedor
from pedidos.models import Pedido
from projetos.models import ItemLinha, LinhaProjeto, Projeto

from .base import TesteApi, criar_cliente


class AdaptadorFalso:
    def __init__(self, falha=None):
        self.falha = falha
        self.enviados = []

    def enviar_pedido(self, pedido):
        if self.falha:
            raise self.falha
        self.enviados.append(pedido["id_vixdro"])
        return {"numero": "F-100", "status": "recebido"}


class EnvioDePedido(TesteApi):
    def setUp(self):
        super().setUp()
        agora = timezone.now()
        fornecedor = Fornecedor.objects.create(nome="Alumínio Teste", slug="aluminio-teste", variavel_chave="CHAVE_TESTE")
        item = ItemFornecedor.objects.create(fornecedor=fornecedor, codigo="P-01", descricao="Trilho", unidade="UN",
                                             preco="25.00", atualizado_em=agora, visto_em=agora)
        self.projeto = Projeto.objects.create(vidraceiro=self.ana, cliente=criar_cliente(self.ana), nome="Sala",
                                              status=Projeto.Status.APROVADO, numero=1)
        linha = LinhaProjeto.objects.create(projeto=self.projeto, nome="Janela", largura_mm=1000, altura_mm=1000)
        ItemLinha.objects.create(linha=linha, item=item, ajuste=2)
        self.dados = {"projeto": str(self.projeto.pk)}

    def test_segundo_envio_do_mesmo_projeto_e_recusado(self):
        adaptador = AdaptadorFalso()
        with mock.patch("pedidos.servico.adaptador_para", return_value=adaptador):
            primeiro = self.api_ana.post("/api/v1/pedidos/", self.dados, format="json")
            segundo = self.api_ana.post("/api/v1/pedidos/", self.dados, format="json")
        self.assertEqual(primeiro.status_code, 201, primeiro.data)
        self.assertEqual(segundo.status_code, 400)
        self.assertEqual(len(adaptador.enviados), 1)
        self.assertEqual(Pedido.objects.filter(projeto=self.projeto).count(), 1)

    def test_falha_inesperada_vira_erro_e_o_pedido_pode_ser_reenviado(self):
        with mock.patch("pedidos.servico.adaptador_para", return_value=AdaptadorFalso(falha=RuntimeError("caiu"))):
            with self.assertLogs("pedidos.servico", level="ERROR"):
                r = self.api_ana.post("/api/v1/pedidos/", self.dados, format="json")
        self.assertEqual(r.status_code, 201)
        pedido = Pedido.objects.get(projeto=self.projeto)
        self.assertEqual(pedido.status, Pedido.Status.ERRO)

        adaptador = AdaptadorFalso()
        with mock.patch("pedidos.servico.adaptador_para", return_value=adaptador):
            r = self.api_ana.post(f"/api/v1/pedidos/{pedido.pk}/reenviar/", format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(adaptador.enviados, [str(pedido.pk)])
        pedido.refresh_from_db()
        self.assertEqual(pedido.status, Pedido.Status.RECEBIDO)

    def test_outro_vidraceiro_nao_reenvia_nem_consulta_o_pedido(self):
        with mock.patch("pedidos.servico.adaptador_para", return_value=AdaptadorFalso()):
            self.api_ana.post("/api/v1/pedidos/", self.dados, format="json")
        pedido = Pedido.objects.get(projeto=self.projeto)
        self.assertEqual(self.api_beto.get(f"/api/v1/pedidos/{pedido.pk}/").status_code, 404)
        self.assertEqual(self.api_beto.post(f"/api/v1/pedidos/{pedido.pk}/reenviar/").status_code, 404)
