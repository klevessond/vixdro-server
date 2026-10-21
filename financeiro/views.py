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

from .models import Lancamento
from .serializers import CobrancasProjetoSerializer, LancamentoSerializer, ParcelamentoSerializer

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
        elif p.get("mes") != "todos":
            ano, mes = mes_do_parametro(p.get("mes"))
            qs = qs.filter(vencimento__year=ano, vencimento__month=mes)
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
        else:
            lanc.pago_em = None
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


class ResumoView(APIView):
    """GET /api/v1/financeiro/resumo/?mes=2026-10  totais do mês e o que está vencido."""

    permission_classes = [IsAuthenticated, RequerPro]

    def get(self, request):
        ano, mes = mes_do_parametro(request.query_params.get("mes"))
        hoje = timezone.localdate()
        base = Lancamento.objects.filter(vidraceiro=request.user)
        do_mes = base.filter(vencimento__year=ano, vencimento__month=mes)

        def soma(qs):
            return Decimal(qs.aggregate(t=Sum("valor"))["t"] or 0).quantize(CENTAVO)

        receber_total = soma(do_mes.filter(tipo="receber"))
        recebido = soma(do_mes.filter(tipo="receber", pago=True))
        pagar_total = soma(do_mes.filter(tipo="pagar"))
        pago = soma(do_mes.filter(tipo="pagar", pago=True))
        vencidos = base.filter(pago=False, vencimento__lt=hoje)
        return Response({
            "mes": f"{ano}-{mes:02d}",
            "receber": {"total": str(receber_total), "recebido": str(recebido), "aberto": str(receber_total - recebido)},
            "pagar": {"total": str(pagar_total), "pago": str(pago), "aberto": str(pagar_total - pago)},
            "saldo_realizado": str((recebido - pago).quantize(CENTAVO)),
            "saldo_previsto": str((receber_total - pagar_total).quantize(CENTAVO)),
            "vencidos": {
                "receber": {"quantidade": vencidos.filter(tipo="receber").count(), "valor": str(soma(vencidos.filter(tipo="receber")))},
                "pagar": {"quantidade": vencidos.filter(tipo="pagar").count(), "valor": str(soma(vencidos.filter(tipo="pagar")))},
            },
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
