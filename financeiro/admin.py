from django.contrib import admin

from .models import Lancamento


@admin.register(Lancamento)
class LancamentoAdmin(admin.ModelAdmin):
    list_display = ("vencimento", "tipo", "descricao", "valor", "pago", "vidraceiro")
    list_filter = ("tipo", "pago")
    search_fields = ("descricao", "vidraceiro__email", "cliente__nome")
    date_hierarchy = "vencimento"
