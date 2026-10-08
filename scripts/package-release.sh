#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
: "${ANDROID_HOME:?Set ANDROID_HOME to your Android SDK directory}"

gradle_version=$(sed -n 's/.*versionName = "\(.*\)".*/\1/p' app/build.gradle.kts | head -n 1)
tag_input="${1:-}"
if [[ -n "$tag_input" ]]; then
  version="${tag_input#v}"
  if [[ "$version" != "$gradle_version" ]]; then
    echo "ERROR: Input tag version ($version) does not match app/build.gradle.kts versionName ($gradle_version)." >&2
    exit 1
  fi
else
  version="$gradle_version"
fi

if [[ -z "$version" ]]; then
  echo "Unable to determine release version name from app/build.gradle.kts or input tag." >&2
  exit 1
fi

echo "Packaging Astronomical Clocks Wallpaper v${version}..."

if [[ -z "${RELEASE_KEYSTORE_PATH:-}" || ! -f "${RELEASE_KEYSTORE_PATH}" ]]; then
  echo "ERROR: RELEASE_KEYSTORE_PATH is not set or file does not exist." >&2
  echo "Release packaging requires a valid signing keystore." >&2
  exit 1
fi

if [[ -z "${RELEASE_KEYSTORE_PASSWORD:-}" || -z "${RELEASE_KEY_ALIAS:-}" ]]; then
  echo "ERROR: RELEASE_KEYSTORE_PASSWORD and RELEASE_KEY_ALIAS must be set." >&2
  exit 1
fi

./gradlew qualityGate :app:assembleRelease

release_apk="app/build/outputs/apk/release/app-release.apk"
if [[ ! -f "$release_apk" ]]; then
  echo "ERROR: Release APK build failed; expected artifact not found at $release_apk" >&2
  exit 1
fi

./scripts/verify-release-apk.sh "$release_apk"

dist_dir="build/dist"
rm -rf "$dist_dir"
mkdir -p "$dist_dir"
dist_apk="$dist_dir/AstronomicalClocksWallpaper-v${version}.apk"
cp "$release_apk" "$dist_apk"

checksum_file="$dist_dir/AstronomicalClocksWallpaper-v${version}-sha256sums.txt"
(
  cd "$dist_dir"
  shasum -a 256 "AstronomicalClocksWallpaper-v${version}.apk" > "AstronomicalClocksWallpaper-v${version}-sha256sums.txt"
)

echo "Release packaging complete."
echo "Artifact: $dist_apk"
echo "Checksums: $checksum_file"
cat "$checksum_file"
