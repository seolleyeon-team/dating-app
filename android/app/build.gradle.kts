import java.io.FileInputStream
import java.util.Properties
import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    id("com.android.application")
    // START: FlutterFire Configuration
    id("com.google.gms.google-services")
    // END: FlutterFire Configuration
    id("kotlin-android")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

val keystoreProperties = Properties()
val keystorePropertiesFile = rootProject.file("key.properties")
val hasReleaseKeystore = keystorePropertiesFile.exists()
if (hasReleaseKeystore) {
    keystoreProperties.load(FileInputStream(keystorePropertiesFile))
}

android {
    namespace = "com.seolleyeon.app"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        isCoreLibraryDesugaringEnabled = true
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }

    defaultConfig {
        // applicationId 는 flavor 가 정한다 (productFlavors 참고).
        // production/staging 모두 설레연 운영 앱인 com.seolleyeon.app을 사용한다.
        // 여기에 기본값을 두면 flavor 를 빼먹은 빌드가 조용히 나갈 수 있으므로
        // applicationId는 각 flavor에서 명시한다.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    flavorDimensions += "environment"

    productFlavors {
        create("production") {
            dimension = "environment"
            // Google Play 에 등록된 실제 앱. 이 값이어야 기존 사용자에게
            // 업데이트로 전달된다.
            applicationId = "com.seolleyeon.app"
        }

        create("staging") {
            dimension = "environment"
            // flavor 이름은 기존 개발 명령 호환성을 위해 유지하지만,
            // 별도 staging 패키지/Firebase 앱은 사용하지 않는다.
            applicationId = "com.seolleyeon.app"
        }
    }

    signingConfigs {
        if (hasReleaseKeystore) {
            create("release") {
                keyAlias = keystoreProperties["keyAlias"] as String
                keyPassword = keystoreProperties["keyPassword"] as String
                storeFile = file(keystoreProperties["storeFile"] as String)
                storePassword = keystoreProperties["storePassword"] as String
            }
        }
    }

    buildTypes {
        release {
            // Fail closed: never fall back to debug signing for release artifacts.
            if (hasReleaseKeystore) {
                signingConfig = signingConfigs.getByName("release")
            }
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(JvmTarget.JVM_11)
    }
}

flutter {
    source = "../.."
}

dependencies {
    coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.4")
}

gradle.taskGraph.whenReady {
    if (!hasReleaseKeystore && allTasks.any { it.name.contains("Release", ignoreCase = true) }) {
        throw GradleException(
            "Missing android/key.properties. Create a release keystore before building an AAB.",
        )
    }
}
