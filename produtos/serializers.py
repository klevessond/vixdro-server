from django.db import transaction
from rest_framework import serializers

from fornecedores.models import ItemFornecedor, item_visivel
from fornecedores.serializers import ItemCatalogoSerializer

from .calculo import modo
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
            raise serializers.ValidationError(
                f"Defina a regra de consumo de {attrs['item'].descricao}."
            )
        return attrs


class ProdutoSerializer(serializers.ModelSerializer):
    componentes = ComponenteSerializer(many=True)

    class Meta:
        model = Produto
        fields = ("id", "nome", "categoria", "descricao", "componentes", "atualizado_em")
        read_only_fields = ("id", "atualizado_em")

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

    @transaction.atomic
    def create(self, validated_data):
        componentes = validated_data.pop("componentes")
        produto = Produto.objects.create(vidraceiro=self.context["request"].user, **validated_data)
        self._salvar_componentes(produto, componentes)
        return produto

    @transaction.atomic
    def update(self, instance, validated_data):
        componentes = validated_data.pop("componentes", None)
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
