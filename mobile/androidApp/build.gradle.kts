import java.util.Properties

plugins {
    // AGP 9 compiles Kotlin itself; no Kotlin Android plugin is applied.
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
}

android {
    namespace = "app.soshuhen"
    compileSdk = libs.versions.android.compileSdk.get().toInt()

    defaultConfig {
        applicationId = "app.soshuhen"
        minSdk = libs.versions.android.minSdk.get().toInt()
        targetSdk = libs.versions.android.targetSdk.get().toInt()
        versionCode = 1
        versionName = "0.1.0"
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
