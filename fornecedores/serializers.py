from rest_framework import serializers

from .models import Fornecedor, ItemFornecedor


class FornecedorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Fornecedor
        fields = ("id", "nome", "slug", "ultima_carga_completa")


class ItemCatalogoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemFornecedor
        fields = ("id", "fornecedor", "codigo", "descricao", "unidade", "comprimento_mm",
                  "preco", "estoque", "ativo", "atualizado_em")
