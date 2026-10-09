#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Shared fail-closed release inputs; source from the repository root.
validate_release_tag() {
  local tag="$1" declared_version
  if [[ ! "$tag" =~ ^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z]+([.-][0-9A-Za-z]+)*)?$ ]]; then
    echo 'ERROR: Expected vX.Y.Z with an optional prerelease suffix.' >&2
    return 1
  fi
  release_version=${tag#v}
  declared_version=$(sed -n 's/^[[:space:]]*versionName = "\([^"]*\)"$/\1/p' app/build.gradle.kts)
  release_code=$(sed -n 's/^[[:space:]]*versionCode = \([0-9]*\)$/\1/p' app/build.gradle.kts)
  if [[ "$release_version" != "$declared_version" || ! "$release_code" =~ ^[1-9][0-9]*$ ]]; then
    echo 'ERROR: Tag must match declared versionName and a positive versionCode.' >&2
    return 1
  fi
}
require_release_tools() {
  : "${ANDROID_HOME:?Set ANDROID_HOME to the pinned Android SDK}"
  apkanalyzer="$ANDROID_HOME/cmdline-tools/23.0/bin/apkanalyzer"
  apksigner="$ANDROID_HOME/build-tools/36.0.0/apksigner"
  zipalign="$ANDROID_HOME/build-tools/36.0.0/zipalign"
  local tool
  for tool in "$apkanalyzer" "$apksigner" "$zipalign"; do
    [[ -x "$tool" ]] || { echo "ERROR: Missing pinned tool: $tool" >&2; return 1; }
  done
  local component revision actual
  for component in cmdline-tools/23.0 build-tools/36.0.0; do
    revision=${component##*/}
    actual=$(sed -n 's/^Pkg\.Revision=//p' "$ANDROID_HOME/$component/source.properties")
    [[ "$actual" == "$revision" ]] || { echo "ERROR: Incorrect SDK revision: $component" >&2; return 1; }
  done
}
require_release_certificate() {
  release_certificate=$(printf '%s' "${RELEASE_CERT_SHA256:?Set the trusted certificate SHA-256 fingerprint}" | tr '[:upper:]' '[:lower:]' | tr -d ':')
  [[ "$release_certificate" =~ ^[0-9a-f]{64}$ ]] || { echo 'ERROR: Invalid certificate SHA-256 fingerprint.' >&2; return 1; }
}
