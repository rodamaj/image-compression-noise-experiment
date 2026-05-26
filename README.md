# Image Compression & Noise Experiment

This project generates a reproducible dataset for a compression experiment over RAISE TIFF images.

The experimental design used by the pipeline is:
- fixed image resolution: `4928 x 3264`
- blocks: `indoor` and `outdoor`
- treatments: algorithm (`PNG`, `WebP`) x noise level (`low`, `high`)
- experimental units: different images
- randomized treatment order generated through the pipeline

## Setup

Create and activate a virtual environment, then install dependencies:

```bash
python3 -m venv venv
source venv/bin/activate
make install
```

## Main Workflow

The main workflow is `make pipeline`. It does the full sequence:

1. generates `treatment_order.csv`
2. builds `experiment_plan.csv`
3. downloads only the required images, reusing valid cached files
4. runs the experiment
5. writes the dataset and reproducibility artifacts

### Recommended Run

```bash
make pipeline \
  TREATMENT_ORDER_FILE=treatment_order.csv \
  PLAN_OUTPUT=experiment_plan.csv \
  REPS_PER_BLOCK=10 \
  SEED=26
```

Useful overrides:
- `OUTPUT_DIR=experiment_outputs`
- `DOWNLOAD_DIR=images`
- `SAVE_OUTPUTS=1`

Example:

```bash
make pipeline \
  TREATMENT_ORDER_FILE=treatment_order.csv \
  PLAN_OUTPUT=experiment_plan.csv \
  REPS_PER_BLOCK=10 \
  SEED=26 \
  DOWNLOAD_DIR=images \
  OUTPUT_DIR=experiment_outputs \
  SAVE_OUTPUTS=1
```

Here `REPS_PER_BLOCK` means how many times each treatment is repeated in the randomized treatment order.

The simplified rule of the project is:
- a treatment-order file is always required
- `make pipeline` generates it for you
- `make plan` expects that file to exist
- `make download` expects the generated plan
- `make full` expects the generated plan
- if you want a single run, use a `treatment_order.csv` with a single row

## Outputs

The main run produces:
- `results.csv`

`results.csv` is the final dataset for later statistical analysis. It contains:
- `run_order`
- `image_name`
- `content_block`
- `block_sample_index`
- `keywords`
- `algorithm`
- `noise_level`
- `seed`
- `noise_percentage`
- `baseline_compressed_size_kb`
- `noisy_compressed_size_kb`
- `response_percent`

If `SAVE_OUTPUTS=1` is enabled, compressed outputs are also saved using the original image name plus a deterministic suffix.

## Other Flows

These commands are useful when you want to run the pipeline step by step instead of using `make pipeline`.

### Generate only the randomized treatment order

```bash
make treatment-order TREATMENT_ORDER_FILE=treatment_order.csv REPS_PER_BLOCK=10 SEED=26
```

### Generate only the plan

```bash
make plan PLAN_OUTPUT=experiment_plan.csv TREATMENT_ORDER_FILE=treatment_order.csv
```

This creates `experiment_plan.csv`.

### Download only the required images

```bash
make download PLAN_FILE=experiment_plan.csv DOWNLOAD_DIR=images
```

This downloads only the images listed in the plan. Existing valid files are reused. Portrait files with size `3264 x 4928` are rotated automatically.

### Run the experiment from an existing plan

```bash
make full PLAN_FILE=experiment_plan.csv IMAGE_DIR=images OUTPUT_DIR=experiment_outputs
```

This uses the exact run order and image assignments already frozen in `experiment_plan.csv`.

## Available Make Targets

```bash
make install
make treatment-order
make plan
make download
make full
make pipeline
```
