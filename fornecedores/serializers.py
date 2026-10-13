from rest_framework import serializers

from .models import Fornecedor, ItemFornecedor


class FornecedorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Fornecedor
        fields = ("id", "nome", "slug", "ultima_carga_completa")


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
