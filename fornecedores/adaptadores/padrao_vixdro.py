"""Adaptador para fornecedores que instalaram o pacote integracao_vixdro."""

import logging
from decimal import Decimal, InvalidOperation
from urllib.parse import urljoin

import requests
from django.utils.dateparse import parse_datetime

from ..models import VALORES_TIPO, inferir_tipo
from .base import AdaptadorBase, ErroFornecedor, ItemCatalogo, PaginaCatalogo

log = logging.getLogger(__name__)

TAMANHO_PAGINA = 500
TIMEOUT = (5, 60)  # segundos: (conectar, ler)


def _primeira_mensagem(dados):
    if isinstance(dados, str):
        return dados
    if isinstance(dados, list):
        for v in dados:
            m = _primeira_mensagem(v)
            if m:
                return m
    if isinstance(dados, dict):
        for v in dados.values():
            m = _primeira_mensagem(v)
            if m:
                return m
    return None


def _decimal(valor):
    if valor is None or valor == "":
        return None
    try:
        return Decimal(str(valor))
    except InvalidOperation:
        raise ValueError(f"número inválido: {valor!r}")


def converter_item(bruto: dict) -> ItemCatalogo:
    codigo = str(bruto.get("codigo") or "").strip()
    if not codigo:
        raise ValueError("item sem código")
    preco = _decimal(bruto.get("preco"))
    if preco is None or preco < 0:
        raise ValueError(f"preço inválido: {bruto.get('preco')!r}")

    comprimento = bruto.get("comprimento_mm")
    comprimento_mm = int(comprimento) if comprimento not in (None, "", 0) else None
    unidade = str(bruto.get("unidade") or "").strip().upper()[:10]
    # O tipo informado pelo fornecedor vale; vazio ou desconhecido, deduz pela forma de venda.
    tipo = str(bruto.get("tipo") or "").strip().lower()
    if tipo not in VALORES_TIPO:
        tipo = inferir_tipo(unidade, comprimento_mm)
    return ItemCatalogo(
        codigo=codigo,
        descricao=str(bruto.get("descricao") or "").strip()[:255],
        unidade=unidade,
        comprimento_mm=comprimento_mm,
        preco=preco.quantize(Decimal("0.01")),
        estoque=_decimal(bruto.get("estoque")),
        ativo=bool(bruto.get("ativo", True)),
        atualizado_em=parse_datetime(bruto["atualizado_em"]) if bruto.get("atualizado_em") else None,
        tipo=tipo,
    )


class AdaptadorPadraoVixdro(AdaptadorBase):
    def __init__(self, fornecedor, chave):
        super().__init__(fornecedor, chave)
        self._marca_temporal = None
        self.sessao = requests.Session()
        self.sessao.headers["Authorization"] = f"Api-Key {chave}"

    @property
    def marca_temporal(self):
        return self._marca_temporal

    def _requisicao(self, metodo, caminho, params=None, json=None):
        url = urljoin(self.fornecedor.url_base, caminho)
        try:
            resposta = self.sessao.request(metodo, url, params=params, json=json, timeout=TIMEOUT)
        except requests.RequestException as e:
            raise ErroFornecedor(f"Sem conexão com o fornecedor ({url}): {e}") from e
        if resposta.status_code == 401:
            raise ErroFornecedor("O fornecedor recusou a chave de acesso (401). Confira a chave no .env.")
        try:
            dados = resposta.json()
        except ValueError:
            dados = None
        if resposta.status_code == 400 and isinstance(dados, dict):
            # Recusa com motivo (ex: código de item que não existe mais).
            raise ErroFornecedor(f"O fornecedor recusou: {_primeira_mensagem(dados)}")
        if resposta.status_code not in (200, 201):
            raise ErroFornecedor(f"Resposta inesperada {resposta.status_code}: {resposta.text[:300]}")
        if dados is None:
            raise ErroFornecedor("O fornecedor respondeu algo que não é JSON.")
        return dados

    def _get(self, params):
        return self._requisicao("GET", "itens/", params=params)

    def enviar_pedido(self, pedido):
        dados = self._requisicao("POST", "pedidos/", json=pedido)
        return {"numero": str(dados.get("numero", "")), "status": dados.get("status", "recebido")}

    def consultar_pedido(self, id_vixdro):
        dados = self._requisicao("GET", f"pedidos/{id_vixdro}/")
        return {"numero": str(dados.get("numero", "")), "status": dados.get("status", "recebido")}

    def listar_itens(self, atualizado_desde=None):
        params = {"tamanho": TAMANHO_PAGINA, "page": 1}
        if atualizado_desde:
            params["atualizado_desde"] = atualizado_desde.isoformat()

        while True:
            dados = self._get(params)
            if params["page"] == 1:
                # Horário do fornecedor ANTES de lermos os dados: o que mudar
                # durante a leitura entra na próxima sincronização.
                self._marca_temporal = parse_datetime(dados.get("gerado_em") or "")

            itens, ignorados = [], 0
            for bruto in dados.get("itens", []):
                try:
                    itens.append(converter_item(bruto))
                except (ValueError, TypeError, KeyError) as e:
                    ignorados += 1
                    log.warning("Item ignorado de %s: %s (%s)", self.fornecedor, e, bruto)
            yield PaginaCatalogo(itens=itens, ignorados=ignorados)

            # Avança pelo número da página em vez de seguir o link "proxima",
            # que pode trazer um endereço interno do fornecedor.
            if not dados.get("proxima"):
                break
            params["page"] += 1
