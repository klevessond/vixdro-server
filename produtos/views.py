from django.db import transaction
from django.db.models import Case, IntegerField, Q, When
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .calculo import calcular_produto
from .models import Componente, Produto
from .serializers import ProdutoSerializer, SimulacaoSerializer


class ProdutoViewSet(viewsets.ModelViewSet):
    """
    GET    /api/v1/produtos/            produtos do vidraceiro logado
    POST   /api/v1/produtos/            cria (com a lista de componentes)
    GET    /api/v1/produtos/<id>/
    PUT    /api/v1/produtos/<id>/       substitui (inclusive a lista de componentes)
    DELETE /api/v1/produtos/<id>/       arquiva (não apaga de verdade)
    POST   /api/v1/produtos/<id>/duplicar/  cópia própria (ex: de um modelo pronto)

    Modelos prontos (sem vidraceiro) aparecem para todos, mas só a equipe os
    altera, pelo admin.
    POST   /api/v1/produtos/simular/    calcula consumo e custo para uma medida
    """

    serializer_class = ProdutoSerializer
    lookup_value_regex = "[0-9a-f-]{36}"
    pagination_class = None

    def get_queryset(self):
        proprios = Q(vidraceiro=self.request.user)
        if self.action in ("update", "partial_update", "destroy"):
            # Modelos prontos só são alterados pela equipe (no app ou no admin).
            filtro = proprios | Q(vidraceiro__isnull=True) if self.request.user.is_staff else proprios
        else:
            # Vê os próprios e os modelos prontos; os próprios aparecem primeiro.
            filtro = proprios | Q(vidraceiro__isnull=True)
        return (
            Produto.objects.filter(filtro, ativo=True)
            .annotate(_modelo=Case(When(vidraceiro__isnull=True, then=1), default=0, output_field=IntegerField()))
            .order_by("_modelo", "nome")
            .prefetch_related("componentes__item")
        )

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def duplicar(self, request, pk=None):
        """POST /api/v1/produtos/<id>/duplicar/  cria uma cópia própria (ex: de um modelo pronto)."""
        original = self.get_object()
        nomes = set(Produto.objects.filter(vidraceiro=request.user, ativo=True).values_list("nome", flat=True))
        # Nome diferente do original, para não ficarem dois iguais lado a lado na lista.
        base = f"{original.nome} (minha versão)" if original.padrao else f"{original.nome} (cópia)"
        nome, n = base, 2
        while nome in nomes:
            nome = f"{base} {n}"
            n += 1
        copia = Produto.objects.create(
            vidraceiro=request.user, nome=nome, categoria=original.categoria, descricao=original.descricao,
        )
        Componente.objects.bulk_create([
            Componente(
                produto=copia, item=c.item, coef_largura=c.coef_largura, coef_altura=c.coef_altura,
                coef_area=c.coef_area, ajuste=c.ajuste, observacao=c.observacao, cobranca=c.cobranca,
                ordem=c.ordem,
            )
            for c in original.componentes.all()
        ])
        copia = self.get_queryset().get(pk=copia.pk)
        return Response(self.get_serializer(copia).data, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance):
        # Projetos antigos podem ter usado este produto: arquiva em vez de apagar.
        instance.ativo = False
        instance.save(update_fields=["ativo", "atualizado_em"])

    @action(detail=False, methods=["post"])
    def simular(self, request):
        s = SimulacaoSerializer(data=request.data, context={"request": request})
        s.is_valid(raise_exception=True)
        d = s.validated_data
        return Response(calcular_produto(d["componentes"], d["largura_mm"], d["altura_mm"]))
