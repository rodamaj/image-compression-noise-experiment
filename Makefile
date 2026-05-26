PYTHON ?= python3
PIP ?= $(PYTHON) -m pip
RSCRIPT ?= Rscript

empty :=
space := $(empty) $(empty)
comma := ,

METADATA_FILE ?= RAISE_1k.csv
IMAGE_DIR ?= images
DOWNLOAD_DIR ?= $(IMAGE_DIR)
OUTPUT_DIR ?= results
ALGORITHMS ?= PNG WEBP
NOISE_LEVELS ?= low high
CONTENT_BLOCKS ?= indoor outdoor
REPS_PER_BLOCK ?= 1
SEED ?= 26
TREATMENT_ORDER_FILE ?= treatment_order.csv
PLAN_FILE ?=
PLAN_OUTPUT ?= experiment_plan.csv
SAVE_OUTPUTS ?= 0

.PHONY: help install treatmentorder plan download run experiment pipeline

help:
	@echo "Available targets:"
	@echo "  make install"
	@echo "  make treatmentorder [TREATMENT_ORDER_FILE=treatment_order.csv] [ALGORITHMS='PNG WEBP'] [NOISE_LEVELS='low high'] [CONTENT_BLOCKS='indoor outdoor'] [REPS_PER_BLOCK=1] [SEED=26]"
	@echo "  make plan [METADATA_FILE=RAISE_1k.csv] [IMAGE_DIR=images] [PLAN_OUTPUT=experiment_plan.csv] [TREATMENT_ORDER_FILE=treatment_order.csv] [SEED=26]"
	@echo "  make download PLAN_FILE=experiment_plan.csv [DOWNLOAD_DIR=images]"
	@echo "  make experiment PLAN_FILE=experiment_plan.csv [IMAGE_DIR=images] [OUTPUT_DIR=results] [SEED=26] [SAVE_OUTPUTS=1]"
	@echo "  make pipeline [METADATA_FILE=RAISE_1k.csv] [OUTPUT_DIR=results] [IMAGE_DIR=images] [DOWNLOAD_DIR=images] [PLAN_OUTPUT=experiment_plan.csv] [TREATMENT_ORDER_FILE=treatment_order.csv] [ALGORITHMS='PNG WEBP'] [NOISE_LEVELS='low high'] [CONTENT_BLOCKS='indoor outdoor'] [REPS_PER_BLOCK=1] [SEED=26] [SAVE_OUTPUTS=1]"
	@echo "  make run    # alias of make experiment"
	@echo "Optional flag:"
	@echo "  SAVE_OUTPUTS=1   Save compressed noisy outputs to disk"
	@echo "  TREATMENT_ORDER_FILE=treatment_order.csv   CSV generated from R for treatment order"
	@echo "  REPS_PER_BLOCK=1   Repetitions per treatment in the randomized treatment order"

install:
	$(PIP) install -r requirements.txt

treatmentorder:
	$(RSCRIPT) generate_treatment_order.R \
		$(TREATMENT_ORDER_FILE) \
		$(REPS_PER_BLOCK) \
		$(SEED) \
		$(subst $(space),$(comma),$(ALGORITHMS)) \
		$(subst $(space),$(comma),$(NOISE_LEVELS)) \
		$(subst $(space),$(comma),$(CONTENT_BLOCKS))

plan:
	$(PYTHON) build_experiment_plan.py \
		--metadata-csv $(METADATA_FILE) \
		--input-dir $(IMAGE_DIR) \
		--output-plan $(PLAN_OUTPUT) \
		--seed $(SEED) \
		--treatment-order-file $(TREATMENT_ORDER_FILE)

download:
	@if [ -z "$(PLAN_FILE)" ]; then \
		echo "Usage: make download PLAN_FILE=experiment_plan.csv [DOWNLOAD_DIR=images]"; \
		exit 1; \
	fi
	$(PYTHON) download_raise_tiffs.py \
		--outdir $(DOWNLOAD_DIR) \
		--plan-file $(PLAN_FILE)

run: experiment

experiment:
	@if [ -z "$(PLAN_FILE)" ]; then \
		echo "Usage: make experiment PLAN_FILE=experiment_plan.csv [IMAGE_DIR=images] [OUTPUT_DIR=results]"; \
		exit 1; \
	fi
	$(PYTHON) run_full_experiment.py \
		--input-dir $(IMAGE_DIR) \
		--output-dir $(OUTPUT_DIR) \
		--seed $(SEED) \
		--plan-file $(PLAN_FILE) \
		$(if $(filter 1,$(SAVE_OUTPUTS)),--save-compressed-outputs,)

pipeline:
	$(MAKE) treatmentorder \
		TREATMENT_ORDER_FILE=$(TREATMENT_ORDER_FILE) \
		ALGORITHMS="$(ALGORITHMS)" \
		NOISE_LEVELS="$(NOISE_LEVELS)" \
		CONTENT_BLOCKS="$(CONTENT_BLOCKS)" \
		REPS_PER_BLOCK=$(REPS_PER_BLOCK) \
		SEED=$(SEED)
	$(MAKE) plan \
		METADATA_FILE=$(METADATA_FILE) \
		IMAGE_DIR=$(IMAGE_DIR) \
		PLAN_OUTPUT=$(PLAN_OUTPUT) \
		TREATMENT_ORDER_FILE=$(TREATMENT_ORDER_FILE) \
		SEED=$(SEED)
	$(MAKE) download \
		PLAN_FILE=$(PLAN_OUTPUT) \
		DOWNLOAD_DIR=$(DOWNLOAD_DIR)
	$(MAKE) experiment \
		PLAN_FILE=$(PLAN_OUTPUT) \
		IMAGE_DIR=$(IMAGE_DIR) \
		OUTPUT_DIR=$(OUTPUT_DIR) \
		SEED=$(SEED) \
		SAVE_OUTPUTS=$(SAVE_OUTPUTS)
