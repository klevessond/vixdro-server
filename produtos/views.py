from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .calculo import calcular_produto
from .models import Produto
from .serializers import ProdutoSerializer, SimulacaoSerializer


class ProdutoViewSet(viewsets.ModelViewSet):
    """
    GET    /api/v1/produtos/            produtos do vidraceiro logado
    POST   /api/v1/produtos/            cria (com a lista de componentes)
    GET    /api/v1/produtos/<id>/
    PUT    /api/v1/produtos/<id>/       substitui (inclusive a lista de componentes)
    DELETE /api/v1/produtos/<id>/       arquiva (não apaga de verdade)
    POST   /api/v1/produtos/simular/    calcula consumo e custo para uma medida
    """

    serializer_class = ProdutoSerializer
    lookup_value_regex = "[0-9a-f-]{36}"
    pagination_class = None

    def get_queryset(self):
        # Cada vidraceiro só enxerga os próprios produtos.
        return (
            Produto.objects.filter(vidraceiro=self.request.user, ativo=True)
            .prefetch_related("componentes__item")
        )

    def perform_destroy(self, instance):
        # Projetos antigos podem ter usado este produto: arquiva em vez de apagar.
        instance.ativo = False
        instance.save(update_fields=["ativo", "atualizado_em"])

    @action(detail=False, methods=["post"])
    def simular(self, request):
        s = SimulacaoSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        return Response(calcular_produto(d["componentes"], d["largura_mm"], d["altura_mm"]))
