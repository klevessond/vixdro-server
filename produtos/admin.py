from django.contrib import admin

from .models import Componente, Produto


class ComponenteInline(admin.TabularInline):
    model = Componente
    extra = 0
    autocomplete_fields = ("item",)
    fields = ("ordem", "item", "ajuste", "coef_largura", "coef_altura", "coef_area", "cobranca", "observacao")
    verbose_name = "item"
    verbose_name_plural = (
        "Itens e regras de consumo. Quantidade fixa por peça: preencha só o AJUSTE "
        "(ex: 4 roldanas = ajuste 4). Pela medida: COEF. LARGURA/ALTURA = quantas vezes a medida "
        "(ex: 2 trilhos na largura = coef. largura 2), com AJUSTE opcional em metros. "
        "Vidro: COEF. ÁREA 1 = a área da peça."
    )


class TipoProdutoFiltro(admin.SimpleListFilter):
    title = "tipo"
    parameter_name = "tipo"

    def lookups(self, request, model_admin):
        return [("modelo", "Modelos prontos"), ("vidraceiro", "Dos vidraceiros")]

    def queryset(self, request, qs):
        if self.value() == "modelo":
            return qs.filter(vidraceiro__isnull=True)
        if self.value() == "vidraceiro":
            return qs.filter(vidraceiro__isnull=False)
        return qs


@admin.register(Produto)
class ProdutoAdmin(admin.ModelAdmin):
    list_display = ("nome", "categoria", "dono", "qtd_itens", "ativo", "atualizado_em")
    list_filter = (TipoProdutoFiltro, "categoria", "ativo")
    search_fields = ("nome", "vidraceiro__email")
    autocomplete_fields = ("vidraceiro",)
    inlines = [ComponenteInline]
    fieldsets = (
        (None, {
            "fields": ("nome", "categoria", "descricao", "ativo"),
        }),
        ("Dono", {
            "fields": ("vidraceiro",),
            "description": "Vazio = MODELO PRONTO, que aparece para todos os vidraceiros (eles não podem "
                           "alterá-lo, só criar uma cópia própria). Desmarque \"ativo\" para tirar o modelo "
                           "do app sem apagá-lo.",
        }),
    )

    @admin.display(description="Dono")
    def dono(self, obj):
        return "Modelo pronto" if obj.vidraceiro_id is None else obj.vidraceiro.email

    @admin.display(description="Itens")
    def qtd_itens(self, obj):
        return obj.componentes.count()
