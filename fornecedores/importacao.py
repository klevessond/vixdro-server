"""Importação do catálogo de um fornecedor sem integração (adaptador "manual").

Aceita dois formatos:

1. O PDF "Lista de Preço Varejo" do sistema CISS (o mesmo das tabelas ALUMIFONT,
   ALUVID, J ANSELMO e acessórios). Dele são lidas as colunas
   Código, Descrição do Produto, Preço Varejo, Embalagem Venda e Fabricante.
   O grupo do relatório (ex: "6 ALUMINIO") ajuda a separar perfil de acessório.
   O saldo de estoque do fornecedor é ignorado.

2. Planilha CSV com cabeçalho (maiúsculas e acentos não importam):
       codigo; nome; valor; fabricante
   e, se quiser, unidade; comprimento_mm; tipo.
   Também valem os nomes antigos: descricao no lugar de nome, preco no lugar de valor.
   Separador ; ou , (o Excel em português salva com ;).

Regras ao gravar:
- O item é encontrado pelo código: os existentes são atualizados (imagens ficam).
- Perfil (grupo ALUMINIO vendido em barra) nasce com 6000 mm. Comprimento e tipo
  deduzidos só valem para itens novos: se a equipe corrigir no admin, a próxima
  importação não desfaz. Na planilha, as colunas comprimento_mm e tipo sempre valem.
"""

import csv
import io
import re
import unicodedata
from decimal import Decimal, InvalidOperation

from django.utils import timezone

from .models import VALORES_TIPO, ItemFornecedor, inferir_tipo

COMPRIMENTO_BARRA_MM = 6000

# Nomes aceitos para cada coluna da planilha (já sem acento, minúsculos, _ no lugar de espaço).
APELIDOS = {
    "codigo": {"codigo", "cod", "codigo_do_produto", "referencia", "ref"},
    "descricao": {"nome", "descricao", "descricao_do_produto", "produto"},
    "preco": {"valor", "preco", "preco_varejo", "valor_unitario"},
    "fabricante": {"fabricante", "marca", "fabricante_marca"},
    "unidade": {"unidade", "un", "embalagem", "embalagem_venda"},
    "comprimento_mm": {"comprimento_mm", "comprimento"},
    "tipo": {"tipo"},
}

PRECO_RE = r"(?:\d{1,3}(?:\.\d{3})*)?,\d{2}"
VEDACAO = ("GUARNICAO", "BORRACHA", "ESCOVA", "VEDACAO", "GAXETA", "FELTRO")


def _chave(texto):
    t = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode().strip().lower()
    return re.sub(r"[^a-z0-9]+", "_", t).strip("_")


def _preco(texto):
    t = str(texto or "").strip().replace("R$", "").replace(" ", "")
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    return Decimal(t)


# ---------------------------------------------------------------- leitura do PDF

def _trechos(pagina):
    """Junta as letras da página em trechos de texto, na ordem em que o PDF os escreve.

    A ordem de escrita (e não a posição) é o que separa a descrição do preço quando
    uma descrição comprida invade a coluna do preço."""
    trechos, atual = [], None
    for c in pagina.chars:
        # O preço fica uns 0,7 pt mais alto que a descrição: a altura separa os dois
        # mesmo quando uma descrição comprida encosta no preço.
        if atual and abs(c["top"] - atual["top"]) < 0.3 and -3 < c["x0"] - atual["x1"] < 4:
            atual["texto"] += c["text"]
            atual["x1"] = c["x1"]
        else:
            atual = {"texto": c["text"], "x0": c["x0"], "x1": c["x1"], "top": c["top"]}
            trechos.append(atual)
    for t in trechos:
        t["texto"] = re.sub(r"\s+", " ", t["texto"]).strip()
    return [t for t in trechos if t["texto"]]


def _colunas(pagina):
    """Posição das colunas, pelo cabeçalho da página (Código / Descrição / Venda / Fabricante)."""
    palavras = {p["text"]: p for p in pagina.extract_words()}
    if not {"Código", "Fabricante", "Venda"} <= set(palavras):
        return None
    desc = palavras.get("Descrição", {"x0": palavras["Código"]["x1"] + 5})
    return {
        "descricao": desc["x0"] - 3,
        "unidade": palavras["Venda"]["x0"] - 6,
        "fabricante": palavras["Fabricante"]["x0"] - 4,
        "fim_cabecalho": palavras["Fabricante"]["bottom"],
    }


def ler_pdf(conteudo: bytes):
    """Devolve (linhas, erros). Cada linha é um dict com codigo, descricao, preco, unidade,
    fabricante e grupo."""
    import pdfplumber

    linhas, erros, grupo = [], [], ""
    with pdfplumber.open(io.BytesIO(conteudo)) as pdf:
        for n_pag, pagina in enumerate(pdf.pages, start=1):
            col = _colunas(pagina)
            if not col:
                continue
            atual = None

            def fechar():
                if atual is None:
                    return
                meio = " ".join(atual["descricao"])
                m = re.fullmatch(rf"(.*?)\s*({PRECO_RE})", meio)
                if not m or not m.group(1):
                    erros.append(f"Página {n_pag}, código {atual['codigo']}: não consegui ler o valor.")
                    return
                fabricante = re.sub(r"\s*-?[\d.]*,\d{3}$", "", " ".join(atual["fabricante"])).strip()
                linhas.append({
                    "codigo": atual["codigo"], "descricao": m.group(1).strip(), "preco": m.group(2),
                    "unidade": " ".join(atual["unidade"]).strip(), "fabricante": fabricante,
                    "grupo": grupo,
                })

            topo_grupo, pedacos_grupo = None, []
            for t in _trechos(pagina):
                if t["top"] <= col["fim_cabecalho"] or t["texto"].startswith(("Página ", "O software")):
                    continue
                if t["texto"].startswith("Grupo:") or (topo_grupo is not None and abs(t["top"] - topo_grupo) < 2):
                    if topo_grupo is None:
                        fechar()
                        atual, pedacos_grupo = None, []
                    topo_grupo = t["top"]
                    pedacos_grupo.append(t)
                    # Os pedaços da linha do grupo vêm fora de ordem: arruma pela posição.
                    grupo = " ".join(x["texto"] for x in sorted(pedacos_grupo, key=lambda x: x["x0"]))
                    continue
                topo_grupo = None
                if t["x0"] < col["descricao"] and re.fullmatch(r"\d+", t["texto"]):
                    fechar()
                    atual = {"codigo": t["texto"], "descricao": [], "unidade": [], "fabricante": []}
                elif atual is not None:
                    if t["x0"] < col["unidade"]:
                        atual["descricao"].append(t["texto"])
                    elif t["x0"] < col["fabricante"]:
                        atual["unidade"].append(t["texto"])
                    else:
                        atual["fabricante"].append(t["texto"])
            fechar()
    return linhas, erros


def _grupo_principal(grupo):
    """"Grupo: 6 ALUMINIO SubGrupo: 29 BARRA CHATAS" -> ("ALUMINIO", "BARRA CHATAS")."""
    m = re.match(r"Grupo:\s*\d*\s*(.*?)\s*SubGrupo:\s*\d*\s*(.*)", grupo or "")
    return (m.group(1).upper(), m.group(2).upper()) if m else ("", "")


def _tipo_e_comprimento_pdf(linha):
    grupo, subgrupo = _grupo_principal(linha.get("grupo"))
    unidade = linha["unidade"]
    if "ALUMINIO" in grupo:
        if unidade == "KG":
            return "outro", None  # alumínio vendido por quilo
        if unidade == "MT":
            return "perfil", 1000  # vendido por metro
        if linha["descricao"].upper().startswith("KIT"):
            return "acessorio", None  # kits prontos (box, guarda-roupa)
        return "perfil", COMPRIMENTO_BARRA_MM  # BR, UN, BD: a barra inteira
    texto = f"{grupo} {subgrupo} {linha['descricao']}".upper()
    if any(p in texto for p in VEDACAO):
        return "vedacao", None
    return "acessorio", None


# ---------------------------------------------------------------- leitura do CSV

def ler_csv(conteudo: bytes):
    try:
        texto = conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = conteudo.decode("latin-1")  # Excel antigo
    try:
        dialeto = csv.Sniffer().sniff(texto[:2000], delimiters=";,")
    except csv.Error:
        dialeto = csv.excel
        dialeto.delimiter = ";"
    leitor = csv.reader(io.StringIO(texto), dialect=dialeto)
    cabecalho = next(leitor, [])
    indice = {}
    for i, nome in enumerate(cabecalho):
        k = _chave(nome)
        for campo, nomes in APELIDOS.items():
            if k in nomes and campo not in indice:
                indice[campo] = i
    faltando = [nome for campo, nome in (("codigo", "codigo"), ("descricao", "nome"), ("preco", "valor"))
                if campo not in indice]
    if faltando:
        raise ValueError(f"Faltam as colunas: {', '.join(faltando)}. Cabeçalho esperado: codigo;nome;valor;fabricante")
    linhas = []
    for n, valores in enumerate(leitor, start=2):
        linha = {campo: (valores[i].strip() if i < len(valores) else "") for campo, i in indice.items()}
        linha["n"] = n
        linhas.append(linha)
    return linhas


# ---------------------------------------------------------------- gravação

def importar_arquivo(fornecedor, conteudo: bytes, desativar_ausentes=True):
    """Lê PDF ou CSV e grava. Devolve {criados, alterados, desativados, erros} ou {erro_geral}."""
    erros = []
    if conteudo[:5] == b"%PDF-":
        try:
            brutas, erros = ler_pdf(conteudo)
        except Exception as e:  # PDF corrompido, protegido, etc.
            return {"erro_geral": f"Não consegui abrir o PDF ({e.__class__.__name__})."}
        if not brutas:
            return {"erro_geral": "Não encontrei itens no PDF. O arquivo precisa ser a "
                                  "\"Lista de Preço Varejo\" com as colunas Código, Descrição, Preço, Embalagem e Fabricante."}
        linhas = []
        for b in brutas:
            tipo, comprimento = _tipo_e_comprimento_pdf(b)
            linhas.append({**b, "tipo_deduzido": tipo, "comprimento_deduzido": comprimento,
                           "rotulo": f"Código {b['codigo']}"})
    else:
        try:
            linhas = ler_csv(conteudo)
        except ValueError as e:
            return {"erro_geral": str(e)}
        for ln in linhas:
            ln["rotulo"] = f"Linha {ln['n']} ({ln.get('codigo', '')})"
    r = gravar(fornecedor, linhas, desativar_ausentes)
    r["erros"] = erros + r["erros"]
    return r


# Nome antigo, usado pelo admin até esta versão.
def importar_csv(fornecedor, conteudo: bytes, desativar_ausentes=True):
    return importar_arquivo(fornecedor, conteudo, desativar_ausentes)


def gravar(fornecedor, linhas, desativar_ausentes=True):
    agora = timezone.now()
    existentes = {i.codigo: i for i in ItemFornecedor.objects.filter(fornecedor=fornecedor)}
    vistos, criados, alterados, erros = set(), 0, 0, []
    for ln in linhas:
        codigo = str(ln.get("codigo") or "").strip()[:60]
        if not codigo:
            continue
        if codigo in vistos:
            erros.append(f"{ln['rotulo']}: código repetido no arquivo, ficou a primeira linha.")
            continue
        try:
            preco = _preco(ln.get("preco"))
            if preco < 0:
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            erros.append(f"{ln['rotulo']}: valor inválido ({ln.get('preco')}).")
            continue
        unidade = (str(ln.get("unidade") or "").strip().upper() or "UN")[:10]

        # Comprimento e tipo: informados na planilha valem sempre; deduzidos, só no item novo.
        informados = {}
        comp = str(ln.get("comprimento_mm") or "").strip()
        if comp:
            try:
                informados["comprimento_mm"] = int(Decimal(comp.replace(",", "."))) or None
            except (InvalidOperation, ValueError):
                erros.append(f"{ln['rotulo']}: comprimento inválido ({comp}).")
                continue
        tipo = _chave(ln.get("tipo"))
        if tipo in VALORES_TIPO:
            informados["tipo"] = tipo

        dados = {"descricao": str(ln.get("descricao") or "").strip()[:255] or codigo, "unidade": unidade,
                 "preco": preco, "fabricante": str(ln.get("fabricante") or "").strip()[:80],
                 "ativo": True, "visto_em": agora, **informados}
        vistos.add(codigo)
        item = existentes.get(codigo)
        if item is None:
            comprimento = informados.get("comprimento_mm", ln.get("comprimento_deduzido"))
            tipo_novo = informados.get("tipo") or ln.get("tipo_deduzido") or inferir_tipo(unidade, comprimento)
            ItemFornecedor.objects.create(fornecedor=fornecedor, codigo=codigo, atualizado_em=agora,
                                          **{**dados, "comprimento_mm": comprimento, "tipo": tipo_novo})
            criados += 1
            continue
        mudou = any(getattr(item, c) != v for c, v in dados.items() if c != "visto_em")
        for campo, valor in dados.items():
            setattr(item, campo, valor)
        if mudou:
            item.atualizado_em = agora  # o app baixa só o que mudou
            alterados += 1
        item.save()  # as imagens enviadas no admin são preservadas
    desativados = 0
    if desativar_ausentes and vistos:
        desativados = (ItemFornecedor.objects.filter(fornecedor=fornecedor, ativo=True)
                       .exclude(codigo__in=vistos).update(ativo=False, atualizado_em=agora))
    return {"criados": criados, "alterados": alterados, "desativados": desativados, "erros": erros}
