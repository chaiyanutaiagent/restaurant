#!/bin/sh
set -eu

for script in scripts/*.sh; do
  first_line="$(sed -n '1p' "$script")"
  case "$first_line" in
    *bash*) bash -n "$script" ;;
    *) sh -n "$script" ;;
  esac
done
