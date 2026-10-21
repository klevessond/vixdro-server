from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import generics, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from .models import Fornecedor, ItemFornecedor, fornecedor_proprio, fornecedores_visiveis
from .serializers import FornecedorSerializer, ItemCatalogoSerializer, ItemProprioSerializer


class FornecedoresView(generics.ListAPIView):
    """GET /api/v1/fornecedores/"""

    serializer_class = FornecedorSerializer
    pagination_class = None

    def get_queryset(self):
        # Os itens próprios do vidraceiro aparecem como um fornecedor a mais.
        return fornecedores_visiveis(self.request.user).order_by("vidraceiro", "nome")


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
        qs = ItemFornecedor.objects.filter(
            fornecedor_id=fornecedor, fornecedor__in=fornecedores_visiveis(self.request.user)
        )

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
        if p.get("tipo"):
            qs = qs.filter(tipo=p["tipo"])

        return qs.order_by("codigo")


class MeusItensViewSet(viewsets.ModelViewSet):
    """Itens próprios do vidraceiro (o que não está no catálogo do fornecedor).

    GET/POST         /api/v1/meus-itens/
    GET/PUT/PATCH    /api/v1/meus-itens/<id>/
    DELETE           /api/v1/meus-itens/<id>/   desativa (produtos antigos continuam funcionando)
    """

    serializer_class = ItemProprioSerializer
    pagination_class = None

    def get_queryset(self):
        return ItemFornecedor.objects.filter(
            fornecedor__vidraceiro=self.request.user, ativo=True
        ).order_by("descricao")

    def perform_create(self, serializer):
        fornecedor = fornecedor_proprio(self.request.user)
        agora = timezone.now()
        codigo = (serializer.validated_data.get("codigo") or "").strip()
        if not codigo:
            n = ItemFornecedor.objects.filter(fornecedor=fornecedor).count() + 1
            codigo = f"MEU-{n:04d}"
            while ItemFornecedor.objects.filter(fornecedor=fornecedor, codigo=codigo).exists():
                n += 1
                codigo = f"MEU-{n:04d}"
        elif ItemFornecedor.objects.filter(fornecedor=fornecedor, codigo=codigo).exists():
            raise ValidationError({"codigo": "Você já tem um item com este código."})
        serializer.save(fornecedor=fornecedor, codigo=codigo, atualizado_em=agora, visto_em=agora)

    def perform_update(self, serializer):
        serializer.save(atualizado_em=timezone.now())

    def perform_destroy(self, instance):
        instance.ativo = False
        instance.atualizado_em = timezone.now()
        instance.save(update_fields=["ativo", "atualizado_em"])
