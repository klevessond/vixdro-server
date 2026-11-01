"""Estoque de materiais (plano Pro).

O saldo de cada item é a SOMA das movimentações (entradas positivas, saídas
negativas), na unidade de estoque: perfis e itens por metro em METROS, vidros
em m², o resto na unidade de venda (un, cx...). Assim fica o histórico de tudo
o que entrou e saiu, e um erro se corrige com um ajuste, sem perder o rastro."""

import uuid

from django.conf import settings
from django.db import models

from fornecedores.models import ItemFornecedor


class Movimento(models.Model):
    class Motivo(models.TextChoices):
        INVENTARIO = "inventario", "Contagem (inventário)"
        PEDIDO = "pedido", "Pedido recebido"
        COMPRA = "compra", "Compra recebida"
        OBRA = "obra", "Usado em obra"
        PERDA = "perda", "Perda ou quebra"
        AJUSTE = "ajuste", "Ajuste"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vidraceiro = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="movimentos_estoque")
    item = models.ForeignKey(ItemFornecedor, on_delete=models.PROTECT, related_name="movimentos_estoque")
    quantidade = models.DecimalField(max_digits=14, decimal_places=4)  # + entra, - sai (unidade de estoque)
    custo_unitario = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)  # por unidade de estoque
    motivo = models.CharField(max_length=15, choices=Motivo.choices)
    projeto = models.ForeignKey("projetos.Projeto", on_delete=models.SET_NULL, null=True, blank=True, related_name="movimentos_estoque")
    pedido = models.ForeignKey("pedidos.Pedido", on_delete=models.SET_NULL, null=True, blank=True, related_name="movimentos_estoque")
    observacao = models.CharField(max_length=200, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]
        indexes = [models.Index(fields=["vidraceiro", "item"])]


class ConfigItemEstoque(models.Model):
    """Estoque mínimo de um item (aviso quando o saldo fica abaixo)."""

    vidraceiro = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    item = models.ForeignKey(ItemFornecedor, on_delete=models.CASCADE, related_name="+")
    minimo = models.DecimalField(max_digits=14, decimal_places=4, default=0)

    class Meta:
        unique_together = ("vidraceiro", "item")
