from decouple import config

from .base import ErroFornecedor
from .padrao_vixdro import AdaptadorPadraoVixdro

REGISTRO = {
    "padrao_vixdro": AdaptadorPadraoVixdro,
}


def adaptador_para(fornecedor):
    classe = REGISTRO.get(fornecedor.adaptador)
    if classe is None:
        raise ErroFornecedor(f"Adaptador desconhecido: {fornecedor.adaptador}")
    chave = config(fornecedor.variavel_chave, default="")
    if not chave:
        raise ErroFornecedor(
            f"A variável {fornecedor.variavel_chave} não está definida no .env do servidor."
        )
    return classe(fornecedor, chave)
