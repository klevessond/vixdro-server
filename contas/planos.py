"""Planos da conta: o que é Pro e como um recurso pago se protege.

Para tornar um recurso exclusivo do Pro, basta acrescentar RequerPro às
permissões da view:

    class FinanceiroViewSet(viewsets.ModelViewSet):
        permission_classes = [IsAuthenticated, RequerPro]

A verificação fica no servidor: esconder o botão no app não basta, porque a
API pode ser chamada diretamente.
"""

from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission

CODIGO_REQUER_PRO = "requer_pro"

# O que cada plano inclui (mostrado na tela "Meu plano" do app).
RECURSOS = {
    "gratuito": [
        "Orçamentos ilimitados, com PDF para o cliente",
        "Clientes, produtos e itens próprios",
        "Pedidos ao fornecedor",
        "Lembretes de orçamentos sem resposta",
        "Fotos e anotações da medição",
    ],
    "pro": [
        "Tudo do plano gratuito",
        "Agenda de medições e instalações, com mapa e aviso ao cliente",
        "Financeiro: contas a receber e a pagar, parcelas e fluxo de caixa",
        "Estoque de perfis e sobras (em breve)",
        "Relatórios de vendas e margem (em breve)",
    ],
}


class RequerPro(BasePermission):
    """Recusa com um código que o app reconhece, para mostrar o aviso do plano."""

    def has_permission(self, request, view):
        if getattr(request.user, "tem_pro", False):
            return True
        raise PermissionDenied(detail={
            "detail": "Este recurso faz parte do plano Pro.",
            "codigo": CODIGO_REQUER_PRO,
        })


def resumo_plano(v):
    hoje = timezone.localdate()
    dias_restantes = (v.plano_validade - hoje).days if (v.plano == "pro" and v.plano_validade) else None
    return {
        "plano": "pro" if v.tem_pro else "gratuito",
        "pro": v.tem_pro,
        "validade": v.plano_validade.isoformat() if (v.tem_pro and v.plano_validade) else None,
        "dias_restantes": dias_restantes if v.tem_pro else None,
        "expirado": v.plano == "pro" and not v.tem_pro,  # era Pro e venceu
        "recursos": RECURSOS,
    }
