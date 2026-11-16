"""Criação, envio e acompanhamento de pedidos aos fornecedores."""

import logging
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from fornecedores.adaptadores import ErroFornecedor, adaptador_para
from fornecedores.models import ItemFornecedor
from projetos.models import Projeto
from projetos.views import calcular_projeto_salvo

from .models import ItemPedido, Pedido

log = logging.getLogger(__name__)

STATUS_DO_FORNECEDOR = {
    "recebido": Pedido.Status.RECEBIDO,
    "em_separacao": Pedido.Status.EM_SEPARACAO,
    "faturado": Pedido.Status.FATURADO,
    "cancelado": Pedido.Status.CANCELADO,
}


def criar_pedidos(projeto, vidraceiro):
    if projeto.status != Projeto.Status.APROVADO:
        raise ValidationError("Marque o orçamento como aprovado antes de enviar o pedido.")
    _recusar_se_ja_pedido(projeto)

    # Só o que falta comprar: o que sai do estoque do vidraceiro não é pedido.
    lista = [x for x in calcular_projeto_salvo(projeto)["lista_compra"] if Decimal(x["quantidade_pedir"]) > 0]
    if not lista:
        raise ValidationError("Nada a pedir: todos os itens deste projeto saem do seu estoque.")

    itens = ItemFornecedor.objects.select_related("fornecedor").in_bulk([x["item"] for x in lista])
    por_fornecedor = defaultdict(list)
    for x in lista:
        fornecedor = itens[x["item"]].fornecedor
        # Itens próprios do vidraceiro (ex: vidros) são comprados fora: não entram no pedido.
        # Só os fornecedores integrados recebem pedido automático. Itens próprios e
        # de fornecedores por planilha são comprados por fora (lista de compra em PDF).
        if fornecedor.vidraceiro_id is None and fornecedor.integrado:
            por_fornecedor[fornecedor].append(x)
    if not por_fornecedor:
        raise ValidationError("Este projeto só tem itens comprados por fora (próprios ou de fornecedor sem integração): use a lista de compra em PDF.")

    pedidos = []
    with transaction.atomic():
        # Trava o projeto e confere de novo: dois toques seguidos em "enviar
        # pedido" chegam ao mesmo tempo, os dois passavam pela conferência lá de
        # cima e o fornecedor recebia o pedido em dobro. Com a trava, o segundo
        # espera o primeiro gravar e é recusado aqui.
        Projeto.objects.select_for_update().get(pk=projeto.pk)
        _recusar_se_ja_pedido(projeto)
        # Pedidos anteriores que falharam são substituídos pelos novos.
        projeto.pedidos.filter(status=Pedido.Status.ERRO).delete()
        for fornecedor, linhas in por_fornecedor.items():
            pedido = Pedido.objects.create(vidraceiro=vidraceiro, projeto=projeto, fornecedor=fornecedor)
            total = Decimal(0)
            for x in linhas:
                item = itens[x["item"]]
                quantidade = Decimal(x["quantidade_pedir"])
                subtotal = (quantidade * item.preco).quantize(Decimal("0.01"))
                total += subtotal
                ItemPedido.objects.create(
                    pedido=pedido, item=item, codigo=item.codigo, descricao=item.descricao,
                    unidade=item.unidade, quantidade=quantidade, preco_unitario=item.preco, subtotal=subtotal,
                )
            pedido.total = total
            pedido.save(update_fields=["total"])
            pedidos.append(pedido)

    # O envio fica fora da transação: se o fornecedor falhar, o pedido
    # continua gravado com status "erro" e pode ser reenviado.
    for pedido in pedidos:
        enviar(pedido)
    return pedidos


def _recusar_se_ja_pedido(projeto):
    if projeto.pedidos.exclude(status__in=[Pedido.Status.ERRO, Pedido.Status.CANCELADO]).exists():
        raise ValidationError("Este projeto já tem pedido enviado ao fornecedor.")


def _payload(pedido):
    v = pedido.vidraceiro
    p = pedido.projeto
    return {
        "id_vixdro": str(pedido.id),
        "vidraceiro": {
            "nome": v.nome, "empresa": v.empresa, "cpf_cnpj": v.cpf_cnpj, "email": v.email,
            "celular": v.celular, "cidade": v.cidade, "estado": v.estado,
        },
        "referencia": {"orcamento_numero": p.numero, "projeto": p.nome},
        "itens": [
            {
                "codigo": it.codigo,
                "descricao": it.descricao,
                "unidade": it.unidade,
                "quantidade": format(it.quantidade.normalize(), "f"),
                "preco_unitario": str(it.preco_unitario),
            }
            for it in pedido.itens.all()
        ],
        "total_estimado": str(pedido.total),
    }


def _aplicar_resposta(pedido, resposta):
    bruto = str(resposta.get("status", "")).strip().lower()
    pedido.status_fornecedor = bruto
    pedido.status = STATUS_DO_FORNECEDOR.get(bruto, Pedido.Status.RECEBIDO)
    if resposta.get("numero"):
        pedido.numero_fornecedor = resposta["numero"]
    pedido.erro = ""


def criar_conta_a_pagar(pedido):
    """Pedido aceito pelo fornecedor vira uma conta a pagar (plano Pro), uma única vez.
    Vencimento: hoje + o prazo de pagamento do fornecedor."""
    from financeiro.models import Lancamento  # evita importação circular

    v = pedido.vidraceiro
    if not v.tem_pro or pedido.total <= 0 or pedido.lancamentos.exists():
        return None
    projeto = pedido.projeto
    referencia = f"Orçamento nº {projeto.numero}" if projeto.numero else projeto.nome
    return Lancamento.objects.create(
        vidraceiro=v, tipo=Lancamento.Tipo.PAGAR, categoria="Fornecedor de alumínio",
        descricao=f"Pedido {pedido.fornecedor.nome} - {referencia} - {projeto.cliente.nome}",
        valor=pedido.total,
        vencimento=timezone.localdate() + timedelta(days=pedido.fornecedor.prazo_pagamento_dias),
        projeto=projeto, cliente=projeto.cliente, pedido=pedido,
        observacoes="Criada no envio do pedido. Ajuste o valor se a nota fiscal vier diferente.",
    )


def enviar(pedido):
    try:
        resposta = adaptador_para(pedido.fornecedor).enviar_pedido(_payload(pedido))
        _aplicar_resposta(pedido, resposta)
        pedido.enviado_em = timezone.now()
        pedido.save()
        criar_conta_a_pagar(pedido)
    except ErroFornecedor as e:
        pedido.status = Pedido.Status.ERRO
        pedido.erro = str(e)
    except NotImplementedError:
        pedido.status = Pedido.Status.ERRO
        pedido.erro = "Este fornecedor ainda não recebe pedidos pelo Orçaminio."
    except Exception:
        # Falha inesperada: sem isto o pedido ficava para sempre em "enviando",
        # sem poder ser reenviado e com o projeto travado. O envio é idempotente
        # no fornecedor (pelo id), então reenviar depois não duplica.
        log.exception("Falha inesperada enviando o pedido %s", pedido.pk)
        pedido.status = Pedido.Status.ERRO
        pedido.erro = "Não foi possível confirmar o envio. Toque em reenviar."
    pedido.save()
    return pedido


def atualizar(pedido):
    """Consulta o status atual no fornecedor."""
    if pedido.status in (Pedido.Status.ERRO, Pedido.Status.ENVIANDO):
        return pedido
    try:
        _aplicar_resposta(pedido, adaptador_para(pedido.fornecedor).consultar_pedido(str(pedido.id)))
        pedido.save()
        if pedido.status == Pedido.Status.CANCELADO:
            # Pedido cancelado pelo fornecedor: a conta a pagar (ainda não paga) sai.
            pedido.lancamentos.filter(pago=False).delete()
    except (ErroFornecedor, NotImplementedError) as e:
        raise ValidationError(f"Não foi possível consultar o fornecedor: {e}")
    return pedido
