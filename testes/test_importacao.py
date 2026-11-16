import csv

from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.utils import timezone

from fornecedores.importacao import importar_arquivo, ler_csv
from fornecedores.models import Fornecedor, ItemFornecedor

from .base import TesteApi, criar_cliente, criar_vidraceiro

PLANILHA = (
    "codigo;nome;valor;fabricante;comprimento_mm\n"
    "100;TRILHO SUPERIOR;67,00;ALUMIFONT;6000\n"
    "200;ROLDANA 50MM;14,99;CG GONZO;\n"
).encode()


class ImportacaoDePlanilha(TesteApi):
    def setUp(self):
        super().setUp()
        self.fornecedor = Fornecedor.objects.create(nome="Tabela", slug="tabela", adaptador="manual",
                                                    variavel_chave="SEM_CHAVE")

    def itens(self):
        return {i.codigo: i for i in ItemFornecedor.objects.filter(fornecedor=self.fornecedor)}

    def test_cria_atualiza_e_desativa_pelo_codigo(self):
        r = importar_arquivo(self.fornecedor, PLANILHA)
        self.assertEqual((r["criados"], r["alterados"], r["desativados"], r["erros"]), (2, 0, 0, []))
        self.assertEqual(str(self.itens()["100"].preco), "67.00")
        self.assertEqual(self.itens()["100"].comprimento_mm, 6000)

        r = importar_arquivo(self.fornecedor, "codigo;nome;valor\n100;TRILHO SUPERIOR;70,00\n".encode())
        self.assertEqual((r["criados"], r["alterados"], r["desativados"]), (0, 1, 1))
        self.assertEqual(str(self.itens()["100"].preco), "70.00")
        self.assertFalse(self.itens()["200"].ativo)

    def test_valor_absurdo_vira_aviso_na_linha_e_o_resto_entra(self):
        planilha = ("codigo;nome;valor;comprimento_mm\n"
                    "1;INFINITO;Infinity;\n"
                    "2;ENORME;99999999999999,00;\n"
                    "3;NEGATIVO;-5,00;\n"
                    "4;BARRA DE 1 KM;10,00;99999999999\n"
                    "5;BOM;10,00;6000\n").encode()
        r = importar_arquivo(self.fornecedor, planilha, desativar_ausentes=False)
        self.assertEqual(r["criados"], 1)
        self.assertEqual(len(r["erros"]), 4)
        self.assertEqual(list(self.itens()), ["5"])

    def test_planilha_sem_as_colunas_e_recusada_com_explicacao(self):
        r = importar_arquivo(self.fornecedor, b"a;b\n1;2\n")
        self.assertIn("Faltam as colunas", r["erro_geral"])

    def test_pdf_corrompido_nao_derruba_o_servidor(self):
        r = importar_arquivo(self.fornecedor, b"%PDF-1.4 isto nao e um pdf de verdade")
        self.assertIn("erro_geral", r)
        self.assertEqual(self.itens(), {})

    def test_ler_planilha_nao_muda_o_separador_padrao_do_python(self):
        with self.assertRaises(ValueError):  # faltam colunas; o que importa é o separador abaixo
            ler_csv(b"codigo\n")  # uma coluna só: o separador não pode ser deduzido
        self.assertEqual(csv.excel.delimiter, ",")


class TelaDeImportacaoNoAdmin(TesteApi):
    def setUp(self):
        super().setUp()
        self.fornecedor = Fornecedor.objects.create(nome="Tabela", slug="tabela", adaptador="manual",
                                                    variavel_chave="SEM_CHAVE")
        self.url = f"/admin/fornecedores/fornecedor/{self.fornecedor.pk}/importar/"

    def navegador(self, vidraceiro):
        c = Client()
        c.force_login(vidraceiro)
        return c

    def enviar(self, navegador):
        arquivo = SimpleUploadedFile("tabela.csv", PLANILHA, content_type="text/csv")
        return navegador.post(self.url, {"arquivo": arquivo, "desativar": "on"})

    def test_vidraceiro_comum_nao_entra(self):
        self.assertEqual(self.navegador(self.ana).get(self.url).status_code, 302)  # vai para o login do admin
        self.enviar(self.navegador(self.ana))
        self.assertEqual(ItemFornecedor.objects.count(), 0)

    def test_equipe_sem_permissao_de_editar_fornecedor_e_barrada(self):
        ajudante = criar_vidraceiro("ajudante@exemplo.com", is_staff=True)
        self.assertEqual(self.navegador(ajudante).get(self.url).status_code, 403)
        self.assertEqual(self.enviar(self.navegador(ajudante)).status_code, 403)
        self.assertEqual(ItemFornecedor.objects.count(), 0)

    def test_equipe_com_a_permissao_importa(self):
        editor = criar_vidraceiro("editor@exemplo.com", is_staff=True)
        editor.user_permissions.add(Permission.objects.get(codename="change_fornecedor"),
                                    Permission.objects.get(codename="view_fornecedor"))
        self.assertEqual(self.navegador(editor).get(self.url).status_code, 200)
        self.assertEqual(self.enviar(self.navegador(editor)).status_code, 302)
        self.assertEqual(ItemFornecedor.objects.count(), 2)


class MargemPorPeca(TesteApi):
    def projeto(self, margem_valor):
        cliente = criar_cliente(self.ana)
        agora = timezone.now()
        fornecedor = Fornecedor.objects.create(nome="Catálogo", slug="catalogo", variavel_chave="SEM_CHAVE")
        item = ItemFornecedor.objects.create(fornecedor=fornecedor, codigo="P-01", descricao="Trilho", unidade="UN",
                                             preco="25.00", atualizado_em=agora, visto_em=agora)
        linha = {"nome": "Janela", "largura_mm": 1000, "altura_mm": 1000, "quantidade": 1,
                 "itens": [{"item": item.pk, "ajuste": 1}],
                 "margem_tipo": "percentual", "margem_valor": margem_valor}
        return self.api_ana.post("/api/v1/projetos/", {"nome": "Sala", "cliente": str(cliente.pk), "linhas": [linha]},
                                 format="json")

    def test_margem_negativa_e_recusada_ao_salvar(self):
        r = self.projeto("-50")
        self.assertEqual(r.status_code, 400)
        self.assertIn("margem_valor", r.data["linhas"][0])

    def test_margem_normal_e_gravada(self):
        r = self.projeto("35.5")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["linhas"][0]["margem_valor"], "35.50")
