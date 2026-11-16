"""Um vidraceiro nunca vê nem altera o que é de outro."""
import uuid

from clientes.models import Cliente
from projetos.models import Projeto

from .base import TesteApi, criar_cliente


class Clientes(TesteApi):
    def setUp(self):
        super().setUp()
        self.cliente_da_ana = criar_cliente(self.ana, "Cliente da Ana")
        self.url = f"/api/v1/clientes/{self.cliente_da_ana.pk}/"

    def test_lista_so_traz_os_proprios(self):
        criar_cliente(self.beto, "Cliente do Beto")
        nomes = [c["nome"] for c in self.api_beto.get("/api/v1/clientes/").data["clientes"]]
        self.assertEqual(nomes, ["Cliente do Beto"])

    def test_outro_vidraceiro_nao_le_nao_edita_nem_apaga(self):
        self.assertEqual(self.api_beto.get(self.url).status_code, 404)
        self.assertEqual(self.api_beto.patch(self.url, {"nome": "Invadido"}, format="json").status_code, 404)
        self.assertEqual(self.api_beto.delete(self.url).status_code, 404)
        self.cliente_da_ana.refresh_from_db()
        self.assertEqual(self.cliente_da_ana.nome, "Cliente da Ana")
        self.assertTrue(self.cliente_da_ana.ativo)

    def test_criar_com_o_id_de_um_cliente_alheio_e_recusado(self):
        r = self.api_beto.post("/api/v1/clientes/", {"id": str(self.cliente_da_ana.pk), "nome": "Meu"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Cliente.objects.get(pk=self.cliente_da_ana.pk).vidraceiro, self.ana)

    def test_o_dono_edita_e_o_reenvio_do_cadastro_nao_duplica(self):
        self.assertEqual(self.api_ana.patch(self.url, {"nome": "Maria Silva"}, format="json").status_code, 200)
        novo = {"id": str(uuid.uuid4()), "nome": "João"}
        self.assertEqual(self.api_ana.post("/api/v1/clientes/", novo, format="json").status_code, 201)
        self.assertEqual(self.api_ana.post("/api/v1/clientes/", novo, format="json").status_code, 200)
        self.assertEqual(Cliente.objects.filter(vidraceiro=self.ana).count(), 2)


class Projetos(TesteApi):
    def setUp(self):
        super().setUp()
        self.cliente_da_ana = criar_cliente(self.ana)
        self.projeto_da_ana = Projeto.objects.create(vidraceiro=self.ana, cliente=self.cliente_da_ana, nome="Cozinha")

    def test_outro_vidraceiro_nao_abre_nem_muda_o_projeto(self):
        url = f"/api/v1/projetos/{self.projeto_da_ana.pk}/"
        self.assertEqual(self.api_beto.get(url).status_code, 404)
        self.assertEqual(self.api_beto.delete(url).status_code, 404)
        self.assertEqual(self.api_beto.post(url + "status/", {"status": "aprovado"}, format="json").status_code, 404)
        self.assertEqual(self.api_beto.get(url + "calculo/").status_code, 404)
        self.assertEqual(self.api_ana.get(url).status_code, 200)

    def test_nao_da_para_criar_projeto_com_o_cliente_de_outro(self):
        dados = {"nome": "Sala", "cliente": str(self.cliente_da_ana.pk), "linhas": []}
        r = self.api_beto.post("/api/v1/projetos/", dados, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("cliente", r.data)

    def test_nao_da_para_anotar_medicao_no_projeto_de_outro(self):
        dados = {"projeto": str(self.projeto_da_ana.pk), "texto": "parede fora de esquadro"}
        self.assertEqual(self.api_beto.post("/api/v1/medicao/", dados, format="json").status_code, 400)
        self.assertEqual(self.api_ana.post("/api/v1/medicao/", dados, format="json").status_code, 201)
        lista = self.api_beto.get(f"/api/v1/medicao/?projeto={self.projeto_da_ana.pk}")
        self.assertEqual(lista.data, [])

    def test_pedido_do_projeto_de_outro_e_recusado(self):
        r = self.api_beto.post("/api/v1/pedidos/", {"projeto": str(self.projeto_da_ana.pk)}, format="json")
        self.assertEqual(r.status_code, 400)


class ParametrosInvalidos(TesteApi):
    """Valor impossível num filtro responde 400 com explicação, nunca erro 500."""

    def test_filtros_com_id_que_nao_e_uuid(self):
        for rota in ("/api/v1/projetos/?cliente=abc", "/api/v1/medicao/?projeto=abc", "/api/v1/pedidos/?projeto=abc"):
            self.assertEqual(self.api_ana.get(rota).status_code, 400, rota)

    def test_pedido_com_projeto_que_nao_e_uuid(self):
        self.assertEqual(self.api_ana.post("/api/v1/pedidos/", {"projeto": "abc"}, format="json").status_code, 400)
