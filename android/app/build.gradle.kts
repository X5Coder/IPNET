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
        versionCode = 1
        versionName = "1.0.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = true
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
    implementation("androidx.datastore:datastore-preferences:1.1.1")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
    implementation("androidx.browser:browser:1.8.0") // Custom Tabs for OAuth
    implementation("androidx.work:work-runtime-ktx:2.9.0") // endpoint watcher
    // sing-box data plane (gomobile AAR, ~70MB). Pinned to 1.14.x to match
    // the server workflow (SB 1.14.2): same Shadowsocks behavior both ends.
    implementation("com.github.singbox-android:libbox:1.14.0")
    // sing-box core (gomobile AAR) adds ~20MB; attach real artifact here:
    // implementation("io.nekohasekai:sing-box-android:<latest>")
}
