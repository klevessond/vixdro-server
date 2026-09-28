import uuid

from django.conf import settings
from django.db import models

from fornecedores.models import Fornecedor, ItemFornecedor
from projetos.models import Projeto


class Pedido(models.Model):
    """Pedido de compra enviado ao fornecedor, a partir da lista de compra
    de um projeto aprovado. Um projeto com itens de dois fornecedores gera
    dois pedidos."""

    class Status(models.TextChoices):
        ENVIANDO = "enviando", "Enviando"
        ERRO = "erro", "Erro no envio"
        RECEBIDO = "recebido", "Recebido pelo fornecedor"
        EM_SEPARACAO = "em_separacao", "Em separação"
        FATURADO = "faturado", "Faturado"
        CANCELADO = "cancelado", "Cancelado"

    # Também é o identificador enviado ao fornecedor: reenviar o mesmo
    # pedido nunca cria um segundo lá.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vidraceiro = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="pedidos")
    projeto = models.ForeignKey(Projeto, on_delete=models.PROTECT, related_name="pedidos")
    fornecedor = models.ForeignKey(Fornecedor, on_delete=models.PROTECT, related_name="pedidos")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ENVIANDO)
    status_fornecedor = models.CharField(max_length=40, blank=True, help_text="Status exatamente como o fornecedor informou")
    numero_fornecedor = models.CharField(max_length=40, blank=True)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    erro = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    enviado_em = models.DateTimeField(null=True, blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        return f"Pedido {self.numero_fornecedor or self.id} - {self.fornecedor}"


class ItemPedido(models.Model):
    """Cópia do que foi pedido, com o preço da época (o catálogo muda depois)."""

    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name="itens")
    item = models.ForeignKey(ItemFornecedor, on_delete=models.PROTECT, related_name="+")
    codigo = models.CharField(max_length=60)
    descricao = models.CharField(max_length=255)
    unidade = models.CharField(max_length=10)
    quantidade = models.DecimalField(max_digits=12, decimal_places=3)
    preco_unitario = models.DecimalField(max_digits=12, decimal_places=2)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ["codigo"]
