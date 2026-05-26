import argparse
import csv
import json
from pathlib import Path


def load_json(path):
    """Load a JSON file from disk."""

    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_csv_rows(path):
    """Load CSV rows as dictionaries preserving file order."""

    with Path(path).open(newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def normalize_results_rows(rows):
    """Drop output-path columns so optional artifact directories do not affect equality."""

    normalized = []
    for row in rows:
        normalized_row = dict(row)
        normalized_row.pop("compressed_output_path", None)
        normalized.append(normalized_row)
    return normalized


def normalize_configuration(config):
    """Drop run-specific output paths that should not affect reproducibility checks."""

    normalized = dict(config)
    normalized.pop("output_dir", None)
    normalized.pop("results_file", None)
    return normalized


def compare_values(label, left, right, differences):
    """Append a difference entry when two values are not equal."""

    if left != right:
        differences.append(
            {
                "section": label,
                "left": left,
                "right": right,
            }
        )


def compare_image_manifests(left_images, right_images, differences):
    """Compare image manifests by image name and hash."""

    left_by_name = {entry["image_name"]: entry for entry in left_images}
    right_by_name = {entry["image_name"]: entry for entry in right_images}

    compare_values(
        "manifest.images.image_names",
        sorted(left_by_name),
        sorted(right_by_name),
        differences,
    )

    shared_names = sorted(set(left_by_name) & set(right_by_name))
    for image_name in shared_names:
        compare_values(
            f"manifest.images.{image_name}",
            left_by_name[image_name],
            right_by_name[image_name],
            differences,
        )


def compare_results_rows(left_rows, right_rows, differences):
    """Compare two results tables row by row."""

    compare_values("results.row_count", len(left_rows), len(right_rows), differences)
    for index, (left_row, right_row) in enumerate(zip(left_rows, right_rows), start=1):
        if left_row != right_row:
            differences.append(
                {
                    "section": f"results.row_{index}",
                    "left": left_row,
                    "right": right_row,
                }
            )


def build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Compare two experiment output directories and report whether they are "
            "reproducibly identical."
        )
    )
    parser.add_argument("left_run", help="First experiment output directory.")
    parser.add_argument("right_run", help="Second experiment output directory.")
    parser.add_argument(
        "--results-file",
        default="results.csv",
        help="Results CSV filename inside each output directory (default: results.csv).",
    )
    parser.add_argument(
        "--manifest-file",
        default="manifest.json",
        help="Manifest JSON filename inside each output directory (default: manifest.json).",
    )
    parser.add_argument(
        "--summary-file",
        default="summary.json",
        help="Summary JSON filename inside each output directory (default: summary.json).",
    )
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    left_dir = Path(args.left_run)
    right_dir = Path(args.right_run)

    for directory in (left_dir, right_dir):
        if not directory.is_dir():
            parser.error(f"Output directory does not exist: {directory}")

    left_manifest = load_json(left_dir / args.manifest_file)
    right_manifest = load_json(right_dir / args.manifest_file)
    left_summary = load_json(left_dir / args.summary_file)
    right_summary = load_json(right_dir / args.summary_file)
    left_results = normalize_results_rows(load_csv_rows(left_dir / args.results_file))
    right_results = normalize_results_rows(load_csv_rows(right_dir / args.results_file))

    differences = []

    compare_values(
        "manifest.experiment_configuration",
        normalize_configuration(left_manifest.get("experiment_configuration", {})),
        normalize_configuration(right_manifest.get("experiment_configuration", {})),
        differences,
    )
    compare_values(
        "manifest.environment",
        left_manifest.get("environment"),
        right_manifest.get("environment"),
        differences,
    )
    compare_values(
        "summary.configuration",
        normalize_configuration(left_summary),
        normalize_configuration(right_summary),
        differences,
    )
    compare_image_manifests(
        left_manifest.get("images", []),
        right_manifest.get("images", []),
        differences,
    )
    compare_results_rows(left_results, right_results, differences)

    if differences:
        print("Runs differ.")
        print(json.dumps(differences[:20], indent=2))
        if len(differences) > 20:
            print(f"... and {len(differences) - 20} more differences.")
        raise SystemExit(1)

    print("Runs are identical: configuration, environment, inputs, and results match.")


if __name__ == "__main__":
    main()
