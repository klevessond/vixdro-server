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
