plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.ipnet.android"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.ipnet.android"
        minSdk = 26
        targetSdk = 34
        versionCode = 3
        versionName = "1.1.2"
        // libbox ships a big .so per ABI (~70MB x4 = the 324MB APK).
        // arm64-v8a covers virtually all phones from the last 8 years.
        ndk {
            abiFilters += "arm64-v8a"
        }
    }

    buildTypes {
        release {
            // Debug key signs the APK so it installs directly from Releases.
            signingConfig = signingConfigs.getByName("debug")
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
    implementation("androidx.browser:browser:1.8.0") // Custom Tabs for OAuth
    implementation("androidx.work:work-runtime-ktx:2.9.0") // endpoint watcher
    // Data plane = sslocal native binary (~4MB, built in CI from
    // shadowsocks-rust). No giant AAR, so the APK stays ~10-15MB.
}
