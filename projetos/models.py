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

    # Quanto de cada item sai do estoque do vidraceiro: {"<id do item>": "1"}.
    # Não muda o preço para o cliente (o material é usado na obra), só o que
    # é pedido ao fornecedor.
    estoque_usado = models.JSONField(default=dict, blank=True)

    # Forma de pagamento combinada com o cliente (usada ao gerar as contas a receber).
    condicao_pagamento = models.ForeignKey(
        "financeiro.CondicaoPagamento", on_delete=models.SET_NULL, null=True, blank=True, related_name="projetos",
    )

    # Lembrete de orçamento parado (enviado ao cliente e sem resposta).
    lembrete_adiado_ate = models.DateTimeField(
        null=True, blank=True, help_text="Até quando o lembrete fica escondido (\"lembrar depois\")",
    )
    ultimo_contato_em = models.DateTimeField(
        null=True, blank=True, help_text="Última vez que o vidraceiro cobrou o cliente pelo app",
    )

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
    # Acompanhamento da obra: a peça foi produzida/instalada.
    concluida = models.BooleanField(default=False)
    concluida_em = models.DateTimeField(null=True, blank=True)

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


def _caminho_foto(registro, nome):
    # Nome aleatório: a foto não é encontrada por quem não tem o endereço exato.
    return f"medicao/{registro.projeto_id}/{uuid.uuid4().hex}.jpg"


def _caminho_miniatura(registro, nome):
    return f"medicao/{registro.projeto_id}/mini/{uuid.uuid4().hex}.jpg"


class RegistroMedicao(models.Model):
    """Diário da medição: uma foto, uma anotação, ou os dois.

    A peça a que se refere é guardada pelo NOME (ex: "Janela da sala"), e não
    por vínculo: as peças são regravadas a cada salvamento do projeto, e um
    vínculo direto faria as fotos se perderem."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    projeto = models.ForeignKey(Projeto, on_delete=models.CASCADE, related_name="registros")
    referencia = models.CharField(max_length=150, blank=True, help_text="Peça a que se refere (opcional)")
    texto = models.TextField(blank=True)
    foto = models.ImageField(upload_to=_caminho_foto, blank=True)
    miniatura = models.ImageField(upload_to=_caminho_miniatura, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]
