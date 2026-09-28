from django.contrib import admin

from .models import Componente, Produto


class ComponenteInline(admin.TabularInline):
    model = Componente
    extra = 0
    autocomplete_fields = ("item",)
    fields = ("ordem", "item", "coef_largura", "coef_altura", "coef_area", "ajuste", "observacao")


@admin.register(Produto)
class ProdutoAdmin(admin.ModelAdmin):
    list_display = ("nome", "categoria", "vidraceiro", "ativo", "atualizado_em")
    list_filter = ("categoria", "ativo")
    search_fields = ("nome", "vidraceiro__email")
    inlines = [ComponenteInline]
