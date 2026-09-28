from django.contrib import admin

from .models import ItemPedido, Pedido


class ItemPedidoInline(admin.TabularInline):
    model = ItemPedido
    extra = 0
    readonly_fields = ("codigo", "descricao", "unidade", "quantidade", "preco_unitario", "subtotal")
    exclude = ("item",)
    can_delete = False


@admin.register(Pedido)
class PedidoAdmin(admin.ModelAdmin):
    list_display = ("id", "fornecedor", "vidraceiro", "status", "numero_fornecedor", "total", "criado_em")
    list_filter = ("status", "fornecedor")
    search_fields = ("numero_fornecedor", "vidraceiro__email", "projeto__nome")
    readonly_fields = ("id", "criado_em", "enviado_em", "atualizado_em")
    inlines = [ItemPedidoInline]
