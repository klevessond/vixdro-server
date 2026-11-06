from django.db import transaction
from django.db.models import Case, IntegerField, Q, When
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
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

    @action(detail=True, methods=["post", "delete"])
    def imagem(self, request, pk=None):
        """POST {"imagem_base64"} troca a foto do produto; DELETE remove.
        Modelo pronto: só a equipe."""
        from projetos.fotos import FotoInvalida, trocar_imagem

        produto = self.get_object()
        if produto.vidraceiro_id != request.user.pk and not (produto.padrao and request.user.is_staff):
            raise PermissionDenied("Só a equipe do Orçaminio troca a foto de um modelo pronto.")
        try:
            trocar_imagem(produto, "" if request.method == "DELETE" else request.data.get("imagem_base64", ""))
        except FotoInvalida as e:
            raise ValidationError({"imagem_base64": str(e)})
        return Response(self.get_serializer(self.get_queryset().get(pk=produto.pk)).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def duplicar(self, request, pk=None):
        """POST /api/v1/produtos/<id>/duplicar/  {"nome"?}  cria uma cópia própria
        (de um modelo pronto ou de um produto do vidraceiro), com a foto."""
        original = self.get_object()
        nomes = set(Produto.objects.filter(vidraceiro=request.user, ativo=True).values_list("nome", flat=True))
        # Nome escolhido ou, sem ele, diferente do original (para não ficarem dois iguais lado a lado).
        escolhido = str(request.data.get("nome", "")).strip()[:150]
        base = escolhido or (f"{original.nome} (minha versão)" if original.padrao else f"{original.nome} (cópia)")
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
        # A foto vai junto, como arquivos novos: trocar a da cópia não mexe na do original.
        if original.imagem:
            from django.core.files.base import ContentFile

            for campo in ("imagem", "miniatura"):
                arquivo = getattr(original, campo)
                if arquivo:
                    with arquivo.open("rb") as f:
                        getattr(copia, campo).save("foto.jpg", ContentFile(f.read()), save=False)
            copia.save(update_fields=["imagem", "miniatura"])
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
