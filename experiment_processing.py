from io import BytesIO

import numpy as np
from PIL import Image


DEFAULT_RANDOM_SEED = 26


def bytes_to_kb(num_bytes):
    """Convert a byte count to kilobytes using base-10 units."""

    return num_bytes / 1000


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


def run_condition(image, algorithm, noise_level, seed):
    """Run one experimental treatment on an in-memory image."""

    rng = np.random.default_rng(seed)
    noise_percentage = get_noise_percentage(noise_level, rng)

    baseline_compressed_image = compress_image(image, algorithm)
    noisy_image = apply_gaussian_noise(image, noise_percentage, rng)
    noisy_compressed_image = compress_image(noisy_image, algorithm)

    baseline_compressed_size = len(baseline_compressed_image)
    if baseline_compressed_size == 0:
        raise ValueError("The compressed original image has a size of 0 bytes.")

    noisy_compressed_size = len(noisy_compressed_image)
    response = (
        (noisy_compressed_size - baseline_compressed_size) / baseline_compressed_size
    ) * 100

    return {
        "baseline_compressed_image": baseline_compressed_image,
        "noisy_compressed_image": noisy_compressed_image,
        "baseline_compressed_size": baseline_compressed_size,
        "noisy_compressed_size": noisy_compressed_size,
        "response": response,
        "noise_percentage": noise_percentage,
        "algorithm": "WebP" if algorithm.upper() == "WEBP" else "PNG",
        "noise_level": noise_level,
        "seed": seed,
    }
