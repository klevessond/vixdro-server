from decimal import Decimal
import uuid

from django.conf import settings
from django.db import models

from fornecedores.models import ItemFornecedor


class Produto(models.Model):
    """Modelo que o vidraceiro monta uma vez e reutiliza nos projetos.
    Ex: "Janela veneziana 2 folhas". Guarda regras de consumo, não quantidades."""

    class Categoria(models.TextChoices):
        JANELA = "janela", "Janela"
        PORTA = "porta", "Porta"
        PORTAO = "portao", "Portão"
        BOX = "box", "Box"
        OUTRO = "outro", "Outro"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Vazio = MODELO PRONTO: criado pela equipe no admin e visível para todos
    # os vidraceiros, que não podem alterá-lo (podem criar uma cópia própria).
    vidraceiro = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="produtos",
        null=True, blank=True,
        help_text="Deixe vazio para um modelo pronto, disponível para todos os vidraceiros.",
    )
    nome = models.CharField(max_length=150)
    categoria = models.CharField(max_length=20, choices=Categoria.choices, default=Categoria.OUTRO)
    descricao = models.TextField(blank=True)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return self.nome

    @property
    def padrao(self) -> bool:
        """Modelo pronto (da equipe), e não de um vidraceiro."""
        return self.vidraceiro_id is None


class Componente(models.Model):
    """Um item do catálogo dentro do produto, com a regra de consumo:

        consumo = coef_largura × L + coef_altura × A + coef_area × (L × A) + ajuste

    L e A em metros. O consumo sai na unidade de consumo do item:
    metros (perfis e itens vendidos por metro), m² (vidros) ou unidades.
    """

    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, related_name="componentes")
    # PROTECT: um item usado em produto nunca some (o catálogo só desativa).
    item = models.ForeignKey(ItemFornecedor, on_delete=models.PROTECT, related_name="+")
    coef_largura = models.DecimalField(max_digits=8, decimal_places=4, default=0)
    coef_altura = models.DecimalField(max_digits=8, decimal_places=4, default=0)
    coef_area = models.DecimalField(max_digits=8, decimal_places=4, default=0)
    ajuste = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    observacao = models.CharField(max_length=100, blank=True, help_text="Ex: folha móvel, lado esquerdo")
    # Só para itens vendidos em barra: cobrar a barra inteira ou só os metros usados.
    cobranca = models.CharField(
        max_length=10, choices=[("inteira", "Barra inteira"), ("metro", "Por metro usado")], default="inteira",
    )
    ordem = models.PositiveIntegerField(default=0)

    def clean(self):
        from django.core.exceptions import ValidationError

        # Sem nenhuma regra, o item entraria com consumo zero e custo zerado.
        # Vale então quantidade fixa de 1 por peça (1 unidade, 1 m ou 1 m², conforme o item).
        # Só quando NADA foi preenchido: o ajuste também soma às regras pela medida.
        if self.item_id and not any([self.coef_largura, self.coef_altura, self.coef_area, self.ajuste]):
            self.ajuste = Decimal(1)

        # Um modelo pronto aparece para todos: não pode usar o item próprio de um vidraceiro.
        produto = getattr(self, "produto", None)
        if produto is not None and produto.vidraceiro_id is None and self.item_id:
            if self.item.fornecedor.vidraceiro_id is not None:
                raise ValidationError({
                    "item": "Modelos prontos só podem usar itens do catálogo do fornecedor, "
                            "e não itens próprios de um vidraceiro.",
                })

    class Meta:
        ordering = ["ordem", "id"]
