import uuid

from django.conf import settings
from django.db import models

from clientes.models import Cliente
from projetos.models import Projeto


class Lancamento(models.Model):
    """Uma conta a receber ou a pagar (ou uma parcela dela)."""

    class Tipo(models.TextChoices):
        RECEBER = "receber", "A receber"
        PAGAR = "pagar", "A pagar"

    class Forma(models.TextChoices):
        PIX = "pix", "Pix"
        DINHEIRO = "dinheiro", "Dinheiro"
        CARTAO = "cartao", "Cartão"
        BOLETO = "boleto", "Boleto"
        TRANSFERENCIA = "transferencia", "Transferência"
        OUTRA = "outra", "Outra"

    CATEGORIAS = {
        "receber": ["Orçamento", "Serviço avulso", "Outros"],
        "pagar": ["Fornecedor de alumínio", "Vidro", "Acessórios", "Combustível", "Funcionários",
                  "Aluguel", "Ferramentas", "Impostos", "Outros"],
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vidraceiro = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lancamentos")
    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    descricao = models.CharField(max_length=150)
    categoria = models.CharField(max_length=50, blank=True)
    valor = models.DecimalField(max_digits=12, decimal_places=2)
    vencimento = models.DateField(db_index=True)
    pago = models.BooleanField(default=False)
    pago_em = models.DateField(null=True, blank=True)
    forma = models.CharField(max_length=15, choices=Forma.choices, blank=True)
    # Conta onde o dinheiro entrou ou saiu (quando pago).
    conta = models.ForeignKey("Conta", on_delete=models.SET_NULL, null=True, blank=True, related_name="lancamentos")
    cliente = models.ForeignKey(Cliente, on_delete=models.SET_NULL, null=True, blank=True, related_name="lancamentos")
    projeto = models.ForeignKey(Projeto, on_delete=models.SET_NULL, null=True, blank=True, related_name="lancamentos")
    # Parcelamento: as parcelas de um mesmo lançamento compartilham o grupo.
    grupo = models.UUIDField(null=True, blank=True, db_index=True)
    parcela = models.PositiveIntegerField(default=1)
    total_parcelas = models.PositiveIntegerField(default=1)
    observacoes = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["vencimento", "criado_em"]

    def __str__(self):
        return f"{self.get_tipo_display()}: {self.descricao} ({self.valor})"


class CondicaoPagamento(models.Model):
    """Forma de pagamento que o vidraceiro oferece (aparece no PDF do orçamento).

    Ex: "À vista (Pix ou dinheiro)" com 5% de desconto; "Parcelado" em até 3x;
    "Entrada + parcelas" com 50% de entrada."""

    class Tipo(models.TextChoices):
        AVISTA = "avista", "À vista"
        PARCELADO = "parcelado", "Parcelado"
        ENTRADA = "entrada", "Entrada + parcelas"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vidraceiro = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="condicoes_pagamento")
    nome = models.CharField(max_length=60)
    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    desconto_percentual = models.DecimalField(max_digits=5, decimal_places=2, default=0)  # à vista
    acrescimo_percentual = models.DecimalField(max_digits=5, decimal_places=2, default=0)  # parcelado / entrada
    max_parcelas = models.PositiveIntegerField(default=1)
    entrada_percentual = models.DecimalField(max_digits=5, decimal_places=2, default=0)  # entrada + parcelas
    ordem = models.PositiveIntegerField(default=0)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["ordem", "nome"]

    def __str__(self):
        return self.nome


class Conta(models.Model):
    """Onde o dinheiro entra e sai: caixa (dinheiro), banco (Pix, transferência) ou cartão."""

    class Tipo(models.TextChoices):
        DINHEIRO = "dinheiro", "Caixa (dinheiro)"
        BANCO = "banco", "Banco (Pix, transferência)"
        CARTAO = "cartao", "Cartão (crédito, débito)"
        OUTRO = "outro", "Outro"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vidraceiro = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="contas_caixa")
    nome = models.CharField(max_length=60)
    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    saldo_inicial = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    ativo = models.BooleanField(default=True)
    ordem = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["ordem", "nome"]

    def __str__(self):
        return self.nome


# Sugestões criadas na primeira vez que o vidraceiro abre cada cadastro.
CONDICOES_INICIAIS = [
    dict(nome="À vista (Pix ou dinheiro)", tipo="avista", desconto_percentual=5),
    dict(nome="Parcelado", tipo="parcelado", max_parcelas=3),
    dict(nome="Entrada + restante na entrega", tipo="entrada", entrada_percentual=50, max_parcelas=1),
]
CONTAS_INICIAIS = [
    dict(nome="Caixa", tipo="dinheiro"),
    dict(nome="Banco", tipo="banco"),
    dict(nome="Cartão", tipo="cartao"),
]

# Conta sugerida pela forma de pagamento.
TIPO_CONTA_POR_FORMA = {
    "dinheiro": "dinheiro", "pix": "banco", "transferencia": "banco", "boleto": "banco",
    "cartao": "cartao",
}
