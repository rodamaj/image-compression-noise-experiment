import csv
from pathlib import Path


DEFAULT_ALGORITHMS = ("PNG", "WEBP")
DEFAULT_NOISE_LEVELS = ("low", "high")
DEFAULT_CONTENT_BLOCKS = ("indoor", "outdoor")
TREATMENT_LABEL_SEPARATOR = "-"


def classify_content_block(keywords):
    """Classify an image as indoor or outdoor from the dataset keywords."""

    normalized_keywords = (keywords or "").strip().lower()
    has_indoor = "indoor" in normalized_keywords
    has_outdoor = "outdoor" in normalized_keywords

    if has_indoor and not has_outdoor:
        return "indoor"

    if has_outdoor and not has_indoor:
        return "outdoor"

    if has_indoor and has_outdoor:
        raise ValueError(
            f"Keywords contain both indoor and outdoor labels: {keywords!r}"
        )

    raise ValueError(f"Keywords do not contain indoor/outdoor labels: {keywords!r}")


def load_metadata(metadata_csv):
    """Load dataset metadata keyed by image stem."""

    metadata = {}
    with Path(metadata_csv).open(newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        required_columns = {"File", "Keywords", "TIFF", "Image Size"}
        missing_columns = required_columns - set(reader.fieldnames or [])
        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            raise ValueError(f"Metadata CSV is missing required columns: {missing}")

        for row in reader:
            image_stem = (row.get("File") or "").strip().lower()
            keywords = (row.get("Keywords") or "").strip()
            if not image_stem:
                continue

            metadata[image_stem] = {
                "image_name": f"{image_stem}.TIF",
                "keywords": keywords,
                "content_block": classify_content_block(keywords),
                "tiff_url": (row.get("TIFF") or "").strip(),
                "image_size": (row.get("Image Size") or "").strip(),
            }

    return metadata


def build_treatment_label(algorithm, noise_level, content_block):
    """Build a treatment label compatible with the R randomization script."""

    noise_fragment = "LowNoise" if noise_level == "low" else "HighNoise"
    block_fragment = content_block.capitalize()
    algorithm_fragment = "WebP" if algorithm.upper() == "WEBP" else "PNG"
    return TREATMENT_LABEL_SEPARATOR.join(
        [algorithm_fragment, noise_fragment, block_fragment]
    )


def normalize_algorithm(value):
    """Normalize an algorithm token to the internal uppercase representation."""

    algorithm = (value or "").strip().upper()
    if algorithm not in {"PNG", "WEBP"}:
        raise ValueError(f"Unsupported algorithm value: {value!r}")
    return algorithm


def normalize_noise_level(value):
    """Normalize a noise level token to low/high."""

    noise_level = (value or "").strip().lower()
    if noise_level not in {"low", "high"}:
        raise ValueError(f"Unsupported noise level value: {value!r}")
    return noise_level


def normalize_content_block(value):
    """Normalize a content block token to indoor/outdoor."""

    content_block = (value or "").strip().lower()
    if content_block not in {"indoor", "outdoor"}:
        raise ValueError(f"Unsupported content block value: {value!r}")
    return content_block
