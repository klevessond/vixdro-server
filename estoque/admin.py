from django.contrib import admin

from .models import ConfigItemEstoque, Movimento


@admin.register(Movimento)
class MovimentoAdmin(admin.ModelAdmin):
    list_display = ("criado_em", "item", "quantidade", "motivo", "projeto", "vidraceiro")
    list_filter = ("motivo",)
    search_fields = ("item__codigo", "item__descricao", "vidraceiro__email")
    date_hierarchy = "criado_em"


admin.site.register(ConfigItemEstoque)
