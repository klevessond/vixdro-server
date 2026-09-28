from django.contrib import admin

from .models import LinhaProjeto, Projeto


class LinhaInline(admin.TabularInline):
    model = LinhaProjeto
    extra = 0
    fields = ("ordem", "nome", "largura_mm", "altura_mm", "quantidade", "produto")
    show_change_link = True


@admin.register(Projeto)
class ProjetoAdmin(admin.ModelAdmin):
    list_display = ("nome", "cliente", "vidraceiro", "ativo", "atualizado_em")
    list_filter = ("ativo",)
    search_fields = ("nome", "cliente__nome", "vidraceiro__email")
    readonly_fields = ("id", "criado_em", "atualizado_em")
    inlines = [LinhaInline]
