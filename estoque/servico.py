"""Regras do estoque: unidades, saldos, baixa das obras e entradas."""

from decimal import Decimal

from django.db.models import Sum

from produtos.calculo import calcular_componente, modo

from .models import ConfigItemEstoque, Movimento

MIL = Decimal(1000)
CEM = Decimal(100)


# ---------- Unidades ----------

def unidade_estoque(item):
    """Perfis e itens por metro: m. Vidro: m². O resto: a unidade de venda."""
    m = modo(item)
    if m in ("peca_comprimento", "metro"):
        return "m"
    if m == "area":
        return "m²"
    return (item.unidade or "un").lower()


def fator_compra(item):
    """Quantas unidades de estoque há em 1 unidade de compra (1 barra = 6 m)."""
    if modo(item) == "peca_comprimento" and item.comprimento_mm:
        return Decimal(item.comprimento_mm) / MIL
    return Decimal(1)


def para_estoque(item, quantidade_compra):
    return Decimal(quantidade_compra) * fator_compra(item)


def descrever(item, quantidade):
    """'36 m (6 barras)' para perfis; '20 un' para o resto."""
    q = Decimal(quantidade).quantize(Decimal("0.001")).normalize()
    br = lambda d: f"{d:f}".replace(".", ",")  # vírgula decimal
    texto = f"{br(q)} {unidade_estoque(item)}"
    if modo(item) == "peca_comprimento" and item.comprimento_mm:
        barras = (q / fator_compra(item)).quantize(Decimal("0.1")).normalize()
        texto += f" (≈ {br(barras)} barras)"
    return texto


# ---------- Saldos e custo ----------

def saldos(vidraceiro, itens_ids=None):
    """{item_id: saldo} na unidade de estoque."""
    qs = Movimento.objects.filter(vidraceiro=vidraceiro)
    if itens_ids is not None:
        qs = qs.filter(item_id__in=itens_ids)
    return {r["item"]: r["saldo"] or Decimal(0) for r in qs.values("item").annotate(saldo=Sum("quantidade"))}


def custo_medio(vidraceiro, item):
    """Média ponderada das entradas com custo; sem entradas, o preço do catálogo."""
    entradas = Movimento.objects.filter(vidraceiro=vidraceiro, item=item, quantidade__gt=0, custo_unitario__isnull=False)
    qtd = valor = Decimal(0)
    for m in entradas.only("quantidade", "custo_unitario"):
        qtd += m.quantidade
        valor += m.quantidade * m.custo_unitario
    if qtd > 0:
        return valor / qtd
    return Decimal(item.preco) / fator_compra(item)


def minimos(vidraceiro):
    return {c.item_id: c.minimo for c in ConfigItemEstoque.objects.filter(vidraceiro=vidraceiro)}


# ---------- Baixa das obras ----------

def consumo_das_pecas(projeto, todas=False):
    """{item: consumo} das peças concluídas (ou de todas), na unidade de estoque.
    Perfis e itens por metro levam a perda de corte do projeto."""
    perda = 1 + (projeto.perda_percentual or 0) / CEM
    total = {}
    for linha in projeto.linhas.prefetch_related("itens__item").all():
        if not (todas or linha.concluida):
            continue
        for it in linha.itens.all():
            c = calcular_componente(
                it.item, it.coef_largura, it.coef_altura, it.coef_area, it.ajuste,
                linha.largura_mm, linha.altura_mm, quantidade=linha.quantidade, cobranca=it.cobranca,
            )
            q = Decimal(c["consumo"]) * linha.quantidade
            if modo(it.item) in ("peca_comprimento", "metro"):
                q *= perda
            total[it.item] = total.get(it.item, Decimal(0)) + q
    return total


def sincronizar_baixas(projeto):
    """Deixa a saída de material da obra igual ao consumo das peças concluídas
    (ou de todas, com o projeto concluído). Peça desmarcada: o material volta.
    Pode ser chamada quantas vezes for preciso: só registra a diferença."""
    v = projeto.vidraceiro
    if not v.tem_pro:
        return
    alvo = consumo_das_pecas(projeto, todas=projeto.status == "concluido")
    ja = {
        r["item"]: -(r["total"] or 0)
        for r in Movimento.objects.filter(vidraceiro=v, projeto=projeto, motivo=Movimento.Motivo.OBRA)
        .values("item").annotate(total=Sum("quantidade"))
    }
    itens = {i.pk: i for i in alvo}
    for item_id in set(ja) | set(itens):
        item = itens.get(item_id)
        objetivo = alvo.get(item, Decimal(0)) if item else Decimal(0)
        diferenca = objetivo - Decimal(ja.get(item_id, 0))
        if abs(diferenca) < Decimal("0.0005"):
            continue
        Movimento.objects.create(
            vidraceiro=v, item_id=item_id, quantidade=-diferenca, motivo=Movimento.Motivo.OBRA, projeto=projeto,
            observacao=(f"Obra: {projeto.nome}" if diferenca > 0 else f"Devolução (peça desmarcada): {projeto.nome}"),
        )


def tentar_sincronizar(projeto):
    """Para os fluxos do projeto: o estoque nunca pode travar o salvamento."""
    try:
        sincronizar_baixas(projeto)
    except Exception:  # noqa: BLE001
        import logging

        logging.getLogger(__name__).exception("Falha ao dar baixa no estoque do projeto %s", projeto.pk)


# ---------- Entradas ----------

def receber_pedido(pedido):
    """Entrada dos itens do pedido (barras viram metros), uma única vez."""
    if Movimento.objects.filter(pedido=pedido).exists():
        return 0
    n = 0
    for ip in pedido.itens.select_related("item").all():
        fator = fator_compra(ip.item)
        Movimento.objects.create(
            vidraceiro=pedido.vidraceiro, item=ip.item, quantidade=ip.quantidade * fator,
            custo_unitario=ip.preco_unitario / fator, motivo=Movimento.Motivo.PEDIDO,
            pedido=pedido, projeto=pedido.projeto,
            observacao=f"Pedido {pedido.numero_fornecedor or ''} {pedido.fornecedor.nome}".strip(),
        )
        n += 1
    return n


def enriquecer_lista_compra(vidraceiro, lista):
    """Na lista de compra do projeto: quanto há em estoque de cada item (Pro)."""
    if not vidraceiro.tem_pro or not lista:
        return
    from fornecedores.models import ItemFornecedor

    itens = {i.pk: i for i in ItemFornecedor.objects.filter(pk__in=[x["item"] for x in lista])}
    s = saldos(vidraceiro, list(itens))
    for x in lista:
        item = itens.get(x["item"])
        saldo = Decimal(s.get(x["item"], 0))
        x["estoque_disponivel"] = format(saldo.quantize(Decimal("0.001")).normalize(), "f")
        # Em unidades de compra (barras inteiras para perfis), para o campo "Do meu estoque".
        x["estoque_disponivel_compra"] = format(
            (saldo / fator_compra(item)).quantize(Decimal("0.001")).normalize() if item else saldo, "f"
        )
        x["estoque_texto"] = descrever(item, saldo) if item else ""
