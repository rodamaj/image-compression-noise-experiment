import csv
import hashlib
import time
from pathlib import Path

from PIL import Image

try:
    from tqdm import tqdm
except Exception:
    tqdm = None


TARGET_IMAGE_SIZE = (4928, 3264)
ROTATED_TARGET_IMAGE_SIZE = (3264, 4928)


def download_file(session, url, dest_path, max_retries=3, backoff=1.0):
    """Download a file with simple retry logic and optional progress reporting."""

    dest_path = Path(dest_path)
    if dest_path.exists():
        return True

    for attempt in range(1, max_retries + 1):
        try:
            with session.get(url, stream=True, timeout=30) as response:
                response.raise_for_status()
                total = response.headers.get("content-length")
                if total is None or tqdm is None:
                    with dest_path.open("wb") as file_handle:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                file_handle.write(chunk)
                else:
                    total = int(total)
                    with dest_path.open("wb") as file_handle, tqdm(
                        total=total,
                        unit="B",
                        unit_scale=True,
                        desc=dest_path.name,
                    ) as progress_bar:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                file_handle.write(chunk)
                                progress_bar.update(len(chunk))
            return True
        except Exception as error:
            if attempt == max_retries:
                print(f"ERROR: download failed for {url}: {error}")
                return False

            # Linear backoff is enough here because the source is a static dataset,
            # and we only need brief pauses to recover from transient network issues.
            time.sleep(backoff * attempt)

    return False


def normalize_download_image(path):
    """Rotate portrait files when needed and validate the final image size."""

    path = Path(path)
    if not path.exists():
        return False

    try:
        with Image.open(path) as image:
            if image.size == TARGET_IMAGE_SIZE:
                return True

            if image.size == ROTATED_TARGET_IMAGE_SIZE:
                rotated = image.transpose(Image.Transpose.ROTATE_90)
                rotated.save(path)
                return True

            return False
    except Exception:
        return False


def load_download_plan(plan_file):
    """Load the unique image downloads required by an experiment plan CSV."""

    planned_images = {}
    with Path(plan_file).open(newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        required_columns = {
            "run_order",
            "image_name",
            "image_filename",
            "tiff_url",
            "content_block",
        }
        missing_columns = required_columns - set(reader.fieldnames or [])
        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            raise ValueError(f"Experiment plan CSV is missing required columns: {missing}")

        for row in reader:
            run_order = (row.get("run_order") or "").strip()
            image_name = (row.get("image_name") or "").strip()
            image_filename = (row.get("image_filename") or "").strip()
            tiff_url = (row.get("tiff_url") or "").strip()
            content_block = (row.get("content_block") or "").strip().lower()
            if (
                not run_order
                or not image_name
                or not image_filename
                or not tiff_url
                or not content_block
            ):
                continue

            if image_filename not in planned_images:
                planned_images[image_filename] = {
                    "content_block": content_block,
                    "image_name": image_name,
                    "image_filename": image_filename,
                    "tiff_url": tiff_url,
                    "run_orders": [],
                }
            planned_images[image_filename]["run_orders"].append(int(run_order))

    return [planned_images[key] for key in sorted(planned_images)]


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


def derive_condition_seed(base_seed, image_name, content_block, algorithm, noise_level):
    """Create a deterministic seed for one image-treatment combination."""

    digest = hashlib.sha256(
        f"{base_seed}|{image_name}|{content_block}|{algorithm}|{noise_level}".encode(
            "utf-8"
        )
    ).digest()
    return int.from_bytes(digest[:8], byteorder="big") % (2**32)


def build_output_name(stem, content_block, output_id, algorithm, noise_level):
    """Create a deterministic filename for compressed outputs."""

    return (
        f"{stem}__{content_block}__sample{output_id}__"
        f"{algorithm.lower()}__{noise_level}.{algorithm.lower()}"
    )


def save_compressed_output(data, path):
    """Write the compressed noisy output bytes to disk."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
