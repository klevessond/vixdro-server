from django.contrib import admin, messages
from django.utils.html import format_html

from .models import Fornecedor, ItemFornecedor, Sincronizacao

# Uma tabela de preços em PDF tem poucos MB; acima disto não é uma.
IMPORTACAO_TAMANHO_MAXIMO = 20 * 1024 * 1024


@admin.register(Fornecedor)
class FornecedorAdmin(admin.ModelAdmin):
    list_display = ("nome", "slug", "adaptador", "ativo", "importar", "prazo_pagamento_dias", "cursor_sincronizacao", "ultima_carga_completa")
    list_editable = ("ativo",)
    prepopulated_fields = {"slug": ("nome",)}
    readonly_fields = ("cursor_sincronizacao", "ultima_carga_completa")

    # ---------- Importação por planilha (fornecedores sem integração) ----------

    @admin.display(description="Planilha")
    def importar(self, obj):
        if obj.adaptador != "manual":
            return "—"
        from django.urls import reverse
        from django.utils.html import format_html

        return format_html('<a class="button" href="{}">Importar tabela</a>', reverse("admin:fornecedores_importar", args=[obj.pk]))

    def get_urls(self):
        from django.urls import path

        return [path("<int:pk>/importar/", self.admin_site.admin_view(self.importar_view), name="fornecedores_importar")] + super().get_urls()

    def importar_view(self, request, pk):
        from django.contrib import messages
        from django.core.exceptions import PermissionDenied
        from django.shortcuts import get_object_or_404, redirect
        from django.template.response import TemplateResponse

        from .importacao import importar_arquivo

        fornecedor = get_object_or_404(Fornecedor, pk=pk)
        # A importação troca preços e desativa itens do catálogo inteiro: exige a
        # mesma permissão de editar o fornecedor (entrar no admin só não basta).
        if not self.has_change_permission(request, fornecedor):
            raise PermissionDenied
        arquivo = request.FILES.get("arquivo")
        if request.method == "POST" and arquivo and arquivo.size > IMPORTACAO_TAMANHO_MAXIMO:
            messages.error(request, "Arquivo grande demais (o limite é 20 MB).")
        elif request.method == "POST" and arquivo:
            r = importar_arquivo(fornecedor, arquivo.read(), bool(request.POST.get("desativar")))
            if r.get("erro_geral"):
                messages.error(request, r["erro_geral"])
            else:
                messages.success(request, f"{r['criados']} itens novos, {r['alterados']} atualizados, {r['desativados']} desativados.")
                for erro in r["erros"][:20]:
                    messages.warning(request, erro)
                return redirect("admin:fornecedores_fornecedor_changelist")
        contexto = {**self.admin_site.each_context(request), "fornecedor": fornecedor, "title": f"Importar tabela de preços: {fornecedor.nome}"}
        return TemplateResponse(request, "admin/fornecedores/importar.html", contexto)


@admin.register(ItemFornecedor)
class ItemFornecedorAdmin(admin.ModelAdmin):
    list_display = ("foto", "codigo", "descricao", "fabricante", "tipo", "unidade", "comprimento_mm", "preco", "ativo", "fornecedor")
    list_display_links = ("foto", "codigo")
    list_filter = ("tipo", "fornecedor", "ativo", "unidade", ("imagem", admin.EmptyFieldListFilter))
    search_fields = ("codigo", "descricao", "fabricante")
    list_per_page = 50
    actions = ["copiar_imagem"]
    # O catálogo é espelho do fornecedor: só a imagem é editável aqui. O resto
    # seria desfeito na próxima sincronização.
    fields = ("previa", "imagem", "codigo", "descricao", "fabricante", "tipo", "unidade", "comprimento_mm",
              "preco", "estoque", "ativo", "fornecedor", "atualizado_em")
    readonly_fields = ("previa", "codigo", "descricao", "fabricante", "tipo", "unidade", "comprimento_mm",
                       "preco", "estoque", "ativo", "fornecedor", "atualizado_em")

    def get_readonly_fields(self, request, obj=None):
        # Fornecedor por tabela de preços: a tabela não traz o comprimento da barra nem o
        # tipo com certeza, então a equipe pode corrigir. A próxima importação não desfaz.
        if obj is not None and obj.fornecedor.adaptador == "manual":
            return tuple(c for c in self.readonly_fields if c not in ("tipo", "comprimento_mm"))
        return self.readonly_fields

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Imagem")
    def foto(self, obj):
        if not obj.miniatura:
            return format_html('<span style="color:#999">sem imagem</span>')
        return format_html('<img src="{}" style="height:48px;width:48px;object-fit:contain;background:#f4f4f4;border-radius:4px">', obj.miniatura.url)

    @admin.display(description="Prévia")
    def previa(self, obj):
        if not obj.imagem:
            return "Nenhuma imagem enviada ainda."
        return format_html('<img src="{}" style="max-height:260px;max-width:100%;background:#f4f4f4;border-radius:6px">', obj.imagem.url)

    def save_model(self, request, obj, form, change):
        if "imagem" in form.changed_data:
            # O arquivo antigo NÃO é apagado: outros itens (o mesmo perfil em
            # outras cores) podem estar usando a mesma imagem.
            obj.gerar_miniatura()
        if {"tipo", "comprimento_mm"} & set(form.changed_data):
            from django.utils import timezone

            obj.atualizado_em = timezone.now()  # o app baixa só o que mudou
        super().save_model(request, obj, form, change)

    @admin.action(description="Aplicar a imagem de um item aos outros selecionados")
    def copiar_imagem(self, request, queryset):
        com_imagem = [i for i in queryset if i.imagem]
        if len(com_imagem) != 1:
            self.message_user(
                request,
                "Selecione exatamente UM item com imagem, junto com os itens que devem recebê-la "
                "(por exemplo, o mesmo perfil nas outras cores).",
                level=messages.WARNING,
            )
            return
        origem = com_imagem[0]
        destinos = queryset.exclude(pk=origem.pk)
        # Os itens passam a apontar para o mesmo arquivo: não duplica espaço em disco.
        total = destinos.update(imagem=origem.imagem.name, miniatura=origem.miniatura.name)
        self.message_user(request, f"Imagem de {origem.codigo} aplicada a {total} item(ns).", level=messages.SUCCESS)


@admin.register(Sincronizacao)
class SincronizacaoAdmin(admin.ModelAdmin):
    list_display = ("fornecedor", "tipo", "status", "inicio", "fim", "recebidos", "novos", "alterados", "desativados", "ignorados")
    list_filter = ("fornecedor", "status", "tipo")
    readonly_fields = [f.name for f in Sincronizacao._meta.fields]

    def has_add_permission(self, request):
        return False
