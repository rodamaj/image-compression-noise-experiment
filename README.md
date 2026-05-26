# Image Compression & Noise Experiment

This project generates a reproducible dataset for a compression experiment over RAISE TIFF images.

The experimental design used by the pipeline is:
- fixed image resolution: `4928 x 3264`
- blocks: `indoor` and `outdoor`
- treatments: algorithm (`PNG`, `WebP`) x noise level (`low`, `high`)
- experimental units: different images
- randomized treatment order generated through the pipeline

## Setup

This project requires both Python and R, because the randomized treatment order is
generated with `Rscript`.

Install R first, make sure `Rscript` is available in your shell, then create and
activate a Python virtual environment and install dependencies:

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
make pipeline
```

Useful overrides:
- `OUTPUT_DIR=results`
- `IMAGE_DIR=images`
- `DOWNLOAD_DIR=images`
- `SAVE_OUTPUTS=1`
- `PLAN_OUTPUT=experiment_plan.csv`
- `TREATMENT_ORDER_FILE=treatment_order.csv`
- `ALGORITHMS="PNG WEBP"`
- `NOISE_LEVELS="low high"`
- `CONTENT_BLOCKS="indoor outdoor"`
- `REPS_PER_BLOCK=1`
- `SEED=26`

Those parameters remain available for `make pipeline`; they are just optional because the project already provides defaults.

Example:

```bash
make pipeline \
  OUTPUT_DIR=results \
  IMAGE_DIR=images \
  SAVE_OUTPUTS=1
```

Here `REPS_PER_BLOCK` means how many times each treatment is repeated in the randomized treatment order.

The simplified rule of the project is:
- `make treatmentorder` generates the treatment-order file
- `make plan` uses that file to build the experiment plan
- `make download` uses the generated plan to fetch only the required images
- `make experiment` uses the generated plan to run the experiment
- `make pipeline` runs those steps for you automatically
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

If `SAVE_OUTPUTS=1` is enabled, compressed outputs are also saved inside
`compressed_outputs/` using the original image name plus a deterministic suffix.

## Other Flows

These commands are useful when you want to run the pipeline step by step instead of using `make pipeline`.

### Generate only the randomized treatment order

```bash
make treatmentorder \
  TREATMENT_ORDER_FILE=treatment_order.csv \
  ALGORITHMS="PNG WEBP" \
  NOISE_LEVELS="low high" \
  CONTENT_BLOCKS="indoor outdoor" \
  REPS_PER_BLOCK=1 \
  SEED=26
```

This creates `treatment_order.csv`.

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
make experiment PLAN_FILE=experiment_plan.csv IMAGE_DIR=images OUTPUT_DIR=results
```

This uses the exact run order and image assignments already frozen in `experiment_plan.csv`.

## Available Make Targets

```bash
make install
make treatmentorder
make plan
make download
make experiment
make pipeline
```
