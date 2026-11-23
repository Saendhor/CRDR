failed=0
for f in dataset/04_FourthBatch/src/*.png; do
  [[ -e $f ]] || continue

  name=${f##*/}
  out="results/dds/${name%.*}.dds"

  printf 'Converting %s\n' "$f"
  CompressonatorCLI -fd BC7 "$f" "$out" || {
    printf 'FAILED: %s\n' "$f" >&2
    failed=$((failed + 1))
  }
done
