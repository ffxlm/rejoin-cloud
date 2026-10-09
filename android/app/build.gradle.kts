plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.rejoin.agent"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.rejoin.agent"
        minSdk = 24
        targetSdk = 34
        versionCode = 3
        versionName = "0.3.0"
    }

    // ---- signing ถาวร ----
    // ใช้คีย์เดียวกันทุก build (CI ถอดจาก GitHub Secret มาวางที่ keystore/rejoin.jks)
    // → อัปเดต APK ทับได้เลย ไม่ต้องถอนแอป/กรอกรหัสใหม่
    // ถ้าไม่มีไฟล์ (เช่น build ในเครื่อง dev) → fallback เป็น debug keystore ปกติ
    signingConfigs {
        create("rejoin") {
            storeFile = file("keystore/rejoin.jks")
            storePassword = System.getenv("ANDROID_KEYSTORE_PASSWORD") ?: "android"
            keyAlias = System.getenv("ANDROID_KEY_ALIAS") ?: "rejoin"
            keyPassword = System.getenv("ANDROID_KEY_PASSWORD") ?: "android"
        }
    }

    buildTypes {
        debug {
            if (file("keystore/rejoin.jks").exists()) {
                signingConfig = signingConfigs.getByName("rejoin")
            }
        }
        release {
            if (file("keystore/rejoin.jks").exists()) {
                signingConfig = signingConfigs.getByName("rejoin")
            }
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
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

    buildFeatures {
        viewBinding = true
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.4")
    // เก็บ device_token แบบเข้ารหัส (EncryptedSharedPreferences)
    implementation("androidx.security:security-crypto:1.1.0-alpha06")
    // คุยกับเว็บ (register/heartbeat/poll)
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")

    // unit tests (watchdog — pure logic)
    testImplementation("junit:junit:4.13.2")
}
