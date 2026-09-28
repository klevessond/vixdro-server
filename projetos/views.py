import uuid

from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .calculo import calcular_projeto
from .models import Projeto
from .serializers import CAMPOS_PRECO, CalculoSerializer, ProjetoResumoSerializer, ProjetoSerializer


class ProjetoViewSet(viewsets.ModelViewSet):
    """
    GET    /api/v1/projetos/             projetos do vidraceiro logado (resumo)
    POST   /api/v1/projetos/             cria (idempotente pelo id gerado no app)
    GET    /api/v1/projetos/<id>/        completo, com as peças e os itens
    PUT    /api/v1/projetos/<id>/        substitui (inclusive as peças)
    DELETE /api/v1/projetos/<id>/        arquiva
    POST   /api/v1/projetos/calcular/    custo e lista de compra, sem salvar
    GET    /api/v1/projetos/<id>/calculo/  custo e lista de compra do projeto salvo
    GET    /api/v1/projetos/padroes/     margem e mão de obra do último projeto, para
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
        projeto.save(update_fields=["status", "status_atualizado_em", "atualizado_em"])
        return Response({"status": projeto.status, "status_atualizado_em": projeto.status_atualizado_em})

    @action(detail=False, methods=["post"])
    def calcular(self, request):
        s = CalculoSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        precificacao = {c: d[c] for c in CAMPOS_PRECO if c in d}
        return Response(calcular_projeto(d["linhas"], d["perda_percentual"], precificacao))

    @action(detail=False, methods=["get"])
    def padroes(self, request):
        ultimo = (
            Projeto.objects.filter(vidraceiro=request.user)
            .order_by("-criado_em")
            .first()
        )
        modelo = ultimo or Projeto()  # sem projetos: valores padrão do model
        return Response({
            "perda_percentual": str(modelo.perda_percentual),
            **{c: str(getattr(modelo, c)) for c in CAMPOS_PRECO},
        })

    @action(detail=True, methods=["get"])
    def calculo(self, request, pk=None):
        return Response(calcular_projeto_salvo(self.get_object()))


def calcular_projeto_salvo(projeto):
    """Cálculo completo de um projeto gravado no banco (usado também pelos pedidos)."""
    linhas = [
        {
            "nome": ln.nome, "largura_mm": ln.largura_mm, "altura_mm": ln.altura_mm,
            "quantidade": ln.quantidade,
            "itens": [
                {"item": it.item, "coef_largura": it.coef_largura, "coef_altura": it.coef_altura,
                 "coef_area": it.coef_area, "ajuste": it.ajuste, "observacao": it.observacao}
                for it in ln.itens.all()
            ],
        }
        for ln in projeto.linhas.all()
    ]
    precificacao = {c: getattr(projeto, c) for c in CAMPOS_PRECO}
    return calcular_projeto(linhas, projeto.perda_percentual, precificacao)


def _tem_pedido_enviado(projeto):
    """Pedido que chegou ao fornecedor (os que falharam no envio não contam)."""
    from pedidos.models import Pedido  # import local: o app pedidos depende deste

    return projeto.pedidos.exclude(status__in=[Pedido.Status.ERRO, Pedido.Status.CANCELADO]).exists()
