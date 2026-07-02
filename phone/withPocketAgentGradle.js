/**
 * Custom Expo config plugin — adds gradle properties needed for the build.
 *
 * - Adds `expo.modules.core.suppressKotlinVersionCompatibilityCheck=true`
 *   to the project gradle.properties (for the project-level check).
 * - Modifies android/app/build.gradle to add the kotlinOptions
 *   freeCompilerArgs needed for the suppression to take effect.
 *
 * Works around the Kotlin 1.9.24 vs 1.9.25 mismatch between Expo SDK 52
 * and expo-modules-core's Compose Compiler dependency.
 */

const { withGradleProperties, withAppBuildGradle } = require('@expo/config-plugins');

module.exports = (config) => {
  // 1. Add the gradle.properties flag (project-level)
  config = withGradleProperties(config, (mod) => {
    const props = mod.modResults;
    const filtered = props.filter(p =>
      !(p.type === 'property' &&
        p.key === 'expo.modules.core.suppressKotlinVersionCompatibilityCheck')
    );
    filtered.push({
      type: 'property',
      key: 'expo.modules.core.suppressKotlinVersionCompatibilityCheck',
      value: 'true',
    });
    mod.modResults = filtered;
    return mod;
  });

  // 2. Inject suppressKotlinVersionCompatibilityCheck into android/app/build.gradle
  // The Compose Compiler check reads it from composeOptions in the app module.
  config = withAppBuildGradle(config, (mod) => {
    let buildGradle = mod.modResults.contents;
    // If not already patched, add composeOptions block to the android {} section
    if (!buildGradle.includes('suppressKotlinVersionCompatibilityCheck')) {
      // Insert before the closing brace of android { ... }
      // Simple approach: append to the end of the android block by finding the
      // last '}' at column 0... actually let's just inject after composeOptions
      // if it exists, or add a new composeOptions block.
      if (buildGradle.includes('composeOptions {')) {
        buildGradle = buildGradle.replace(
          /composeOptions\s*{/,
          'composeOptions {\n        suppressKotlinVersionCompatibilityCheck = true'
        );
      } else {
        // Add a composeOptions block inside android {}
        buildGradle = buildGradle.replace(
          /android\s*{/,
          'android {\n    composeOptions {\n        suppressKotlinVersionCompatibilityCheck = true\n    }'
        );
      }
    }
    mod.modResults.contents = buildGradle;
    return mod;
  });

  return config;
};
