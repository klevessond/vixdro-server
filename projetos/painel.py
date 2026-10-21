"""Números da tela inicial, numa consulta só (para o app abrir rápido)."""

from datetime import timedelta

from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from clientes.models import Cliente
from fornecedores.models import ItemFornecedor
from produtos.models import Componente, Produto

from agenda.views import resumo_agenda
from contas.planos import resumo_plano

from .models import Projeto
from .views import orcamentos_parados

DIAS_PRECO_NOVO = 7


class PainelView(APIView):
    """GET /api/v1/painel/  (exige login)"""

    def get(self, request):
        v = request.user
        agora = timezone.now()
        inicio_mes = agora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        clientes = Cliente.objects.filter(vidraceiro=v, ativo=True)
        projetos = Projeto.objects.filter(vidraceiro=v, ativo=True)

        # Itens usados nos produtos do vidraceiro cujo preço o fornecedor mudou há pouco.
        itens_usados = Componente.objects.filter(produto__vidraceiro=v, produto__ativo=True).values("item_id")
        precos_novos = ItemFornecedor.objects.filter(
            pk__in=itens_usados, ativo=True, atualizado_em__gte=agora - timedelta(days=DIAS_PRECO_NOVO)
        ).count()

        # Perfil da empresa: o que aparece no orçamento em PDF.
        checagens = {
            "logomarca": bool(v.logo),
            "nome da empresa": bool(v.empresa),
            "CPF/CNPJ": bool(v.cpf_cnpj),
            "celular": bool(v.celular),
            "endereço": bool(v.rua and v.cidade),
        }
        faltando = [nome for nome, ok in checagens.items() if not ok]

        return Response({
            "clientes": {
                "total": clientes.count(),
                "novos_mes": clientes.filter(criado_em__gte=inicio_mes).count(),
            },
            "projetos": {
                "ativos": projetos.exclude(status=Projeto.Status.RECUSADO).count(),
                "aguardando_cliente": projetos.filter(status=Projeto.Status.ENVIADO).count(),
                # Lembrete: enviados ao cliente e sem resposta há mais de N dias.
                "parados": orcamentos_parados(v).count(),
                "dias_lembrete": v.dias_lembrete,
            },
            "precos": {
                "margem_padrao": str(v.margem_padrao),
                "itens_preco_novo": precos_novos,
                "dias": DIAS_PRECO_NOVO,
            },
            "agenda": resumo_agenda(v),
            "plano": {k: val for k, val in resumo_plano(v).items() if k != "recursos"},
            "produtos": Produto.objects.filter(vidraceiro=v, ativo=True).count(),
            "meus_itens": ItemFornecedor.objects.filter(fornecedor__vidraceiro=v, ativo=True).count(),
            "empresa": {
                "percentual": round(100 * (len(checagens) - len(faltando)) / len(checagens)),
                "faltando": faltando,
                "logo_url": request.build_absolute_uri(v.logo.url) if v.logo else None,
            },
        })
