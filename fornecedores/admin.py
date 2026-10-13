from django.contrib import admin, messages
from django.utils.html import format_html

from .models import Fornecedor, ItemFornecedor, Sincronizacao


@admin.register(Fornecedor)
class FornecedorAdmin(admin.ModelAdmin):
    list_display = ("nome", "slug", "adaptador", "ativo", "cursor_sincronizacao", "ultima_carga_completa")
    prepopulated_fields = {"slug": ("nome",)}
    readonly_fields = ("cursor_sincronizacao", "ultima_carga_completa")


@admin.register(ItemFornecedor)
class ItemFornecedorAdmin(admin.ModelAdmin):
    list_display = ("foto", "codigo", "descricao", "unidade", "comprimento_mm", "preco", "estoque", "ativo", "fornecedor")
    list_display_links = ("foto", "codigo")
    list_filter = ("fornecedor", "ativo", "unidade", ("imagem", admin.EmptyFieldListFilter))
    search_fields = ("codigo", "descricao")
    list_per_page = 50
    actions = ["copiar_imagem"]
    # O catálogo é espelho do fornecedor: só a imagem é editável aqui. O resto
    # seria desfeito na próxima sincronização.
    fields = ("previa", "imagem", "codigo", "descricao", "unidade", "comprimento_mm", "preco",
              "estoque", "ativo", "fornecedor", "atualizado_em")
    readonly_fields = ("previa", "codigo", "descricao", "unidade", "comprimento_mm", "preco",
                       "estoque", "ativo", "fornecedor", "atualizado_em")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Imagem")
    def foto(self, obj):
        if not obj.miniatura:
            return format_html('<span style="color:#999">sem imagem</span>')
        return format_html('<img src="{}" style="height:48px;width:48px;object-fit:contain;background:#f4f4f4;border-radius:4px">', obj.miniatura.url)

    @admin.display(description="Prévia")
    def previa(self, obj):
        if not obj.imagem:
            return "Nenhuma imagem enviada ainda."
        return format_html('<img src="{}" style="max-height:260px;max-width:100%;background:#f4f4f4;border-radius:6px">', obj.imagem.url)

    def save_model(self, request, obj, form, change):
        if "imagem" in form.changed_data:
            # O arquivo antigo NÃO é apagado: outros itens (o mesmo perfil em
            # outras cores) podem estar usando a mesma imagem.
            obj.gerar_miniatura()
        super().save_model(request, obj, form, change)

    @admin.action(description="Aplicar a imagem de um item aos outros selecionados")
    def copiar_imagem(self, request, queryset):
        com_imagem = [i for i in queryset if i.imagem]
        if len(com_imagem) != 1:
            self.message_user(
                request,
                "Selecione exatamente UM item com imagem, junto com os itens que devem recebê-la "
                "(por exemplo, o mesmo perfil nas outras cores).",
                level=messages.WARNING,
            )
            return
        origem = com_imagem[0]
        destinos = queryset.exclude(pk=origem.pk)
        # Os itens passam a apontar para o mesmo arquivo: não duplica espaço em disco.
        total = destinos.update(imagem=origem.imagem.name, miniatura=origem.miniatura.name)
        self.message_user(request, f"Imagem de {origem.codigo} aplicada a {total} item(ns).", level=messages.SUCCESS)


@admin.register(Sincronizacao)
class SincronizacaoAdmin(admin.ModelAdmin):
    list_display = ("fornecedor", "tipo", "status", "inicio", "fim", "recebidos", "novos", "alterados", "desativados", "ignorados")
    list_filter = ("fornecedor", "status", "tipo")
    readonly_fields = [f.name for f in Sincronizacao._meta.fields]

    def has_add_permission(self, request):
        return False
