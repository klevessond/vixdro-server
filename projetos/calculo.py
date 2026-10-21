"""Custo do projeto e lista de compra.

- Custo de cada linha: proporcional (0,4 barra paga 0,4 barra), como no produto.
- Lista de compra: soma o consumo de cada item em TODAS as linhas e só
  então arredonda para o que se compra de fato (barras inteiras), com a
  perda de corte do projeto.
"""

from decimal import ROUND_CEILING, Decimal

from produtos.calculo import CENTAVO, DISCRETAS, MIL, MILESIMO, calcular_componente, modo

PRECIFICACAO_PADRAO = {
    "margem_percentual": Decimal(0),
    "mao_de_obra_m2": Decimal(0),
    "mao_de_obra_minima": Decimal(0),
    "descricao_adicional": "",
    "valor_adicional": Decimal(0),
    "desconto": Decimal(0),
}

ORDEM_MODO = {"peca_comprimento": 0, "metro": 1, "area": 2, "unidade": 3}


def calcular_projeto(linhas, perda_percentual, precificacao=None, estoque_usado=None):
    """precificacao: margem, mão de obra, adicional e desconto (dict). Opcional."""
    pr = {**PRECIFICACAO_PADRAO, **(precificacao or {})}
    fator_perda = 1 + Decimal(perda_percentual) / 100
    fator_margem = 1 + Decimal(pr["margem_percentual"]) / 100
    subtotal = Decimal(0)
    total_mao_de_obra = Decimal(0)
    total_material_com_perda = Decimal(0)
    acumulado = {}  # item.pk -> {"item", "consumo"}
    resultado_linhas = []
    custo_materiais = Decimal(0)

    for ln in linhas:
        qtd = ln.get("quantidade", 1)
        itens = []
        custo_linha = Decimal(0)
        for it in ln["itens"]:
            # Cada item da peça é cobrado pela barra inteira (padrão) ou pelos
            # metros usados, conforme escolhido. A perda de corte não entra no
            # preço: ela serve só para decidir quantas barras comprar.
            c = calcular_componente(
                it["item"], it.get("coef_largura", 0), it.get("coef_altura", 0),
                it.get("coef_area", 0), it.get("ajuste", 0), ln["largura_mm"], ln["altura_mm"],
                quantidade=qtd, cobranca=it.get("cobranca", "inteira"),
            )
            c["observacao"] = it.get("observacao", "")
            custo_linha += Decimal(c["custo_total"])
            itens.append(c)
            a = acumulado.setdefault(it["item"].pk, {"item": it["item"], "consumo": Decimal(0)})
            a["consumo"] += Decimal(c["consumo"]) * qtd

        custo_unitario = custo_linha / qtd
        material_com_perda = custo_unitario
        custo_materiais += custo_linha

        # Preço para o cliente: material (com perda) + margem + mão de obra.
        area_m2 = Decimal(ln["largura_mm"]) * Decimal(ln["altura_mm"]) / Decimal(1_000_000)
        # Peça sem área (sem largura ou sem altura, ex: acessórios avulsos):
        # não cobra mão de obra, nem o mínimo por peça.
        if area_m2 > 0:
            mao_de_obra = max(area_m2 * Decimal(pr["mao_de_obra_m2"]), Decimal(pr["mao_de_obra_minima"]))
        else:
            mao_de_obra = Decimal(0)
        preco_unitario = (material_com_perda * fator_margem + mao_de_obra).quantize(CENTAVO)
        preco_total = preco_unitario * qtd
        subtotal += preco_total
        total_mao_de_obra += mao_de_obra * qtd
        total_material_com_perda += material_com_perda * qtd

        resultado_linhas.append({
            "nome": ln["nome"],
            "largura_mm": ln["largura_mm"],
            "altura_mm": ln["altura_mm"],
            "quantidade": qtd,
            "area_m2": str(area_m2.quantize(MILESIMO)),
            "custo_unitario": str(custo_unitario.quantize(CENTAVO)),
            "custo_total": str(custo_linha.quantize(CENTAVO)),
            "mao_de_obra_unitaria": str(mao_de_obra.quantize(CENTAVO)),
            "preco_unitario": str(preco_unitario),
            "preco_total": str(preco_total.quantize(CENTAVO)),
            "itens": itens,
        })

    lista_compra = []
    custo_compra = Decimal(0)
    estoque_usado = estoque_usado or {}
    for a in acumulado.values():
        item, consumo = a["item"], a["consumo"]
        m = modo(item)
        sobra = None
        if m == "peca_comprimento":
            comprimento_m = Decimal(item.comprimento_mm) / MIL
            quantidade = (consumo * fator_perda / comprimento_m).to_integral_value(rounding=ROUND_CEILING)
            unidade_compra = "peça"
            sobra = quantidade * comprimento_m - consumo
        elif m == "metro":
            quantidade = (consumo * fator_perda).quantize(CENTAVO, rounding=ROUND_CEILING)
            unidade_compra = "m"
        elif m == "area":
            # Vidro é cortado sob medida: sem perda.
            quantidade = consumo.quantize(MILESIMO)
            unidade_compra = "m²"
        else:
            quantidade = consumo
            if item.unidade in DISCRETAS:
                quantidade = quantidade.to_integral_value(rounding=ROUND_CEILING)
            unidade_compra = item.unidade.lower()

        # O que sai do estoque do vidraceiro não é pedido nem comprado.
        do_estoque = min(Decimal(str(estoque_usado.get(str(item.pk), 0) or 0)), quantidade)
        pedir = quantidade - do_estoque
        custo = quantidade * item.preco
        custo_pedir = pedir * item.preco
        custo_compra += custo_pedir
        lista_compra.append({
            "item": item.pk,
            "codigo": item.codigo,
            "descricao": item.descricao,
            "item_ativo": item.ativo,
            "modo": m,
            "consumo_total": str(consumo.quantize(MILESIMO)),
            "comprimento_mm": item.comprimento_mm,
            "quantidade_compra": format(quantidade.normalize(), "f"),  # 10 -> "10", 2.50 -> "2.5"
            "quantidade_estoque": format(do_estoque.normalize(), "f"),
            "quantidade_pedir": format(pedir.normalize(), "f"),
            "custo_pedir": str(custo_pedir.quantize(CENTAVO)),
            "unidade_compra": unidade_compra,
            "sobra_m": str(sobra.quantize(MILESIMO)) if sobra is not None else None,
            "preco_unitario": str(item.preco),
            "custo": str(custo.quantize(CENTAVO)),
        })

    lista_compra.sort(key=lambda x: (ORDEM_MODO[x["modo"]], x["codigo"]))

    adicional = Decimal(pr["valor_adicional"])
    desconto = Decimal(pr["desconto"])
    total = max(subtotal + adicional - desconto, Decimal(0))
    material_com_margem = total_material_com_perda * fator_margem
    orcamento = {
        # O que o cliente vê
        "subtotal": str(subtotal.quantize(CENTAVO)),
        "descricao_adicional": pr["descricao_adicional"],
        "valor_adicional": str(adicional.quantize(CENTAVO)),
        "desconto": str(desconto.quantize(CENTAVO)),
        "total": str(total.quantize(CENTAVO)),
        # Só para o vidraceiro
        "material_com_perda": str(total_material_com_perda.quantize(CENTAVO)),
        "lucro_material": str((material_com_margem - total_material_com_perda).quantize(CENTAVO)),
        "mao_de_obra": str(total_mao_de_obra.quantize(CENTAVO)),
    }

    return {
        "orcamento": orcamento,
        "perda_percentual": str(perda_percentual),
        "linhas": resultado_linhas,
        "custo_materiais": str(custo_materiais.quantize(CENTAVO)),
        "lista_compra": lista_compra,
        "custo_compra": str(custo_compra.quantize(CENTAVO)),
    }
