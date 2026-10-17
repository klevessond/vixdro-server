from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .models import Compromisso
from .serializers import CompromissoSerializer


class CompromissoViewSet(viewsets.ModelViewSet):
    """
    GET    /api/v1/agenda/?de=2026-10-12&ate=2026-10-18   compromissos no período (datas locais)
                       &projeto=<id>                      só os de um projeto
    POST   /api/v1/agenda/
    PATCH  /api/v1/agenda/<id>/
    DELETE /api/v1/agenda/<id>/
    POST   /api/v1/agenda/<id>/concluir/   {"concluido": true | false}
    """

    serializer_class = CompromissoSerializer
    pagination_class = None
    lookup_value_regex = "[0-9a-f-]{36}"

    def get_queryset(self):
        qs = Compromisso.objects.filter(vidraceiro=self.request.user).select_related("cliente", "projeto")
        if self.action != "list":
            return qs
        p = self.request.query_params
        for nome, filtro in (("de", "inicio__date__gte"), ("ate", "inicio__date__lte")):
            if p.get(nome):
                data = parse_date(p[nome])
                if data is None:
                    raise ValidationError({nome: "Use o formato AAAA-MM-DD."})
                qs = qs.filter(**{filtro: data})
        if p.get("projeto"):
            qs = qs.filter(projeto_id=p["projeto"])
        return qs.order_by("inicio")

    def perform_create(self, serializer):
        serializer.save(vidraceiro=self.request.user)

    @action(detail=True, methods=["post"])
    def concluir(self, request, pk=None):
        c = self.get_object()
        c.concluido = bool(request.data.get("concluido", True))
        c.concluido_em = timezone.now() if c.concluido else None
        c.save(update_fields=["concluido", "concluido_em", "atualizado_em"])
        return Response(self.get_serializer(c).data)


def resumo_agenda(vidraceiro):
    """Para a tela inicial: compromissos de hoje e o próximo pendente."""
    agora = timezone.now()
    hoje = timezone.localdate()
    pendentes = Compromisso.objects.filter(vidraceiro=vidraceiro, concluido=False).select_related("cliente")
    proximo = pendentes.filter(inicio__gte=agora - timezone.timedelta(hours=1)).order_by("inicio").first()
    return {
        "hoje": pendentes.filter(inicio__date=hoje).count(),
        "proximo": None if proximo is None else {
            "id": str(proximo.id),
            "tipo": proximo.tipo,
            "tipo_texto": proximo.get_tipo_display(),
            "inicio": proximo.inicio.isoformat(),
            "cliente_nome": proximo.cliente.nome if proximo.cliente else None,
            "endereco": proximo.endereco,
        },
    }
