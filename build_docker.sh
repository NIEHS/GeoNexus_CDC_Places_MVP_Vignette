#!/bin/sh
set -e

#IMAGE=ghcr.io/niehs/geonexus-cdc-places-geography-selector:0.1.0
IMAGE=pateldes/geonexus-cdc-places-geography-selector:0.1.3

docker buildx build --no-cache --platform linux/amd64 -t "$IMAGE" .

# Uncomment to push to registry after a successful build:
docker push "$IMAGE"

# ── Local test run ────────────────────────────────────────────────────────────
mkdir -p test_output

docker run --rm \
  --platform linux/amd64 \
  -v "$(pwd)/test_output:/output" \
  "$IMAGE" \
  --states AZ \
  --measures DIABETES OBESITY CSMOKING \
  --estimate-type crude_prevalence \
  --selection-measure DIABETES \
  --selection-method top_n \
  --top-n 5 \
  --output-mode both

# ── Two-container workflow ────────────────────────────────────────────────────
# After CDC Places runs, pipe its manifest directly into the Amadeus container:
#
# docker run --rm \
#   --platform linux/amd64 \
#   -v "$(pwd)/test_output/selected:/input:ro" \
#   -v "$(pwd)/amadeus_output:/output" \
#   ghcr.io/niehs/geonexus-amadeus-covariate-builder:0.1.0 \
#   --input-locations /input/amadeus_location_manifest.csv \
#   --covariate-dataset gridmet \
#   --covariate-variable tmmx \
#   --start-date 2020-07-01 \
#   --end-date 2021-07-07
