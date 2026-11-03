"""Estoque de materiais (plano Pro).

GET  /api/v1/estoque/itens/?busca=&tipo=&abaixo=1   itens com saldo (ou mínimo definido)
GET  /api/v1/estoque/itens/<item>/                    um item, com o histórico
POST /api/v1/estoque/itens/<item>/minimo/             {"minimo": 12}
POST /api/v1/estoque/movimentos/                      contagem, entrada, perda ou ajuste
POST /api/v1/estoque/entrada-projeto/                 itens próprios recebidos de uma compra
"""

from decimal import Decimal, InvalidOperation

from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from contas.planos import RequerPro
from fornecedores.models import ItemFornecedor, item_visivel
from projetos.models import Projeto

from .models import ConfigItemEstoque, Movimento
from .servico import custo_medio, descrever, fator_compra, minimos, para_estoque, saldos, unidade_estoque

Q4 = Decimal("0.0001")


def dec(valor, campo):
    try:
        return Decimal(str(valor).replace(",", "."))
    except (InvalidOperation, TypeError):
        raise ValidationError({campo: "Informe um número."})


def item_do_usuario(request, item_id):
    item = get_object_or_404(ItemFornecedor.objects.select_related("fornecedor"), pk=item_id)
    if not item_visivel(item, request.user):
        raise ValidationError({"item": "Item não encontrado."})
    return item


def resumo_item(v, item, saldo, minimo):
    saldo = Decimal(saldo or 0)
    medio = custo_medio(v, item)
    return {
        "item": item.pk, "codigo": item.codigo, "descricao": item.descricao, "tipo": item.tipo,
        "proprio": item.fornecedor.vidraceiro_id is not None,
        "unidade": unidade_estoque(item), "fator_compra": str(fator_compra(item)),
        "comprimento_mm": item.comprimento_mm,
        "saldo": str(saldo.quantize(Q4).normalize()), "saldo_texto": descrever(item, saldo),
        "minimo": str(Decimal(minimo or 0).normalize()) if minimo else None,
        "abaixo_minimo": bool(minimo) and saldo < minimo,
        "custo_medio": str(medio.quantize(Q4)), "valor": str((max(saldo, Decimal(0)) * medio).quantize(Decimal("0.01"))),
    }


class ItensView(APIView):
    permission_classes = [IsAuthenticated, RequerPro]

    def get(self, request):
        v = request.user
        s = saldos(v)
        mins = minimos(v)
        ids = set(s) | set(mins)
        qs = ItemFornecedor.objects.filter(pk__in=ids).select_related("fornecedor")
        p = request.query_params
        if p.get("busca"):
            qs = qs.filter(Q(codigo__icontains=p["busca"]) | Q(descricao__icontains=p["busca"]))
        if p.get("tipo"):
            qs = qs.filter(tipo=p["tipo"])
        lista = [resumo_item(v, i, s.get(i.pk), mins.get(i.pk)) for i in qs.order_by("descricao")]
        if p.get("abaixo"):
            lista = [x for x in lista if x["abaixo_minimo"]]
        return Response({
            "itens": lista,
            "valor_total": str(sum((Decimal(x["valor"]) for x in lista), Decimal(0))),
            "abaixo_minimo": sum(1 for x in lista if x["abaixo_minimo"]),
        })


class ItemView(APIView):
    permission_classes = [IsAuthenticated, RequerPro]

    def get(self, request, item_id):
        v = request.user
        item = item_do_usuario(request, item_id)
        dados = resumo_item(v, item, saldos(v, [item.pk]).get(item.pk), minimos(v).get(item.pk))
        movs = Movimento.objects.filter(vidraceiro=v, item=item).select_related("projeto")[:100]
        dados["movimentos"] = [{
            "id": str(m.id), "quantidade": str(m.quantidade.normalize()), "texto": descrever(item, abs(m.quantidade)),
            "motivo": m.motivo, "motivo_texto": m.get_motivo_display(), "observacao": m.observacao,
            "projeto": str(m.projeto_id) if m.projeto_id else None,
            "projeto_numero": m.projeto.numero if m.projeto_id else None,
            "criado_em": m.criado_em.isoformat(),
        } for m in movs]
        return Response(dados)


class MinimoView(APIView):
    permission_classes = [IsAuthenticated, RequerPro]

    def post(self, request, item_id):
        item = item_do_usuario(request, item_id)
        minimo = dec(request.data.get("minimo", 0), "minimo")
        if minimo < 0:
            raise ValidationError({"minimo": "Não pode ser negativo."})
        if request.data.get("unidade") == "compra":
            minimo = para_estoque(item, minimo)
        ConfigItemEstoque.objects.update_or_create(vidraceiro=request.user, item=item, defaults={"minimo": minimo})
        return Response({"minimo": str(minimo.normalize())})


class MovimentosView(APIView):
    """{"item", "motivo": inventario|compra|perda|ajuste, "quantidade", "unidade": "estoque"|"compra",
        "custo_unitario"?, "observacao"?}
    inventario: a quantidade é o que foi CONTADO (o saldo passa a ser esse).
    compra: entra. perda: sai. ajuste: soma (pode ser negativo)."""

    permission_classes = [IsAuthenticated, RequerPro]

    def post(self, request):
        v = request.user
        item = item_do_usuario(request, request.data.get("item"))
        motivo = request.data.get("motivo")
        if motivo not in ("inventario", "compra", "perda", "ajuste"):
            raise ValidationError({"motivo": "Use inventario, compra, perda ou ajuste."})
        q = dec(request.data.get("quantidade"), "quantidade")
        if request.data.get("unidade") == "compra":
            q = para_estoque(item, q)
        if motivo in ("compra", "perda") and q <= 0:
            raise ValidationError({"quantidade": "Informe uma quantidade maior que zero."})
        if motivo == "inventario":
            if q < 0:
                raise ValidationError({"quantidade": "A contagem não pode ser negativa."})
            q = q - Decimal(saldos(v, [item.pk]).get(item.pk, 0))  # o que falta para chegar ao contado
            if q == 0:
                return Response({"saldo_texto": descrever(item, saldos(v, [item.pk]).get(item.pk, 0)), "sem_mudanca": True})
        elif motivo == "perda":
            q = -q
        custo = None
        if request.data.get("custo_unitario") not in (None, ""):
            custo = dec(request.data["custo_unitario"], "custo_unitario")
            if request.data.get("unidade") == "compra":
                custo = custo / fator_compra(item)  # preço da barra -> preço do metro
        elif q > 0:
            custo = custo_medio(v, item)  # entrada sem custo: vale o custo médio atual
        Movimento.objects.create(
            vidraceiro=v, item=item, quantidade=q, custo_unitario=custo, motivo=motivo,
            observacao=str(request.data.get("observacao", ""))[:200],
        )
        return Response({"saldo_texto": descrever(item, saldos(v, [item.pk]).get(item.pk, 0))}, status=201)


class EntradaProjetoView(APIView):
    """Itens próprios de um projeto recebidos (comprados fora do pedido).
    {"projeto", "itens": [{"item", "quantidade" (unidade de compra), "custo_unitario"? (por unidade de compra)}]}"""

    permission_classes = [IsAuthenticated, RequerPro]

    def post(self, request):
        v = request.user
        projeto = get_object_or_404(Projeto, pk=request.data.get("projeto"), vidraceiro=v)
        ja = Movimento.objects.filter(vidraceiro=v, projeto=projeto, motivo=Movimento.Motivo.COMPRA).exists()
        if ja and not request.data.get("nova_compra"):
            # Evita entrada duplicada por um toque repetido.
            raise ValidationError({"codigo": "ja_recebido", "detail": "Os itens próprios deste projeto já entraram no estoque."})
        criados = 0
        for linha in request.data.get("itens") or []:
            item = item_do_usuario(request, linha.get("item"))
            q = dec(linha.get("quantidade"), "quantidade")
            if q <= 0:
                continue
            fator = fator_compra(item)
            preco = dec(linha["custo_unitario"], "custo_unitario") if linha.get("custo_unitario") not in (None, "") else Decimal(item.preco)
            Movimento.objects.create(
                vidraceiro=v, item=item, quantidade=q * fator, custo_unitario=preco / fator,
                motivo=Movimento.Motivo.COMPRA, projeto=projeto, observacao=f"Compra para: {projeto.nome}",
            )
            criados += 1
        if not criados:
            raise ValidationError("Nenhum item com quantidade para dar entrada.")
        return Response({"entradas": criados}, status=201)


def resumo_painel(vidraceiro):
    if not vidraceiro.tem_pro:
        return {"disponivel": False}
    s = saldos(vidraceiro)
    mins = minimos(vidraceiro)
    abaixo = sum(1 for i, m in mins.items() if m and Decimal(s.get(i, 0)) < m)
    return {"disponivel": True, "itens": len([x for x in s.values() if x]), "abaixo_minimo": abaixo}


# ---------- Peças prontas ----------

from django.db.models import Q as _Q  # noqa: E402

from produtos.models import Produto  # noqa: E402

from .models import MovimentoPeca, PecaPronta  # noqa: E402
from .servico import custo_peca, produzir, saldo_peca, simular_producao  # noqa: E402


def _produto(request):
    p = Produto.objects.filter(
        _Q(vidraceiro=request.user) | _Q(vidraceiro__isnull=True), pk=request.data.get("produto"), ativo=True,
    ).first()
    if p is None:
        raise ValidationError({"produto": "Produto não encontrado."})
    return p


def _medidas_e_quantidade(request):
    try:
        largura = int(request.data.get("largura_mm") or 0)
        altura = int(request.data.get("altura_mm") or 0)
        qtd = int(request.data.get("quantidade") or 0)
    except (TypeError, ValueError):
        raise ValidationError("Medidas e quantidade precisam ser números.")
    if not 1 <= qtd <= 999:
        raise ValidationError({"quantidade": "Informe de 1 a 999 peças."})
    return largura, altura, qtd


def _resumo_peca(p):
    return {
        "id": str(p.id), "produto": str(p.produto_id) if p.produto_id else None, "nome": p.nome,
        "largura_mm": p.largura_mm, "altura_mm": p.altura_mm, "observacao": p.observacao,
        "saldo": saldo_peca(p), "custo_unitario": str(custo_peca(p)),
    }


class PecasProntasView(APIView):
    """GET ?produto=&largura_mm=&altura_mm= (para achar as iguais a uma peça do projeto)."""

    permission_classes = [IsAuthenticated, RequerPro]

    def get(self, request):
        qs = PecaPronta.objects.filter(vidraceiro=request.user)
        p = request.query_params
        if p.get("produto"):
            qs = qs.filter(produto_id=p["produto"])
        for campo in ("largura_mm", "altura_mm"):
            if p.get(campo):
                qs = qs.filter(**{campo: p[campo]})
        lista = [_resumo_peca(x) for x in qs]
        if p.get("com_saldo"):
            lista = [x for x in lista if x["saldo"] > 0]
        return Response(lista)


class PecaProntaView(APIView):
    permission_classes = [IsAuthenticated, RequerPro]

    def get(self, request, peca_id):
        peca = get_object_or_404(PecaPronta, pk=peca_id, vidraceiro=request.user)
        dados = _resumo_peca(peca)
        dados["movimentos"] = [{
            "id": str(m.id), "quantidade": m.quantidade, "motivo": m.motivo, "motivo_texto": m.get_motivo_display(),
            "observacao": m.observacao, "projeto": str(m.projeto_id) if m.projeto_id else None,
            "custo_unitario": str(m.custo_unitario) if m.custo_unitario is not None else None,
            "criado_em": m.criado_em.isoformat(),
        } for m in peca.movimentos.all()[:100]]
        return Response(dados)

    def post(self, request, peca_id):
        """Contagem (o saldo passa a ser o contado) ou saída (vendida/descartada)."""
        peca = get_object_or_404(PecaPronta, pk=peca_id, vidraceiro=request.user)
        motivo = request.data.get("motivo")
        try:
            q = int(request.data.get("quantidade"))
        except (TypeError, ValueError):
            raise ValidationError({"quantidade": "Informe um número inteiro."})
        if motivo == "contagem":
            if q < 0:
                raise ValidationError({"quantidade": "A contagem não pode ser negativa."})
            q -= saldo_peca(peca)
        elif motivo == "saida":
            if q <= 0:
                raise ValidationError({"quantidade": "Informe quantas saíram."})
            q = -q
        else:
            raise ValidationError({"motivo": "Use contagem ou saida."})
        if q:
            MovimentoPeca.objects.create(peca=peca, quantidade=q, motivo=motivo, observacao=str(request.data.get("observacao", ""))[:200])
        return Response(_resumo_peca(peca))


class SimularProducaoView(APIView):
    permission_classes = [IsAuthenticated, RequerPro]

    def post(self, request):
        largura, altura, qtd = _medidas_e_quantidade(request)
        return Response(simular_producao(request.user, _produto(request), largura, altura, qtd))


class ProduzirView(APIView):
    permission_classes = [IsAuthenticated, RequerPro]

    def post(self, request):
        largura, altura, qtd = _medidas_e_quantidade(request)
        peca = produzir(request.user, _produto(request), largura, altura, qtd, str(request.data.get("observacao", ""))[:100])
        return Response(_resumo_peca(peca), status=201)
