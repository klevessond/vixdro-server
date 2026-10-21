from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from clientes.models import Cliente
from projetos.models import Projeto

from .models import Lancamento


class LancamentoSerializer(serializers.ModelSerializer):
    cliente = serializers.PrimaryKeyRelatedField(queryset=Cliente.objects.none(), required=False, allow_null=True)
    projeto = serializers.PrimaryKeyRelatedField(queryset=Projeto.objects.none(), required=False, allow_null=True)
    cliente_nome = serializers.CharField(source="cliente.nome", read_only=True, default=None)
    projeto_nome = serializers.CharField(source="projeto.nome", read_only=True, default=None)
    projeto_numero = serializers.IntegerField(source="projeto.numero", read_only=True, default=None)
    valor = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    vencido = serializers.SerializerMethodField()

    class Meta:
        model = Lancamento
        fields = ("id", "tipo", "descricao", "categoria", "valor", "vencimento", "pago", "pago_em", "forma",
                  "cliente", "cliente_nome", "projeto", "projeto_nome", "projeto_numero",
                  "grupo", "parcela", "total_parcelas", "observacoes", "vencido")
        read_only_fields = ("id", "grupo", "parcela", "total_parcelas")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request is not None:
            self.fields["cliente"].queryset = Cliente.objects.filter(vidraceiro=request.user, ativo=True)
            self.fields["projeto"].queryset = Projeto.objects.filter(vidraceiro=request.user, ativo=True)

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
    entrada_percentual = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=100)
    vencimento_entrada = serializers.DateField()
    parcelas_restantes = serializers.IntegerField(min_value=0, max_value=60)
    primeiro_vencimento = serializers.DateField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["projeto"].queryset = Projeto.objects.filter(vidraceiro=self.context["request"].user, ativo=True)

    def validate(self, attrs):
        resto = attrs["entrada_percentual"] < 100
        if resto and attrs["parcelas_restantes"] < 1:
            raise serializers.ValidationError("Informe em quantas parcelas fica o restante.")
        if resto and not attrs.get("primeiro_vencimento"):
            raise serializers.ValidationError("Informe o vencimento da primeira parcela do restante.")
        return attrs
