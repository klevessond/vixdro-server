"""Formas de pagamento: valores de cada condição para um total de orçamento."""

from decimal import ROUND_DOWN, Decimal

from .models import CONDICOES_INICIAIS, CONTAS_INICIAIS, CondicaoPagamento, Conta

CENTAVO = Decimal("0.01")
CEM = Decimal(100)


def garantir_condicoes(vidraceiro):
    """Cria as sugestões na primeira vez (se o vidraceiro nunca teve nenhuma)."""
    if not CondicaoPagamento.objects.filter(vidraceiro=vidraceiro).exists():
        for i, dados in enumerate(CONDICOES_INICIAIS):
            CondicaoPagamento.objects.create(vidraceiro=vidraceiro, ordem=i, **dados)


def garantir_contas(vidraceiro):
    if not Conta.objects.filter(vidraceiro=vidraceiro).exists():
        for i, dados in enumerate(CONTAS_INICIAIS):
            Conta.objects.create(vidraceiro=vidraceiro, ordem=i, **dados)


def simular(cond, total, parcelas=None):
    """Quanto o cliente paga nesta condição. parcelas: escolhida (até o máximo)."""
    total = Decimal(total)
    if cond.tipo == CondicaoPagamento.Tipo.AVISTA:
        final = (total * (1 - cond.desconto_percentual / CEM)).quantize(CENTAVO)
        return {"total": final, "entrada": Decimal(0), "parcelas": 1, "valor_parcela": final}
    final = (total * (1 + cond.acrescimo_percentual / CEM)).quantize(CENTAVO)
    n = max(1, min(int(parcelas or cond.max_parcelas), cond.max_parcelas))
    entrada = Decimal(0)
    if cond.tipo == CondicaoPagamento.Tipo.ENTRADA:
        entrada = (final * cond.entrada_percentual / CEM).quantize(CENTAVO)
    resto = final - entrada
    parcela = (resto / n).quantize(CENTAVO, rounding=ROUND_DOWN) if resto > 0 else Decimal(0)
    return {"total": final, "entrada": entrada, "parcelas": n, "valor_parcela": parcela}


def condicoes_para_orcamento(vidraceiro, total):
    """As condições ativas com os valores já calculados (para o PDF)."""
    garantir_condicoes(vidraceiro)
    saida = []
    for c in CondicaoPagamento.objects.filter(vidraceiro=vidraceiro, ativo=True):
        v = simular(c, total)
        saida.append({
            "id": str(c.id), "nome": c.nome, "tipo": c.tipo,
            "desconto_percentual": str(c.desconto_percentual), "acrescimo_percentual": str(c.acrescimo_percentual),
            "entrada_percentual": str(c.entrada_percentual),
            "total": str(v["total"]), "entrada": str(v["entrada"]),
            "parcelas": v["parcelas"], "valor_parcela": str(v["valor_parcela"]),
        })
    return saida
