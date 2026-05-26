import csv
import os
import argparse
import random
import requests
from PIL import Image
from urllib.parse import urlparse
import time

try:
    from tqdm import tqdm
except Exception:
    tqdm = None


TARGET_IMAGE_SIZE = (4928, 3264)
ROTATED_TARGET_IMAGE_SIZE = (3264, 4928)
DEFAULT_CONTENT_BLOCKS = ("indoor", "outdoor")


def ensure_dir(p):
    """Create the target directory when it does not already exist."""
    if not os.path.exists(p):
        os.makedirs(p, exist_ok=True)


def download_file(session, url, dest_path, max_retries=3, backoff=1.0):
    """Download a file with simple retry logic and optional progress reporting."""
    if os.path.exists(dest_path):
        return True
    for attempt in range(1, max_retries + 1):
        try:
            with session.get(url, stream=True, timeout=30) as r:
                r.raise_for_status()
                total = r.headers.get('content-length')
                if total is None or tqdm is None:
                    with open(dest_path, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                else:
                    total = int(total)
                    with open(dest_path, 'wb') as f, tqdm(total=total, unit='B', unit_scale=True, desc=os.path.basename(dest_path)) as pbar:
                        for chunk in r.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                pbar.update(len(chunk))
            return True
        except Exception as e:
            if attempt == max_retries:
                print(f"ERROR: download failed for {url}: {e}")
                return False
            else:
                # Linear backoff is enough here because the source is a static dataset,
                # and we only need brief pauses to recover from transient network issues.
                time.sleep(backoff * attempt)
    return False


def classify_content_block(keywords):
    """Classify the dataset keywords into indoor/outdoor blocks."""

    normalized_keywords = (keywords or "").strip().lower()
    has_indoor = "indoor" in normalized_keywords
    has_outdoor = "outdoor" in normalized_keywords

    if has_indoor and not has_outdoor:
        return "indoor"

    if has_outdoor and not has_indoor:
        return "outdoor"

    raise ValueError(f"Could not derive a unique content block from keywords: {keywords!r}")


def is_valid_download(path):
    """Return True when the file exists and matches the required size."""

    if not os.path.exists(path):
        return False

    try:
        with Image.open(path) as image:
            return image.size == TARGET_IMAGE_SIZE
    except Exception:
        return False


def normalize_download_image(path):
    """Rotate portrait files when needed and validate the final image size."""

    if not os.path.exists(path):
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
    with open(plan_file, newline='', encoding='utf-8') as csv_file:
        reader = csv.DictReader(csv_file)
        required_columns = {'run_order', 'image_name', 'image_filename', 'tiff_url', 'content_block'}
        missing_columns = required_columns - set(reader.fieldnames or [])
        if missing_columns:
            missing = ', '.join(sorted(missing_columns))
            raise ValueError(f'Experiment plan CSV is missing required columns: {missing}')

        for row in reader:
            run_order = (row.get('run_order') or '').strip()
            image_name = (row.get('image_name') or '').strip()
            image_filename = (row.get('image_filename') or '').strip()
            tiff_url = (row.get('tiff_url') or '').strip()
            content_block = (row.get('content_block') or '').strip().lower()
            if not run_order or not image_name or not image_filename or not tiff_url or not content_block:
                continue
            if image_filename not in planned_images:
                planned_images[image_filename] = {
                    'content_block': content_block,
                    'image_name': image_name,
                    'image_filename': image_filename,
                    'tiff_url': tiff_url,
                    'run_orders': [],
                }
            planned_images[image_filename]['run_orders'].append(int(run_order))

    return [planned_images[key] for key in sorted(planned_images)]


def main():
    """Download sampled RAISE TIFF files with the fixed experiment resolution."""
    p = argparse.ArgumentParser(
        description='Download sampled 4928x3264 RAISE TIFFs from a CSV file'
    )
    p.add_argument('--csv', default='RAISE_1k.csv', help='Path to the CSV file (default: RAISE_1k.csv)')
    p.add_argument('--outdir', default='input_images', help='Output directory')
    p.add_argument(
        '--plan-file',
        help='Optional experiment plan CSV. If provided, download only the images listed there.',
    )
    p.add_argument(
        '--content-blocks',
        nargs='+',
        default=list(DEFAULT_CONTENT_BLOCKS),
        choices=['indoor', 'outdoor'],
        help='Content blocks to sample (default: indoor outdoor)',
    )
    p.add_argument(
        '--reps-per-block',
        type=int,
        default=0,
        help='Number of random images to sample per block (0 = all eligible images).',
    )
    p.add_argument(
        '--seed',
        type=int,
        default=26,
        help='Random seed for reproducible image sampling (default: 26).',
    )
    args = p.parse_args()

    if not os.path.exists(args.csv) and not args.plan_file:
        print(f"CSV not found: {args.csv}")
        return

    if args.reps_per_block < 0:
        print("--reps-per-block must be 0 or a positive integer.")
        return

    ensure_dir(args.outdir)

    session = requests.Session()

    if args.plan_file:
        try:
            sampled_images = load_download_plan(args.plan_file)
        except (OSError, ValueError) as error:
            print(error)
            return
    else:
        candidates_by_block = {block: [] for block in args.content_blocks}
        with open(args.csv, newline='', encoding='utf-8') as fh:
            reader = csv.DictReader(fh)
            try:
                required_columns = {'TIFF', 'File', 'Image Size', 'Keywords'}
                missing_columns = required_columns - set(reader.fieldnames or [])
                if missing_columns:
                    raise ValueError(', '.join(sorted(missing_columns)))
            except ValueError as e:
                print('Expected CSV headers were not found:', e)
                return

            for row in reader:
                url = row.get('TIFF')
                name = row.get('File')
                image_size = row.get('Image Size', '')
                keywords = row.get('Keywords', '')
                if not url or '4928 x 3264' not in image_size:
                    continue

                try:
                    block = classify_content_block(keywords)
                except ValueError:
                    continue

                if block in candidates_by_block:
                    filename = os.path.basename(urlparse(url).path) or f"{name}.tif"
                    candidates_by_block[block].append((name, filename, url))

        rng = random.Random(args.seed)
        sampled_images = []
        for block in args.content_blocks:
            block_candidates = sorted(candidates_by_block.get(block, []), key=lambda item: item[0])
            if args.reps_per_block and len(block_candidates) < args.reps_per_block:
                print(
                    f"Block '{block}' only has {len(block_candidates)} eligible images, "
                    f"but {args.reps_per_block} were requested."
                )
                return

            if args.reps_per_block:
                block_candidates = rng.sample(block_candidates, args.reps_per_block)
                block_candidates.sort(key=lambda item: item[0])

            sampled_images.extend((block, name, filename, url) for name, filename, url in block_candidates)

    total = len(sampled_images)
    print(f"Sampled images to satisfy the design: {total}")

    downloaded = 0
    already_present = 0
    for entry in sampled_images:
        if args.plan_file:
            block = entry['content_block']
            name = entry['image_name']
            filename = entry['image_filename']
            url = entry['tiff_url']
            run_orders = ','.join(str(value) for value in entry['run_orders'])
            run_order_label = f"runs {run_orders}"
        else:
            block, name, filename, url = entry
            run_order_label = "no-plan"

        dest_path = os.path.join(args.outdir, filename)
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
                with Image.open(dest_path) as im:
                    print(f"Warning: {filename} has size {im.size}, removed")
            except Exception as e:
                print(f"Error opening {filename}: {e}")
            try:
                os.remove(dest_path)
            except Exception:
                pass
            continue

        downloaded += 1

    print(f"Downloaded and validated: {downloaded} / {total}")
    print(f"Already present and reused: {already_present}")


if __name__ == '__main__':
    main()
