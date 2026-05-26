import csv
from pathlib import Path

from experiment_metadata import (
    build_treatment_label,
    normalize_algorithm,
    normalize_content_block,
    normalize_noise_level,
)


TREATMENT_ORDER_REQUIRED_COLUMNS = {"algorithm", "noise_level", "content_block"}
EXPERIMENT_PLAN_REQUIRED_COLUMNS = {
    "run_order",
    "image_name",
    "image_filename",
    "tiff_url",
    "content_block",
    "block_sample_index",
    "keywords",
    "treatment_label",
    "algorithm",
    "noise_level",
}


def load_treatment_order(order_file):
    """Load a treatment-order CSV exported from R."""

    rows = []
    with Path(order_file).open(newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        missing_columns = TREATMENT_ORDER_REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            raise ValueError(
                "Treatment order CSV is missing required columns: "
                f"{missing}"
            )

        for row_index, row in enumerate(reader, start=2):
            try:
                algorithm = normalize_algorithm(row.get("algorithm"))
                noise_level = normalize_noise_level(row.get("noise_level"))
                content_block = normalize_content_block(row.get("content_block"))
            except ValueError as error:
                raise ValueError(
                    f"Invalid treatment order row {row_index}: {error}"
                ) from error

            run_order_raw = (row.get("run_order") or "").strip()
            run_order = None
            if run_order_raw:
                try:
                    run_order = int(run_order_raw)
                except ValueError as error:
                    raise ValueError(
                        f"Invalid run_order in treatment order row {row_index}: "
                        f"{run_order_raw!r}"
                    ) from error

            rows.append(
                {
                    "run_order": run_order,
                    "label": build_treatment_label(
                        algorithm, noise_level, content_block
                    ),
                    "algorithm": algorithm,
                    "noise_level": noise_level,
                    "content_block": content_block,
                }
            )

    if not rows:
        raise ValueError("Treatment order CSV is empty.")

    if any(row["run_order"] is not None for row in rows):
        if not all(row["run_order"] is not None for row in rows):
            raise ValueError(
                "Treatment order CSV must either define run_order for every row or for none."
            )
        rows.sort(key=lambda row: row["run_order"])

    return rows


def count_required_images_by_block(treatment_order):
    """Return how many distinct images are needed in each block."""

    required_counts = {}
    for treatment in treatment_order:
        block = treatment["content_block"]
        required_counts[block] = required_counts.get(block, 0) + 1
    return required_counts


def load_experiment_plan(plan_file, input_dir):
    """Load a fully specified experiment plan exported before download/run."""

    run_plan = []
    with Path(plan_file).open(newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        missing_columns = EXPERIMENT_PLAN_REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            raise ValueError(f"Experiment plan CSV is missing required columns: {missing}")

        for row_index, row in enumerate(reader, start=2):
            try:
                run_order = int((row.get("run_order") or "").strip())
                block_sample_index = int((row.get("block_sample_index") or "").strip())
                algorithm = normalize_algorithm(row.get("algorithm"))
                noise_level = normalize_noise_level(row.get("noise_level"))
                content_block = normalize_content_block(row.get("content_block"))
            except ValueError as error:
                raise ValueError(f"Invalid experiment plan row {row_index}: {error}") from error

            image_name = (row.get("image_name") or "").strip()
            image_filename = (row.get("image_filename") or "").strip()
            tiff_url = (row.get("tiff_url") or "").strip()
            keywords = (row.get("keywords") or "").strip()
            treatment_label = (row.get("treatment_label") or "").strip()

            if not image_name or not image_filename or not tiff_url or not treatment_label:
                raise ValueError(
                    f"Invalid experiment plan row {row_index}: missing image_name, "
                    "image_filename, tiff_url, or treatment_label."
                )

            expected_label = build_treatment_label(algorithm, noise_level, content_block)
            if treatment_label != expected_label:
                raise ValueError(
                    f"Invalid experiment plan row {row_index}: treatment_label "
                    f"{treatment_label!r} does not match the row values "
                    f"({expected_label!r})."
                )

            run_plan.append(
                {
                    "run_order": run_order,
                    "image_path": Path(input_dir) / image_filename,
                    "record": {
                        "image_name": image_name,
                        "tiff_url": tiff_url,
                        "content_block": content_block,
                        "block_sample_index": block_sample_index,
                        "keywords": keywords,
                    },
                    "algorithm": algorithm,
                    "noise_level": noise_level,
                    "treatment_label": treatment_label,
                }
            )

    if not run_plan:
        raise ValueError("Experiment plan CSV is empty.")

    run_plan.sort(key=lambda item: item["run_order"])
    return run_plan


def build_run_plan(experiment_images, algorithms, noise_levels, treatment_order=None):
    """Create the exact ordered list of runs to execute."""

    images_by_block = {}
    for image_path, record in experiment_images:
        images_by_block.setdefault(record["content_block"], []).append((image_path, record))

    for block_images in images_by_block.values():
        block_images.sort(key=lambda item: item[1]["block_sample_index"])

    runs = []
    if treatment_order:
        for treatment in treatment_order:
            for image_path, record in images_by_block.get(treatment["content_block"], []):
                runs.append(
                    {
                        "image_path": image_path,
                        "record": record,
                        "algorithm": treatment["algorithm"],
                        "noise_level": treatment["noise_level"],
                        "treatment_label": treatment["label"],
                    }
                )
        return runs

    for image_path, record in experiment_images:
        for algorithm in algorithms:
            for noise_level in noise_levels:
                runs.append(
                    {
                        "image_path": image_path,
                        "record": record,
                        "algorithm": algorithm,
                        "noise_level": noise_level,
                        "treatment_label": build_treatment_label(
                            algorithm, noise_level, record["content_block"]
                        ),
                    }
                )

    return runs


def build_run_plan_from_csv(experiment_images, treatment_order):
    """Create the exact ordered list of runs defined row by row in the CSV plan."""

    images_by_block = {}
    for image_path, record in experiment_images:
        images_by_block.setdefault(record["content_block"], []).append((image_path, record))

    for block_images in images_by_block.values():
        block_images.sort(key=lambda item: item[1]["block_sample_index"])

    block_offsets = {block: 0 for block in images_by_block}
    runs = []

    for row_index, treatment in enumerate(treatment_order, start=1):
        block = treatment["content_block"]
        candidates = images_by_block.get(block, [])
        offset = block_offsets.get(block, 0)
        if offset >= len(candidates):
            raise ValueError(
                f"Run-plan row {row_index} requires another image from block "
                f"{block!r}, but no eligible sampled images remain. Increase "
                "--reps-per-block or reduce the number of CSV rows for that block."
            )
        image_path, record = candidates[offset]
        block_offsets[block] = offset + 1

        runs.append(
            {
                "image_path": image_path,
                "record": record,
                "algorithm": treatment["algorithm"],
                "noise_level": treatment["noise_level"],
                "treatment_label": treatment["label"],
            }
        )

    return runs


def unique_experiment_images_from_run_plan(run_plan):
    """Extract the unique images actually used by the ordered run plan."""

    seen = set()
    unique_images = []
    for planned_run in run_plan:
        image_path = planned_run["image_path"]
        record = planned_run["record"]
        key = str(image_path.resolve()).lower()
        if key in seen:
            continue
        seen.add(key)
        unique_images.append((image_path, record))
    return unique_images
