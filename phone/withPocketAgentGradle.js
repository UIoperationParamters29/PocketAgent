/**
 * Custom Expo config plugin — works around the Kotlin/Compose Compiler
 * version mismatch between Expo SDK 52 (Kotlin 1.9.24) and
 * expo-modules-core's Compose Compiler 1.5.15 (which wants Kotlin 1.9.25).
 *
 * Approach: force-downgrade androidx.compose.compiler:compiler to 1.5.14
 * (the version compatible with Kotlin 1.9.24) at the project level so it
 * applies to ALL modules including expo-modules-core.
 *
 * Also sets kotlinCompilerExtensionVersion on the app's composeOptions.
 */

const { withAppBuildGradle, withProjectBuildGradle } = require('@expo/config-plugins');

module.exports = (config) => {
  // 1. Force the Compose Compiler dependency to 1.5.14 at the project level
  config = withProjectBuildGradle(config, (mod) => {
    let buildGradle = mod.modResults.contents;
    if (!buildGradle.includes('force.*compose.compiler') && !buildGradle.includes('androidx.compose.compiler:compiler')) {
      // Inject a force block into the buildscript's dependencies OR the allprojects
      // The cleanest: add to the allprojects repositories { } block as a resolutionStrategy
      // Look for "allprojects {" or just append before the final closing brace
      const forceBlock = `
    configurations.all {
        resolutionStrategy {
            force 'androidx.compose.compiler:compiler:1.5.14'
        }
    }`;
      // Insert after "allprojects {" if it exists; otherwise wrap it
      if (/^allprojects\s*{/m.test(buildGradle)) {
        buildGradle = buildGradle.replace(
          /^allprojects\s*{/m,
          'allprojects {' + forceBlock
        );
      } else {
        // Append a new allprojects block
        buildGradle += '\nallprojects {' + forceBlock + '\n}\n';
      }
    }
    mod.modResults.contents = buildGradle;
    return mod;
  });

  // 2. Also pin kotlinCompilerExtensionVersion in the app's composeOptions
  config = withAppBuildGradle(config, (mod) => {
    let buildGradle = mod.modResults.contents;
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
    mod.modResults.contents = buildGradle;
    return mod;
  });

  return config;
};
