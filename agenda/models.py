import uuid

from django.conf import settings
from django.db import models

from clientes.models import Cliente
from projetos.models import Projeto


class Compromisso(models.Model):
    """Uma medição, instalação ou visita na agenda do vidraceiro."""

    class Tipo(models.TextChoices):
        MEDICAO = "medicao", "Medição"
        INSTALACAO = "instalacao", "Instalação"
        VISITA = "visita", "Visita"
        OUTRO = "outro", "Outro"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vidraceiro = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="compromissos")
    tipo = models.CharField(max_length=15, choices=Tipo.choices, default=Tipo.MEDICAO)
    cliente = models.ForeignKey(Cliente, on_delete=models.SET_NULL, null=True, blank=True, related_name="compromissos")
    projeto = models.ForeignKey(Projeto, on_delete=models.SET_NULL, null=True, blank=True, related_name="compromissos")
    inicio = models.DateTimeField(db_index=True)
    duracao_min = models.PositiveIntegerField(default=60)
    # Pode ser diferente do endereço do cliente: a obra nem sempre é onde ele mora.
    endereco = models.CharField(max_length=300, blank=True)
    observacoes = models.TextField(blank=True)
    concluido = models.BooleanField(default=False)
    concluido_em = models.DateTimeField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["inicio"]

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.inicio:%d/%m %H:%M}"
