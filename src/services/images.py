"""Photos : vérification du format réel, redimensionnement, recompression JPEG (supprime les métadonnées GPS)."""

import os

from PIL import Image
from PIL import ImageOps

from ..config import ALLOWED_EXTENSIONS, JPEG_QUALITY, MAX_IMAGE_DIMENSION, MAX_IMAGE_PIXELS


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

class ImageRejected(Exception):
    """Image refusée avec un message affichable tel quel à l'utilisateur."""

def save_optimized_image(file_storage, dest_path):
    """
    Redimensionne et recompresse une photo uploadée avant de l'écrire sur
    le disque : indispensable sur un hébergement au quota de stockage
    limité (les photos de téléphone font souvent plusieurs Mo, une fois
    redimensionnées à 1600px et recompressées en JPEG elles pèsent
    généralement quelques centaines de Ko).

    Sécurité : on vérifie le vrai format (pas seulement l'extension) et le
    nombre de pixels AVANT de décoder l'image, pour refuser les « bombes »
    (petit fichier qui se décompresse en une image gigantesque et fait
    planter le serveur). Le ré-encodage en JPEG supprime aussi tout contenu
    caché et les métadonnées (dont la position GPS de la photo).
    """
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    try:
        img = Image.open(file_storage)  # lecture de l'en-tête seulement
        if img.format not in ("JPEG", "PNG", "WEBP"):
            raise ImageRejected("Format non accepté : utilisez une photo JPG, PNG ou WEBP.")
        if img.width * img.height > MAX_IMAGE_PIXELS:
            raise ImageRejected(
                f"Image trop grande ({MAX_IMAGE_PIXELS // 1_000_000} mégapixels maximum)."
            )
        if img.format == "JPEG":
            # Décodage directement à taille réduite : beaucoup moins de mémoire
            img.draft("RGB", (MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION))
        # Un téléphone tenu à la verticale enregistre en fait l'image "à plat" et
        # note juste dans les métadonnées EXIF qu'il faut la tourner à l'affichage.
        # Sans ce traitement, la photo perd cette info à la recompression et
        # ressort à l'horizontale. exif_transpose applique réellement la rotation
        # aux pixels, une bonne fois pour toutes.
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGB")  # nécessaire pour sauver en JPEG (PNG/WEBP peuvent être en RGBA)
        img.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION))  # garde le ratio
        img.save(dest_path, "JPEG", quality=JPEG_QUALITY, optimize=True)
    except Image.DecompressionBombError:
        # Pillow refuse d'ouvrir une image démesurée dès l'en-tête (> 2x la limite)
        raise ImageRejected(f"Image trop grande ({MAX_IMAGE_PIXELS // 1_000_000} mégapixels maximum).")
    except Exception:
        if os.path.exists(dest_path):
            os.remove(dest_path)  # pas de fichier à moitié écrit qui traîne
        raise


def migrate_legacy_uploads(legacy_folder, upload_folder):
    """Déplace les anciennes photos de static/uploads vers uploads/ (un simple renommage : aucun espace disque en plus)."""
    if not os.path.isdir(legacy_folder):
        return
    for name in os.listdir(legacy_folder):
        src = os.path.join(legacy_folder, name)
        dst = os.path.join(upload_folder, name)
        if name.startswith(".") or not os.path.isfile(src):
            continue
        try:
            if not os.path.exists(dst):
                os.replace(src, dst)
        except OSError:
            pass  # autre processus en train de faire la même chose : sans conséquence
