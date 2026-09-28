from django.db import models

ADAPTADORES = [
    ("padrao_vixdro", "Padrão vixdro (pacote integracao_vixdro)"),
]


class Fornecedor(models.Model):
    """Empresa fornecedora cujo catálogo o vixdro espelha."""

    nome = models.CharField(max_length=150)
    slug = models.SlugField(unique=True, help_text="Identificador curto, ex: aluminio-serido")
    adaptador = models.CharField(max_length=50, choices=ADAPTADORES, default="padrao_vixdro")
    url_base = models.URLField(
        help_text="Endereço da API do fornecedor, terminando em /. Ex: http://localhost:8001/api/vixdro/v1/"
    )
    variavel_chave = models.CharField(
        max_length=100,
        help_text="Nome da variável do .env que guarda a chave de acesso. "
        "A chave nunca fica no banco. Ex: FORNECEDOR_SERIDO_CHAVE",
    )
    ativo = models.BooleanField(default=True)

    # Controle da sincronização
    cursor_sincronizacao = models.DateTimeField(
        null=True, blank=True, editable=False,
        help_text="Horário informado pelo fornecedor na última sincronização bem-sucedida",
    )
    ultima_carga_completa = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        verbose_name = "fornecedor"
        verbose_name_plural = "fornecedores"
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class ItemFornecedor(models.Model):
    """Cópia local de um item do catálogo do fornecedor.

    Itens nunca são apagados, só desativados: produtos montados pelos
    vidraceiros apontam para eles.
    """

    fornecedor = models.ForeignKey(Fornecedor, on_delete=models.PROTECT, related_name="itens")
    codigo = models.CharField(max_length=60)
    descricao = models.CharField(max_length=255)
    unidade = models.CharField(max_length=10)
    comprimento_mm = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Preenchido quando o item é vendido em peças de comprimento fixo (barras, rolos)",
    )
    preco = models.DecimalField(max_digits=12, decimal_places=2)
    estoque = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    ativo = models.BooleanField(default=True)

    atualizado_no_fornecedor = models.DateTimeField(null=True, blank=True)
    # Muda só quando algum dado do item muda de fato. É o que o app usa
    # para baixar apenas as alterações.
    atualizado_em = models.DateTimeField(db_index=True)
    # Última carga em que o item apareceu. Usado na carga completa para
    # desativar itens que sumiram da lista do fornecedor.
    visto_em = models.DateTimeField()

    class Meta:
        verbose_name = "item do fornecedor"
        verbose_name_plural = "itens dos fornecedores"
        constraints = [
            models.UniqueConstraint(fields=["fornecedor", "codigo"], name="item_unico_por_fornecedor"),
        ]
        ordering = ["codigo"]

    def __str__(self):
        return f"{self.codigo} - {self.descricao}"

    @property
    def vendido_por_comprimento(self):
        return self.comprimento_mm is not None


class Sincronizacao(models.Model):
    """Registro de cada execução, para acompanhar pelo admin."""

    class Tipo(models.TextChoices):
        INCREMENTAL = "incremental", "Incremental"
        COMPLETA = "completa", "Completa"

    class Status(models.TextChoices):
        EXECUTANDO = "executando", "Executando"
        SUCESSO = "sucesso", "Sucesso"
        ERRO = "erro", "Erro"

    fornecedor = models.ForeignKey(Fornecedor, on_delete=models.CASCADE, related_name="sincronizacoes")
    tipo = models.CharField(max_length=15, choices=Tipo.choices)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.EXECUTANDO)
    inicio = models.DateTimeField(auto_now_add=True)
    fim = models.DateTimeField(null=True, blank=True)
    recebidos = models.PositiveIntegerField(default=0)
    novos = models.PositiveIntegerField(default=0)
    alterados = models.PositiveIntegerField(default=0)
    desativados = models.PositiveIntegerField(default=0)
    ignorados = models.PositiveIntegerField(default=0)
    erro = models.TextField(blank=True)

    class Meta:
        verbose_name = "sincronização"
        verbose_name_plural = "sincronizações"
        ordering = ["-inicio"]

    def __str__(self):
        return f"{self.fornecedor} - {self.get_tipo_display()} - {self.inicio:%d/%m/%Y %H:%M}"
