import re

from rest_framework import serializers

from contas.models import UF_CHOICES

from .models import Cliente

UFS = {uf for uf, _ in UF_CHOICES}


def _digitos(valor):
    return re.sub(r"\D", "", valor or "")


class ClienteSerializer(serializers.ModelSerializer):
    # O app manda o id que ele mesmo gerou (UUID).
    id = serializers.UUIDField(required=False)
    # Aceitam o valor com máscara; a limpeza acontece nos validate_*.
    cpf_cnpj = serializers.CharField(max_length=20, required=False, allow_blank=True)
    cep = serializers.CharField(max_length=10, required=False, allow_blank=True)
    celular = serializers.CharField(max_length=20, required=False, allow_blank=True)
    estado = serializers.CharField(max_length=2, required=False, allow_blank=True)

    class Meta:
        model = Cliente
        fields = (
            "id", "nome", "empresa", "email", "celular", "cpf_cnpj",
            "cep", "rua", "numero", "complemento", "bairro", "cidade", "estado",
            "ativo", "criado_em", "atualizado_em",
        )
        read_only_fields = ("ativo", "criado_em", "atualizado_em")

    def validate(self, attrs):
        # O id só é definido na criação; numa edição ele nunca muda.
        if self.instance is not None:
            attrs.pop("id", None)
        return attrs

    def validate_nome(self, valor):
        valor = valor.strip()
        if not valor:
            raise serializers.ValidationError("Informe o nome do cliente.")
        return valor

    def validate_email(self, valor):
        return valor.strip().lower()

    def validate_cpf_cnpj(self, valor):
        digitos = _digitos(valor)
        if digitos and len(digitos) not in (11, 14):
            raise serializers.ValidationError("Informe um CPF (11 dígitos) ou CNPJ (14 dígitos).")
        return digitos

    def validate_cep(self, valor):
        digitos = _digitos(valor)
        if digitos and len(digitos) != 8:
            raise serializers.ValidationError("CEP inválido.")
        return digitos

    def validate_celular(self, valor):
        return _digitos(valor)

    def validate_estado(self, valor):
        valor = (valor or "").strip().upper()
        if valor and valor not in UFS:
            raise serializers.ValidationError("UF inválida.")
        return valor
