from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from .models import Fornecedor, ItemFornecedor
from .serializers import FornecedorSerializer, ItemCatalogoSerializer


class FornecedoresView(generics.ListAPIView):
    """GET /api/v1/fornecedores/"""

    serializer_class = FornecedorSerializer
    pagination_class = None
    queryset = Fornecedor.objects.filter(ativo=True)


class PaginacaoCatalogo(PageNumberPagination):
    page_size = 500
    page_size_query_param = "tamanho"
    max_page_size = 1000

    def get_paginated_response(self, data):
        return Response({
            "total": self.page.paginator.count,
            "proxima": self.get_next_link(),
            # O app guarda este horário e manda como atualizado_desde na próxima vez.
            "gerado_em": self.request._gerado_em.isoformat(),
            "itens": data,
        })


class CatalogoView(generics.ListAPIView):
    """GET /api/v1/catalogo/itens/

    Parâmetros:
      fornecedor=<id>              obrigatório
      atualizado_desde=<ISO 8601>  só o que mudou (inclui desativados, para o
                                   app atualizar a cópia offline)
      busca=trilho                 filtra por código ou descrição
      page, tamanho                paginação
    """

    serializer_class = ItemCatalogoSerializer
    pagination_class = PaginacaoCatalogo

    def get_queryset(self):
        self.request._gerado_em = timezone.now()
        p = self.request.query_params

        fornecedor = p.get("fornecedor")
        if not fornecedor or not fornecedor.isdigit():
            raise ValidationError({"fornecedor": "Informe o id do fornecedor."})
        qs = ItemFornecedor.objects.filter(fornecedor_id=fornecedor, fornecedor__ativo=True)

        desde_txt = p.get("atualizado_desde")
        if desde_txt:
            desde = parse_datetime(desde_txt)
            if desde is None:
                raise ValidationError({"atualizado_desde": "Use o formato ISO 8601."})
            qs = qs.filter(atualizado_em__gt=desde)
        else:
            qs = qs.filter(ativo=True)

        busca = p.get("busca", "").strip()
        if busca:
            qs = qs.filter(Q(codigo__icontains=busca) | Q(descricao__icontains=busca))

        return qs.order_by("codigo")
