args <- commandArgs(trailingOnly = TRUE)

output_file <- if (length(args) >= 1) {
  args[[1]]
} else {
  "treatment_order.csv"
}
reps_per_block <- if (length(args) >= 2) {
  as.integer(args[[2]])
} else {
  1L
}
seed <- if (length(args) >= 3) {
  as.integer(args[[3]])
} else {
  26L
}
algorithms_arg <- if (length(args) >= 4) {
  args[[4]]
} else {
  "PNG,WebP"
}
noise_levels_arg <- if (length(args) >= 5) {
  args[[5]]
} else {
  "low,high"
}
content_blocks_arg <- if (length(args) >= 6) {
  args[[6]]
} else {
  "indoor,outdoor"
}

if (is.na(reps_per_block) || reps_per_block <= 0) {
  stop("reps_per_block must be a positive integer.")
}

if (is.na(seed)) {
  stop("seed must be an integer.")
}

parse_csv_values <- function(value) {
  parts <- trimws(strsplit(value, ",", fixed = TRUE)[[1]])
  parts[nzchar(parts)]
}

normalize_algorithm <- function(value) {
  normalized <- toupper(trimws(value))
  if (normalized == "WEBP") {
    return("WebP")
  }
  if (normalized == "PNG") {
    return("PNG")
  }
  stop(sprintf("unsupported algorithm value: %s", value))
}

normalize_noise_level <- function(value) {
  normalized <- tolower(trimws(value))
  if (!(normalized %in% c("low", "high"))) {
    stop(sprintf("unsupported noise level value: %s", value))
  }
  normalized
}

normalize_content_block <- function(value) {
  normalized <- tolower(trimws(value))
  if (!(normalized %in% c("indoor", "outdoor"))) {
    stop(sprintf("unsupported content block value: %s", value))
  }
  normalized
}

algorithms <- unique(
  vapply(
    parse_csv_values(algorithms_arg), normalize_algorithm,
    character(1)
  )
)
noise_levels <- unique(
  vapply(
    parse_csv_values(noise_levels_arg), normalize_noise_level,
    character(1)
  )
)
content_blocks <- unique(
  vapply(
    parse_csv_values(content_blocks_arg),
    normalize_content_block,
    character(1)
  )
)

if (
  length(algorithms) == 0 ||
    length(noise_levels) == 0 ||
    length(content_blocks) == 0
) {
  stop(
    paste0(
      "algorithms, noise levels, and content blocks must each ",
      "contain at least one value."
    )
  )
}

base_treatments <- expand.grid(
  algorithm = algorithms,
  noise_level = noise_levels,
  content_block = content_blocks,
  stringsAsFactors = FALSE
)

treatment_rows <- base_treatments[
  rep(seq_len(nrow(base_treatments)), each = reps_per_block),
]

set.seed(seed)
randomized_indices <- sample(nrow(treatment_rows))
treatment_order <- treatment_rows[randomized_indices, ]
treatment_order$run_order <- seq_len(nrow(treatment_order))

treatment_order <- treatment_order[, c(
  "run_order", "algorithm", "noise_level", "content_block"
)]

print(treatment_order)
write.csv(treatment_order, output_file, row.names = FALSE)

cat("\nWrote treatment order to:", output_file, "\n")
cat("Reps per block:", reps_per_block, "\n")
cat("Seed:", seed, "\n")
cat("Algorithms:", paste(algorithms, collapse = ", "), "\n")
cat("Noise levels:", paste(noise_levels, collapse = ", "), "\n")
cat("Content blocks:", paste(content_blocks, collapse = ", "), "\n")
