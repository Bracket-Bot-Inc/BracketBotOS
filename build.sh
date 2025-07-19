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

echo "[*] Copying only constants.py files (excluding venv)..."
find bbos/daemons -type f -name constants.py -not -path "*/venv/*" | while read -r src; do
  relpath="${src#bbos/}"
  dst="$STAGING/$NAME/$relpath"
  mkdir -p "$(dirname "$dst")"
  cp "$src" "$dst"
done

echo "[*] Writing setup.py and pyproject.toml..."
cat > "$STAGING/setup.py" <<EOF
from setuptools import setup

setup(
    name="${NAME}",
    version="${VERSION}",
    packages=[],
    include_package_data=True,
    package_data={"": ["daemons/*/constants.py"]},
    install_requires=[
        "sshkeyboard",
        "posix_ipc",
        "numpy",
        "pillow",
    ],
)
EOF

cat > "$STAGING/pyproject.toml" <<EOF
[build-system]
requires = ["setuptools>=64", "wheel"]
build-backend = "setuptools.build_meta"
EOF

echo "[*] Building clean wheel..."
(
  cd "$STAGING"
  python3 -m build --wheel
)

echo "[*] Moving wheel to ./dist/"
mv "$STAGING/dist/"*.whl "$WHEELDIR/"

echo "[*] Verifying no extra files slipped in..."
bad=$(unzip -l "$WHEELDIR"/*.whl | grep -vE 'constants\.py|\.dist-info' || true)
if [[ -n "$bad" ]]; then
  echo "❌ Unexpected files in wheel:"
  echo "$bad"
  exit 1
fi

echo "[+] Build complete. Final contents:"
unzip -l "$WHEELDIR"/*.whl | grep constants.py
