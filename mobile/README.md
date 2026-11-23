# Soshuhen for Android

A reader for the library a Soshuhen server already holds. It finds the server on
the home network, shows the library the way the web interface does, and copies
the series you mark to a folder on the device so they can be read offline. It never
fetches anything from a source site: downloading stays the server's job.

Design: `docs/superpowers/specs/2026-10-20-android-client-design.md`.

## Building

You need JDK 21 and the Android SDK with platform 37. Gradle itself comes from
the wrapper.

```bash
export JAVA_HOME=$(/usr/libexec/java_home -v 21)
echo "sdk.dir=$HOME/Library/Android/sdk" > local.properties
./gradlew :shared:jvmTest            # the shared code's tests, on the JVM
./gradlew :androidApp:assembleDebug  # the APK
./gradlew :androidApp:installDebug   # onto a phone connected over USB
```

The default JDK on a machine may be newer than 21; Gradle and AGP are run on 21.

The version comes from git. `versionCode` is the commit count, so a build of a
later commit always installs over an earlier one; `versionName` reads
`0.1.0+<count>.<hash>`, with `-dirty` when `mobile/` has uncommitted changes.
Settings shows it, and `adb shell dumpsys package app.soshuhen | grep version`
reads it off a device. A branch can count fewer commits than a newer `main`, and
Android refuses that as a downgrade: install with `adb install -r -d`.

## Layout

- `shared/` is Kotlin Multiplatform: every screen, view model, API call and rule
  lives in `commonMain`. Android services sit in `androidMain`. The `jvm()`
  target is not shipped; it exists so `commonTest` runs without an emulator.
- `androidApp/` is the Android application: activity, manifest, icon, splash and
  the network security config that allows plain HTTP to the server's LAN IP.
- `shared/src/commonMain/kotlin/app/soshuhen/ui/theme/Tokens.kt` is the only
  place a colour or size lives, copied from `frontend/tailwind.config.ts`.

## Signing

Keep one keystore for every build you install. Android refuses to install an
update signed with a different key, and uninstalling to get past that loses the
app's database and any progress not yet sent to the server. **The keystore must
never change, and must never be lost: back it up somewhere other than this
machine.**

Create it once, in `mobile/`:

```bash
keytool -genkeypair -v -keystore soshuhen.keystore -alias soshuhen -keyalg RSA -keysize 4096 -validity 36500
```

Then write `mobile/keystore.properties` next to it:

```properties
storeFile=soshuhen.keystore
storePassword=<the store password you chose>
keyAlias=soshuhen
keyPassword=<the key password you chose>
```

Both files are gitignored. `storeFile` is relative to `mobile/`. With them in
place:

```bash
./gradlew :androidApp:installRelease
```

Without `keystore.properties` a release build is signed with the debug key, so
it still builds on a fresh clone and in CI; an update signed with your own key is
refused over such an install until it is rotated, below. Release builds are not
minified.

### Moving an install off the debug key

An install signed with the debug key can take your key without being uninstalled,
through APK Signature Scheme v3 rotation: a lineage file records the debug key
authorising yours, and one APK carrying it moves the device across. After that,
ordinary `installRelease` builds install over it. The two devices in use were
moved this way on 2026-11-23, and `soshuhen.lineage` from that move sits next to
the keystore, gitignored; back it up with them.

With `BT=~/Library/Android/sdk/build-tools/37.0.0` and the store password in
`KS_PW`, from `mobile/`:

```bash
$BT/apksigner rotate --out soshuhen.lineage \
  --old-signer --ks ~/.android/debug.keystore --ks-pass pass:android \
  --new-signer --ks soshuhen.keystore --ks-pass env:KS_PW
```

```bash
$BT/apksigner sign --ks ~/.android/debug.keystore --ks-pass pass:android \
  --next-signer --ks soshuhen.keystore --ks-pass env:KS_PW \
  --lineage soshuhen.lineage --rotation-min-sdk-version 28 \
  --out rotated.apk androidApp/build/outputs/apk/release/androidApp-release.apk
```

```bash
adb install -r rotated.apk
```

`rotate` is only needed once; reuse the existing lineage after that. Keep
`--rotation-min-sdk-version 28`: apksigner otherwise applies rotation from API 33
only, and a device below that, such as the Android 11 tablet, keeps the debug key
and later refuses every build signed with yours. A refused `install -r` changes
nothing on the device, so it is safe to try.
