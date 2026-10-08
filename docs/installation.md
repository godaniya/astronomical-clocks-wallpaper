# Installation and Upgrades

Astronomical Clock Wallpaper is an independent, 100% offline Android live wallpaper. It requests no internet permissions (`android.permission.INTERNET` is not included in the application manifest) and contains zero third-party telemetry, trackers, or advertising SDKs.

This guide outlines recommended installation and upgrade procedures across supported channels.

---

## Supported Methods

| Method | Best For | Automatic Updates | Store Intermediary |
| :--- | :--- | :--- | :--- |
| **[Obtainium](#method-1-obtainium-recommended)** | Friends, testers, and power users | Yes (background check & one-tap) | None (Direct from GitHub) |
| **[Direct APK](#method-2-direct-apk-download)** | One-off manual installation | No (manual download) | None (Direct from GitHub) |
| **[ADB](#method-3-developer-installation-adb)** | Developers and local testing | Via CLI | None (Local host) |

---

## Method 1: Obtainium (Recommended)

[Obtainium](https://obtainium.imranr.dev/) is an open-source, privacy-respecting Android application manager that allows you to install and update apps directly from their release source (GitHub Releases) without third-party app stores or account registration.

### One-Click Setup

If you already have Obtainium installed on your Android device:

[![Add to Obtainium](https://raw.githubusercontent.com/ImranR98/Obtainium/main/assets/graphics/badge_small.png)](obtainium://app/add/https://github.com/godaniya/astronomical-clocks-wallpaper)

Or tap this link on your device:  
👉 [`obtainium://app/add/https://github.com/godaniya/astronomical-clocks-wallpaper`](obtainium://app/add/https://github.com/godaniya/astronomical-clocks-wallpaper)

### Step-by-Step Instructions

1. **Install Obtainium**: Download and install Obtainium on your Android phone from [obtainium.imranr.dev](https://obtainium.imranr.dev/) or [GitHub](https://github.com/ImranR98/Obtainium/releases/latest).
2. **Add Repository**:
   - Tap the **Add to Obtainium** button above in your mobile browser, **or**:
   - Open Obtainium, tap **Add App**, and paste the repository URL:
     ```
     https://github.com/godaniya/astronomical-clocks-wallpaper
     ```
3. **Prerelease Configuration**:
   - Milestone releases prior to v1.0 are flagged as pre-releases on GitHub.
   - In the app configuration screen, enable **Include Prereleases**.
4. **Install**:
   - Tap **Add**. Obtainium will query the repository, fetch the latest signed release APK, and prompt you to install.
   - Future updates will be checked automatically in the background according to your Obtainium schedule.

---

## Method 2: Direct APK Download

You can download and install signed release APKs directly from GitHub Releases.

1. Open the [GitHub Releases page](https://github.com/godaniya/astronomical-clocks-wallpaper/releases).
2. Under the latest release, download the release APK:
   `AstronomicalClocksWallpaper-vX.Y.Z.apk`
3. *(Optional but recommended)* Download `AstronomicalClocksWallpaper-vX.Y.Z-sha256sums.txt` and verify the cryptographic checksum:
   ```sh
   shasum -a 256 -c AstronomicalClocksWallpaper-vX.Y.Z-sha256sums.txt
   ```
4. On your Android device, open the downloaded file and confirm installation when prompted by Android's package installer. If prompted, allow your browser or file manager permission to *"Install unknown apps"*.

---

## Method 3: Developer Installation (ADB)

For developers connected to an Android device or emulator via `adb`:

```sh
adb install -r AstronomicalClocksWallpaper-vX.Y.Z.apk
```

To set the wallpaper active and open its configuration:
```sh
adb shell am start -a android.service.wallpaper.LIVE_WALLPAPER_CHOOSER
```

---

## Cryptographic Identity and Upgrade Guarantees

### Signature Continuity
All official release APKs share the durable application ID:
```
io.github.godaniya.astronomicalclockswallpaper
```
Release builds are signed with a retained, durable release key. Android enforces cryptographic signature continuity during updates:
* Installing an update with the same application ID and the same signing certificate preserves all saved user preferences, including observing location, custom coordinates, and dial layer choices.
* Version codes (`versionCode`) monotonically increase across releases to ensure clean forward upgrades.

### Debug vs. Release Builds
Development and CI quality-gate builds use the distinct debug identity:
```
io.github.godaniya.astronomicalclockswallpaper.debug
```
Debug builds are signed with disposable debug keys and run with `debuggable = true`. Because debug and release builds use different cryptographic keys and distinct application IDs:
* Debug and release variants can coexist on the same device as separate installations.
* You cannot in-place upgrade a debug APK to a release APK (Android will report `INSTALL_FAILED_UPDATE_INCOMPATIBLE`). If migrating from a debug build, uninstall the debug app first.

---

## Ecosystem Distribution Roadmap

In accordance with [Issue #71](https://github.com/godaniya/astronomical-clocks-wallpaper/issues/71), the project evaluates privacy-focused and open-source distribution channels:

* **Obtainium (Active)**: Fully supported via standardized GitHub Release artifacts and deep links.
* **IzzyOnDroid (Planned)**: Tagged release APKs following standard SemVer and asset naming are staged for submission to the IzzyOnDroid F-Droid-compatible repository.
* **F-Droid (Milestone Goal)**: Inclusion in the official F-Droid catalog from source builds is planned following physical-device hardware qualification ([Issue #8](https://github.com/godaniya/astronomical-clocks-wallpaper/issues/8)).
* **Accrescent (Future Exploration)**: Under evaluation for zero-privilege, unattended atomic updates.
