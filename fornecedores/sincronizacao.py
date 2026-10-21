"""Copia o catálogo do fornecedor para o banco do vixdro.

- Incremental: pede ao fornecedor só o que mudou desde a última vez.
- Completa: pede tudo e desativa os itens que não vieram (sumiram do
  catálogo do fornecedor). Corrige qualquer diferença acumulada.

Só grava o que mudou de fato, para que o app baixe apenas as alterações.
"""

import logging
from contextlib import contextmanager

from django.db import connection, transaction
from django.utils import timezone

from .adaptadores import ErroFornecedor, adaptador_para
from .models import ItemFornecedor, Sincronizacao

log = logging.getLogger(__name__)

CAMPOS_COMPARADOS = ("descricao", "unidade", "comprimento_mm", "preco", "estoque", "ativo", "tipo")


class SincronizacaoEmAndamento(Exception):
    pass


@contextmanager
def _trava(fornecedor):
    """Impede duas sincronizações do mesmo fornecedor ao mesmo tempo
    (ex: a incremental de hora em hora rodando junto com a completa)."""
    if connection.vendor != "postgresql":
        yield
        return
    chave = 7_000_000 + fornecedor.pk
    with connection.cursor() as c:
        c.execute("SELECT pg_try_advisory_lock(%s)", [chave])
        if not c.fetchone()[0]:
            raise SincronizacaoEmAndamento(f"Já existe uma sincronização de {fornecedor} em andamento.")
    try:
        yield
    finally:
        with connection.cursor() as c:
            c.execute("SELECT pg_advisory_unlock(%s)", [chave])


def _aplicar_pagina(fornecedor, itens, agora, registro):
    codigos = [i.codigo for i in itens]
    existentes = {
        obj.codigo: obj
        for obj in ItemFornecedor.objects.filter(fornecedor=fornecedor, codigo__in=codigos)
    }

    novos, alterados, so_vistos = [], [], []
    vistos_na_pagina = set()

    for item in itens:
        if item.codigo in vistos_na_pagina:
            # Código repetido na mesma resposta: vale o último.
            log.warning("Código repetido vindo de %s: %s", fornecedor, item.codigo)
        vistos_na_pagina.add(item.codigo)

        dados = {campo: getattr(item, campo) for campo in CAMPOS_COMPARADOS}
        obj = existentes.get(item.codigo)

        if obj is None:
            obj = ItemFornecedor(
                fornecedor=fornecedor, codigo=item.codigo,
                atualizado_no_fornecedor=item.atualizado_em,
                atualizado_em=agora, visto_em=agora, **dados,
            )
            existentes[item.codigo] = obj
            novos.append(obj)
            continue

        mudou = any(getattr(obj, c) != v for c, v in dados.items())
        obj.visto_em = agora
        obj.atualizado_no_fornecedor = item.atualizado_em
        if mudou:
            for c, v in dados.items():
                setattr(obj, c, v)
            obj.atualizado_em = agora
            alterados.append(obj)
        else:
            so_vistos.append(obj)

    # Um item novo que se repete na página fica só uma vez na lista.
    novos = list({o.codigo: o for o in novos}.values())
    alterados = [o for o in {o.codigo: o for o in alterados}.values() if o.pk]

    with transaction.atomic():
        ItemFornecedor.objects.bulk_create(novos, batch_size=500)
        ItemFornecedor.objects.bulk_update(
            alterados,
            [*CAMPOS_COMPARADOS, "atualizado_no_fornecedor", "atualizado_em", "visto_em"],
            batch_size=500,
        )
        ItemFornecedor.objects.filter(pk__in=[o.pk for o in so_vistos if o.pk]).update(visto_em=agora)

    registro.novos += len(novos)
    registro.alterados += len(alterados)


def sincronizar(fornecedor, completa=False):
    """Executa uma sincronização e devolve o registro (Sincronizacao)."""
    # Sem histórico, a primeira vez é sempre completa.
    completa = completa or fornecedor.cursor_sincronizacao is None
    registro = Sincronizacao.objects.create(
        fornecedor=fornecedor,
        tipo=Sincronizacao.Tipo.COMPLETA if completa else Sincronizacao.Tipo.INCREMENTAL,
    )
    agora = timezone.now()

    try:
        with _trava(fornecedor):
            adaptador = adaptador_para(fornecedor)
            desde = None if completa else fornecedor.cursor_sincronizacao

            for pagina in adaptador.listar_itens(atualizado_desde=desde):
                registro.recebidos += len(pagina.itens)
                registro.ignorados += pagina.ignorados
                _aplicar_pagina(fornecedor, pagina.itens, agora, registro)

            if completa:
                # O que não veio na carga completa saiu do catálogo.
                registro.desativados = ItemFornecedor.objects.filter(
                    fornecedor=fornecedor, ativo=True, visto_em__lt=agora
                ).update(ativo=False, atualizado_em=agora)
                fornecedor.ultima_carga_completa = agora

            # O cursor só avança se TUDO deu certo. Se falhar no meio, a
            # próxima execução pede os mesmos dados de novo (sem problema,
            # porque aplicar a mesma alteração duas vezes não muda nada).
            fornecedor.cursor_sincronizacao = adaptador.marca_temporal or agora
            fornecedor.save(update_fields=["cursor_sincronizacao", "ultima_carga_completa"])

        registro.status = Sincronizacao.Status.SUCESSO
    except (ErroFornecedor, SincronizacaoEmAndamento) as e:
        registro.status = Sincronizacao.Status.ERRO
        registro.erro = str(e)
    except Exception as e:  # erro inesperado: registra e deixa aparecer no log
        registro.status = Sincronizacao.Status.ERRO
        registro.erro = f"{type(e).__name__}: {e}"
        log.exception("Falha inesperada sincronizando %s", fornecedor)
    finally:
        registro.fim = timezone.now()
        registro.save()

    return registro
