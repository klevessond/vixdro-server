from datetime import timedelta

from django.contrib import admin, messages
from django.contrib.admin.helpers import AdminForm
from django.contrib.admin.utils import unquote
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import AdminPasswordChangeForm
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from .models import Vidraceiro

# Nome do sistema no painel do admin (no lugar de "Administração do Django").
admin.site.site_header = "Orçaminio · Administração"
admin.site.site_title = "Orçaminio"
admin.site.index_title = "Painel"


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
    readonly_fields = ("id", "senha", "last_login", "criado_em", "atualizado_em")
    actions = ["liberar_pro_30", "liberar_pro_sem_prazo", "voltar_gratuito"]
    fieldsets = (
        (None, {"fields": ("id", "email", "nome", "empresa", "celular", "cpf_cnpj")}),
        ("Plano", {"fields": ("plano", "plano_validade", "plano_observacao")}),
        ("Endereço", {"fields": ("cep", "rua", "numero", "complemento", "bairro", "cidade", "estado"), "classes": ("collapse",)}),
        ("Acesso", {"fields": ("senha", "is_active", "is_staff", "is_superuser", "last_login", "criado_em", "atualizado_em")}),
    )

    # ---------- Senha ----------
    # A senha fica guardada criptografada e não aparece no formulário. A troca
    # é feita numa tela própria (a mesma do Django para usuários).

    @admin.display(description="Senha")
    def senha(self, obj):
        if obj is None or obj.pk is None:
            return "Defina depois de salvar."
        url = reverse("admin:contas_vidraceiro_senha", args=[obj.pk])
        return format_html('<a class="button" href="{}">Definir nova senha</a>', url)

    def get_urls(self):
        return [
            path("<id>/senha/", self.admin_site.admin_view(self.alterar_senha), name="contas_vidraceiro_senha"),
        ] + super().get_urls()

    def alterar_senha(self, request, id):
        usuario = self.get_object(request, unquote(id))
        if usuario is None:
            raise Http404("Vidraceiro não encontrado.")
        if not self.has_change_permission(request, usuario):
            raise PermissionDenied
        if request.method == "POST":
            form = AdminPasswordChangeForm(usuario, request.POST)
            if form.is_valid():
                form.save()
                if request.user.pk == usuario.pk:
                    update_session_auth_hash(request, form.user)  # não desloga quem trocou a própria senha
                self.message_user(request, f"Senha de {usuario.email} alterada.", messages.SUCCESS)
                return redirect(reverse("admin:contas_vidraceiro_change", args=[usuario.pk]))
        else:
            form = AdminPasswordChangeForm(usuario)
        contexto = {
            **self.admin_site.each_context(request),
            "title": f"Nova senha: {usuario.email}",
            "adminForm": AdminForm(form, [(None, {"fields": list(form.base_fields)})], {}),
            "form_url": "",
            "form": form,
            "is_popup": False,
            "is_popup_var": "_popup",
            "add": True,
            "change": False,
            "has_delete_permission": False,
            "has_change_permission": True,
            "has_absolute_url": False,
            "opts": self.opts,
            "original": usuario,
            "save_as": False,
            "show_save": True,
        }
        request.current_app = self.admin_site.name
        return TemplateResponse(request, "admin/auth/user/change_password.html", contexto)

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
