"""Tratamento das fotos da medição: corrige a rotação, reduz e gera miniatura."""

import base64
import binascii
from io import BytesIO

from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

LADO_FOTO = 1600  # px: dá para ver os detalhes do vão sem pesar
LADO_MINIATURA = 320

# Só estes formatos são abertos (o Pillow conhece dezenas, alguns antigos e frágeis).
FORMATOS = ("JPEG", "PNG", "WEBP")
# Uma imagem pequena em bytes pode ter bilhões de pixels e, ao ser aberta,
# ocupar toda a memória do servidor. 80 milhões cobre qualquer foto de celular.
MAXIMO_PIXELS = 80_000_000


class FotoInvalida(Exception):
    pass


def abrir_imagem(texto):
    """Imagem (Pillow) a partir do base64 enviado pelo app, já conferida:
    formato aceito e tamanho que cabe na memória. Lança FotoInvalida."""
    texto = str(texto or "")
    if "," in texto[:100]:
        texto = texto.split(",", 1)[1]  # aceita "data:image/jpeg;base64,..."
    try:
        bruto = base64.b64decode(texto, validate=True)
        with Image.open(BytesIO(bruto), formats=FORMATOS) as original:
            largura, altura = original.size
            if largura * altura > MAXIMO_PIXELS:
                raise FotoInvalida("A imagem é grande demais. Envie uma foto menor.")
            # Fotos de celular guardam a orientação à parte (EXIF); sem isto,
            # muitas aparecem deitadas.
            return ImageOps.exif_transpose(original).copy()
    except (binascii.Error, ValueError, UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise FotoInvalida("Envie uma foto em JPEG ou PNG.")


def _jpeg(img, lado, qualidade):
    copia = img.copy()
    copia.thumbnail((lado, lado))
    saida = BytesIO()
    copia.save(saida, format="JPEG", quality=qualidade, optimize=True)
    return ContentFile(saida.getvalue())


def processar_base64(texto):
    """Devolve (foto, miniatura) prontas para salvar, a partir do base64 do app."""
    img = abrir_imagem(texto).convert("RGB")
    return _jpeg(img, LADO_FOTO, 82), _jpeg(img, LADO_MINIATURA, 75)


def trocar_imagem(obj, base64_texto):
    """Grava a foto (e a miniatura) num objeto com os campos imagem/miniatura,
    apagando as anteriores. base64 vazio = só remove."""
    # Primeiro confere a nova (se for inválida, a antiga continua).
    nova = processar_base64(base64_texto) if base64_texto else None
    for campo in (obj.imagem, obj.miniatura):
        if campo:
            campo.delete(save=False)
    if nova:
        foto, mini = nova
        obj.imagem.save("foto.jpg", foto, save=False)
        obj.miniatura.save("mini.jpg", mini, save=False)
    obj.save(update_fields=["imagem", "miniatura"])


def url_de(request, arquivo):
    if not arquivo:
        return None
    return request.build_absolute_uri(arquivo.url) if request else arquivo.url
