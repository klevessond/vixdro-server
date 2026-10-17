"""Tratamento das fotos da medição: corrige a rotação, reduz e gera miniatura."""

import base64
import binascii
from io import BytesIO

from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

LADO_FOTO = 1600  # px: dá para ver os detalhes do vão sem pesar
LADO_MINIATURA = 320


class FotoInvalida(Exception):
    pass


def _jpeg(img, lado, qualidade):
    copia = img.copy()
    copia.thumbnail((lado, lado))
    saida = BytesIO()
    copia.save(saida, format="JPEG", quality=qualidade, optimize=True)
    return ContentFile(saida.getvalue())


def processar_base64(texto):
    """Devolve (foto, miniatura) prontas para salvar, a partir do base64 do app."""
    if "," in texto[:100]:
        texto = texto.split(",", 1)[1]  # aceita "data:image/jpeg;base64,..."
    try:
        bruto = base64.b64decode(texto, validate=True)
        with Image.open(BytesIO(bruto)) as original:
            # Fotos de celular guardam a orientação à parte (EXIF); sem isto,
            # muitas aparecem deitadas.
            img = ImageOps.exif_transpose(original)
            img = img.convert("RGB")
    except (binascii.Error, ValueError, UnidentifiedImageError, OSError):
        raise FotoInvalida("Envie uma foto em JPEG ou PNG.")
    return _jpeg(img, LADO_FOTO, 82), _jpeg(img, LADO_MINIATURA, 75)
