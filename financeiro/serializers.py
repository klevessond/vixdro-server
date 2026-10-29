from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from clientes.models import Cliente
from projetos.models import Projeto

from .models import CondicaoPagamento, Conta, Lancamento


class LancamentoSerializer(serializers.ModelSerializer):
    cliente = serializers.PrimaryKeyRelatedField(queryset=Cliente.objects.none(), required=False, allow_null=True)
    projeto = serializers.PrimaryKeyRelatedField(queryset=Projeto.objects.none(), required=False, allow_null=True)
    cliente_nome = serializers.CharField(source="cliente.nome", read_only=True, default=None)
    projeto_nome = serializers.CharField(source="projeto.nome", read_only=True, default=None)
    projeto_numero = serializers.IntegerField(source="projeto.numero", read_only=True, default=None)
    conta = serializers.PrimaryKeyRelatedField(queryset=Conta.objects.none(), required=False, allow_null=True)
    conta_nome = serializers.CharField(source="conta.nome", read_only=True, default=None)
    valor = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    vencido = serializers.SerializerMethodField()

    class Meta:
        model = Lancamento
        fields = ("id", "tipo", "descricao", "categoria", "valor", "vencimento", "pago", "pago_em", "forma",
                  "cliente", "cliente_nome", "projeto", "projeto_nome", "projeto_numero", "conta", "conta_nome",
                  "grupo", "parcela", "total_parcelas", "observacoes", "vencido")
        read_only_fields = ("id", "grupo", "parcela", "total_parcelas")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request is not None:
            self.fields["cliente"].queryset = Cliente.objects.filter(vidraceiro=request.user, ativo=True)
            self.fields["projeto"].queryset = Projeto.objects.filter(vidraceiro=request.user, ativo=True)
            self.fields["conta"].queryset = Conta.objects.filter(vidraceiro=request.user)

    def get_vencido(self, obj):
        return not obj.pago and obj.vencimento < timezone.localdate()

    def validate_descricao(self, valor):
        valor = valor.strip()
        if not valor:
            raise serializers.ValidationError("Descreva o lançamento.")
        return valor

    def validate(self, attrs):
        projeto = attrs.get("projeto", getattr(self.instance, "projeto", None))
        if projeto is not None and attrs.get("cliente", getattr(self.instance, "cliente", None)) is None:
            attrs["cliente"] = projeto.cliente  # o projeto já diz quem é o cliente
        pago = attrs.get("pago", getattr(self.instance, "pago", False))
        if pago and not attrs.get("pago_em", getattr(self.instance, "pago_em", None)):
            attrs["pago_em"] = timezone.localdate()
        if not pago:
            attrs["pago_em"] = None
        return attrs


class ParcelamentoSerializer(serializers.Serializer):
    """Cria várias parcelas de uma vez (a divisão dos centavos fica na última)."""

    tipo = serializers.ChoiceField(choices=Lancamento.Tipo.choices)
    descricao = serializers.CharField(max_length=150)
    categoria = serializers.CharField(max_length=50, required=False, allow_blank=True, default="")
    valor_total = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    parcelas = serializers.IntegerField(min_value=1, max_value=60)
    primeiro_vencimento = serializers.DateField()
    cliente = serializers.PrimaryKeyRelatedField(queryset=Cliente.objects.none(), required=False, allow_null=True)
    projeto = serializers.PrimaryKeyRelatedField(queryset=Projeto.objects.none(), required=False, allow_null=True)
    observacoes = serializers.CharField(required=False, allow_blank=True, default="")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context["request"]
        self.fields["cliente"].queryset = Cliente.objects.filter(vidraceiro=request.user, ativo=True)
        self.fields["projeto"].queryset = Projeto.objects.filter(vidraceiro=request.user, ativo=True)


class CobrancasProjetoSerializer(serializers.Serializer):
    """Sinal + restante parcelado, a partir do total do orçamento."""

    projeto = serializers.PrimaryKeyRelatedField(queryset=Projeto.objects.none())
    # Pela forma de pagamento combinada (recomendado)...
    condicao = serializers.PrimaryKeyRelatedField(queryset=CondicaoPagamento.objects.none(), required=False, allow_null=True)
    parcelas = serializers.IntegerField(min_value=1, max_value=60, required=False)
    # ...ou personalizado (sinal em % + parcelas).
    entrada_percentual = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=100, required=False)
    vencimento_entrada = serializers.DateField()
    parcelas_restantes = serializers.IntegerField(min_value=0, max_value=60, required=False, default=0)
    primeiro_vencimento = serializers.DateField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        usuario = self.context["request"].user
        self.fields["projeto"].queryset = Projeto.objects.filter(vidraceiro=usuario, ativo=True)
        self.fields["condicao"].queryset = CondicaoPagamento.objects.filter(vidraceiro=usuario)

    def validate(self, attrs):
        if attrs.get("condicao"):
            return attrs  # as datas são resolvidas na geração (views.cobrancas_projeto)
        if attrs.get("entrada_percentual") is None:
            raise serializers.ValidationError("Escolha a forma de pagamento ou informe o sinal.")
        resto = attrs["entrada_percentual"] < 100
        if resto and attrs["parcelas_restantes"] < 1:
            raise serializers.ValidationError("Informe em quantas parcelas fica o restante.")
        if resto and not attrs.get("primeiro_vencimento"):
            raise serializers.ValidationError("Informe o vencimento da primeira parcela do restante.")
        return attrs


class CondicaoPagamentoSerializer(serializers.ModelSerializer):
    desconto_percentual = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=100, required=False)
    acrescimo_percentual = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=100, required=False)
    entrada_percentual = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=100, required=False)
    max_parcelas = serializers.IntegerField(min_value=1, max_value=60, required=False)

    class Meta:
        model = CondicaoPagamento
        fields = ("id", "nome", "tipo", "desconto_percentual", "acrescimo_percentual", "max_parcelas",
                  "entrada_percentual", "ordem", "ativo")
        read_only_fields = ("id",)

    def validate_nome(self, valor):
        valor = valor.strip()
        if not valor:
            raise serializers.ValidationError("Dê um nome à forma de pagamento.")
        return valor


class ContaSerializer(serializers.ModelSerializer):
    saldo_inicial = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    saldo = serializers.SerializerMethodField()

    class Meta:
        model = Conta
        fields = ("id", "nome", "tipo", "saldo_inicial", "ativo", "ordem", "saldo")
        read_only_fields = ("id",)

    def get_saldo(self, obj):
        """Saldo inicial + o que entrou - o que saiu (lançamentos pagos nesta conta)."""
        entradas = getattr(obj, "entradas", None) or 0
        saidas = getattr(obj, "saidas", None) or 0
        return str((obj.saldo_inicial + Decimal(entradas) - Decimal(saidas)).quantize(Decimal("0.01")))

    def validate_nome(self, valor):
        valor = valor.strip()
        if not valor:
            raise serializers.ValidationError("Dê um nome à conta.")
        return valor
