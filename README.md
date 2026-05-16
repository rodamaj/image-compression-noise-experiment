# Image Compression & Noise Experiment

Repository with scripts to experiment with image compression algorithms and additive noise.

## 🧰 Tech Stack
- Python 3.12.x
- NumPy
- Pillow
- OpenCV (opencv-python)
- scikit-image
- Matplotlib

---

## ⚙️ Environment Setup

It is recommended to use a virtual environment to manage dependencies.

### 1. Create a virtual environment

```bash
python3 -m venv venv
```

### 2. Activate the environment

- On macOS/Linux:
```bash
source venv/bin/activate
```

- On Windows:
```bash
venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. How to run

```bash
python compression_experiment.py <image_path> <algorithm> <noise_level>
```

Required positional arguments:

- `image_path`: Path to the input image file.
- `algorithm`: Compression algorithm. Use `PNG` or `WebP`.
- `noise_level`: Noise intensity. Use `low` or `high`.

Optional argument:

- `--output`: Path where the compressed file will be saved.
- `--seed`: Random seed used for reproducible noise generation. Defaults to `42`.

### Arguments

The script accepts the following command-line arguments:

- `image_path` (positional): Path to the original image file to process.
- `algorithm` (positional): Compression algorithm to use. Choose `PNG` or `WebP` (case-insensitive).
- `noise_level` (positional): Noise level to apply. Choose `low` or `high`.
- `--output` (optional): Path to save the resulting compressed image. If omitted, the compressed bytes are not saved to disk.
- `--seed` (optional): Integer seed for deterministic noise sampling and Gaussian noise generation. If omitted, the script uses `42`.

Examples:

```bash
# Run the experiment and print results
python compression_experiment.py input.TIF WebP low

# Run and save the compressed output
python compression_experiment.py input.TIF PNG high --output compressed.png

# Run with an explicit seed for a reproducible result
python compression_experiment.py input.TIF WebP low --seed 123
```

---

## Downloading RAISE TIFFs (recommended)

The easiest and most reproducible way to obtain the RAISE TIFF images for this experiment is to use the included script `download_raise_tiffs.py`. The script filters entries in `RAISE_1k.csv` by the `Image Size == 4928 x 3264` column, downloads the URLs from the `TIFF` column, validates the image resolution, and automatically rotates portrait images (3264×4928) so they become 4928×3264.

Minimal example (run from the project root):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python download_raise_tiffs.py --csv RAISE_1k.csv --outdir raise_tiffs_4928x3264
```

Quick test (download N images):

```bash
python download_raise_tiffs.py --csv RAISE_1k.csv --outdir raise_tiffs_test --limit 10
```

Notes:
- The script removes files whose resolution does not match 4928×3264 after validation.
- Images with size 3264×4928 are rotated 90° automatically.

Recommendation: use `download_raise_tiffs.py` to download and validate images because it automates filtering, checks resolution, and corrects orientation, avoiding corrupted or incorrectly sized files in your experiments.

If you need help or want to contribute, open an issue or submit a pull request.
