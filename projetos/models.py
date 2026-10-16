import uuid

from django.conf import settings
from django.db import models

from clientes.models import Cliente
from fornecedores.models import ItemFornecedor
from produtos.models import Produto


class Projeto(models.Model):
    """Um trabalho para um cliente: as janelas, portas e boxes com as medidas."""

    class Status(models.TextChoices):
        RASCUNHO = "rascunho", "Rascunho"
        ENVIADO = "enviado", "Enviado ao cliente"
        APROVADO = "aprovado", "Aprovado"
        RECUSADO = "recusado", "Recusado"

    # Gerado no app (como nos clientes), para a versão offline no futuro.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    vidraceiro = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="projetos"
    )
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="projetos")
    nome = models.CharField(max_length=150, help_text="Ex: Reforma da cozinha")
    observacoes = models.TextField(blank=True)
    perda_percentual = models.DecimalField(
        max_digits=5, decimal_places=2, default=10,
        help_text="Sobra estimada no corte dos perfis, usada na lista de compra",
    )

    # Numeração do orçamento, sequencial por vidraceiro (Orçamento nº 12).
    numero = models.PositiveIntegerField(null=True, blank=True, editable=False)

    # Preço para o cliente final. O cliente vê só o resultado, nunca o custo.
    margem_percentual = models.DecimalField(
        max_digits=6, decimal_places=2, default=30,
        help_text="Lucro sobre o material (já com a perda de corte)",
    )
    mao_de_obra_m2 = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                                         help_text="Mão de obra por m² de peça")
    mao_de_obra_minima = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                                             help_text="Valor mínimo de mão de obra por peça")
    descricao_adicional = models.CharField(max_length=100, blank=True, default="Instalação",
                                           help_text="Ex: Instalação e frete")
    valor_adicional = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    desconto = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    validade_dias = models.PositiveIntegerField(default=15)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.RASCUNHO)
    status_atualizado_em = models.DateTimeField(null=True, blank=True)

    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        ordering = ["-atualizado_em"]

    def __str__(self):
        return self.nome


class LinhaProjeto(models.Model):
    """Uma peça do projeto, ex: "Janela da sala", 1200 x 1000 mm, 2 unidades."""

    projeto = models.ForeignKey(Projeto, on_delete=models.CASCADE, related_name="linhas")
    # Só referência de origem. Os itens ficam copiados em ItemLinha, então
    # mudar ou excluir o produto depois não altera o projeto.
    produto = models.ForeignKey(Produto, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    nome = models.CharField(max_length=150)
    largura_mm = models.PositiveIntegerField()
    altura_mm = models.PositiveIntegerField()
    quantidade = models.PositiveIntegerField(default=1)
    observacao = models.CharField(max_length=150, blank=True)
    ordem = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["ordem", "id"]


class ItemLinha(models.Model):
    """Cópia de um componente do produto, editável só nesta linha."""

    linha = models.ForeignKey(LinhaProjeto, on_delete=models.CASCADE, related_name="itens")
    item = models.ForeignKey(ItemFornecedor, on_delete=models.PROTECT, related_name="+")
    coef_largura = models.DecimalField(max_digits=8, decimal_places=4, default=0)
    coef_altura = models.DecimalField(max_digits=8, decimal_places=4, default=0)
    coef_area = models.DecimalField(max_digits=8, decimal_places=4, default=0)
    ajuste = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    observacao = models.CharField(max_length=100, blank=True)
    # Só para itens vendidos em barra: cobrar a barra inteira ou só os metros usados.
    cobranca = models.CharField(
        max_length=10, choices=[("inteira", "Barra inteira"), ("metro", "Por metro usado")], default="inteira",
    )
    ordem = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["ordem", "id"]
