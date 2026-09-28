import uuid

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Max
from rest_framework import serializers

from clientes.models import Cliente
from fornecedores.models import ItemFornecedor
from fornecedores.serializers import ItemCatalogoSerializer
from produtos.calculo import modo
from produtos.models import Produto

from .models import ItemLinha, LinhaProjeto, Projeto

CAMPOS_REGRA = ("coef_largura", "coef_altura", "coef_area", "ajuste")
CAMPOS_PRECO = ("margem_percentual", "mao_de_obra_m2", "mao_de_obra_minima",
                "descricao_adicional", "valor_adicional", "desconto", "validade_dias")


def _validar_regra(attrs):
    if all(attrs.get(c, 0) == 0 for c in CAMPOS_REGRA):
        raise serializers.ValidationError(f"Defina a regra de consumo de {attrs['item'].descricao}.")
    return attrs


class ItemLinhaSerializer(serializers.ModelSerializer):
    item = serializers.PrimaryKeyRelatedField(queryset=ItemFornecedor.objects.all())
    item_detalhe = ItemCatalogoSerializer(source="item", read_only=True)
    modo = serializers.SerializerMethodField()

    class Meta:
        model = ItemLinha
        fields = ("item", "item_detalhe", "modo", *CAMPOS_REGRA, "observacao")

    def get_modo(self, obj):
        return modo(obj.item)

    def validate(self, attrs):
        return _validar_regra(attrs)


class LinhaSerializer(serializers.ModelSerializer):
    itens = ItemLinhaSerializer(many=True)
    produto = serializers.PrimaryKeyRelatedField(queryset=Produto.objects.all(), required=False, allow_null=True)
    largura_mm = serializers.IntegerField(min_value=1, max_value=20000)
    altura_mm = serializers.IntegerField(min_value=1, max_value=20000)
    quantidade = serializers.IntegerField(min_value=1, max_value=999)

    class Meta:
        model = LinhaProjeto
        fields = ("id", "produto", "nome", "largura_mm", "altura_mm", "quantidade", "observacao", "itens")
        read_only_fields = ("id",)

    def validate_produto(self, produto):
        # Só produtos do próprio vidraceiro.
        if produto is not None and produto.vidraceiro_id != self.context["request"].user.pk:
            raise serializers.ValidationError("Produto não encontrado.")
        return produto

    def validate_itens(self, itens):
        if not itens:
            raise serializers.ValidationError("A peça precisa ter pelo menos um item.")
        return itens


class ProjetoResumoSerializer(serializers.ModelSerializer):
    """Versão leve, para a lista de projetos."""

    cliente_nome = serializers.CharField(source="cliente.nome", read_only=True)
    total_pecas = serializers.IntegerField(read_only=True)

    class Meta:
        model = Projeto
        fields = ("id", "numero", "nome", "cliente", "cliente_nome", "status", "total_pecas", "atualizado_em")


class ProjetoSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(required=False)
    cliente = serializers.PrimaryKeyRelatedField(
        queryset=Cliente.objects.none(),
        error_messages={
            "does_not_exist": "Cliente não encontrado. Se ele foi cadastrado agora, "
                              "aguarde o envio (é preciso estar com internet).",
        },
    )
    cliente_nome = serializers.CharField(source="cliente.nome", read_only=True)
    linhas = LinhaSerializer(many=True)
    perda_percentual = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=50, required=False)
    margem_percentual = serializers.DecimalField(max_digits=6, decimal_places=2, min_value=0, max_value=1000, required=False)
    mao_de_obra_m2 = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0, required=False)
    mao_de_obra_minima = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0, required=False)
    valor_adicional = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0, required=False)
    desconto = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0, required=False)
    validade_dias = serializers.IntegerField(min_value=1, max_value=365, required=False)

    class Meta:
        model = Projeto
        fields = ("id", "numero", "nome", "cliente", "cliente_nome", "status", "status_atualizado_em",
                  "observacoes", "perda_percentual", *CAMPOS_PRECO, "linhas", "criado_em", "atualizado_em")
        # O status muda só pela ação própria (POST .../status/), nunca junto com a edição.
        read_only_fields = ("numero", "status", "status_atualizado_em", "criado_em", "atualizado_em")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request is not None:
            # Só é possível escolher clientes do próprio vidraceiro.
            self.fields["cliente"].queryset = Cliente.objects.filter(vidraceiro=request.user, ativo=True)

    def validate(self, attrs):
        if self.instance is not None:
            attrs.pop("id", None)  # o id nunca muda numa edição
        return attrs

    def validate_nome(self, valor):
        valor = valor.strip()
        if not valor:
            raise serializers.ValidationError("Dê um nome ao projeto.")
        return valor

    @staticmethod
    def _salvar_linhas(projeto, linhas):
        projeto.linhas.all().delete()
        for ordem, dados in enumerate(linhas):
            itens = dados.pop("itens")
            linha = LinhaProjeto.objects.create(projeto=projeto, ordem=ordem, **dados)
            ItemLinha.objects.bulk_create(
                [ItemLinha(linha=linha, ordem=i, **it) for i, it in enumerate(itens)]
            )

    @transaction.atomic
    def create(self, validated_data):
        linhas = validated_data.pop("linhas")
        usuario = self.context["request"].user
        # Trava o vidraceiro enquanto numera, para dois projetos criados ao
        # mesmo tempo não ganharem o mesmo número.
        get_user_model().objects.select_for_update().filter(pk=usuario.pk).first()
        ultimo = Projeto.objects.filter(vidraceiro=usuario).aggregate(m=Max("numero"))["m"] or 0
        projeto = Projeto.objects.create(vidraceiro=usuario, numero=ultimo + 1, **validated_data)
        self._salvar_linhas(projeto, linhas)
        return projeto

    @transaction.atomic
    def update(self, instance, validated_data):
        linhas = validated_data.pop("linhas", None)
        for campo, valor in validated_data.items():
            setattr(instance, campo, valor)
        instance.save()
        if linhas is not None:
            self._salvar_linhas(instance, linhas)
        return instance


# ---------- Cálculo sem salvar (o app calcula enquanto edita) ----------

class ItemCalculoSerializer(serializers.Serializer):
    item = serializers.PrimaryKeyRelatedField(queryset=ItemFornecedor.objects.all())
    coef_largura = serializers.DecimalField(max_digits=8, decimal_places=4, default=0)
    coef_altura = serializers.DecimalField(max_digits=8, decimal_places=4, default=0)
    coef_area = serializers.DecimalField(max_digits=8, decimal_places=4, default=0)
    ajuste = serializers.DecimalField(max_digits=10, decimal_places=4, default=0)
    observacao = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")


class LinhaCalculoSerializer(serializers.Serializer):
    nome = serializers.CharField(max_length=150)
    largura_mm = serializers.IntegerField(min_value=1, max_value=20000)
    altura_mm = serializers.IntegerField(min_value=1, max_value=20000)
    quantidade = serializers.IntegerField(min_value=1, max_value=999, default=1)
    itens = ItemCalculoSerializer(many=True)


class CalculoSerializer(serializers.Serializer):
    perda_percentual = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=50, default=10)
    margem_percentual = serializers.DecimalField(max_digits=6, decimal_places=2, min_value=0, max_value=1000, default=0)
    mao_de_obra_m2 = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0, default=0)
    mao_de_obra_minima = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0, default=0)
    descricao_adicional = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    valor_adicional = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0, default=0)
    desconto = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0, default=0)
    linhas = LinhaCalculoSerializer(many=True)
