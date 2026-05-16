import csv
import os
import argparse
import requests
from PIL import Image
from urllib.parse import urlparse
import time

try:
    from tqdm import tqdm
except Exception:
    tqdm = None


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


def main():
    """Download and validate RAISE TIFF files that match the expected resolution."""
    p = argparse.ArgumentParser(description='Download 4928x3264 RAISE TIFFs from a CSV file')
    p.add_argument('--csv', default='RAISE_1k.csv', help='Path to the CSV file (default: RAISE_1k.csv)')
    p.add_argument('--outdir', default='input_images', help='Output directory')
    p.add_argument('--limit', type=int, default=0, help='Download limit (0 = all)')
    args = p.parse_args()

    if not os.path.exists(args.csv):
        print(f"CSV not found: {args.csv}")
        return

    ensure_dir(args.outdir)

    session = requests.Session()

    to_download = []
    with open(args.csv, newline='', encoding='utf-8') as fh:
        reader = csv.reader(fh)
        headers = next(reader)
        # Locate the required column indices.
        try:
            idx_tiff = headers.index('TIFF')
            idx_size = headers.index('Image Size')
            idx_file = headers.index('File')
        except ValueError as e:
            print('Expected CSV headers were not found:', e)
            return

        for row in reader:
            img_size = row[idx_size]
            if '4928 x 3264' in img_size:
                url = row[idx_tiff]
                name = row[idx_file]
                if url:
                    to_download.append((name, url))

    total = len(to_download)
    print(f"Images found (4928x3264): {total}")
    if args.limit and args.limit > 0:
        to_download = to_download[: args.limit]

    downloaded = 0
    for name, url in to_download:
        filename = os.path.basename(urlparse(url).path)
        if not filename:
            filename = f"{name}.tif"
        dest_path = os.path.join(args.outdir, filename)
        if os.path.exists(dest_path):
            try:
                im = Image.open(dest_path)
                if im.size == (4928, 3264):
                    print(f"Already exists and is valid: {filename}")
                    downloaded += 1
                    continue
            except Exception:
                pass

        ok = download_file(session, url, dest_path)
        if not ok:
            continue

        # Verify image size and fix orientation when needed.
        try:
            with Image.open(dest_path) as im:
                if im.size == (4928, 3264):
                    pass
                elif im.size == (3264, 4928):
                    try:
                        # Some files arrive with swapped dimensions but valid pixel data,
                        # so we rotate them instead of discarding them outright.
                        im2 = im.transpose(Image.ROTATE_90)
                        im2.save(dest_path)
                        print(f"Rotated and saved: {filename} -> {im2.size}")
                    except Exception as e:
                        print(f"Error rotating {filename}: {e}")
                        try:
                            os.remove(dest_path)
                        except Exception:
                            pass
                        continue
                else:
                    print(f"Warning: {filename} has size {im.size}, removed")
                    try:
                        os.remove(dest_path)
                    except Exception:
                        pass
                    continue
        except Exception as e:
            print(f"Error opening {filename}: {e}")
            try:
                os.remove(dest_path)
            except Exception:
                pass
            continue

        downloaded += 1

    print(f"Downloaded and validated: {downloaded} / {total}")


if __name__ == '__main__':
    main()
