#!/usr/bin/env bash
set -euo pipefail

NAME=bbos
VERSION=0.0.1
STAGING=".build_staging"
WHEELDIR="dist"

echo "[*] Cleaning staging and dist..."
rm -rf "$STAGING" "$WHEELDIR"
mkdir -p "$STAGING/$NAME/daemons"
mkdir -p "$WHEELDIR"
echo "[*] Copying Python files..."

# Copy all .py files from bbos root (excluding daemons)
find bbos -maxdepth 1 -type f -name "*.py" | while read -r src; do
  relpath="${src#bbos/}"
  dst="$STAGING/$NAME/$relpath"
  mkdir -p "$(dirname "$dst")"
  cp "$src" "$dst"
done

# Copy only constants.py and __init__.py files from daemons (excluding venv)
find bbos/daemons -type f \( -name constants.py \) -not -path "*/venv/*" | while read -r src; do
  relpath="${src#bbos/}"
  dst="$STAGING/$NAME/$relpath"
  mkdir -p "$(dirname "$dst")"
  cp "$src" "$dst"
done

echo "[*] Writing project.toml..."

cp pyproject.toml "$STAGING/"

echo "[*] Building clean wheel..."
(
  cd "$STAGING"
  python3 -m build --wheel
)

echo "[*] Moving wheel to ./dist/"
mv "$STAGING/dist/"*.whl "$WHEELDIR/"

echo "[+] Build complete. Final contents:"
unzip -l "$WHEELDIR"/*.whl | grep constants.py
