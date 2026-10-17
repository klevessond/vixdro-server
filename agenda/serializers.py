from rest_framework import serializers

from clientes.models import Cliente
from projetos.models import Projeto

from .models import Compromisso


class CompromissoSerializer(serializers.ModelSerializer):
    cliente = serializers.PrimaryKeyRelatedField(
        queryset=Cliente.objects.none(), required=False, allow_null=True,
        error_messages={"does_not_exist": "Cliente não encontrado. Se ele foi cadastrado agora, aguarde o envio."},
    )
    projeto = serializers.PrimaryKeyRelatedField(
        queryset=Projeto.objects.none(), required=False, allow_null=True,
        error_messages={"does_not_exist": "Projeto não encontrado."},
    )
    cliente_nome = serializers.CharField(source="cliente.nome", read_only=True, default=None)
    cliente_celular = serializers.CharField(source="cliente.celular", read_only=True, default=None)
    projeto_nome = serializers.CharField(source="projeto.nome", read_only=True, default=None)
    projeto_numero = serializers.IntegerField(source="projeto.numero", read_only=True, default=None)
    duracao_min = serializers.IntegerField(min_value=5, max_value=24 * 60, required=False)

    class Meta:
        model = Compromisso
        fields = ("id", "tipo", "cliente", "cliente_nome", "cliente_celular", "projeto", "projeto_nome",
                  "projeto_numero", "inicio", "duracao_min", "endereco", "observacoes", "concluido", "concluido_em")
        read_only_fields = ("id", "concluido", "concluido_em")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request is not None:
            # Só clientes e projetos do próprio vidraceiro.
            self.fields["cliente"].queryset = Cliente.objects.filter(vidraceiro=request.user, ativo=True)
            self.fields["projeto"].queryset = Projeto.objects.filter(vidraceiro=request.user, ativo=True)

    def validate(self, attrs):
        cliente = attrs.get("cliente", getattr(self.instance, "cliente", None))
        projeto = attrs.get("projeto", getattr(self.instance, "projeto", None))
        if projeto is not None:
            if cliente is None:
                attrs["cliente"] = projeto.cliente  # o projeto já diz quem é o cliente
            elif projeto.cliente_id != cliente.pk:
                raise serializers.ValidationError({"projeto": "Este projeto é de outro cliente."})
        return attrs
