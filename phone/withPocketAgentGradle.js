/**
 * Custom Expo config plugin — works around the Kotlin/Compose Compiler
 * version mismatch between Expo SDK 52 (Kotlin 1.9.24) and
 * expo-modules-core's Compose Compiler 1.5.15 (which wants Kotlin 1.9.25).
 *
 * Approach: pin the Compose Compiler to 1.5.14 which is compatible with
 * Kotlin 1.9.24, by setting kotlinCompilerExtensionVersion in composeOptions.
 */

const { withAppBuildGradle } = require('@expo/config-plugins');

module.exports = (config) => {
  return withAppBuildGradle(config, (mod) => {
    let buildGradle = mod.modResults.contents;

    if (!buildGradle.includes('kotlinCompilerExtensionVersion')) {
      // Insert composeOptions block inside the android { ... } block
      // Find the first 'android {' (top-level) and inject after it
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

    mod.modResults.contents = buildGradle;
    return mod;
  });
};
