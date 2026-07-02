/**
 * Custom Expo config plugin — adds gradle properties needed for the build.
 *
 * - Adds `expo.modules.core.suppressKotlinVersionCompatibilityCheck=true`
 *   to android/gradle.properties (works around the Kotlin 1.9.24 vs 1.9.25
 *   mismatch between Expo SDK 52 and expo-modules-core).
 */

const { withGradleProperties } = require('@expo/config-plugins');

module.exports = (config) => {
  return withGradleProperties(config, (mod) => {
    const props = mod.modResults;
    // Remove any existing entry with the same key (idempotent)
    const filtered = props.filter(p =>
      !(p.type === 'property' &&
        p.key === 'expo.modules.core.suppressKotlinVersionCompatibilityCheck')
    );
    // Add ours
    filtered.push({
      type: 'property',
      key: 'expo.modules.core.suppressKotlinVersionCompatibilityCheck',
      value: 'true',
    });
    mod.modResults = filtered;
    return mod;
  });
};
