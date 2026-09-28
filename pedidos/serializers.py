from rest_framework import serializers

from .models import ItemPedido, Pedido


class ItemPedidoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemPedido
        fields = ("codigo", "descricao", "unidade", "quantidade", "preco_unitario", "subtotal")


class PedidoSerializer(serializers.ModelSerializer):
    fornecedor_nome = serializers.CharField(source="fornecedor.nome", read_only=True)
    status_texto = serializers.CharField(source="get_status_display", read_only=True)
    itens = ItemPedidoSerializer(many=True, read_only=True)

    class Meta:
        model = Pedido
        fields = ("id", "projeto", "fornecedor", "fornecedor_nome", "status", "status_texto",
                  "numero_fornecedor", "total", "erro", "criado_em", "enviado_em", "itens")
