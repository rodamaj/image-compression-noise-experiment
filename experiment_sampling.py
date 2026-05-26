import random
from pathlib import Path
from urllib.parse import urlparse


def build_candidate_images(input_dir, metadata, selected_blocks, image_name=None):
    """Return eligible dataset entries as local-path candidates."""

    candidates = []
    normalized_image_name = image_name.strip().lower() if image_name else None

    for image_stem, record in sorted(metadata.items()):
        if record["content_block"] not in selected_blocks:
            continue

        if "4928 x 3264" not in record["image_size"]:
            continue

        if not record["tiff_url"]:
            continue

        if normalized_image_name and record["image_name"].lower() != normalized_image_name:
            continue

        filename = Path(urlparse(record["tiff_url"]).path).name or record["image_name"]
        image_path = Path(input_dir) / filename
        candidates.append(
            (
                image_path,
                {
                    **record,
                    "image_stem": image_stem,
                },
            )
        )

    return candidates


def select_images_by_block_requirements(experiment_images, required_counts, seed):
    """Select as many images from each block as the run plan requires."""

    selected_blocks = set(required_counts)
    selected_images = []
    grouped_images = {block: [] for block in selected_blocks}
    for image_path, record in experiment_images:
        grouped_images[record["content_block"]].append((image_path, record))

    rng = random.Random(seed)
    for block in sorted(selected_blocks):
        block_images = sorted(grouped_images.get(block, []), key=lambda item: item[0].name)
        required = required_counts.get(block, 0)
        if required > len(block_images):
            raise ValueError(
                f"Run plan requires {required} images from block '{block}', "
                f"but only {len(block_images)} eligible images are available."
            )

        block_images = rng.sample(block_images, required)
        block_images.sort(key=lambda item: item[0].name)

        for sample_index, (image_path, record) in enumerate(block_images, start=1):
            selected_images.append(
                (
                    image_path,
                    {
                        **record,
                        "block_sample_index": sample_index,
                    },
                )
            )

    return selected_images
