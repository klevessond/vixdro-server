import uuid

import re
from datetime import timedelta

from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .calculo import calcular_projeto
from .models import Projeto
from .serializers import (
    CAMPOS_PRECO,
    CalculoSerializer,
    ProjetoResumoSerializer,
    ProjetoSerializer,
    padroes_do_vidraceiro,
)


class ProjetoViewSet(viewsets.ModelViewSet):
    """
    GET    /api/v1/projetos/             projetos do vidraceiro logado (resumo)
             ?busca=maria                por nome do projeto, número do orçamento,
                                         nome/empresa, celular ou CPF/CNPJ do cliente
    POST   /api/v1/projetos/             cria (idempotente pelo id gerado no app)
    GET    /api/v1/projetos/<id>/        completo, com as peças e os itens
    PUT    /api/v1/projetos/<id>/        substitui (inclusive as peças)
    DELETE /api/v1/projetos/<id>/        arquiva
    POST   /api/v1/projetos/calcular/    custo e lista de compra, sem salvar
    GET    /api/v1/projetos/<id>/calculo/  custo e lista de compra do projeto salvo
    GET    /api/v1/projetos/padroes/     padrões de preço do vidraceiro, para
                                         preencher um projeto novo
    POST   /api/v1/projetos/<id>/status/ {"status": "enviado" | "aprovado" | "recusado" | "rascunho"}
    """

    lookup_value_regex = "[0-9a-f-]{36}"
    pagination_class = None

    def get_serializer_class(self):
        return ProjetoResumoSerializer if self.action == "list" else ProjetoSerializer

    def get_queryset(self):
        qs = Projeto.objects.filter(vidraceiro=self.request.user, ativo=True).select_related("cliente")
        if self.action == "list":
            busca = self.request.query_params.get("busca", "").strip()
            if busca:
                qs = qs.filter(_filtro_busca(busca))
            cliente = self.request.query_params.get("cliente")
            if cliente:
                qs = qs.filter(cliente_id=cliente)
            return qs.annotate(total_pecas=Sum("linhas__quantidade"))
        return qs.prefetch_related("linhas__itens__item")

    def create(self, request, *args, **kwargs):
        id_ = request.data.get("id")
        if id_:
            try:
                existente = Projeto.objects.filter(pk=uuid.UUID(str(id_))).first()
            except ValueError:
                existente = None
            if existente is not None:
                if existente.vidraceiro_id != request.user.pk:
                    raise ValidationError({"id": "Este identificador já está em uso."})
                return Response(ProjetoSerializer(existente, context=self.get_serializer_context()).data,
                                status=status.HTTP_200_OK)
        return super().create(request, *args, **kwargs)

    def perform_update(self, serializer):
        # Depois que o pedido foi ao fornecedor, o projeto fica congelado:
        # alterar as peças criaria diferença entre o orçamento e o que foi pedido.
        if _tem_pedido_enviado(serializer.instance):
            raise ValidationError(
                "Este projeto já tem pedido enviado ao fornecedor e não pode mais ser alterado."
            )
        serializer.save()

    def perform_destroy(self, instance):
        if _tem_pedido_enviado(instance):
            raise ValidationError("Este projeto tem pedido enviado ao fornecedor e não pode ser excluído.")
        instance.ativo = False
        instance.save(update_fields=["ativo", "atualizado_em"])

    @action(detail=True, methods=["post"])
    def status(self, request, pk=None):
        projeto = self.get_object()
        novo = request.data.get("status")
        if novo not in Projeto.Status.values:
            raise ValidationError({"status": f"Use um destes: {', '.join(Projeto.Status.values)}."})
        if novo != Projeto.Status.APROVADO and _tem_pedido_enviado(projeto):
            raise ValidationError({"status": "Já existe pedido enviado ao fornecedor para este projeto."})
        projeto.status = novo
        projeto.status_atualizado_em = timezone.now()
        # Mudou a situação: o lembrete recomeça do zero.
        projeto.lembrete_adiado_ate = None
        projeto.save(update_fields=["status", "status_atualizado_em", "lembrete_adiado_ate", "atualizado_em"])
        return Response({"status": projeto.status, "status_atualizado_em": projeto.status_atualizado_em})

    @action(detail=False, methods=["get"])
    def parados(self, request):
        """GET /api/v1/projetos/parados/  orçamentos enviados ao cliente e sem resposta."""
        agora = timezone.now()
        resultado = []
        for p in orcamentos_parados(request.user).select_related("cliente").prefetch_related("linhas__itens__item"):
            desde = p.status_atualizado_em or p.atualizado_em
            resultado.append({
                "id": str(p.id),
                "numero": p.numero,
                "nome": p.nome,
                "cliente": str(p.cliente_id),
                "cliente_nome": p.cliente.nome,
                "cliente_celular": p.cliente.celular,
                "enviado_em": desde.isoformat(),
                "dias_parado": (agora - desde).days,
                "ultimo_contato_em": p.ultimo_contato_em.isoformat() if p.ultimo_contato_em else None,
                "total": calcular_projeto_salvo(p)["orcamento"]["total"],
            })
        resultado.sort(key=lambda x: -x["dias_parado"])
        return Response({"dias_lembrete": request.user.dias_lembrete, "orcamentos": resultado})

    @action(detail=True, methods=["post"], url_path="adiar-lembrete")
    def adiar_lembrete(self, request, pk=None):
        """POST /api/v1/projetos/<id>/adiar-lembrete/  {"dias": 3, "contatou": true}

        Esconde o lembrete por alguns dias. contatou=true registra que o
        cliente foi cobrado (ex: pelo WhatsApp)."""
        projeto = self.get_object()
        try:
            dias = int(request.data.get("dias", 3))
        except (TypeError, ValueError):
            raise ValidationError({"dias": "Informe um número de dias."})
        if not 1 <= dias <= 60:
            raise ValidationError({"dias": "Use de 1 a 60 dias."})
        agora = timezone.now()
        projeto.lembrete_adiado_ate = agora + timedelta(days=dias)
        campos = ["lembrete_adiado_ate"]
        if request.data.get("contatou"):
            projeto.ultimo_contato_em = agora
            campos.append("ultimo_contato_em")
        projeto.save(update_fields=campos)
        return Response({"lembrete_adiado_ate": projeto.lembrete_adiado_ate})

    @action(detail=False, methods=["post"])
    def calcular(self, request):
        s = CalculoSerializer(data=request.data, context={"request": request})
        s.is_valid(raise_exception=True)
        d = s.validated_data
        precificacao = {c: d[c] for c in CAMPOS_PRECO if c in d}
        return Response(calcular_projeto(d["linhas"], d["perda_percentual"], precificacao))

    @action(detail=False, methods=["get"])
    def padroes(self, request):
        return Response(padroes_do_vidraceiro(request.user))

    @action(detail=True, methods=["get"])
    def calculo(self, request, pk=None):
        return Response(calcular_projeto_salvo(self.get_object()))


def _filtro_busca(busca):
    """Um único texto que procura em vários campos ao mesmo tempo."""
    filtro = (
        Q(nome__icontains=busca)
        | Q(cliente__nome__icontains=busca)
        | Q(cliente__empresa__icontains=busca)
    )
    # Celular e CPF/CNPJ são guardados só com dígitos: "(84) 9999" vira "849999".
    digitos = re.sub(r"[^0-9]", "", busca)
    if len(digitos) >= 4:
        # A partir de 4 dígitos: trecho de celular ou de CPF/CNPJ.
        filtro |= Q(cliente__celular__contains=digitos) | Q(cliente__cpf_cnpj__contains=digitos)
    if digitos and len(digitos) <= 6:
        # "12", "nº 12" ou "#12": número do orçamento (exato).
        filtro |= Q(numero=int(digitos))
    return filtro


def calcular_projeto_salvo(projeto):
    """Cálculo completo de um projeto gravado no banco (usado também pelos pedidos)."""
    linhas = [
        {
            "nome": ln.nome, "largura_mm": ln.largura_mm, "altura_mm": ln.altura_mm,
            "quantidade": ln.quantidade,
            "itens": [
                {"item": it.item, "coef_largura": it.coef_largura, "coef_altura": it.coef_altura,
                 "coef_area": it.coef_area, "ajuste": it.ajuste, "observacao": it.observacao,
                 "cobranca": it.cobranca}
                for it in ln.itens.all()
            ],
        }
        for ln in projeto.linhas.all()
    ]
    precificacao = {c: getattr(projeto, c) for c in CAMPOS_PRECO}
    return calcular_projeto(linhas, projeto.perda_percentual, precificacao)


def orcamentos_parados(vidraceiro):
    """Enviados ao cliente há mais de N dias, sem resposta e sem lembrete adiado."""
    agora = timezone.now()
    limite = agora - timedelta(days=vidraceiro.dias_lembrete)
    return (
        Projeto.objects.filter(vidraceiro=vidraceiro, ativo=True, status=Projeto.Status.ENVIADO)
        .annotate(desde=Coalesce("status_atualizado_em", "atualizado_em"))
        .filter(desde__lte=limite)
        .filter(Q(lembrete_adiado_ate__isnull=True) | Q(lembrete_adiado_ate__lte=agora))
    )


def _tem_pedido_enviado(projeto):
    """Pedido que chegou ao fornecedor (os que falharam no envio não contam)."""
    from pedidos.models import Pedido  # import local: o app pedidos depende deste

    return projeto.pedidos.exclude(status__in=[Pedido.Status.ERRO, Pedido.Status.CANCELADO]).exists()
