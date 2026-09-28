from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from .models import Cliente
from .serializers import ClienteSerializer


class PaginacaoClientes(PageNumberPagination):
    page_size = 500
    page_size_query_param = "tamanho"
    max_page_size = 1000

    def get_paginated_response(self, data):
        return Response({
            "total": self.page.paginator.count,
            "proxima": self.get_next_link(),
            # O app guarda este horário e usa como atualizado_desde na próxima vez.
            "gerado_em": self.request._gerado_em.isoformat(),
            "clientes": data,
        })


class ClienteViewSet(viewsets.ModelViewSet):
    """
    GET    /api/v1/clientes/                  clientes do vidraceiro logado
             ?atualizado_desde=<ISO>          só o que mudou (inclui excluídos, com ativo=false)
             ?busca=maria                     por nome, empresa ou celular
    POST   /api/v1/clientes/                  cria (idempotente pelo id gerado no app)
    GET    /api/v1/clientes/<id>/
    PUT    /api/v1/clientes/<id>/
    PATCH  /api/v1/clientes/<id>/
    DELETE /api/v1/clientes/<id>/             arquiva
    """

    serializer_class = ClienteSerializer
    pagination_class = PaginacaoClientes
    lookup_value_regex = "[0-9a-f-]{36}"

    def get_queryset(self):
        # Isolamento: cada vidraceiro só enxerga os próprios clientes.
        qs = Cliente.objects.filter(vidraceiro=self.request.user)
        if self.action != "list":
            return qs.filter(ativo=True)

        self.request._gerado_em = timezone.now()
        p = self.request.query_params
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
            from django.db.models import Q
            qs = qs.filter(Q(nome__icontains=busca) | Q(empresa__icontains=busca) | Q(celular__icontains=busca))
        return qs.order_by("nome")

    def create(self, request, *args, **kwargs):
        id_ = request.data.get("id")
        if id_:
            existente = Cliente.objects.filter(pk=id_).first() if _uuid_valido(id_) else None
            if existente is not None:
                if existente.vidraceiro_id != request.user.pk:
                    # Na prática não acontece (UUID aleatório), mas nunca
                    # deixamos um vidraceiro mexer no registro de outro.
                    raise ValidationError({"id": "Este identificador já está em uso."})
                # Reenvio da fila de sincronização: o cliente já chegou antes.
                return Response(self.get_serializer(existente).data, status=status.HTTP_200_OK)
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        # O dono é sempre quem está logado, nunca um campo enviado pelo app.
        serializer.save(vidraceiro=self.request.user)

    def perform_destroy(self, instance):
        instance.ativo = False
        instance.save(update_fields=["ativo", "atualizado_em"])


def _uuid_valido(valor):
    import uuid
    try:
        uuid.UUID(str(valor))
        return True
    except ValueError:
        return False
