"""Cálculo de consumo e custo. Fonte única da regra: o app e o site
pedem o cálculo ao servidor, para os dois nunca divergirem."""

from decimal import ROUND_CEILING, Decimal

MIL = Decimal(1000)
CENTAVO = Decimal("0.01")
MILESIMO = Decimal("0.001")

# Unidades que só existem em quantidades inteiras (não se compra meia roldana).
DISCRETAS = {"UN", "PC", "PÇ", "PAR", "CX", "JG", "KIT", "CJ"}

UNIDADE_CONSUMO = {
    "peca_comprimento": "m",
    "metro": "m",
    "area": "m²",
    "unidade": "un",
}


def modo(item):
    """Como o consumo do item é medido."""
    if item.comprimento_mm:
        return "peca_comprimento"  # barra de 6 m, rolo: consome metros, compra peças
    if item.unidade == "M":
        return "metro"
    if item.unidade == "M2":
        return "area"
    return "unidade"


# Como um item vendido em barra é cobrado:
#   "inteira": pelas barras inteiras que a peça precisa (padrão)
#   "metro":   só pelos metros usados (o resto da barra fica como sobra)
COBRANCA_INTEIRA = "inteira"
COBRANCA_METRO = "metro"


def calcular_componente(item, coef_largura, coef_altura, coef_area, ajuste, largura_mm, altura_mm,
                        quantidade=1, cobranca=COBRANCA_INTEIRA):
    """Consumo e custo de um item numa peça.

    quantidade: quantas unidades da peça (ex: 4 janelas iguais). O arredondamento
    para barras inteiras é feito sobre o TOTAL das unidades, e não unidade por
    unidade: 4 janelas que usam 2 m cada (8 m) pagam 2 barras, e não 4.
    """
    L = Decimal(largura_mm) / MIL
    A = Decimal(altura_mm) / MIL
    consumo = coef_largura * L + coef_altura * A + coef_area * L * A + ajuste
    if consumo < 0:
        consumo = Decimal(0)

    m = modo(item)
    if m == "unidade" and item.unidade in DISCRETAS:
        consumo = consumo.to_integral_value(rounding=ROUND_CEILING)

    quantidade = Decimal(quantidade or 1)
    consumo_total = consumo * quantidade
    pecas = None
    barras_cobradas = None
    if m == "peca_comprimento":
        comprimento_m = Decimal(item.comprimento_mm) / MIL
        pecas = consumo / comprimento_m
        if cobranca == COBRANCA_METRO:
            # 8 m de uma barra de 6 m = 1,333 barra.
            custo_total = consumo_total / comprimento_m * item.preco
        else:
            # 8 m pedem 2 barras inteiras.
            barras_cobradas = (consumo_total / comprimento_m).to_integral_value(rounding=ROUND_CEILING)
            custo_total = barras_cobradas * item.preco
    else:
        custo_total = consumo_total * item.preco
    custo = custo_total / quantidade  # por unidade da peça

    return {
        "item": item.pk,
        "codigo": item.codigo,
        "descricao": item.descricao,
        "item_ativo": item.ativo,
        "modo": m,
        "consumo": str(consumo.quantize(MILESIMO)),
        "unidade_consumo": UNIDADE_CONSUMO[m],
        "pecas": str(pecas.quantize(MILESIMO)) if pecas is not None else None,
        "comprimento_mm": item.comprimento_mm,
        "preco_unitario": str(item.preco),
        "cobranca": cobranca if m == "peca_comprimento" else None,
        "barras_cobradas": str(barras_cobradas) if barras_cobradas is not None else None,
        "custo": str(custo.quantize(CENTAVO)),
        "custo_total": str(custo_total.quantize(CENTAVO)),
    }


def calcular_produto(componentes, largura_mm, altura_mm):
    """componentes: lista de dicts com item (ItemFornecedor), coeficientes, ajuste e observacao."""
    linhas = []
    total = Decimal(0)
    for c in componentes:
        linha = calcular_componente(
            c["item"], c.get("coef_largura", 0), c.get("coef_altura", 0),
            c.get("coef_area", 0), c.get("ajuste", 0), largura_mm, altura_mm,
            cobranca=c.get("cobranca", COBRANCA_INTEIRA),
        )
        linha["observacao"] = c.get("observacao", "")
        total += Decimal(linha["custo"])
        linhas.append(linha)
    return {
        "largura_mm": largura_mm,
        "altura_mm": altura_mm,
        "linhas": linhas,
        "custo_total": str(total.quantize(CENTAVO)),
    }
