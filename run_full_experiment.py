import argparse
import csv
import hashlib
import json
import platform
import random
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
import requests
from PIL import Image
from PIL import __version__ as PILLOW_VERSION

from compression_experiment import (
    DEFAULT_RANDOM_SEED,
    apply_gaussian_noise,
    bytes_to_kb,
    compress_image,
    get_noise_percentage,
)
from download_raise_tiffs import TARGET_IMAGE_SIZE, download_file, normalize_download_image


DEFAULT_ALGORITHMS = ("PNG", "WEBP")
DEFAULT_NOISE_LEVELS = ("low", "high")
DEFAULT_CONTENT_BLOCKS = ("indoor", "outdoor")
DEFAULT_MODE = "full"
TREATMENT_LABEL_SEPARATOR = "-"
TREATMENT_ORDER_REQUIRED_COLUMNS = {"algorithm", "noise_level", "content_block"}
EXPERIMENT_PLAN_REQUIRED_COLUMNS = {
    "run_order",
    "image_name",
    "image_filename",
    "tiff_url",
    "content_block",
    "block_sample_index",
    "keywords",
    "treatment_label",
    "algorithm",
    "noise_level",
}


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


def build_candidate_images(input_dir, metadata, selected_blocks, image_name=None):
    """Return eligible dataset entries as local-path candidates."""

    candidates = []
    skipped_images = []
    normalized_image_name = image_name.strip().lower() if image_name else None

    for image_stem, record in sorted(metadata.items()):
        if record["content_block"] not in selected_blocks:
            continue

        if "4928 x 3264" not in record["image_size"]:
            skipped_images.append(
                {
                    "image_name": record["image_name"],
                    "reason": f"dataset size {record['image_size']!r} does not match required size",
                }
            )
            continue

        if not record["tiff_url"]:
            skipped_images.append(
                {
                    "image_name": record["image_name"],
                    "reason": "missing TIFF URL in metadata",
                }
            )
            continue

        if normalized_image_name and record["image_name"].lower() != normalized_image_name:
            continue

        filename = Path(urlparse(record["tiff_url"]).path).name or record["image_name"]
        image_path = Path(input_dir) / filename
        candidates.append(
            (
                image_path,
                {
                    **record,
                    "image_stem": image_stem,
                },
            )
        )

    return candidates, skipped_images


def select_images_by_block(experiment_images, selected_blocks, reps_per_block, seed):
    """Select a reproducible sample of distinct images within each content block."""

    grouped_images = {block: [] for block in selected_blocks}
    for image_path, record in experiment_images:
        grouped_images[record["content_block"]].append((image_path, record))

    rng = random.Random(seed)
    selected_images = []

    for block in sorted(selected_blocks):
        block_images = sorted(grouped_images.get(block, []), key=lambda item: item[0].name)
        if reps_per_block and len(block_images) < reps_per_block:
            raise ValueError(
                f"Block '{block}' only has {len(block_images)} eligible images, "
                f"but {reps_per_block} were requested."
            )

        if reps_per_block:
            block_images = rng.sample(block_images, reps_per_block)
            block_images.sort(key=lambda item: item[0].name)

        for sample_index, (image_path, record) in enumerate(block_images, start=1):
            selected_images.append(
                (
                    image_path,
                    {
                        **record,
                        "block_sample_index": sample_index,
                    },
                )
            )

    return selected_images


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


def unique_experiment_images_from_run_plan(run_plan):
    """Extract the unique images actually used by the ordered run plan."""

    seen = set()
    unique_images = []
    for planned_run in run_plan:
        image_path = planned_run["image_path"]
        record = planned_run["record"]
        key = str(image_path.resolve()).lower()
        if key in seen:
            continue
        seen.add(key)
        unique_images.append((image_path, record))
    return unique_images


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


def load_treatment_order(order_file):
    """Load a treatment-order CSV exported from R."""

    rows = []
    with Path(order_file).open(newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        missing_columns = TREATMENT_ORDER_REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            raise ValueError(
                "Treatment order CSV is missing required columns: "
                f"{missing}"
            )

        for row_index, row in enumerate(reader, start=2):
            try:
                algorithm = normalize_algorithm(row.get("algorithm"))
                noise_level = normalize_noise_level(row.get("noise_level"))
                content_block = normalize_content_block(row.get("content_block"))
            except ValueError as error:
                raise ValueError(
                    f"Invalid treatment order row {row_index}: {error}"
                ) from error

            run_order_raw = (row.get("run_order") or "").strip()
            run_order = None
            if run_order_raw:
                try:
                    run_order = int(run_order_raw)
                except ValueError as error:
                    raise ValueError(
                        f"Invalid run_order in treatment order row {row_index}: "
                        f"{run_order_raw!r}"
                    ) from error

            rows.append(
                {
                    "run_order": run_order,
                    "label": build_treatment_label(
                        algorithm, noise_level, content_block
                    ),
                    "algorithm": algorithm,
                    "noise_level": noise_level,
                    "content_block": content_block,
                }
            )

    if not rows:
        raise ValueError("Treatment order CSV is empty.")

    if any(row["run_order"] is not None for row in rows):
        if not all(row["run_order"] is not None for row in rows):
            raise ValueError(
                "Treatment order CSV must either define run_order for every row or for none."
            )
        rows.sort(key=lambda row: row["run_order"])

    return rows


def count_required_images_by_block(treatment_order):
    """Return how many distinct images are needed in each block."""

    required_counts = {}
    for treatment in treatment_order:
        block = treatment["content_block"]
        required_counts[block] = required_counts.get(block, 0) + 1
    return required_counts


def load_experiment_plan(plan_file, input_dir):
    """Load a fully specified experiment plan exported before download/run."""

    run_plan = []
    with Path(plan_file).open(newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        missing_columns = EXPERIMENT_PLAN_REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            raise ValueError(f"Experiment plan CSV is missing required columns: {missing}")

        for row_index, row in enumerate(reader, start=2):
            try:
                run_order = int((row.get("run_order") or "").strip())
                block_sample_index = int((row.get("block_sample_index") or "").strip())
                algorithm = normalize_algorithm(row.get("algorithm"))
                noise_level = normalize_noise_level(row.get("noise_level"))
                content_block = normalize_content_block(row.get("content_block"))
            except ValueError as error:
                raise ValueError(f"Invalid experiment plan row {row_index}: {error}") from error

            image_name = (row.get("image_name") or "").strip()
            image_filename = (row.get("image_filename") or "").strip()
            tiff_url = (row.get("tiff_url") or "").strip()
            keywords = (row.get("keywords") or "").strip()
            treatment_label = (row.get("treatment_label") or "").strip()

            if not image_name or not image_filename or not tiff_url or not treatment_label:
                raise ValueError(
                    f"Invalid experiment plan row {row_index}: missing image_name, "
                    "image_filename, tiff_url, or treatment_label."
                )

            expected_label = build_treatment_label(algorithm, noise_level, content_block)
            if treatment_label != expected_label:
                raise ValueError(
                    f"Invalid experiment plan row {row_index}: treatment_label "
                    f"{treatment_label!r} does not match the row values "
                    f"({expected_label!r})."
                )

            run_plan.append(
                {
                    "run_order": run_order,
                    "image_path": Path(input_dir) / image_filename,
                    "record": {
                        "image_name": image_name,
                        "tiff_url": tiff_url,
                        "content_block": content_block,
                        "block_sample_index": block_sample_index,
                        "keywords": keywords,
                    },
                    "algorithm": algorithm,
                    "noise_level": noise_level,
                    "treatment_label": treatment_label,
                }
            )

    if not run_plan:
        raise ValueError("Experiment plan CSV is empty.")

    run_plan.sort(key=lambda item: item["run_order"])
    return run_plan


def build_run_plan(experiment_images, algorithms, noise_levels, treatment_order=None):
    """Create the exact ordered list of runs to execute."""

    images_by_block = {}
    for image_path, record in experiment_images:
        images_by_block.setdefault(record["content_block"], []).append((image_path, record))

    for block_images in images_by_block.values():
        block_images.sort(key=lambda item: item[1]["block_sample_index"])

    runs = []
    if treatment_order:
        for treatment in treatment_order:
            for image_path, record in images_by_block.get(treatment["content_block"], []):
                runs.append(
                    {
                        "image_path": image_path,
                        "record": record,
                        "algorithm": treatment["algorithm"],
                        "noise_level": treatment["noise_level"],
                        "treatment_label": treatment["label"],
                    }
                )
        return runs

    for image_path, record in experiment_images:
        for algorithm in algorithms:
            for noise_level in noise_levels:
                runs.append(
                    {
                        "image_path": image_path,
                        "record": record,
                        "algorithm": algorithm,
                        "noise_level": noise_level,
                        "treatment_label": build_treatment_label(
                            algorithm, noise_level, record["content_block"]
                        ),
                    }
                )

    return runs


def select_images_by_block_requirements(experiment_images, required_counts, seed):
    """Select as many images from each block as the run plan requires."""

    selected_blocks = set(required_counts)
    selected_images = []
    grouped_images = {block: [] for block in selected_blocks}
    for image_path, record in experiment_images:
        grouped_images[record["content_block"]].append((image_path, record))

    rng = random.Random(seed)
    for block in sorted(selected_blocks):
        block_images = sorted(grouped_images.get(block, []), key=lambda item: item[0].name)
        required = required_counts.get(block, 0)
        if required > len(block_images):
            raise ValueError(
                f"Run plan requires {required} images from block '{block}', "
                f"but only {len(block_images)} eligible images are available."
            )

        block_images = rng.sample(block_images, required)
        block_images.sort(key=lambda item: item[0].name)

        for sample_index, (image_path, record) in enumerate(block_images, start=1):
            selected_images.append(
                (
                    image_path,
                    {
                        **record,
                        "block_sample_index": sample_index,
                    },
                )
            )

    return selected_images


def build_run_plan_from_csv(experiment_images, treatment_order):
    """Create the exact ordered list of runs defined row by row in the CSV plan."""
    images_by_block = {}
    for image_path, record in experiment_images:
        images_by_block.setdefault(record["content_block"], []).append((image_path, record))

    for block_images in images_by_block.values():
        block_images.sort(key=lambda item: item[1]["block_sample_index"])

    block_offsets = {block: 0 for block in images_by_block}
    runs = []

    for row_index, treatment in enumerate(treatment_order, start=1):
        block = treatment["content_block"]
        candidates = images_by_block.get(block, [])
        offset = block_offsets.get(block, 0)
        if offset >= len(candidates):
                raise ValueError(
                    f"Run-plan row {row_index} requires another image from block "
                    f"{block!r}, but no eligible sampled images remain. Increase "
                    "--reps-per-block or reduce the number of CSV rows for that block."
                )
        image_path, record = candidates[offset]
        block_offsets[block] = offset + 1

        runs.append(
            {
                "image_path": image_path,
                "record": record,
                "algorithm": treatment["algorithm"],
                "noise_level": treatment["noise_level"],
                "treatment_label": treatment["label"],
            }
        )

    return runs


def build_output_name(stem, content_block, algorithm, noise_level):
    """Create a deterministic filename for compressed outputs."""

    return f"{stem}__{content_block}__{algorithm.lower()}__{noise_level}.{algorithm.lower()}"


def run_condition(image, algorithm, noise_level, seed):
    """Run one experimental treatment on an in-memory image."""

    rng = np.random.default_rng(seed)
    noise_percentage = get_noise_percentage(noise_level, rng)

    baseline_compressed_image = compress_image(image, algorithm)
    noisy_image = apply_gaussian_noise(image, noise_percentage, rng)
    noisy_compressed_image = compress_image(noisy_image, algorithm)

    baseline_compressed_size = len(baseline_compressed_image)
    if baseline_compressed_size == 0:
        raise ValueError("The compressed original image has a size of 0 bytes.")

    noisy_compressed_size = len(noisy_compressed_image)
    response = (
        (noisy_compressed_size - baseline_compressed_size) / baseline_compressed_size
    ) * 100

    return {
        "baseline_compressed_image": baseline_compressed_image,
        "noisy_compressed_image": noisy_compressed_image,
        "baseline_compressed_size": baseline_compressed_size,
        "noisy_compressed_size": noisy_compressed_size,
        "response": response,
        "noise_percentage": noise_percentage,
        "algorithm": "WebP" if algorithm.upper() == "WEBP" else "PNG",
        "noise_level": noise_level,
        "seed": seed,
    }


def save_compressed_output(data, path):
    """Write the compressed noisy output bytes to disk."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def create_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Run either the full compression experiment or a single treatment across "
            "4928x3264 images, blocking by indoor/outdoor content and selecting "
            "distinct images per block reproducibly."
        )
    )
    parser.add_argument(
        "--mode",
        choices=["full", "single-treatment"],
        default=DEFAULT_MODE,
        help=(
            "Run the full factorial experiment or a single treatment subset "
            f"(default: {DEFAULT_MODE})."
        ),
    )
    parser.add_argument(
        "--input-dir",
        default="images",
        help=(
            "Directory used as the local cache for 4928x3264 source images "
            "(default: images). Missing sampled images are downloaded there."
        ),
    )
    parser.add_argument(
        "--metadata-csv",
        default="RAISE_1k.csv",
        help="CSV file containing the dataset metadata and Keywords column.",
    )
    parser.add_argument(
        "--output-dir",
        default="experiment_outputs",
        help="Directory where results and optional artifacts will be stored.",
    )
    parser.add_argument(
        "--content-blocks",
        nargs="+",
        default=list(DEFAULT_CONTENT_BLOCKS),
        choices=["indoor", "outdoor"],
        help="Content blocks to include in the run (default: indoor outdoor).",
    )
    parser.add_argument(
        "--algorithms",
        nargs="+",
        default=list(DEFAULT_ALGORITHMS),
        choices=["PNG", "png", "WEBP", "webp", "WebP"],
        help="Compression algorithms to evaluate (default: PNG WEBP).",
    )
    parser.add_argument(
        "--noise-levels",
        nargs="+",
        default=list(DEFAULT_NOISE_LEVELS),
        choices=["low", "high"],
        help="Noise levels to evaluate (default: low high).",
    )
    parser.add_argument(
        "--reps-per-block",
        type=int,
        default=0,
        help=(
            "Number of distinct images to sample without replacement from each selected "
            "block. Use 0 to include all eligible images (default: 0)."
        ),
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_RANDOM_SEED,
        help=(
            "Base seed used for reproducible image selection and deterministic noise "
            f"(default: {DEFAULT_RANDOM_SEED})."
        ),
    )
    parser.add_argument(
        "--save-compressed-outputs",
        action="store_true",
        help="Save the noisy compressed output for each treatment combination.",
    )
    parser.add_argument(
        "--results-file",
        default="results.csv",
        help="Name of the CSV file to generate inside the output directory.",
    )
    parser.add_argument(
        "--image-name",
        help=(
            "Optional image filename to process. If provided, the run is restricted to "
            "that single image."
        ),
    )
    parser.add_argument(
        "--treatment-order-file",
        help=(
            "Optional CSV file with columns algorithm, noise_level, and content_block "
            "(and optional run_order). If provided, runs follow that CSV plan while "
            "Python assigns sampled images within each block."
        ),
    )
    parser.add_argument(
        "--plan-file",
        help=(
            "Optional fully specified experiment plan CSV. If provided, Python uses "
            "that exact plan instead of selecting images and treatments again."
        ),
    )
    return parser


def main():
    parser = create_parser()
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    input_dir.mkdir(parents=True, exist_ok=True)

    metadata_csv = Path(args.metadata_csv)
    if not metadata_csv.is_file():
        parser.error(f"Metadata CSV does not exist: {metadata_csv}")

    if args.reps_per_block < 0:
        parser.error("--reps-per-block must be 0 or a positive integer.")

    algorithms = [algorithm.upper() for algorithm in args.algorithms]
    noise_levels = list(args.noise_levels)
    selected_blocks = set(args.content_blocks)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()

    try:
        metadata = load_metadata(metadata_csv)
    except ValueError as error:
        parser.error(str(error))

    treatment_order = None
    if args.plan_file:
        try:
            run_plan = load_experiment_plan(args.plan_file, input_dir)
        except (OSError, ValueError) as error:
            parser.error(str(error))

        experiment_images = unique_experiment_images_from_run_plan(run_plan)
        skipped_images = []
        algorithms = sorted({planned_run["algorithm"] for planned_run in run_plan})
        noise_levels = sorted({planned_run["noise_level"] for planned_run in run_plan})
        selected_blocks = sorted(
            {planned_run["record"]["content_block"] for planned_run in run_plan}
        )
    else:
        try:
            experiment_images, skipped_images = build_candidate_images(
                input_dir,
                metadata,
                set(selected_blocks),
                image_name=args.image_name,
            )
        except ValueError as error:
            parser.error(str(error))

        if not experiment_images:
            parser.error(
                "No dataset entries matched the selected content blocks and image filter."
            )

        if args.mode == "single-treatment":
            if len(algorithms) != 1 or len(noise_levels) != 1:
                parser.error(
                    "--mode single-treatment requires exactly one algorithm and one noise level."
                )

        treatment_order = None
        if args.treatment_order_file:
            try:
                treatment_order = load_treatment_order(args.treatment_order_file)
            except (OSError, ValueError) as error:
                parser.error(str(error))

            allowed_labels = {
                build_treatment_label(algorithm, noise_level, block)
                for algorithm in algorithms
                for noise_level in noise_levels
                for block in selected_blocks
            }
            invalid_labels = [
                treatment["label"]
                for treatment in treatment_order
                if treatment["label"] not in allowed_labels
            ]
            if invalid_labels:
                parser.error(
                    "Treatment order file contains labels outside the selected "
                    f"algorithms/noise levels/blocks: {', '.join(invalid_labels)}"
                )

    if not args.plan_file:
        if args.image_name:
            for sample_index, (image_path, record) in enumerate(experiment_images, start=1):
                record["block_sample_index"] = sample_index
        elif treatment_order:
            try:
                experiment_images = select_images_by_block_requirements(
                    experiment_images,
                    count_required_images_by_block(treatment_order),
                    args.seed,
                )
            except ValueError as error:
                parser.error(str(error))
        else:
            try:
                experiment_images = select_images_by_block(
                    experiment_images,
                    set(selected_blocks),
                    args.reps_per_block,
                    args.seed,
                )
            except ValueError as error:
                parser.error(str(error))

        try:
            if treatment_order:
                run_plan = build_run_plan_from_csv(experiment_images, treatment_order)
            else:
                run_plan = build_run_plan(
                    experiment_images,
                    algorithms,
                    noise_levels,
                    treatment_order=None,
                )
        except ValueError as error:
            parser.error(str(error))

    results_path = output_dir / args.results_file
    summary_path = output_dir / "summary.json"
    manifest_path = output_dir / "manifest.json"

    fieldnames = [
        "run_order",
        "image_name",
        "content_block",
        "block_sample_index",
        "keywords",
        "algorithm",
        "noise_level",
        "seed",
        "noise_percentage",
        "baseline_compressed_size_kb",
        "noisy_compressed_size_kb",
        "response_percent",
    ]

    total_runs = len(run_plan)
    completed_runs = 0
    used_images = unique_experiment_images_from_run_plan(run_plan)
    for image_path, record in used_images:
        try:
            ensure_local_image(image_path, record, session)
        except ValueError as error:
            parser.error(str(error))
    image_manifest = build_image_manifest(used_images)
    environment_manifest = build_environment_manifest()

    with results_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()

        for planned_run in run_plan:
            image_path = planned_run["image_path"]
            record = planned_run["record"]
            try:
                image_path = ensure_local_image(image_path, record, session)
            except ValueError as error:
                parser.error(str(error))

            with Image.open(image_path) as original_image:
                experiment_image = original_image.convert("RGB")
                algorithm = planned_run["algorithm"]
                noise_level = planned_run["noise_level"]
                seed = derive_condition_seed(
                    args.seed,
                    image_path.name,
                    record["content_block"],
                    algorithm,
                    noise_level,
                )
                result = run_condition(
                    experiment_image,
                    algorithm=algorithm,
                    noise_level=noise_level,
                    seed=seed,
                )

                if args.save_compressed_outputs:
                    compressed_output_path = (
                        output_dir
                        / "compressed_outputs"
                        / record["content_block"]
                        / algorithm.lower()
                        / noise_level
                        / build_output_name(
                            image_path.stem,
                            record["content_block"],
                            algorithm,
                            noise_level,
                        )
                    )
                    save_compressed_output(
                        result["noisy_compressed_image"],
                        compressed_output_path,
                    )

                writer.writerow(
                    {
                        "run_order": completed_runs + 1,
                        "image_name": image_path.name,
                        "content_block": record["content_block"],
                        "block_sample_index": record["block_sample_index"],
                        "keywords": record["keywords"],
                        "algorithm": result["algorithm"],
                        "noise_level": result["noise_level"],
                        "seed": result["seed"],
                        "noise_percentage": result["noise_percentage"],
                        "baseline_compressed_size_kb": bytes_to_kb(
                            result["baseline_compressed_size"]
                        ),
                        "noisy_compressed_size_kb": bytes_to_kb(
                            result["noisy_compressed_size"]
                        ),
                        "response_percent": result["response"],
                    }
                )

                completed_runs += 1
                print(
                    f"[{completed_runs}/{total_runs}] "
                    f"{image_path.name} | {planned_run['treatment_label']} | "
                    f"sample {record['block_sample_index']}"
                )

    summary = {
        "mode": args.mode,
        "input_dir": str(input_dir.resolve()),
        "metadata_csv": str(metadata_csv.resolve()),
        "output_dir": str(output_dir.resolve()),
        "results_file": str(results_path.resolve()),
        "images_processed": len(used_images),
        "content_blocks": sorted(selected_blocks),
        "algorithms": ["WebP" if value == "WEBP" else "PNG" for value in algorithms],
        "noise_levels": noise_levels,
        "reps_per_block": args.reps_per_block,
        "base_seed": args.seed,
        "image_name_filter": args.image_name,
        "treatment_order_file": (
            str(Path(args.treatment_order_file).resolve())
            if args.treatment_order_file
            else None
        ),
        "total_runs": total_runs,
        "save_compressed_outputs": args.save_compressed_outputs,
        "skipped_images": skipped_images,
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    manifest = {
        "experiment_configuration": {
            "mode": args.mode,
            "input_dir": str(input_dir.resolve()),
            "metadata_csv": str(metadata_csv.resolve()),
            "output_dir": str(output_dir.resolve()),
            "results_file": str(results_path.resolve()),
            "content_blocks": sorted(selected_blocks),
            "algorithms": [
                "WebP" if value == "WEBP" else "PNG" for value in algorithms
            ],
            "noise_levels": noise_levels,
            "reps_per_block": args.reps_per_block,
            "base_seed": args.seed,
            "image_name_filter": args.image_name,
            "treatment_order_file": (
                str(Path(args.treatment_order_file).resolve())
                if args.treatment_order_file
                else None
            ),
            "required_image_size": {
                "width": TARGET_IMAGE_SIZE[0],
                "height": TARGET_IMAGE_SIZE[1],
            },
        },
        "environment": environment_manifest,
        "images": image_manifest,
        "skipped_images": skipped_images,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"\nResults written to: {results_path}")
    print(f"Summary written to: {summary_path}")
    print(f"Manifest written to: {manifest_path}")


if __name__ == "__main__":
    main()
