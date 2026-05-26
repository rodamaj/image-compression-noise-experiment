PYTHON ?= python3
PIP ?= $(PYTHON) -m pip
RSCRIPT ?= Rscript

CSV ?= RAISE_1k.csv
IMAGE_DIR ?= images
DOWNLOAD_DIR ?= raise_tiffs_4928x3264
OUTPUT_DIR ?= experiment_outputs
CONTENT_BLOCKS ?= indoor outdoor
ALGORITHMS ?= PNG WEBP
NOISE_LEVELS ?= low high
IMAGE_NAME ?=
REPS_PER_BLOCK ?= 0
SEED ?= 26
LIMIT ?= 0
RUN1 ?=
RUN2 ?=
SINGLE_OUTPUT_DIR ?= experiment_single_image
TREATMENT_ALGORITHM ?= PNG
TREATMENT_NOISE_LEVEL ?= low
TREATMENT_OUTPUT_DIR ?= experiment_single_treatment
TREATMENT_ORDER_FILE ?=
PLAN_FILE ?=
PLAN_OUTPUT ?= experiment_plan.csv
SAVE_OUTPUTS ?= 0

.PHONY: help install plan download run full single treatment compare pipeline

help:
	@echo "Available targets:"
	@echo "  make install"
	@echo "  make plan [PLAN_OUTPUT=experiment_plan.csv] [TREATMENT_ORDER_FILE=treatment_order.csv] [REPS_PER_BLOCK=10] [SEED=26]"
	@echo "  make download [CSV=RAISE_1k.csv] [DOWNLOAD_DIR=raise_tiffs_4928x3264] [CONTENT_BLOCKS='indoor outdoor'] [REPS_PER_BLOCK=10] [SEED=26]"
	@echo "  make full [IMAGE_DIR=images] [OUTPUT_DIR=experiment_outputs] [CONTENT_BLOCKS='indoor outdoor'] [REPS_PER_BLOCK=10] [SEED=26]"
	@echo "  make single IMAGE_NAME=file.TIF [SINGLE_OUTPUT_DIR=experiment_single_image] [ALGORITHMS='PNG WEBP'] [NOISE_LEVELS='low high']"
	@echo "  make treatment [IMAGE_DIR=images] [TREATMENT_OUTPUT_DIR=experiment_single_treatment] [TREATMENT_ALGORITHM=PNG] [TREATMENT_NOISE_LEVEL=low] [REPS_PER_BLOCK=10] [IMAGE_NAME=file.TIF]"
	@echo "  make pipeline [PLAN_OUTPUT=experiment_plan.csv] [TREATMENT_ORDER_FILE=treatment_order.csv] [REPS_PER_BLOCK=10] [SEED=26]"
	@echo "  make run    # alias of make full"
	@echo "  make compare RUN1=experiment_outputs_run_1 RUN2=experiment_outputs_run_2"
	@echo "Optional flag:"
	@echo "  SAVE_OUTPUTS=1   Save compressed noisy outputs to disk"
	@echo "  TREATMENT_ORDER_FILE=treatment_order.csv   Follow the treatment order exported from R"
	@echo "  REPS_PER_BLOCK=10   Used only when no treatment-order CSV is provided"

install:
	$(PIP) install -r requirements.txt

plan:
	$(PYTHON) prepare_experiment_plan.py \
		--metadata-csv $(CSV) \
		--input-dir $(IMAGE_DIR) \
		--output-plan $(PLAN_OUTPUT) \
		--content-blocks $(CONTENT_BLOCKS) \
		--algorithms $(ALGORITHMS) \
		--noise-levels $(NOISE_LEVELS) \
		--reps-per-block $(REPS_PER_BLOCK) \
		--seed $(SEED) \
		$(if $(TREATMENT_ORDER_FILE),--treatment-order-file $(TREATMENT_ORDER_FILE),) \
		$(if $(IMAGE_NAME),--image-name $(IMAGE_NAME),)

download:
	$(PYTHON) download_raise_tiffs.py \
		--csv $(CSV) \
		--outdir $(DOWNLOAD_DIR) \
		--content-blocks $(CONTENT_BLOCKS) \
		--reps-per-block $(REPS_PER_BLOCK) \
		--seed $(SEED) \
		$(if $(PLAN_FILE),--plan-file $(PLAN_FILE),)

run: full

full:
	$(PYTHON) run_full_experiment.py \
		--mode full \
		--input-dir $(IMAGE_DIR) \
		--metadata-csv $(CSV) \
		--output-dir $(OUTPUT_DIR) \
		--content-blocks $(CONTENT_BLOCKS) \
		--algorithms $(ALGORITHMS) \
		--noise-levels $(NOISE_LEVELS) \
		--reps-per-block $(REPS_PER_BLOCK) \
		--seed $(SEED) \
		$(if $(TREATMENT_ORDER_FILE),--treatment-order-file $(TREATMENT_ORDER_FILE),) \
		$(if $(PLAN_FILE),--plan-file $(PLAN_FILE),) \
		$(if $(filter 1,$(SAVE_OUTPUTS)),--save-compressed-outputs,)

single:
	@if [ -z "$(IMAGE_NAME)" ]; then \
		echo "Usage: make single IMAGE_NAME=file.TIF [CONTENT_BLOCKS='indoor'] [ALGORITHMS='PNG WEBP'] [NOISE_LEVELS='low high']"; \
		exit 1; \
	fi
	$(PYTHON) run_full_experiment.py \
		--mode full \
		--input-dir $(IMAGE_DIR) \
		--metadata-csv $(CSV) \
		--output-dir $(SINGLE_OUTPUT_DIR) \
		--content-blocks $(CONTENT_BLOCKS) \
		--algorithms $(ALGORITHMS) \
		--noise-levels $(NOISE_LEVELS) \
		--reps-per-block 1 \
		--seed $(SEED) \
		$(if $(TREATMENT_ORDER_FILE),--treatment-order-file $(TREATMENT_ORDER_FILE),) \
		$(if $(PLAN_FILE),--plan-file $(PLAN_FILE),) \
		$(if $(filter 1,$(SAVE_OUTPUTS)),--save-compressed-outputs,) \
		--image-name $(IMAGE_NAME)

treatment:
	$(PYTHON) run_full_experiment.py \
		--mode single-treatment \
		--input-dir $(IMAGE_DIR) \
		--metadata-csv $(CSV) \
		--output-dir $(TREATMENT_OUTPUT_DIR) \
		--content-blocks $(CONTENT_BLOCKS) \
		--algorithms $(TREATMENT_ALGORITHM) \
		--noise-levels $(TREATMENT_NOISE_LEVEL) \
		--reps-per-block $(REPS_PER_BLOCK) \
		--seed $(SEED) \
		$(if $(TREATMENT_ORDER_FILE),--treatment-order-file $(TREATMENT_ORDER_FILE),) \
		$(if $(PLAN_FILE),--plan-file $(PLAN_FILE),) \
		$(if $(filter 1,$(SAVE_OUTPUTS)),--save-compressed-outputs,) \
		$(if $(IMAGE_NAME),--image-name $(IMAGE_NAME),)

pipeline: plan
	$(PYTHON) download_raise_tiffs.py --plan-file $(PLAN_OUTPUT) --outdir $(IMAGE_DIR)
	$(PYTHON) run_full_experiment.py \
		--mode full \
		--input-dir $(IMAGE_DIR) \
		--metadata-csv $(CSV) \
		--output-dir $(OUTPUT_DIR) \
		--plan-file $(PLAN_OUTPUT) \
		--seed $(SEED) \
		$(if $(filter 1,$(SAVE_OUTPUTS)),--save-compressed-outputs,)

compare:
	@if [ -z "$(RUN1)" ] || [ -z "$(RUN2)" ]; then \
		echo "Usage: make compare RUN1=experiment_outputs_run_1 RUN2=experiment_outputs_run_2"; \
		exit 1; \
	fi
	$(PYTHON) compare_experiment_runs.py $(RUN1) $(RUN2)
