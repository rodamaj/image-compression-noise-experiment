PYTHON ?= python3
PIP ?= $(PYTHON) -m pip
RSCRIPT ?= Rscript

CSV ?= RAISE_1k.csv
IMAGE_DIR ?= images
DOWNLOAD_DIR ?= raise_tiffs_4928x3264
OUTPUT_DIR ?= experiment_outputs
REPS_PER_BLOCK ?= 0
SEED ?= 26
TREATMENT_ORDER_FILE ?= treatment_order.csv
PLAN_FILE ?=
PLAN_OUTPUT ?= experiment_plan.csv
SAVE_OUTPUTS ?= 0

.PHONY: help install treatment-order plan download run full pipeline

help:
	@echo "Available targets:"
	@echo "  make install"
	@echo "  make treatment-order [TREATMENT_ORDER_FILE=treatment_order.csv] [REPS_PER_BLOCK=10] [SEED=26]"
	@echo "  make plan [PLAN_OUTPUT=experiment_plan.csv] [TREATMENT_ORDER_FILE=treatment_order.csv] [SEED=26]"
	@echo "  make download PLAN_FILE=experiment_plan.csv [DOWNLOAD_DIR=raise_tiffs_4928x3264]"
	@echo "  make full PLAN_FILE=experiment_plan.csv [IMAGE_DIR=images] [OUTPUT_DIR=experiment_outputs] [SEED=26]"
	@echo "  make pipeline [PLAN_OUTPUT=experiment_plan.csv] [TREATMENT_ORDER_FILE=treatment_order.csv] [REPS_PER_BLOCK=10] [SEED=26]"
	@echo "  make run    # alias of make full"
	@echo "Optional flag:"
	@echo "  SAVE_OUTPUTS=1   Save compressed noisy outputs to disk"
	@echo "  TREATMENT_ORDER_FILE=treatment_order.csv   CSV generated from R for treatment order"
	@echo "  REPS_PER_BLOCK=10   In treatment-order/pipeline: repetitions per treatment in R"

install:
	$(PIP) install -r requirements.txt

treatment-order:
	$(RSCRIPT) generate_treatment_order.R $(TREATMENT_ORDER_FILE) $(REPS_PER_BLOCK) $(SEED)

plan:
	$(PYTHON) build_experiment_plan.py \
		--metadata-csv $(CSV) \
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

run: full

full:
	@if [ -z "$(PLAN_FILE)" ]; then \
		echo "Usage: make full PLAN_FILE=experiment_plan.csv [IMAGE_DIR=images] [OUTPUT_DIR=experiment_outputs]"; \
		exit 1; \
	fi
	$(PYTHON) run_full_experiment.py \
		--input-dir $(IMAGE_DIR) \
		--output-dir $(OUTPUT_DIR) \
		--seed $(SEED) \
		--plan-file $(PLAN_FILE) \
		$(if $(filter 1,$(SAVE_OUTPUTS)),--save-compressed-outputs,)

pipeline: treatment-order plan
	$(MAKE) download PLAN_FILE=$(PLAN_OUTPUT) DOWNLOAD_DIR=$(IMAGE_DIR)
	$(MAKE) full PLAN_FILE=$(PLAN_OUTPUT) IMAGE_DIR=$(IMAGE_DIR) OUTPUT_DIR=$(OUTPUT_DIR) SEED=$(SEED) SAVE_OUTPUTS=$(SAVE_OUTPUTS)
