import argparse
from pathlib import Path

import requests
from PIL import Image

from compression_experiment import DEFAULT_RANDOM_SEED
from experiment_downloads import (
    download_file,
    load_download_plan,
    normalize_download_image,
)
from experiment_metadata import DEFAULT_CONTENT_BLOCKS, load_metadata
from experiment_sampling import build_candidate_images, select_images_by_block


def create_parser():
    parser = argparse.ArgumentParser(
        description="Download sampled 4928x3264 RAISE TIFFs from metadata or a plan."
    )
    parser.add_argument(
        "--csv",
        default="RAISE_1k.csv",
        help="Path to the metadata CSV (default: RAISE_1k.csv).",
    )
    parser.add_argument("--outdir", default="input_images", help="Output directory.")
    parser.add_argument(
        "--plan-file",
        help="Optional experiment plan CSV. If provided, download only the images listed there.",
    )
    parser.add_argument(
        "--content-blocks",
        nargs="+",
        default=list(DEFAULT_CONTENT_BLOCKS),
        choices=["indoor", "outdoor"],
        help="Content blocks to sample (default: indoor outdoor).",
    )
    parser.add_argument(
        "--reps-per-block",
        type=int,
        default=0,
        help="Number of random images to sample per block (0 = all eligible images).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_RANDOM_SEED,
        help=f"Random seed for reproducible image sampling (default: {DEFAULT_RANDOM_SEED}).",
    )
    return parser


def build_sampled_images_from_metadata(metadata_csv, outdir, content_blocks, reps_per_block, seed):
    """Select the image downloads needed from metadata."""

    metadata = load_metadata(metadata_csv)
    candidate_images, _ = build_candidate_images(outdir, metadata, set(content_blocks))
    selected_images = select_images_by_block(
        candidate_images,
        set(content_blocks),
        reps_per_block,
        seed,
    )

    sampled_images = []
    for image_path, record in selected_images:
        sampled_images.append(
            {
                "content_block": record["content_block"],
                "image_name": record["image_name"],
                "image_filename": image_path.name,
                "tiff_url": record["tiff_url"],
                "run_orders": [],
            }
        )
    return sampled_images


def main():
    """Download sampled RAISE TIFF files with the fixed experiment resolution."""

    parser = create_parser()
    args = parser.parse_args()

    if args.reps_per_block < 0:
        print("--reps-per-block must be 0 or a positive integer.")
        return

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()

    if args.plan_file:
        try:
            sampled_images = load_download_plan(args.plan_file)
        except (OSError, ValueError) as error:
            print(error)
            return
    else:
        metadata_csv = Path(args.csv)
        if not metadata_csv.is_file():
            print(f"CSV not found: {args.csv}")
            return

        try:
            sampled_images = build_sampled_images_from_metadata(
                metadata_csv,
                outdir,
                args.content_blocks,
                args.reps_per_block,
                args.seed,
            )
        except (OSError, ValueError) as error:
            print(error)
            return

    total = len(sampled_images)
    print(f"Sampled images to satisfy the design: {total}")

    downloaded = 0
    already_present = 0
    for entry in sampled_images:
        block = entry["content_block"]
        filename = entry["image_filename"]
        url = entry["tiff_url"]
        run_orders = ",".join(str(value) for value in entry["run_orders"])
        run_order_label = f"runs {run_orders}" if run_orders else "no-plan"

        dest_path = outdir / filename
        if normalize_download_image(dest_path):
            print(f"Already exists and is valid: {filename} ({block}, {run_order_label})")
            downloaded += 1
            already_present += 1
            continue

        print(f"Downloading: {filename} ({block}, {run_order_label})")
        ok = download_file(session, url, dest_path)
        if not ok:
            continue

        if not normalize_download_image(dest_path):
            try:
                with Image.open(dest_path) as image:
                    print(f"Warning: {filename} has size {image.size}, removed")
            except Exception as error:
                print(f"Error opening {filename}: {error}")

            try:
                dest_path.unlink()
            except Exception:
                pass
            continue

        downloaded += 1

    print(f"Downloaded and validated: {downloaded} / {total}")
    print(f"Already present and reused: {already_present}")


if __name__ == "__main__":
    main()
