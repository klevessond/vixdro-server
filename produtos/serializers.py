from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from fornecedores.models import ItemFornecedor, item_visivel
from fornecedores.serializers import ItemCatalogoSerializer

from .calculo import calcular_produto, modo

# Medida usada para mostrar o custo de um produto na lista (o custo real
# depende do tamanho de cada peça).
REFERENCIA_MM = 1000
from .models import Componente, Produto


class ComponenteSerializer(serializers.ModelSerializer):
    item = serializers.PrimaryKeyRelatedField(queryset=ItemFornecedor.objects.select_related("fornecedor"))
    item_detalhe = ItemCatalogoSerializer(source="item", read_only=True)
    modo = serializers.SerializerMethodField()

    class Meta:
        model = Componente
        fields = ("id", "item", "item_detalhe", "modo", "coef_largura", "coef_altura",
                  "coef_area", "ajuste", "observacao", "cobranca")
        read_only_fields = ("id",)

    def get_modo(self, obj):
        return modo(obj.item)

    def validate(self, attrs):
        if not item_visivel(attrs["item"], self.context["request"].user):
            raise serializers.ValidationError({"item": "Item não encontrado."})
        if not attrs["item"].fornecedor.ativo:
            raise serializers.ValidationError({"item": "Este fornecedor não está mais ativo."})
        regra = [attrs.get(c, 0) for c in ("coef_largura", "coef_altura", "coef_area", "ajuste")]
        if all(v == 0 for v in regra):
            # Sem regra: quantidade fixa de 1 por peça (1 unidade, 1 m ou 1 m², conforme o item).
            attrs["ajuste"] = Decimal(1)
        return attrs


class ProdutoSerializer(serializers.ModelSerializer):
    componentes = ComponenteSerializer(many=True)
    custo_referencia = serializers.SerializerMethodField()
    custo_depende_medida = serializers.SerializerMethodField()
    # Modelo pronto (visível para todos). Só contas da equipe podem marcar.
    padrao = serializers.BooleanField(required=False)

    class Meta:
        model = Produto
        fields = ("id", "nome", "categoria", "descricao", "componentes", "atualizado_em",
                  "custo_referencia", "custo_depende_medida", "padrao")
        read_only_fields = ("id", "atualizado_em")

    def _regras(self, obj):
        return [
            {"item": c.item, "coef_largura": c.coef_largura, "coef_altura": c.coef_altura,
             "coef_area": c.coef_area, "ajuste": c.ajuste, "cobranca": c.cobranca}
            for c in obj.componentes.all()
        ]

    def get_custo_referencia(self, obj):
        """Custo dos itens numa peça de 1,00 x 1,00 m (ou o custo exato, se nada depende da medida)."""
        return calcular_produto(self._regras(obj), REFERENCIA_MM, REFERENCIA_MM)["custo_total"]

    def get_custo_depende_medida(self, obj):
        return any(
            c.coef_largura or c.coef_altura or c.coef_area for c in obj.componentes.all()
        )

    def validate_nome(self, valor):
        valor = valor.strip()
        if not valor:
            raise serializers.ValidationError("Dê um nome ao produto.")
        return valor

    def validate_componentes(self, componentes):
        if not componentes:
            raise serializers.ValidationError("Adicione pelo menos um item ao produto.")
        # Item desativado no fornecedor: só pode continuar em produto que já o usava.
        ja_usados = set()
        if self.instance is not None:
            ja_usados = set(self.instance.componentes.values_list("item_id", flat=True))
        for c in componentes:
            item = c["item"]
            if not item.ativo and item.pk not in ja_usados:
                raise serializers.ValidationError(
                    f"O item {item.codigo} saiu de linha no fornecedor e não pode ser adicionado."
                )
        return componentes

    @staticmethod
    def _salvar_componentes(produto, componentes):
        produto.componentes.all().delete()
        Componente.objects.bulk_create(
            [Componente(produto=produto, ordem=i, **c) for i, c in enumerate(componentes)]
        )

    def validate(self, attrs):
        usuario = self.context["request"].user
        modelo = attrs.get("padrao", self.instance.padrao if self.instance is not None else False)
        if modelo and not usuario.is_staff:
            raise serializers.ValidationError("Só a equipe do Orçaminio cria e altera modelos prontos.")
        if modelo:
            for c in attrs.get("componentes") or []:
                if c["item"].fornecedor.vidraceiro_id is not None:
                    raise serializers.ValidationError(
                        f"\"{c['item'].descricao}\" é um item próprio: modelos prontos só usam itens do catálogo do fornecedor."
                    )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        componentes = validated_data.pop("componentes")
        modelo = validated_data.pop("padrao", False)
        dono = None if modelo else self.context["request"].user
        produto = Produto.objects.create(vidraceiro=dono, **validated_data)
        self._salvar_componentes(produto, componentes)
        return produto

    @transaction.atomic
    def update(self, instance, validated_data):
        componentes = validated_data.pop("componentes", None)
        if "padrao" in validated_data:
            # Equipe: marcar vira modelo pronto; desmarcar volta a ser um produto da própria conta.
            instance.vidraceiro = None if validated_data.pop("padrao") else self.context["request"].user
        for campo, valor in validated_data.items():
            setattr(instance, campo, valor)
        instance.save()
        if componentes is not None:
            self._salvar_componentes(instance, componentes)
        return instance


class ComponenteSimulacaoSerializer(serializers.Serializer):
    item = serializers.PrimaryKeyRelatedField(queryset=ItemFornecedor.objects.all())
    coef_largura = serializers.DecimalField(max_digits=8, decimal_places=4, default=0)
    coef_altura = serializers.DecimalField(max_digits=8, decimal_places=4, default=0)
    coef_area = serializers.DecimalField(max_digits=8, decimal_places=4, default=0)
    ajuste = serializers.DecimalField(max_digits=10, decimal_places=4, default=0)
    observacao = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    cobranca = serializers.ChoiceField(choices=["inteira", "metro"], default="inteira")

    def validate_item(self, item):
        if not item_visivel(item, self.context["request"].user):
            raise serializers.ValidationError("Item não encontrado.")
        return item


class SimulacaoSerializer(serializers.Serializer):
    largura_mm = serializers.IntegerField(min_value=0, max_value=20000, default=0)
    altura_mm = serializers.IntegerField(min_value=0, max_value=20000, default=0)
    componentes = ComponenteSimulacaoSerializer(many=True)
