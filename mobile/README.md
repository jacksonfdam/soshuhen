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
it still builds on a fresh clone and in CI; such an APK cannot later be updated
by one signed with your own key. Release builds are not minified.
