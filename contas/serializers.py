import re

from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import UF_CHOICES, Vidraceiro

CAMPOS_PUBLICOS = (
    "id", "email", "nome", "empresa", "celular", "cpf_cnpj",
    "cep", "rua", "numero", "complemento", "bairro", "cidade", "estado",
)
UFS = {uf for uf, _ in UF_CHOICES}


class VidraceiroSerializer(serializers.ModelSerializer):
    """Dados do vidraceiro devolvidos ao app (nunca inclui a senha)."""

    class Meta:
        model = Vidraceiro
        fields = CAMPOS_PUBLICOS
        read_only_fields = CAMPOS_PUBLICOS


class CadastroSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(required=False)
    email = serializers.EmailField()
    estado = serializers.CharField(max_length=2)
    # Aceitam o valor com máscara (pontos, traço, barra); a limpeza
    # para só dígitos acontece nos validate_* abaixo.
    cpf_cnpj = serializers.CharField(max_length=20)
    cep = serializers.CharField(max_length=10, required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    class Meta:
        model = Vidraceiro
        fields = CAMPOS_PUBLICOS + ("password",)

    def validate_email(self, valor):
        valor = valor.strip().lower()
        if Vidraceiro.objects.filter(email__iexact=valor).exists():
            raise serializers.ValidationError("Já existe uma conta com este email.")
        return valor

    def validate_cpf_cnpj(self, valor):
        digitos = re.sub(r"\D", "", valor)
        if len(digitos) not in (11, 14):
            raise serializers.ValidationError("Informe um CPF (11 dígitos) ou CNPJ (14 dígitos).")
        return digitos

    def validate_cep(self, valor):
        digitos = re.sub(r"\D", "", valor)
        if digitos and len(digitos) != 8:
            raise serializers.ValidationError("CEP inválido.")
        return digitos

    def validate_celular(self, valor):
        return re.sub(r"\D", "", valor)

    def validate_estado(self, valor):
        valor = valor.strip().upper()
        if valor not in UFS:
            raise serializers.ValidationError("UF inválida.")
        return valor

    def validate(self, attrs):
        dados_sem_senha = {k: v for k, v in attrs.items() if k != "password"}
        try:
            password_validation.validate_password(attrs["password"], Vidraceiro(**dados_sem_senha))
        except DjangoValidationError as e:
            raise serializers.ValidationError({"password": list(e.messages)})
        return attrs

    def create(self, validated_data):
        return Vidraceiro.objects.create_user(**validated_data)


class LoginSerializer(TokenObtainPairSerializer):
    """Login por email + senha. Devolve os tokens e os dados do vidraceiro."""

    default_error_messages = {
        "no_active_account": "Email ou senha incorretos.",
    }

    def validate(self, attrs):
        attrs[self.username_field] = attrs.get(self.username_field, "").strip().lower()
        data = super().validate(attrs)
        data["vidraceiro"] = VidraceiroSerializer(self.user).data
        return data
