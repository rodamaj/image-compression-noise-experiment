import argparse
from pathlib import Path

import requests
from PIL import Image

from experiment_downloads import download_file, load_download_plan, normalize_download_image


def create_parser():
    parser = argparse.ArgumentParser(
        description="Download the 4928x3264 RAISE TIFFs required by an experiment plan."
    )
    parser.add_argument("--outdir", default="input_images", help="Output directory.")
    parser.add_argument(
        "--plan-file",
        required=True,
        help="Experiment plan CSV. Only the images listed there are downloaded.",
    )
    return parser


def main():
    """Download sampled RAISE TIFF files with the fixed experiment resolution."""

    parser = create_parser()
    args = parser.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()

    try:
        sampled_images = load_download_plan(args.plan_file)
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

        dest_path = outdir / filename
        if normalize_download_image(dest_path):
            print(f"Already exists and is valid: {filename} ({block}, runs {run_orders})")
            downloaded += 1
            already_present += 1
            continue

        print(f"Downloading: {filename} ({block}, runs {run_orders})")
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
