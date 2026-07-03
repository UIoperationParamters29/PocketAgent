/**
 * Custom Expo config plugin — works around build issues for PocketAgent.
 *
 * 1. Compose Compiler version mismatch (Expo SDK 52 Kotlin 1.9.24 vs
 *    expo-modules-core Compose Compiler 1.5.15 wanting Kotlin 1.9.25):
 *    Force-downgrade androidx.compose.compiler:compiler to 1.5.14 globally.
 *
 * 2. Release signing: configure the app's signingConfig to read the keystore
 *    from android/app/release.keystore (where the CI workflow deposits it).
 *    Env vars supply the passwords at build time.
 */

const { withAppBuildGradle, withProjectBuildGradle } = require('@expo/config-plugins');

module.exports = (config) => {
  // 1. Force Compose Compiler 1.5.14 globally
  config = withProjectBuildGradle(config, (mod) => {
    let buildGradle = mod.modResults.contents;
    if (!buildGradle.includes('androidx.compose.compiler:compiler')) {
      const forceBlock = `
    configurations.all {
        resolutionStrategy {
            force 'androidx.compose.compiler:compiler:1.5.14'
        }
    }`;
      if (/^allprojects\s*{/m.test(buildGradle)) {
        buildGradle = buildGradle.replace(
          /^allprojects\s*{/m,
          'allprojects {' + forceBlock
        );
      } else {
        buildGradle += '\nallprojects {' + forceBlock + '\n}\n';
      }
    }
    mod.modResults.contents = buildGradle;
    return mod;
  });

  // 2. Configure release signing + pin Compose Compiler extension version
  config = withAppBuildGradle(config, (mod) => {
    let buildGradle = mod.modResults.contents;

    // Add composeOptions with pinned kotlinCompilerExtensionVersion
    if (!buildGradle.includes('kotlinCompilerExtensionVersion')) {
      const androidMatch = buildGradle.match(/^android\s*\{/m);
      if (androidMatch) {
        const insertAt = androidMatch.index + androidMatch[0].length;
        const injection = `
    composeOptions {
        kotlinCompilerExtensionVersion = "1.5.14"
    }`;
        buildGradle = buildGradle.slice(0, insertAt) + injection + buildGradle.slice(insertAt);
      }
    }

    // Add a signingConfigs.release block + wire it into buildTypes.release
    // The keystore file lives at android/app/release.keystore (CI writes it there).
    // Passwords come from env vars (set by the CI workflow).
    if (!buildGradle.includes('signingConfigs {')) {
      const androidMatch = buildGradle.match(/^android\s*\{/m);
      if (androidMatch) {
        const insertAt = androidMatch.index + androidMatch[0].length;
        const signingBlock = `
    signingConfigs {
        release {
            if (project.hasProperty('PA_RELEASE_STORE_FILE')) {
                storeFile file(project.findProperty('PA_RELEASE_STORE_FILE'))
                storePassword project.findProperty('PA_RELEASE_STORE_PASSWORD')
                keyAlias project.findProperty('PA_RELEASE_KEY_ALIAS')
                keyPassword project.findProperty('PA_RELEASE_KEY_PASSWORD')
            }
        }
    }`;
        buildGradle = buildGradle.slice(0, insertAt) + signingBlock + buildGradle.slice(insertAt);

        // Wire signingConfig into the release build type
        // Find "buildTypes {" then "release {" inside it, then add signingConfig
        buildGradle = buildGradle.replace(
          /(buildTypes\s*{[\s\S]*?release\s*{)/m,
          '$1\n            signingConfig signingConfigs.release'
        );
      }
    }

    mod.modResults.contents = buildGradle;
    return mod;
  });

  return config;
};
