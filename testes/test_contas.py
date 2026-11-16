import base64
import uuid
from io import BytesIO

from PIL import Image
from rest_framework.test import APIClient

from .base import SENHA, TesteApi

CADASTRO = dict(nome="Carla", celular="84988887777", cpf_cnpj="123.456.789-01", rua="Rua B", numero="2",
                bairro="Centro", cidade="Natal", estado="RN")


def imagem_base64(tamanho, formato="PNG", modo="1"):
    saida = BytesIO()
    Image.new(modo, tamanho).save(saida, format=formato)
    return base64.b64encode(saida.getvalue()).decode()


class Cadastro(TesteApi):
    def cadastrar(self, senha, **extra):
        dados = {**CADASTRO, "email": f"{uuid.uuid4().hex[:8]}@exemplo.com", "password": senha, **extra}
        return APIClient().post("/api/v1/vidraceiros/", dados, format="json")

    def test_senha_curta_e_recusada(self):
        self.assertEqual(self.cadastrar("abc123").status_code, 400)

    def test_senha_so_de_numeros_e_recusada(self):
        self.assertEqual(self.cadastrar("48151623").status_code, 400)

    def test_senha_muito_comum_e_recusada(self):
        self.assertEqual(self.cadastrar("password123").status_code, 400)

    def test_senha_boa_cria_a_conta_e_devolve_tokens(self):
        r = self.cadastrar(SENHA)
        self.assertEqual(r.status_code, 201, r.data)
        self.assertIn("access", r.data)
        self.assertNotIn("password", r.data["vidraceiro"])

    def test_id_de_outra_conta_e_recusado_sem_erro_500(self):
        r = self.cadastrar(SENHA, id=str(self.ana.pk))
        self.assertEqual(r.status_code, 400)


class LimiteDeLogin(TesteApi):
    def tentar(self, email, cabecalho_xff):
        return APIClient().post("/api/v1/auth/login/", {"email": email, "password": "errada-000"},
                                format="json", HTTP_X_FORWARDED_FOR=cabecalho_xff)

    def test_trocar_o_x_forwarded_for_nao_burla_o_limite_por_ip(self):
        # O Nginx acrescenta o IP real no FIM do cabeçalho; o começo é o que o cliente mandou.
        codigos = [self.tentar(f"alvo{i}@exemplo.com", f"10.0.0.{i}, 203.0.113.7").status_code for i in range(12)]
        self.assertEqual(codigos[:10], [401] * 10)
        self.assertEqual(codigos[10:], [429, 429])

    def test_muitas_tentativas_na_mesma_conta_sao_barradas_mesmo_de_ips_diferentes(self):
        codigos = [self.tentar("ana@exemplo.com", f"198.51.100.{i}").status_code for i in range(22)]
        self.assertEqual(codigos[:20], [401] * 20)
        self.assertEqual(codigos[20:], [429, 429])

    def test_login_certo_funciona(self):
        r = APIClient().post("/api/v1/auth/login/", {"email": "ANA@exemplo.com ", "password": SENHA}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["vidraceiro"]["email"], "ana@exemplo.com")


class Logomarca(TesteApi):
    URL = "/api/v1/vidraceiros/me/logo/"

    def test_png_normal_e_aceito(self):
        r = self.api_ana.post(self.URL, {"imagem_base64": imagem_base64((300, 200), modo="RGB")}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertTrue(r.data["logo_data_uri"].startswith("data:image/png;base64,"))
        self.ana.refresh_from_db()
        self.ana.logo.delete(save=True)  # não deixa arquivo de teste no disco

    def test_imagem_com_pixels_demais_e_recusada(self):
        gigante = imagem_base64((10000, 9000))  # 90 milhões de pixels em poucos KB
        r = self.api_ana.post(self.URL, {"imagem_base64": gigante}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_formato_fora_da_lista_e_recusado(self):
        r = self.api_ana.post(self.URL, {"imagem_base64": imagem_base64((10, 10), formato="BMP")}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_texto_qualquer_e_recusado(self):
        r = self.api_ana.post(self.URL, {"imagem_base64": "isto não é imagem"}, format="json")
        self.assertEqual(r.status_code, 400)


class SemLogin(TesteApi):
    def test_rotas_exigem_token(self):
        for rota in ("/api/v1/clientes/", "/api/v1/projetos/", "/api/v1/painel/", "/api/v1/vidraceiros/me/",
                     "/api/v1/financeiro/lancamentos/", "/api/v1/estoque/itens/", "/api/v1/pedidos/"):
            self.assertEqual(APIClient().get(rota).status_code, 401, rota)
