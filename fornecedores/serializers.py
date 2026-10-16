from rest_framework import serializers

from .models import Fornecedor, ItemFornecedor


class FornecedorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Fornecedor
        fields = ("id", "nome", "slug", "proprio", "ultima_carga_completa")

    proprio = serializers.SerializerMethodField()

    def get_proprio(self, obj):
        return obj.vidraceiro_id is not None


class ItemCatalogoSerializer(serializers.ModelSerializer):
    imagem_url = serializers.SerializerMethodField()
    miniatura_url = serializers.SerializerMethodField()

    class Meta:
        model = ItemFornecedor
        fields = ("id", "fornecedor", "codigo", "descricao", "unidade", "comprimento_mm",
                  "preco", "estoque", "ativo", "atualizado_em", "imagem_url", "miniatura_url")

    def _url(self, arquivo):
        if not arquivo:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(arquivo.url) if request else arquivo.url

    def get_imagem_url(self, obj):
        return self._url(obj.imagem)

    def get_miniatura_url(self, obj):
        return self._url(obj.miniatura)


class ItemProprioSerializer(serializers.ModelSerializer):
    """Item que o vidraceiro cadastra (ex: vidros), fora do catálogo do fornecedor."""

    codigo = serializers.CharField(max_length=60, required=False, allow_blank=True)
    unidade = serializers.ChoiceField(choices=["M", "M2", "UN"])
    comprimento_mm = serializers.IntegerField(min_value=1, max_value=20000, required=False, allow_null=True)
    preco = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)
    imagem_url = serializers.SerializerMethodField()
    miniatura_url = serializers.SerializerMethodField()

    class Meta:
        model = ItemFornecedor
        fields = ("id", "fornecedor", "codigo", "descricao", "unidade", "comprimento_mm",
                  "preco", "estoque", "ativo", "atualizado_em", "imagem_url", "miniatura_url")
        read_only_fields = ("fornecedor", "estoque", "ativo", "atualizado_em")

    def get_imagem_url(self, obj):
        return None

    def get_miniatura_url(self, obj):
        return None

    def validate_descricao(self, valor):
        valor = valor.strip()
        if not valor:
            raise serializers.ValidationError("Dê um nome ao item.")
        return valor

    def validate(self, attrs):
        # Comprimento só faz sentido para peças inteiras vendidas por unidade (barras).
        if attrs.get("unidade", getattr(self.instance, "unidade", None)) != "UN":
            attrs["comprimento_mm"] = None
        return attrs
