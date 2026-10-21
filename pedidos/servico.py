"""Criação, envio e acompanhamento de pedidos aos fornecedores."""

from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from fornecedores.adaptadores import ErroFornecedor, adaptador_para
from fornecedores.models import ItemFornecedor
from projetos.models import Projeto
from projetos.views import calcular_projeto_salvo

from .models import ItemPedido, Pedido

STATUS_DO_FORNECEDOR = {
    "recebido": Pedido.Status.RECEBIDO,
    "em_separacao": Pedido.Status.EM_SEPARACAO,
    "faturado": Pedido.Status.FATURADO,
    "cancelado": Pedido.Status.CANCELADO,
}


def criar_pedidos(projeto, vidraceiro):
    if projeto.status != Projeto.Status.APROVADO:
        raise ValidationError("Marque o orçamento como aprovado antes de enviar o pedido.")
    if projeto.pedidos.exclude(status__in=[Pedido.Status.ERRO, Pedido.Status.CANCELADO]).exists():
        raise ValidationError("Este projeto já tem pedido enviado ao fornecedor.")

    # Só o que falta comprar: o que sai do estoque do vidraceiro não é pedido.
    lista = [x for x in calcular_projeto_salvo(projeto)["lista_compra"] if Decimal(x["quantidade_pedir"]) > 0]
    if not lista:
        raise ValidationError("Nada a pedir: todos os itens deste projeto saem do seu estoque.")

    itens = ItemFornecedor.objects.select_related("fornecedor").in_bulk([x["item"] for x in lista])
    por_fornecedor = defaultdict(list)
    for x in lista:
        fornecedor = itens[x["item"]].fornecedor
        # Itens próprios do vidraceiro (ex: vidros) são comprados fora: não entram no pedido.
        if fornecedor.vidraceiro_id is None:
            por_fornecedor[fornecedor].append(x)
    if not por_fornecedor:
        raise ValidationError("Este projeto só tem itens próprios, que não são pedidos ao fornecedor.")

    pedidos = []
    with transaction.atomic():
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


def enviar(pedido):
    try:
        resposta = adaptador_para(pedido.fornecedor).enviar_pedido(_payload(pedido))
        _aplicar_resposta(pedido, resposta)
        pedido.enviado_em = timezone.now()
    except ErroFornecedor as e:
        pedido.status = Pedido.Status.ERRO
        pedido.erro = str(e)
    except NotImplementedError:
        pedido.status = Pedido.Status.ERRO
        pedido.erro = "Este fornecedor ainda não recebe pedidos pelo Orçaminio."
    pedido.save()
    return pedido


def atualizar(pedido):
    """Consulta o status atual no fornecedor."""
    if pedido.status in (Pedido.Status.ERRO, Pedido.Status.ENVIANDO):
        return pedido
    try:
        _aplicar_resposta(pedido, adaptador_para(pedido.fornecedor).consultar_pedido(str(pedido.id)))
        pedido.save()
    except (ErroFornecedor, NotImplementedError) as e:
        raise ValidationError(f"Não foi possível consultar o fornecedor: {e}")
    return pedido
