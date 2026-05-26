args <- commandArgs(trailingOnly = TRUE)

output_file <- if (length(args) >= 1) args[[1]] else "treatment_order.csv"
reps_per_block <- if (length(args) >= 2) as.integer(args[[2]]) else 1L
seed <- if (length(args) >= 3) as.integer(args[[3]]) else 26L

if (is.na(reps_per_block) || reps_per_block <= 0) {
  stop("reps_per_block must be a positive integer.")
}

if (is.na(seed)) {
  stop("seed must be an integer.")
}

base_treatments <- data.frame(
  algorithm = c("PNG", "WebP", "PNG", "WebP", "PNG", "WebP", "PNG", "WebP"),
  noise_level = c("low", "low", "high", "high", "low", "low", "high", "high"),
  content_block = c(
    "indoor", "indoor", "indoor", "indoor",
    "outdoor", "outdoor", "outdoor", "outdoor"
  ),
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
