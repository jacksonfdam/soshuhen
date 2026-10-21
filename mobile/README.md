# Soshuhen for Android

A reader for the library a Soshuhen server already holds. It finds the server on
the home network, shows the library the way the web interface does, and (next)
copies the series you mark to the device so they can be read offline. It never
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
app's database and any progress not yet sent to the server. Release signing is
set up with the offline work; until then the debug signature is used.
