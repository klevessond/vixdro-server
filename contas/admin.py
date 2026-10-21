from datetime import timedelta

from django.contrib import admin, messages
from django.utils import timezone
from django.utils.html import format_html

from .models import Vidraceiro


class PlanoFiltro(admin.SimpleListFilter):
    title = "plano ativo"
    parameter_name = "plano_ativo"

    def lookups(self, request, model_admin):
        return [("pro", "Pro ativo"), ("vencido", "Pro vencido"), ("gratuito", "Gratuito")]

    def queryset(self, request, qs):
        hoje = timezone.localdate()
        if self.value() == "pro":
            return qs.filter(plano="pro").exclude(plano_validade__lt=hoje)
        if self.value() == "vencido":
            return qs.filter(plano="pro", plano_validade__lt=hoje)
        if self.value() == "gratuito":
            return qs.filter(plano="gratuito")
        return qs


@admin.register(Vidraceiro)
class VidraceiroAdmin(admin.ModelAdmin):
    list_display = ("email", "nome", "empresa", "cidade", "situacao_plano", "plano_validade", "is_active", "criado_em")
    list_filter = (PlanoFiltro, "estado", "is_active")
    search_fields = ("email", "nome", "empresa", "cpf_cnpj")
    exclude = ("password",)
    readonly_fields = ("id", "last_login", "criado_em", "atualizado_em")
    actions = ["liberar_pro_30", "liberar_pro_sem_prazo", "voltar_gratuito"]
    fieldsets = (
        (None, {"fields": ("id", "email", "nome", "empresa", "celular", "cpf_cnpj")}),
        ("Plano", {"fields": ("plano", "plano_validade", "plano_observacao")}),
        ("Endereço", {"fields": ("cep", "rua", "numero", "complemento", "bairro", "cidade", "estado"), "classes": ("collapse",)}),
        ("Acesso", {"fields": ("is_active", "is_staff", "is_superuser", "last_login", "criado_em", "atualizado_em"), "classes": ("collapse",)}),
    )

    @admin.display(description="Plano")
    def situacao_plano(self, obj):
        if obj.tem_pro:
            return format_html('<b style="color:#1E5B57">Pro</b>')
        if obj.plano == "pro":
            return format_html('<span style="color:#A32121">Pro vencido</span>')
        return "Gratuito"

    @admin.action(description="Liberar Pro por 30 dias")
    def liberar_pro_30(self, request, qs):
        validade = timezone.localdate() + timedelta(days=30)
        n = qs.update(plano="pro", plano_validade=validade)
        self.message_user(request, f"Pro liberado para {n} conta(s) até {validade:%d/%m/%Y}.", messages.SUCCESS)

    @admin.action(description="Liberar Pro sem prazo")
    def liberar_pro_sem_prazo(self, request, qs):
        n = qs.update(plano="pro", plano_validade=None)
        self.message_user(request, f"Pro liberado sem prazo para {n} conta(s).", messages.SUCCESS)

    @admin.action(description="Voltar para o plano gratuito")
    def voltar_gratuito(self, request, qs):
        n = qs.update(plano="gratuito", plano_validade=None)
        self.message_user(request, f"{n} conta(s) voltaram para o plano gratuito.", messages.SUCCESS)
