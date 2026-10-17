from django.contrib import admin

from .models import Compromisso


@admin.register(Compromisso)
class CompromissoAdmin(admin.ModelAdmin):
    list_display = ("inicio", "tipo", "cliente", "projeto", "vidraceiro", "concluido")
    list_filter = ("tipo", "concluido")
    search_fields = ("cliente__nome", "endereco", "vidraceiro__email")
    date_hierarchy = "inicio"
