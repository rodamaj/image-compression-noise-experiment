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

### Optional: use the Makefile

The project includes a `Makefile` with the most common workflows:

```bash
make install
make plan
make download
make full
make single
make treatment
make pipeline
make compare RUN1=experiment_outputs_run_1 RUN2=experiment_outputs_run_2
```

Useful overrides:
- `make plan PLAN_OUTPUT=experiment_plan.csv TREATMENT_ORDER_FILE=treatment_order.csv`
- `make download PLAN_FILE=experiment_plan.csv DOWNLOAD_DIR=raise_tiffs_4928x3264`
- `make full PLAN_FILE=experiment_plan.csv IMAGE_DIR=images OUTPUT_DIR=experiment_outputs`
- `make full CONTENT_BLOCKS="indoor outdoor" ALGORITHMS="PNG WEBP" NOISE_LEVELS="low high"`
- `make full SAVE_OUTPUTS=1`
- `make single IMAGE_NAME=r001d260dt.TIF`
- `make single IMAGE_NAME=r001d260dt.TIF SAVE_OUTPUTS=1`
- `make single IMAGE_NAME=r001d260dt.TIF CONTENT_BLOCKS="outdoor" ALGORITHMS="PNG WEBP" NOISE_LEVELS="low high"`
- `make treatment TREATMENT_ALGORITHM=PNG TREATMENT_NOISE_LEVEL=low REPS_PER_BLOCK=10`
- `make pipeline PLAN_OUTPUT=experiment_plan.csv TREATMENT_ORDER_FILE=treatment_order.csv`

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
- `--seed`: Random seed used for reproducible noise generation. Defaults to `26`.

### Arguments

The script accepts the following command-line arguments:

- `image_path` (positional): Path to the original image file to process.
- `algorithm` (positional): Compression algorithm to use. Choose `PNG` or `WebP` (case-insensitive).
- `noise_level` (positional): Noise level to apply. Choose `low` or `high`.
- `--output` (optional): Path to save the resulting compressed image. If omitted, the compressed bytes are not saved to disk.
- `--seed` (optional): Integer seed for deterministic noise sampling and Gaussian noise generation. If omitted, the script uses `26`.

The script prints JSON output with explicit units. Compressed sizes include raw `bytes` plus derived `kB` and `MB` values, and noise/response values include `%`.

Examples:

```bash
# Run the experiment and print results
python compression_experiment.py input.TIF WebP low

# Run and save the compressed output
python compression_experiment.py input.TIF PNG high --output compressed.png

# Run with an explicit seed for a reproducible result
python compression_experiment.py input.TIF WebP low --seed 123
```

### Experiment runner

To run either the complete experiment, one image with selected factors, or a single treatment, use `run_full_experiment.py`.

Full experiment example:

```bash
python run_full_experiment.py \
  --mode full \
  --input-dir images \
  --metadata-csv RAISE_1k.csv \
  --output-dir experiment_outputs \
  --plan-file experiment_plan.csv \
  --save-compressed-outputs \
  --seed 26
```

Single-image example:

```bash
python run_full_experiment.py \
  --mode full \
  --input-dir images \
  --metadata-csv RAISE_1k.csv \
  --output-dir experiment_single_image \
  --content-blocks outdoor \
  --algorithms PNG WEBP \
  --noise-levels low high \
  --image-name r001d260dt.TIF
```

Single-treatment example:

```bash
python run_full_experiment.py \
  --mode single-treatment \
  --input-dir images \
  --metadata-csv RAISE_1k.csv \
  --output-dir experiment_single_treatment \
  --content-blocks outdoor \
  --algorithms PNG \
  --noise-levels low \
  --reps-per-block 10
```

This script:
- Can execute a precomputed `experiment_plan.csv` exactly as written.
- Otherwise, it looks up each image in `RAISE_1k.csv` and assigns its block from the `Keywords` column.
- Uses `indoor` or `outdoor` as the experimental block.
- Only processes images with the fixed experiment resolution `4928 x 3264`.
- Selects distinct images within each block reproducibly using the fixed `--seed`.
- Downloads missing sampled images into `--input-dir` automatically before execution.
- In `full` mode, runs every combination of selected image, algorithm, and noise level.
- If you pass `--image-name`, the run is restricted to that single image.
- In `single-treatment` mode, requires exactly one algorithm and one noise level.
- If you pass `--plan-file`, Python follows that exact precomputed plan.
- Writes a `results.csv` dataset with the measured response, `run_order`, and compressed sizes in `kb` only.
- Writes a `summary.json` file with the run configuration.
- Writes a `manifest.json` file with the run parameters, software versions, and SHA-256 hashes of the input images.
- Optionally saves compressed noisy outputs for inspection, using the original image name plus a deterministic suffix.

For reproducibility:
- `requirements.txt` pins dependency versions.
- `manifest.json` records the Python/platform versions plus the exact input files used.
- The image selection and noise generation are deterministic for a given `--seed`.

To verify that two runs are identical, compare their output folders with:

```bash
python compare_experiment_runs.py experiment_outputs_run_1 experiment_outputs_run_2
```

The comparison checks:
- experiment configuration
- software environment recorded in `manifest.json`
- SHA-256 hashes of input images
- row-by-row equality of `results.csv`

### Treatment order from R

If your professor wants R to define the run plan, the cleanest exchange format is a CSV file like this:

```csv
run_order,algorithm,noise_level,content_block
1,PNG,low,indoor
2,WebP,low,indoor
3,PNG,high,indoor
4,WebP,high,indoor
5,PNG,low,outdoor
6,WebP,low,outdoor
7,PNG,high,outdoor
8,WebP,high,outdoor
```

Recommended R export:

```r
source("generate_treatment_order.R")
```

Or run it directly from the command line:

```bash
Rscript generate_treatment_order.R treatment_order.csv 10 26
```

Arguments:
- first: output CSV path
- second: replicates per treatment (`each` in the original R idea)
- third: random seed

Then prepare the full experiment plan:

```bash
python prepare_experiment_plan.py \
  --metadata-csv RAISE_1k.csv \
  --input-dir images \
  --output-plan experiment_plan.csv \
  --content-blocks indoor outdoor \
  --algorithms PNG WEBP \
  --noise-levels low high \
  --reps-per-block 10 \
  --seed 26 \
  --treatment-order-file treatment_order.csv
```

Or with `make`:

```bash
make plan PLAN_OUTPUT=experiment_plan.csv TREATMENT_ORDER_FILE=treatment_order.csv
```

Behavior:
- R defines the treatment sequence row by row.
- `prepare_experiment_plan.py` infers how many images each block needs from `treatment_order.csv` and selects them once.
- `download_raise_tiffs.py` can prefetch only the files listed in that plan.
- `run_full_experiment.py` executes exactly the runs listed in that plan.

One-command pipeline:

```bash
make pipeline PLAN_OUTPUT=experiment_plan.csv TREATMENT_ORDER_FILE=treatment_order.csv
```

---

## Downloading RAISE TIFFs (optional prefetch)

`run_full_experiment.py` can now download missing sampled images automatically. The separate script `download_raise_tiffs.py` is still useful if you want to prefetch the image cache from a fixed `experiment_plan.csv` ahead of time. It downloads only the missing files listed in the plan and validates that each downloaded image matches the required size.

Minimal example (run from the project root):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python download_raise_tiffs.py --plan-file experiment_plan.csv --outdir raise_tiffs_4928x3264
```

Quick test:

```bash
python download_raise_tiffs.py --plan-file experiment_plan.csv --outdir raise_tiffs_test
```

Notes:
- The main workflow is now: plan -> optional prefetch -> run.
- The script can read `experiment_plan.csv` and download only the listed images.
- Images with size `3264 x 4928` are rotated automatically to `4928 x 3264`.
- The script skips files that are already present and match the required size.
- The script removes files that fail validation or do not match the required size after download.

Recommendation: use `download_raise_tiffs.py` when you want to warm the local cache from a fixed plan before running the experiment.

If you need help or want to contribute, open an issue or submit a pull request.
