import hashlib
import platform
from pathlib import Path

import numpy as np
from PIL import __version__ as PILLOW_VERSION

from experiment_downloads import TARGET_IMAGE_SIZE, download_file, normalize_download_image


def compute_sha256(path):
    """Return the SHA-256 hash for a file."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_valid_local_image(path):
    """Return True when a local file exists and matches the required size."""

    path = Path(path)
    if not path.is_file():
        return False

    return normalize_download_image(path)


def ensure_local_image(image_path, record, session):
    """Download the image only when it is missing or invalid locally."""

    image_path = Path(image_path)
    image_path.parent.mkdir(parents=True, exist_ok=True)

    if is_valid_local_image(image_path):
        return image_path

    if image_path.exists():
        image_path.unlink()

    ok = download_file(session, record["tiff_url"], str(image_path))
    if not ok:
        raise ValueError(f"Could not download image: {record['image_name']}")

    if not is_valid_local_image(image_path):
        if image_path.exists():
            image_path.unlink()
        raise ValueError(
            f"Downloaded image does not match required size {TARGET_IMAGE_SIZE}: "
            f"{record['image_name']}"
        )

    return image_path


def build_image_manifest(experiment_images):
    """Build a reproducibility manifest for the selected images."""

    manifest = []
    for image_path, record in experiment_images:
        manifest.append(
            {
                "image_name": image_path.name,
                "source_path": str(image_path.resolve()),
                "content_block": record["content_block"],
                "block_sample_index": record.get("block_sample_index"),
                "keywords": record["keywords"],
                "sha256": compute_sha256(image_path),
            }
        )
    return manifest


def build_environment_manifest():
    """Capture the local software environment used for the run."""

    return {
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "numpy_version": np.__version__,
        "pillow_version": PILLOW_VERSION,
    }


def derive_condition_seed(base_seed, image_name, content_block, algorithm, noise_level):
    """Create a deterministic seed for one image-treatment combination."""

    digest = hashlib.sha256(
        f"{base_seed}|{image_name}|{content_block}|{algorithm}|{noise_level}".encode(
            "utf-8"
        )
    ).digest()
    return int.from_bytes(digest[:8], byteorder="big") % (2**32)


def build_output_name(stem, content_block, algorithm, noise_level):
    """Create a deterministic filename for compressed outputs."""

    return f"{stem}__{content_block}__{algorithm.lower()}__{noise_level}.{algorithm.lower()}"


def save_compressed_output(data, path):
    """Write the compressed noisy output bytes to disk."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
