from django.contrib import admin

from .models import Cliente


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ("nome", "empresa", "celular", "cidade", "vidraceiro", "ativo", "atualizado_em")
    list_filter = ("ativo", "estado")
    search_fields = ("nome", "empresa", "celular", "cpf_cnpj", "vidraceiro__email")
    readonly_fields = ("id", "criado_em", "atualizado_em")
