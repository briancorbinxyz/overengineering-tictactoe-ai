plugins {
    java
    id("org.springframework.boot") version "4.1.1"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "org.xxdc.oss.example"
version = "0.2.0-SNAPSHOT"
description = "Over-Engineering Tic-Tac-Toe w. Spring AI"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(25)
    }
}

repositories {
    mavenCentral()
}

// Episode 1 ran on Spring Boot 3.5 and Spring AI 1.0. Spring AI 2.0 needs Boot 4.
extra["springAiVersion"] = "2.0.1"

dependencies {
    implementation("org.xxdc.oss.example:tictactoe-api:3.0.0-jdk25")
    implementation("org.springframework.boot:spring-boot-starter")
    implementation("org.springframework.ai:spring-ai-starter-model-ollama")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

dependencyManagement {
    imports {
        mavenBom("org.springframework.ai:spring-ai-bom:${property("springAiVersion")}")
    }
}

tasks.withType<Test> {
    useJUnitPlatform()
}
