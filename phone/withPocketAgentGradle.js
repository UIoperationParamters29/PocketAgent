/**
 * Custom Expo config plugin — adds gradle properties needed for the build.
 *
 * - Adds `expo.modules.core.suppressKotlinVersionCompatibilityCheck=true`
 *   to android/gradle.properties (works around the Kotlin 1.9.24 vs 1.9.25
 *   mismatch between Expo SDK 52 and expo-modules-core).
 */

const { withProjectBuildGradle } = require('@expo/config-plugins');

const withGradleProperties = (config) => {
  return withProjectBuildGradle(config, (mod) => {
    const gradleBuild = mod.modResults;
    // Inject our extra properties at the end of the build.gradle (top-level)
    // Actually, we want gradle.properties — use a different approach below.
    return mod;
  });
};

// Simpler: use the withGradleProperties mod
const { withGradleProperties } = require('@expo/config-plugins');

module.exports = (config) => {
  return withGradleProperties(config, (mod) => {
    const props = mod.modResults;
    // Add our property if not present
    const exists = props.some(p =>
      p.type === 'property' &&
      p.key === 'expo.modules.core.suppressKotlinVersionCompatibilityCheck'
    );
    if (!exists) {
      props.push({
        type: 'property',
        key: 'expo.modules.core.suppressKotlinVersionCompatibilityCheck',
        value: 'true',
      });
    }
    return mod;
  });
};
