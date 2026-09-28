from django.contrib import admin

from .models import Fornecedor, ItemFornecedor, Sincronizacao


@admin.register(Fornecedor)
class FornecedorAdmin(admin.ModelAdmin):
    list_display = ("nome", "slug", "adaptador", "ativo", "cursor_sincronizacao", "ultima_carga_completa")
    prepopulated_fields = {"slug": ("nome",)}
    readonly_fields = ("cursor_sincronizacao", "ultima_carga_completa")


@admin.register(ItemFornecedor)
class ItemFornecedorAdmin(admin.ModelAdmin):
    list_display = ("codigo", "descricao", "unidade", "comprimento_mm", "preco", "estoque", "ativo", "fornecedor")
    list_filter = ("fornecedor", "ativo", "unidade")
    search_fields = ("codigo", "descricao")
    # O catálogo é espelho do fornecedor: editar aqui seria desfeito na próxima sincronização.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Sincronizacao)
class SincronizacaoAdmin(admin.ModelAdmin):
    list_display = ("fornecedor", "tipo", "status", "inicio", "fim", "recebidos", "novos", "alterados", "desativados", "ignorados")
    list_filter = ("fornecedor", "status", "tipo")
    readonly_fields = [f.name for f in Sincronizacao._meta.fields]

    def has_add_permission(self, request):
        return False
