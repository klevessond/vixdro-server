from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from projetos.models import Projeto

from .models import Pedido
from .serializers import PedidoSerializer
from .servico import atualizar, criar_pedidos, enviar


class PedidoViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """
    GET  /api/v1/pedidos/?projeto=<id>        pedidos do vidraceiro (de um projeto)
    POST /api/v1/pedidos/  {"projeto": <id>}  cria e envia (um por fornecedor)
    POST /api/v1/pedidos/<id>/reenviar/       tenta de novo um pedido com erro
    POST /api/v1/pedidos/<id>/atualizar/      consulta o status no fornecedor
    """

    serializer_class = PedidoSerializer
    pagination_class = None
    lookup_value_regex = "[0-9a-f-]{36}"

    def get_queryset(self):
        qs = (
            Pedido.objects.filter(vidraceiro=self.request.user)
            .select_related("fornecedor")
            .prefetch_related("itens")
        )
        projeto = self.request.query_params.get("projeto")
        if projeto:
            qs = qs.filter(projeto_id=projeto)
        return qs

    def create(self, request):
        projeto = Projeto.objects.filter(
            pk=request.data.get("projeto"), vidraceiro=request.user, ativo=True
        ).first()
        if projeto is None:
            raise ValidationError({"projeto": "Projeto não encontrado."})
        pedidos = criar_pedidos(projeto, request.user)
        return Response(PedidoSerializer(pedidos, many=True).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def reenviar(self, request, pk=None):
        pedido = self.get_object()
        if pedido.status != Pedido.Status.ERRO:
            raise ValidationError("Só é possível reenviar um pedido que falhou.")
        return Response(PedidoSerializer(enviar(pedido)).data)

    @action(detail=True, methods=["post"], url_path="atualizar")
    def atualizar_status(self, request, pk=None):
        return Response(PedidoSerializer(atualizar(self.get_object())).data)
