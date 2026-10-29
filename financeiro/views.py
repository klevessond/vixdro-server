"""Financeiro (plano Pro): contas a receber e a pagar, parcelas e resumo do mês."""

import calendar
import uuid
from datetime import date
from decimal import ROUND_DOWN, Decimal

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from contas.planos import RequerPro
from projetos.views import calcular_projeto_salvo

from django.db.models import Case, DateField, F, When

from .condicoes import garantir_condicoes, garantir_contas, simular
from .models import TIPO_CONTA_POR_FORMA, CondicaoPagamento, Conta, Lancamento
from .serializers import (
    CobrancasProjetoSerializer,
    CondicaoPagamentoSerializer,
    ContaSerializer,
    LancamentoSerializer,
    ParcelamentoSerializer,
)

CENTAVO = Decimal("0.01")


def somar_meses(d: date, meses: int) -> date:
    """Mesmo dia, N meses depois (31/01 + 1 mês = 28 ou 29/02)."""
    m = d.month - 1 + meses
    ano, mes = d.year + m // 12, m % 12 + 1
    return date(ano, mes, min(d.day, calendar.monthrange(ano, mes)[1]))


def dividir(total: Decimal, partes: int):
    """Divide em partes iguais; a diferença dos centavos vai para a última."""
    base = (total / partes).quantize(CENTAVO, rounding=ROUND_DOWN)
    valores = [base] * partes
    valores[-1] = total - base * (partes - 1)
    return valores


def mes_do_parametro(texto):
    """'2026-10' -> (2026, 10). Sem parâmetro, o mês atual."""
    if not texto:
        hoje = timezone.localdate()
        return hoje.year, hoje.month
    try:
        ano, mes = (int(x) for x in texto.split("-"))
        date(ano, mes, 1)
        return ano, mes
    except (ValueError, TypeError):
        raise ValidationError({"mes": "Use o formato AAAA-MM."})


class LancamentoViewSet(viewsets.ModelViewSet):
    """
    GET    /api/v1/financeiro/lancamentos/?mes=2026-10&tipo=receber&situacao=aberto|pago|vencido&projeto=<id>
    POST   /api/v1/financeiro/lancamentos/                 um lançamento
    POST   /api/v1/financeiro/lancamentos/parcelar/        várias parcelas de uma vez
    POST   /api/v1/financeiro/lancamentos/cobrancas-projeto/  sinal + parcelas a partir do orçamento
    POST   /api/v1/financeiro/lancamentos/<id>/pagar/      {"pago": true, "pago_em"?, "forma"?}
    PATCH / DELETE /api/v1/financeiro/lancamentos/<id>/
    """

    serializer_class = LancamentoSerializer
    pagination_class = None
    permission_classes = [IsAuthenticated, RequerPro]
    lookup_value_regex = "[0-9a-f-]{36}"

    def get_queryset(self):
        qs = Lancamento.objects.filter(vidraceiro=self.request.user).select_related("cliente", "projeto")
        if self.action != "list":
            return qs
        p = self.request.query_params
        if p.get("projeto"):
            qs = qs.filter(projeto_id=p["projeto"])  # todas as parcelas do projeto, de qualquer mês
        else:
            qs = filtrar_periodo(qs, p)
        if p.get("conta"):
            qs = qs.filter(conta_id=p["conta"])
        if p.get("tipo") in ("receber", "pagar"):
            qs = qs.filter(tipo=p["tipo"])
        situacao = p.get("situacao")
        hoje = timezone.localdate()
        if situacao == "aberto":
            qs = qs.filter(pago=False)
        elif situacao == "pago":
            qs = qs.filter(pago=True)
        elif situacao == "vencido":
            qs = qs.filter(pago=False, vencimento__lt=hoje)
        return qs.order_by("vencimento", "criado_em")

    def perform_create(self, serializer):
        l = serializer.validated_data
        if l.get("pago") and not l.get("conta"):
            serializer.validated_data["conta"] = conta_sugerida(self.request.user, l.get("forma"))
        serializer.save(vidraceiro=self.request.user)

    @action(detail=True, methods=["post"])
    def pagar(self, request, pk=None):
        lanc = self.get_object()
        lanc.pago = bool(request.data.get("pago", True))
        if lanc.pago:
            lanc.pago_em = request.data.get("pago_em") or timezone.localdate()
            forma = request.data.get("forma")
            if forma in Lancamento.Forma.values:
                lanc.forma = forma
            conta_id = request.data.get("conta")
            if conta_id:
                conta = Conta.objects.filter(pk=conta_id, vidraceiro=request.user).first()
                if conta is None:
                    raise ValidationError({"conta": "Conta não encontrada."})
                lanc.conta = conta
            elif lanc.conta_id is None:
                lanc.conta = conta_sugerida(request.user, lanc.forma)
        else:
            lanc.pago_em = None
            lanc.conta = None
        lanc.save()
        lanc.refresh_from_db()
        return Response(self.get_serializer(lanc).data)

    def _criar_parcelas(self, *, tipo, descricao, categoria, valores, vencimentos, cliente, projeto, observacoes=""):
        grupo = uuid.uuid4() if len(valores) > 1 else None
        criados = []
        for i, (valor, venc) in enumerate(zip(valores, vencimentos), start=1):
            criados.append(Lancamento.objects.create(
                vidraceiro=self.request.user, tipo=tipo, categoria=categoria, valor=valor, vencimento=venc,
                descricao=descricao if len(valores) == 1 else f"{descricao} ({i}/{len(valores)})",
                cliente=cliente, projeto=projeto, grupo=grupo, parcela=i, total_parcelas=len(valores),
                observacoes=observacoes,
            ))
        return criados

    @action(detail=False, methods=["post"])
    @transaction.atomic
    def parcelar(self, request):
        s = ParcelamentoSerializer(data=request.data, context={"request": request})
        s.is_valid(raise_exception=True)
        d = s.validated_data
        projeto = d.get("projeto")
        criados = self._criar_parcelas(
            tipo=d["tipo"], descricao=d["descricao"].strip(), categoria=d["categoria"],
            valores=dividir(d["valor_total"], d["parcelas"]),
            vencimentos=[somar_meses(d["primeiro_vencimento"], i) for i in range(d["parcelas"])],
            cliente=d.get("cliente") or (projeto.cliente if projeto else None), projeto=projeto,
            observacoes=d["observacoes"],
        )
        return Response(self.get_serializer(criados, many=True).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="cobrancas-projeto")
    @transaction.atomic
    def cobrancas_projeto(self, request):
        s = CobrancasProjetoSerializer(data=request.data, context={"request": request})
        s.is_valid(raise_exception=True)
        d = s.validated_data
        projeto = d["projeto"]
        if projeto.lancamentos.filter(tipo=Lancamento.Tipo.RECEBER).exists():
            raise ValidationError("Este projeto já tem cobranças. Apague as atuais para gerar de novo.")
        total = Decimal(calcular_projeto_salvo(projeto)["orcamento"]["total"])
        if total <= 0:
            raise ValidationError("O orçamento deste projeto está sem valor.")
        nome = f"Orçamento nº {projeto.numero} - {projeto.cliente.nome}" if projeto.numero else projeto.nome
        if d.get("condicao"):
            return self._cobrancas_pela_condicao(projeto, d, total, nome)
        entrada = (total * d["entrada_percentual"] / 100).quantize(CENTAVO)
        criados = []
        if entrada > 0:
            criados += self._criar_parcelas(
                tipo="receber", descricao=f"Sinal - {nome}", categoria="Orçamento", valores=[entrada],
                vencimentos=[d["vencimento_entrada"]], cliente=projeto.cliente, projeto=projeto,
            )
        restante = total - entrada
        if restante > 0:
            n = d["parcelas_restantes"]
            criados += self._criar_parcelas(
                tipo="receber", descricao=f"Restante - {nome}" if n == 1 else f"Parcela - {nome}",
                categoria="Orçamento", valores=dividir(restante, n),
                vencimentos=[somar_meses(d["primeiro_vencimento"], i) for i in range(n)],
                cliente=projeto.cliente, projeto=projeto,
            )
        return Response(self.get_serializer(criados, many=True).data, status=status.HTTP_201_CREATED)


    def _cobrancas_pela_condicao(self, projeto, d, total, nome):
        """À vista: 1 lançamento com desconto. Parcelado: N parcelas mensais.
        Entrada + parcelas: a entrada e o restante em parcelas mensais."""
        c = d["condicao"]
        v = simular(c, total, d.get("parcelas"))
        primeira = d["vencimento_entrada"]
        criados = []
        if c.tipo == CondicaoPagamento.Tipo.AVISTA:
            criados += self._criar_parcelas(
                tipo="receber", descricao=f"À vista - {nome}", categoria="Orçamento", valores=[v["total"]],
                vencimentos=[primeira], cliente=projeto.cliente, projeto=projeto,
                observacoes=f"{c.nome} ({c.desconto_percentual}% de desconto)" if c.desconto_percentual else c.nome,
            )
        else:
            if v["entrada"] > 0:
                criados += self._criar_parcelas(
                    tipo="receber", descricao=f"Entrada - {nome}", categoria="Orçamento", valores=[v["entrada"]],
                    vencimentos=[primeira], cliente=projeto.cliente, projeto=projeto, observacoes=c.nome,
                )
            resto = v["total"] - v["entrada"]
            if resto > 0:
                n = v["parcelas"]
                inicio = d.get("primeiro_vencimento") or (somar_meses(primeira, 1) if v["entrada"] > 0 else primeira)
                criados += self._criar_parcelas(
                    tipo="receber", descricao=(f"Restante - {nome}" if n == 1 else f"Parcela - {nome}"),
                    categoria="Orçamento", valores=dividir(resto, n),
                    vencimentos=[somar_meses(inicio, i) for i in range(n)],
                    cliente=projeto.cliente, projeto=projeto, observacoes=c.nome,
                )
        projeto.condicao_pagamento = c
        projeto.save(update_fields=["condicao_pagamento"])
        return Response(self.get_serializer(criados, many=True).data, status=status.HTTP_201_CREATED)


def filtrar_periodo(qs, p):
    """Período por ?de=&ate= (datas), ?mes=AAAA-MM ou nada (?mes=todos = tudo).

    Data de referência: quando foi pago, a data do pagamento; em aberto, o
    vencimento. Assim, "o que entrou nesta semana" mostra o dinheiro da semana."""
    qs = qs.annotate(data_ref=Case(When(pago=True, pago_em__isnull=False, then=F("pago_em")),
                                   default=F("vencimento"), output_field=DateField()))
    if p.get("de") or p.get("ate"):
        for nome, filtro in (("de", "data_ref__gte"), ("ate", "data_ref__lte")):
            if p.get(nome):
                try:
                    qs = qs.filter(**{filtro: date.fromisoformat(p[nome])})
                except ValueError:
                    raise ValidationError({nome: "Use o formato AAAA-MM-DD."})
        return qs
    if p.get("mes") == "todos":
        return qs
    ano, mes = mes_do_parametro(p.get("mes"))
    return qs.filter(data_ref__year=ano, data_ref__month=mes)


def conta_sugerida(vidraceiro, forma):
    """Conta pelo tipo da forma (Pix -> Banco; dinheiro -> Caixa); senão, a primeira conta."""
    garantir_contas(vidraceiro)
    contas = Conta.objects.filter(vidraceiro=vidraceiro, ativo=True)
    tipo = TIPO_CONTA_POR_FORMA.get(forma or "")
    return (contas.filter(tipo=tipo).first() if tipo else None) or contas.first()


class CondicaoPagamentoViewSet(viewsets.ModelViewSet):
    """Formas de pagamento do vidraceiro (plano gratuito: aparecem no PDF).
    DELETE só desativa, para não afetar projetos que já usam a condição."""

    serializer_class = CondicaoPagamentoSerializer
    pagination_class = None
    lookup_value_regex = "[0-9a-f-]{36}"

    def get_queryset(self):
        garantir_condicoes(self.request.user)
        return CondicaoPagamento.objects.filter(vidraceiro=self.request.user, ativo=True).order_by("ordem", "nome")

    def perform_create(self, serializer):
        # Nova condição vai para o fim da lista.
        serializer.save(vidraceiro=self.request.user,
                        ordem=CondicaoPagamento.objects.filter(vidraceiro=self.request.user).count())

    def perform_destroy(self, instance):
        instance.ativo = False
        instance.save(update_fields=["ativo"])


class ContaViewSet(viewsets.ModelViewSet):
    """Contas de caixa (Pro), com o saldo de cada uma. DELETE só desativa."""

    serializer_class = ContaSerializer
    pagination_class = None
    permission_classes = [IsAuthenticated, RequerPro]
    lookup_value_regex = "[0-9a-f-]{36}"

    def get_queryset(self):
        garantir_contas(self.request.user)
        return Conta.objects.filter(vidraceiro=self.request.user, ativo=True).annotate(
            entradas=Sum("lancamentos__valor", filter=Q(lancamentos__pago=True, lancamentos__tipo="receber")),
            saidas=Sum("lancamentos__valor", filter=Q(lancamentos__pago=True, lancamentos__tipo="pagar")),
        ).order_by("ordem", "nome")

    def perform_create(self, serializer):
        serializer.save(vidraceiro=self.request.user, ordem=Conta.objects.filter(vidraceiro=self.request.user).count())

    def perform_destroy(self, instance):
        instance.ativo = False
        instance.save(update_fields=["ativo"])


class ResumoView(APIView):
    """GET /api/v1/financeiro/resumo/?de=&ate=  (ou ?mes=AAAA-MM, ou ?mes=todos)
    Totais do período, o que está vencido e o saldo de cada conta."""

    permission_classes = [IsAuthenticated, RequerPro]

    def get(self, request):
        hoje = timezone.localdate()
        base = Lancamento.objects.filter(vidraceiro=request.user)
        periodo = filtrar_periodo(base, request.query_params)

        def soma(qs):
            return Decimal(qs.aggregate(t=Sum("valor"))["t"] or 0).quantize(CENTAVO)

        receber_total = soma(periodo.filter(tipo="receber"))
        recebido = soma(periodo.filter(tipo="receber", pago=True))
        pagar_total = soma(periodo.filter(tipo="pagar"))
        pago = soma(periodo.filter(tipo="pagar", pago=True))
        vencidos = base.filter(pago=False, vencimento__lt=hoje)
        contas = ContaViewSet(request=request, format_kwarg=None).get_queryset()
        return Response({
            "receber": {"total": str(receber_total), "recebido": str(recebido), "aberto": str(receber_total - recebido)},
            "pagar": {"total": str(pagar_total), "pago": str(pago), "aberto": str(pagar_total - pago)},
            "saldo_realizado": str((recebido - pago).quantize(CENTAVO)),
            "saldo_previsto": str((receber_total - pagar_total).quantize(CENTAVO)),
            "vencidos": {
                "receber": {"quantidade": vencidos.filter(tipo="receber").count(), "valor": str(soma(vencidos.filter(tipo="receber")))},
                "pagar": {"quantidade": vencidos.filter(tipo="pagar").count(), "valor": str(soma(vencidos.filter(tipo="pagar")))},
            },
            "contas": ContaSerializer(contas, many=True).data,
            "categorias": Lancamento.CATEGORIAS,
        })


def resumo_painel(vidraceiro):
    """Para a tela inicial."""
    if not vidraceiro.tem_pro:
        return {"disponivel": False}
    hoje = timezone.localdate()
    base = Lancamento.objects.filter(vidraceiro=vidraceiro, pago=False)
    receber_mes = base.filter(tipo="receber", vencimento__year=hoje.year, vencimento__month=hoje.month)
    vencidos = base.filter(tipo="receber", vencimento__lt=hoje)
    return {
        "disponivel": True,
        "receber_mes": str(Decimal(receber_mes.aggregate(t=Sum("valor"))["t"] or 0).quantize(CENTAVO)),
        "vencidos": vencidos.count(),
    }
