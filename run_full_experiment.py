import argparse
import csv
from pathlib import Path

import requests
from PIL import Image

from experiment_processing import (
    DEFAULT_RANDOM_SEED,
    bytes_to_kb,
    run_condition,
)
from experiment_downloads import (
    build_output_name,
    derive_condition_seed,
    ensure_local_image,
    save_compressed_output,
)
from build_experiment_plan import load_experiment_plan, unique_experiment_images_from_run_plan


def create_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Run the compression experiment across 4928x3264 images using a fixed "
            "experiment plan."
        )
    )
    parser.add_argument(
        "--input-dir",
        default="images",
        help=(
            "Directory used as the local cache for 4928x3264 source images "
            "(default: images). Missing planned images are downloaded there."
        ),
    )
    parser.add_argument(
        "--output-dir",
        default="experiment_outputs",
        help="Directory where results and optional artifacts will be stored.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_RANDOM_SEED,
        help=(
            "Base seed used for deterministic noise generation "
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
        "--plan-file",
        required=True,
        help="Fully specified experiment plan CSV to execute exactly as written.",
    )
    return parser


def main():
    parser = create_parser()
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    input_dir.mkdir(parents=True, exist_ok=True)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()

    try:
        run_plan = load_experiment_plan(args.plan_file, input_dir)
    except (OSError, ValueError) as error:
        parser.error(str(error))

    results_path = output_dir / args.results_file

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

    print(f"\nResults written to: {results_path}")


if __name__ == "__main__":
    main()
