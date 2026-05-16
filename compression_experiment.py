import argparse
import json
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image


DEFAULT_RANDOM_SEED = 26


def get_noise_percentage(noise_level, rng):
    """Sample a noise percentage from the configured range for a noise tier."""

    if noise_level == "low":
        return rng.uniform(1, 5)

    if noise_level == "high":
        return rng.uniform(45, 50)

    raise ValueError("Noise level must be 'low' or 'high'.")


def apply_gaussian_noise(image, noise_percentage, rng):
    """Return a copy of the image with additive Gaussian noise applied in RGB space."""

    rgb_image = image.convert("RGB")
    pixels = np.asarray(rgb_image, dtype=np.float32)

    # The percentage is expressed relative to the full 8-bit channel range, so
    # we convert it into a standard deviation on the 0-255 intensity scale.
    sigma = (noise_percentage / 100) * 255
    noise = rng.normal(loc=0, scale=sigma, size=pixels.shape)

    # Clipping keeps noisy values within valid image bounds before converting
    # back to uint8 for Pillow.
    noisy_pixels = np.clip(pixels + noise, 0, 255).astype(np.uint8)
    return Image.fromarray(noisy_pixels, mode="RGB")


def compress_image(image, algorithm):
    """Compress an image to the requested lossless format and return the bytes."""

    buffer = BytesIO()
    algorithm = algorithm.upper()

    if algorithm == "PNG":
        image.save(buffer, format="PNG", optimize=True)
    elif algorithm == "WEBP":
        image.save(buffer, format="WEBP", lossless=True, method=6)
    else:
        raise ValueError("Algorithm must be 'PNG' or 'WebP'.")

    return buffer.getvalue()


def run_experiment(image_path, algorithm, noise_level, output=None, seed=DEFAULT_RANDOM_SEED):
    """Run the noise and compression experiment and return the measured results."""

    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(f"Image does not exist: {path}")

    rng = np.random.default_rng(seed)
    noise_percentage = get_noise_percentage(noise_level, rng)

    with Image.open(path) as original_image:
        baseline_compressed_image = compress_image(original_image, algorithm)
        noisy_image = apply_gaussian_noise(original_image, noise_percentage, rng)
        noisy_compressed_image = compress_image(noisy_image, algorithm)

    baseline_compressed_size = len(baseline_compressed_image)
    if baseline_compressed_size == 0:
        raise ValueError("The compressed original image has a size of 0 bytes.")

    noisy_compressed_size = len(noisy_compressed_image)
    # Response is the percentage change in compressed size relative to the
    # clean image compressed with the same algorithm.
    response = (
        (noisy_compressed_size - baseline_compressed_size) / baseline_compressed_size
    ) * 100

    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(noisy_compressed_image)

    return {
        "baseline_compressed_size": baseline_compressed_size,
        "noisy_compressed_size": noisy_compressed_size,
        "response": response,
        "algorithm": "WebP" if algorithm.upper() == "WEBP" else "PNG",
        "noise_level": noise_level,
        "noise_percentage": noise_percentage,
        "seed": seed,
    }


def main():
    """Parse CLI arguments, run the experiment, and print the JSON result."""
    parser = argparse.ArgumentParser(
        description="Applies Gaussian noise, compresses an image, and calculates the response variable."
    )
    parser.add_argument("image_path", help="Path to the original image.")
    parser.add_argument("algorithm", choices=["PNG", "png", "WebP", "webp", "WEBP"])
    parser.add_argument("noise_level", choices=["low", "high"])
    parser.add_argument(
        "--output",
        help="Optional path to save the resulting compressed image.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_RANDOM_SEED,
        help=f"Random seed for reproducible noise generation (default: {DEFAULT_RANDOM_SEED}).",
    )

    args = parser.parse_args()

    try:
        result = run_experiment(
            args.image_path,
            args.algorithm,
            args.noise_level,
            output=args.output,
            seed=args.seed,
        )
    except (FileNotFoundError, ValueError) as error:
        parser.error(str(error))

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
