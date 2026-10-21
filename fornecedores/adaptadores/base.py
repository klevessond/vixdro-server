"""Interface comum a todos os adaptadores de fornecedor.

Cada fornecedor fala a sua própria "língua". O adaptador traduz para o
formato único que o vixdro entende (ItemCatalogo). O resto do sistema
nunca conversa direto com a API de um fornecedor.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Iterator, Optional


class ErroFornecedor(Exception):
    """Falha ao falar com o fornecedor (fora do ar, chave inválida, resposta estranha)."""


@dataclass
class ItemCatalogo:
    codigo: str
    descricao: str
    unidade: str
    comprimento_mm: Optional[int]
    preco: Decimal
    estoque: Optional[Decimal]
    ativo: bool
    atualizado_em: Optional[datetime]
    tipo: str = "acessorio"  # perfil | acessorio | vidro | vedacao | outro


@dataclass
class PaginaCatalogo:
    itens: list  # list[ItemCatalogo]
    ignorados: int  # itens com dados inválidos, descartados


class AdaptadorBase:
    def __init__(self, fornecedor, chave: str):
        self.fornecedor = fornecedor
        self.chave = chave

    def listar_itens(self, atualizado_desde: Optional[datetime] = None) -> Iterator[PaginaCatalogo]:
        """Devolve o catálogo página por página."""
        raise NotImplementedError

    @property
    def marca_temporal(self) -> Optional[datetime]:
        """Horário do fornecedor a usar como atualizado_desde na próxima vez."""
        raise NotImplementedError

    def enviar_pedido(self, pedido: dict) -> dict:
        """Envia um pedido. Devolve {"numero": str, "status": str}.
        Deve ser idempotente pelo pedido["id_vixdro"]: reenviar não duplica."""
        raise NotImplementedError

    def consultar_pedido(self, id_vixdro: str) -> dict:
        """Situação atual de um pedido. Devolve {"numero": str, "status": str}."""
        raise NotImplementedError
