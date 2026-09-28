from django.contrib import admin

from .models import Vidraceiro


@admin.register(Vidraceiro)
class VidraceiroAdmin(admin.ModelAdmin):
    list_display = ("email", "nome", "empresa", "cidade", "estado", "is_active", "criado_em")
    list_filter = ("estado", "is_active")
    search_fields = ("email", "nome", "empresa", "cpf_cnpj")
    exclude = ("password",)
    readonly_fields = ("id", "last_login", "criado_em", "atualizado_em")
