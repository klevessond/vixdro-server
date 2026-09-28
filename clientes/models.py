import uuid

from django.conf import settings
from django.db import models

from contas.models import UF_CHOICES


class Cliente(models.Model):
    """Cliente do vidraceiro (quem recebe o orçamento).

    O id é gerado pelo APP, no momento do cadastro, mesmo offline. Assim,
    se a fila de sincronização reenviar o mesmo cadastro, o servidor
    reconhece o id e não cria um cliente duplicado.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    vidraceiro = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="clientes"
    )
    nome = models.CharField(max_length=150)
    empresa = models.CharField(max_length=150, blank=True)
    email = models.EmailField(blank=True)
    celular = models.CharField(max_length=20, blank=True)
    cpf_cnpj = models.CharField("CPF/CNPJ", max_length=14, blank=True, help_text="Somente dígitos")

    cep = models.CharField(max_length=8, blank=True)
    rua = models.CharField(max_length=200, blank=True)
    numero = models.CharField("número", max_length=20, blank=True)
    complemento = models.CharField(max_length=100, blank=True)
    bairro = models.CharField(max_length=100, blank=True)
    cidade = models.CharField(max_length=100, blank=True)
    estado = models.CharField(max_length=2, choices=UF_CHOICES, blank=True)

    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return self.nome
