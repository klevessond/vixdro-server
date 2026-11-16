"""Tratamento de erros da API.

O Django lança ValidationError quando um filtro recebe um valor impossível
(ex: ?projeto=abc num campo UUID, ou uma data mal formada gravada num
DateField). Sem tratamento isso vira erro 500. Aqui vira 400, com a mensagem.
"""
from django.core.exceptions import ValidationError as ErroDeValidacaoDjango
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler


def tratar_excecao(exc, context):
    resposta = exception_handler(exc, context)
    if resposta is None and isinstance(exc, ErroDeValidacaoDjango):
        return Response(
            {"detail": "Valor inválido: " + " ".join(str(m) for m in exc.messages)},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return resposta
