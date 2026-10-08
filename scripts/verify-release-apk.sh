#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
: "${ANDROID_HOME:?Set ANDROID_HOME to your Android SDK directory}"

apk=${1:-app/build/outputs/apk/release/app-release.apk}
mkdir -p build/reports

if [[ ! -f "$apk" ]]; then
  echo "Release APK not found at: $apk" >&2
  exit 1
fi

apkanalyzer="$ANDROID_HOME/cmdline-tools/23.0/bin/apkanalyzer"
if [[ ! -x "$apkanalyzer" ]]; then
  apkanalyzer=$(find "$ANDROID_HOME/cmdline-tools" -name apkanalyzer 2>/dev/null | head -n 1)
fi

if [[ -z "$apkanalyzer" || ! -x "$apkanalyzer" ]]; then
  echo "ERROR: apkanalyzer not found or not executable under $ANDROID_HOME/cmdline-tools" >&2
  exit 1
fi

"$apkanalyzer" manifest print "$apk" > build/reports/apk-release-manifest.xml

python3 - "$apk" <<'PY'
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

android = '{http://schemas.android.com/apk/res/android}'


def check(condition, message):
    if not condition:
        print(f'Release APK verification failed: {message}', file=sys.stderr)
        raise SystemExit(1)


manifest = ET.parse('build/reports/apk-release-manifest.xml').getroot()
check(
    manifest.get('package') == 'io.github.godaniya.astronomicalclockswallpaper',
    'unexpected application ID: release package must be io.github.godaniya.astronomicalclockswallpaper',
)

sdk = manifest.find('uses-sdk')
check(sdk is not None, 'missing uses-sdk element')
check(sdk.get(android + 'minSdkVersion') == '26', 'minSdkVersion must be 26')
check(sdk.get(android + 'targetSdkVersion') == '37', 'targetSdkVersion must be 37')

version_name = manifest.get(android + 'versionName')
check(
    bool(version_name) and not version_name.endswith('-debug'),
    f'release application must have a valid non-debug versionName (got {version_name})',
)

permission_names = [e.get(android + 'name') for e in manifest.iter() if e.tag.startswith('uses-permission')]
check(
    permission_names == ['android.permission.ACCESS_COARSE_LOCATION'],
    'unexpected permissions: expected only ACCESS_COARSE_LOCATION',
)

application = manifest.find('application')
check(application is not None, 'missing application element')
debuggable = application.get(android + 'debuggable')
check(
    debuggable is None or debuggable == 'false',
    f'release application must not be debuggable (debuggable={debuggable})',
)

service = application.find('service')
check(service is not None, 'missing service element')
check(
    service.get(android + 'name')
    == 'io.github.godaniya.astronomicalclockswallpaper.AstronomicalClocksWallpaperService',
    'service name mismatch',
)
check(service.get(android + 'exported') == 'true', 'service must be exported')
check(
    service.get(android + 'permission') == 'android.permission.BIND_WALLPAPER',
    'service must require BIND_WALLPAPER',
)

action = service.find('intent-filter/action')
check(action is not None, 'missing intent-filter action')
check(
    action.get(android + 'name') == 'android.service.wallpaper.WallpaperService',
    'missing wallpaper intent-filter action',
)

metadata = service.find('meta-data')
check(metadata is not None, 'missing meta-data element')
check(metadata.get(android + 'name') == 'android.service.wallpaper', 'meta-data name mismatch')
check(metadata.get(android + 'resource'), 'meta-data must declare a resource')
print('Release APK application ID, SDK levels, debuggable flag, permissions, and service verified.')

license_asset = 'assets/licenses/astronomy-engine-LICENSE.txt'
expected_license = Path('app/src/main', license_asset).read_bytes()
check(expected_license, 'bundled Astronomy Engine license must not be empty')
with ZipFile(sys.argv[1]) as archive:
    check(license_asset in archive.namelist(), 'missing Astronomy Engine license')
    check(
        archive.read(license_asset) == expected_license,
        'Astronomy Engine license differs from the complete bundled upstream notice',
    )
print('Release APK Astronomy Engine license verified against the bundled upstream notice.')
PY

apksigner="$ANDROID_HOME/build-tools/36.0.0/apksigner"
if [[ ! -x "$apksigner" ]]; then
  apksigner=$(find "$ANDROID_HOME/build-tools" -name apksigner 2>/dev/null | head -n 1)
fi

if [[ -z "$apksigner" || ! -x "$apksigner" ]]; then
  echo "ERROR: apksigner not found or not executable under $ANDROID_HOME/build-tools" >&2
  exit 1
fi

"$apksigner" verify --verbose --print-certs "$apk" | tee build/reports/apk-release-signature.txt
if grep -Eq 'Signer #1 certificate DN: .*CN=Android Debug' build/reports/apk-release-signature.txt; then
  echo "Verification failed: Release APK must not be signed with Android Debug certificate!" >&2
  exit 1
fi

shasum -a 256 "$apk" | tee build/reports/apk-release-sha256.txt
echo "Release APK passed all verification checks successfully."
