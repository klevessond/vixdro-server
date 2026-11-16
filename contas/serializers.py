import re

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as ErroDeValidacaoDjango
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

    # Conta da equipe do Orçaminio: pode criar e editar modelos prontos pelo app.
    equipe = serializers.BooleanField(source="is_staff", read_only=True)

    class Meta:
        model = Vidraceiro
        fields = CAMPOS_PUBLICOS + ("equipe",)
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

    def validate_id(self, valor):
        # O id vem do app; um repetido daria erro 500 ao gravar.
        if Vidraceiro.objects.filter(pk=valor).exists():
            raise serializers.ValidationError("Este identificador já está em uso.")
        return valor

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
        # A política de senha é a do settings (AUTH_PASSWORD_VALIDATORS): mínimo de
        # 8 caracteres, não pode ser só números, nem uma senha muito comum, nem
        # parecida com o e-mail ou o nome. Antes ela só valia no admin.
        candidato = Vidraceiro(email=attrs.get("email", ""), nome=attrs.get("nome", ""))
        try:
            validate_password(attrs["password"], user=candidato)
        except ErroDeValidacaoDjango as e:
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


class PerfilSerializer(serializers.ModelSerializer):
    """Dados do vidraceiro editáveis na tela "Minha empresa".
    O e-mail não muda aqui: ele é o login da conta."""

    cpf_cnpj = serializers.CharField(max_length=20)
    cep = serializers.CharField(max_length=10, required=False, allow_blank=True)
    estado = serializers.CharField(max_length=2)

    class Meta:
        model = Vidraceiro
        fields = ("nome", "empresa", "celular", "cpf_cnpj", "cep", "rua", "numero",
                  "complemento", "bairro", "cidade", "estado")

    def validate_nome(self, valor):
        valor = valor.strip()
        if not valor:
            raise serializers.ValidationError("Informe o nome.")
        return valor

    # Mesmas regras do cadastro da conta.
    validate_cpf_cnpj = CadastroSerializer.validate_cpf_cnpj
    validate_cep = CadastroSerializer.validate_cep
    validate_celular = CadastroSerializer.validate_celular
    validate_estado = CadastroSerializer.validate_estado


class PrecosPadraoSerializer(serializers.ModelSerializer):
    """Padrões de preço do vidraceiro (tela "Preços e margem" do app)."""

    margem_padrao = serializers.DecimalField(max_digits=6, decimal_places=2, min_value=0, max_value=1000)
    mao_de_obra_m2_padrao = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    mao_de_obra_minima_padrao = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    perda_padrao = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=50)
    validade_padrao = serializers.IntegerField(min_value=1, max_value=365)
    dias_lembrete = serializers.IntegerField(min_value=1, max_value=60, required=False)
    margem_modo = serializers.ChoiceField(choices=["fixa", "variavel"], required=False)

    class Meta:
        model = Vidraceiro
        fields = ("margem_padrao", "mao_de_obra_m2_padrao", "mao_de_obra_minima_padrao",
                  "perda_padrao", "validade_padrao", "dias_lembrete", "margem_modo")
