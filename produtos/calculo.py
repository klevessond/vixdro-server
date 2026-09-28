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


def calcular_componente(item, coef_largura, coef_altura, coef_area, ajuste, largura_mm, altura_mm):
    L = Decimal(largura_mm) / MIL
    A = Decimal(altura_mm) / MIL
    consumo = coef_largura * L + coef_altura * A + coef_area * L * A + ajuste
    if consumo < 0:
        consumo = Decimal(0)

    m = modo(item)
    if m == "unidade" and item.unidade in DISCRETAS:
        consumo = consumo.to_integral_value(rounding=ROUND_CEILING)

    pecas = None
    if m == "peca_comprimento":
        # Custo proporcional: 2,40 m de uma barra de 6 m = 0,4 barra.
        # A compra em barras inteiras é calculada no projeto, somando tudo.
        pecas = consumo / (Decimal(item.comprimento_mm) / MIL)
        custo = pecas * item.preco
    else:
        custo = consumo * item.preco

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
        "custo": str(custo.quantize(CENTAVO)),
    }


def calcular_produto(componentes, largura_mm, altura_mm):
    """componentes: lista de dicts com item (ItemFornecedor), coeficientes, ajuste e observacao."""
    linhas = []
    total = Decimal(0)
    for c in componentes:
        linha = calcular_componente(
            c["item"], c.get("coef_largura", 0), c.get("coef_altura", 0),
            c.get("coef_area", 0), c.get("ajuste", 0), largura_mm, altura_mm,
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
