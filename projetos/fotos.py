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
