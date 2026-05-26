import argparse
import csv
import json
from pathlib import Path

from run_full_experiment import (
    DEFAULT_CONTENT_BLOCKS,
    DEFAULT_NOISE_LEVELS,
    DEFAULT_RANDOM_SEED,
    TARGET_IMAGE_SIZE,
    build_candidate_images,
    build_run_plan,
    build_run_plan_from_csv,
    build_treatment_label,
    count_required_images_by_block,
    load_metadata,
    load_treatment_order,
    select_images_by_block,
    select_images_by_block_requirements,
)


def create_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Prepare a fully specified experiment plan before downloading images "
            "or running the experiment."
        )
    )
    parser.add_argument(
        "--metadata-csv",
        default="RAISE_1k.csv",
        help="CSV file containing the dataset metadata and TIFF URLs.",
    )
    parser.add_argument(
        "--input-dir",
        default="images",
        help="Directory that will hold the downloaded source images.",
    )
    parser.add_argument(
        "--output-plan",
        default="experiment_plan.csv",
        help="Path to the generated experiment plan CSV.",
    )
    parser.add_argument(
        "--content-blocks",
        nargs="+",
        default=list(DEFAULT_CONTENT_BLOCKS),
        choices=["indoor", "outdoor"],
        help="Content blocks to include in the plan (default: indoor outdoor).",
    )
    parser.add_argument(
        "--algorithms",
        nargs="+",
        default=["PNG", "WEBP"],
        choices=["PNG", "png", "WEBP", "webp", "WebP"],
        help="Algorithms to include when not using a treatment-order CSV.",
    )
    parser.add_argument(
        "--noise-levels",
        nargs="+",
        default=list(DEFAULT_NOISE_LEVELS),
        choices=["low", "high"],
        help="Noise levels to include when not using a treatment-order CSV.",
    )
    parser.add_argument(
        "--reps-per-block",
        type=int,
        default=0,
        help=(
            "Number of distinct images to sample without replacement from each selected "
            "block. Use 0 to include all eligible images."
        ),
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_RANDOM_SEED,
        help="Base seed for reproducible image selection (default: 26).",
    )
    parser.add_argument(
        "--image-name",
        help="Optional image filename to restrict the plan to a single image.",
    )
    parser.add_argument(
        "--treatment-order-file",
        help=(
            "Optional CSV file with columns algorithm, noise_level, and content_block "
            "that defines the treatment sequence row by row."
        ),
    )
    return parser


def main():
    parser = create_parser()
    args = parser.parse_args()

    if args.reps_per_block < 0:
        parser.error("--reps-per-block must be 0 or a positive integer.")

    try:
        metadata = load_metadata(args.metadata_csv)
    except (OSError, ValueError) as error:
        parser.error(str(error))

    try:
        candidate_images, skipped_images = build_candidate_images(
            args.input_dir,
            metadata,
            set(args.content_blocks),
            image_name=args.image_name,
        )
    except ValueError as error:
        parser.error(str(error))

    if not candidate_images:
        parser.error(
            "No dataset entries matched the selected content blocks and image filter."
        )

    algorithms = [algorithm.upper() for algorithm in args.algorithms]
    noise_levels = list(args.noise_levels)

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
            for block in args.content_blocks
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

    if args.image_name:
        for sample_index, (image_path, record) in enumerate(candidate_images, start=1):
            record["block_sample_index"] = sample_index
        selected_images = candidate_images
    elif treatment_order:
        try:
            selected_images = select_images_by_block_requirements(
                candidate_images,
                count_required_images_by_block(treatment_order),
                args.seed,
            )
        except ValueError as error:
            parser.error(str(error))
    else:
        try:
            selected_images = select_images_by_block(
                candidate_images,
                set(args.content_blocks),
                args.reps_per_block,
                args.seed,
            )
        except ValueError as error:
            parser.error(str(error))

    try:
        if treatment_order:
            run_plan = build_run_plan_from_csv(selected_images, treatment_order)
        else:
            run_plan = build_run_plan(
                selected_images,
                algorithms,
                noise_levels,
                treatment_order=None,
            )
    except ValueError as error:
        parser.error(str(error))

    plan_path = Path(args.output_plan)
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
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
    ]

    with plan_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for run_order, planned_run in enumerate(run_plan, start=1):
            image_path = planned_run["image_path"]
            record = planned_run["record"]
            writer.writerow(
                {
                    "run_order": run_order,
                    "image_name": record["image_name"],
                    "image_filename": image_path.name,
                    "tiff_url": record["tiff_url"],
                    "content_block": record["content_block"],
                    "block_sample_index": record["block_sample_index"],
                    "keywords": record["keywords"],
                    "treatment_label": planned_run["treatment_label"],
                    "algorithm": planned_run["algorithm"],
                    "noise_level": planned_run["noise_level"],
                }
            )

    summary = {
        "metadata_csv": str(Path(args.metadata_csv).resolve()),
        "input_dir": str(Path(args.input_dir).resolve()),
        "output_plan": str(plan_path.resolve()),
        "content_blocks": list(args.content_blocks),
        "algorithms": ["WebP" if value == "WEBP" else "PNG" for value in algorithms],
        "noise_levels": noise_levels,
        "reps_per_block": args.reps_per_block,
        "seed": args.seed,
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
        "selected_images": len(selected_images),
        "planned_runs": len(run_plan),
        "skipped_images": skipped_images,
    }
    summary_path = plan_path.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Experiment plan written to: {plan_path}")
    print(f"Plan summary written to: {summary_path}")
    print(f"Selected images: {len(selected_images)}")
    print(f"Planned runs: {len(run_plan)}")


if __name__ == "__main__":
    main()
