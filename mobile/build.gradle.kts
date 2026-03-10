plugins {
    kotlin("multiplatform") version "2.0.0" apply false
    kotlin("plugin.serialization") version "2.0.0" apply false
    id("com.android.application") version "8.2.0" apply false
    id("com.android.library") version "8.2.0" apply false
    id("app.cash.sqldelight") version "2.0.1" apply false
}

allprojects {
    repositories {
        google()
        mavenCentral()
    }
}
