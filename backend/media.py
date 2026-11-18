"""Bounded image decoding and re-encoding; no original files or EXIF are stored."""
from io import BytesIO
import warnings
from PIL import Image, ImageOps, UnidentifiedImageError


def prepare_photos(files):
    files = [file for file in files if file.filename]
    if len(files) > 3:
        raise ValueError("Upload up to 3 photos per listing.")
    result = []
    for file in files:
        data = file.read(1048577)
        if len(data) > 1048576:
            raise ValueError("Each photo must be no larger than 1 MB.")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(BytesIO(data)) as image:
                    if image.format not in ("JPEG", "PNG", "WEBP") or image.width * image.height > 16000000:
                        raise ValueError("Use JPG, PNG or WebP photos up to 16 megapixels.")
                    image = ImageOps.exif_transpose(image)
                    image.thumbnail((1400, 1400))
                    if image.mode in ("RGBA", "LA") or "transparency" in image.info:
                        rgba = image.convert("RGBA")
                        image = Image.new("RGB", rgba.size, "white")
                        image.paste(rgba, mask=rgba.getchannel("A"))
                    else:
                        image = image.convert("RGB")
                    output = BytesIO()
                    image.save(output, format="JPEG", quality=82, optimize=True)
                    encoded = output.getvalue()
                    if len(encoded) > 1048576:
                        raise ValueError("Photo is too complex. Please choose a smaller image.")
                    result.append(encoded)
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise ValueError("This file is not a supported image. Use JPG, PNG or WebP.") from None
    return result
