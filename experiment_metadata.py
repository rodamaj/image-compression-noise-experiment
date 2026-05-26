import csv
from pathlib import Path


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

            try:
                content_block = classify_content_block(keywords)
            except ValueError:
                continue

            metadata[image_stem] = {
                "image_name": f"{image_stem}.TIF",
                "keywords": keywords,
                "content_block": content_block,
                "tiff_url": (row.get("TIFF") or "").strip(),
                "image_size": (row.get("Image Size") or "").strip(),
            }

    return metadata
