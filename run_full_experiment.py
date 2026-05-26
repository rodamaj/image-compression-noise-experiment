import argparse
import csv
import json
from pathlib import Path

import numpy as np
import requests
from PIL import Image

from compression_experiment import (
    DEFAULT_RANDOM_SEED,
    apply_gaussian_noise,
    bytes_to_kb,
    compress_image,
    get_noise_percentage,
)
from experiment_downloads import TARGET_IMAGE_SIZE
from experiment_io import (
    build_environment_manifest,
    build_image_manifest,
    build_output_name,
    derive_condition_seed,
    ensure_local_image,
    save_compressed_output,
)
from experiment_metadata import (
    DEFAULT_ALGORITHMS,
    DEFAULT_CONTENT_BLOCKS,
    DEFAULT_NOISE_LEVELS,
    build_treatment_label,
    load_metadata,
)
from experiment_plan import (
    build_run_plan,
    build_run_plan_from_csv,
    count_required_images_by_block,
    load_experiment_plan,
    load_treatment_order,
    unique_experiment_images_from_run_plan,
)
from experiment_sampling import (
    build_candidate_images,
    select_images_by_block,
    select_images_by_block_requirements,
)


DEFAULT_MODE = "full"


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
            for sample_index, (_, record) in enumerate(experiment_images, start=1):
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
