import java.util.Properties

plugins {
    // AGP 9 compiles Kotlin itself; no Kotlin Android plugin is applied.
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
}

// A fixed versionCode made every build look the same on a device: the only way
// to tell whether a phone was current was its install date. The commit count
// rises with every commit on main, so a newer build always installs over an
// older one, and the hash in versionName names the exact code. "-dirty" marks a
// build of uncommitted changes, which shares the commit's number.
// Only changes under mobile/ count as dirty: a backend edit does not change the
// app. A shallow clone (CI) counts only its own depth; nothing built there ships.
fun git(vararg args: String): String? = runCatching {
    providers.exec {
        workingDir(rootDir)
        commandLine("git", *args)
        isIgnoreExitValue = true
    }.standardOutput.asText.get().trim()
}.getOrNull()?.takeIf { it.isNotEmpty() }

val gitCommitCount = git("rev-list", "--count", "HEAD")?.toIntOrNull() ?: 1
val gitRevision = (git("rev-parse", "--short=7", "HEAD") ?: "unknown") +
    if (git("status", "--porcelain", "--untracked-files=no", "--", ".").isNullOrEmpty()) "" else "-dirty"

android {
    namespace = "app.soshuhen"
    compileSdk = libs.versions.android.compileSdk.get().toInt()

    defaultConfig {
        applicationId = "app.soshuhen"
        minSdk = libs.versions.android.minSdk.get().toInt()
        targetSdk = libs.versions.android.targetSdk.get().toInt()
        versionCode = gitCommitCount
        versionName = "0.1.0+$gitCommitCount.$gitRevision"
    }

    // The key is the app's identity: Android refuses an update signed with
    // another one, and uninstalling to get past that loses unsent progress.
    // Without keystore.properties a release is signed with the debug key, so
    // the build still works on a fresh clone and in CI.
    val keystore = rootProject.file("keystore.properties").takeIf { it.exists() }?.let { file ->
        Properties().apply { file.inputStream().use(::load) }
    }
    signingConfigs {
        if (keystore != null) {
            create("release") {
                storeFile = rootProject.file(keystore.getProperty("storeFile"))
                storePassword = keystore.getProperty("storePassword")
                keyAlias = keystore.getProperty("keyAlias")
                keyPassword = keystore.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            // Off until shrinking has been tried against kotlinx.serialization,
            // Room and Ktor; a stripped class fails only at runtime.
            isMinifyEnabled = false
            signingConfig = signingConfigs.findByName("release") ?: signingConfigs.getByName("debug")
        }
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }
}

dependencies {
    implementation(project(":shared"))
    implementation(libs.activity.compose)
    implementation(libs.splashscreen)
    implementation(libs.coroutines.core)
    implementation(libs.ktor.client.core)
    implementation(libs.okio)
    implementation(libs.room.runtime)
    // The manifest names WorkManager's foreground service; shared depends on
    // WorkManager only privately, and lint cannot see the class otherwise.
    implementation(libs.work.runtime)
}
