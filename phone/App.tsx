/**
 * PocketAgent — root component.
 * Shows Onboarding on first run, then the main tab navigator (Chat / Files / Settings).
 */

import React, { useEffect, useState } from 'react';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaView, StyleSheet } from 'react-native';
import { NavigationContainer, DarkTheme } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { colors, typography } from './src/theme/colors';
import { isOnboarded } from './src/lib/secure-store';
import { OnboardingScreen } from './src/screens/OnboardingScreen';
import { ChatScreen } from './src/screens/ChatScreen';
import { FilesScreen } from './src/screens/FilesScreen';
import { SettingsScreen } from './src/screens/SettingsScreen';

const Tab = createBottomTabNavigator();

const navTheme = {
  ...DarkTheme,
  colors: {
    ...DarkTheme.colors,
    background: colors.bg,
    card: colors.surface,
    text: colors.text,
    border: colors.border,
    primary: colors.accent,
  },
};

export default function App() {
  const [onboarded, setOnboarded] = useState<boolean | null>(null);

  useEffect(() => {
    (async () => setOnboarded(await isOnboarded()))();
  }, []);

  if (onboarded === null) {
    // Splash while we check secure store
    return (
      <SafeAreaView style={styles.splash}>
        <StatusBar style="light" />
      </SafeAreaView>
    );
  }

  if (!onboarded) {
    return (
      <SafeAreaView style={styles.flex}>
        <StatusBar style="light" />
        <OnboardingScreen onDone={() => setOnboarded(true)} />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.flex}>
      <StatusBar style="light" />
      <NavigationContainer theme={navTheme}>
        <Tab.Navigator
          screenOptions={{
            headerShown: false,
            tabBarActiveTintColor: colors.accent,
            tabBarInactiveTintColor: colors.textTertiary,
            tabBarStyle: { backgroundColor: colors.surface, borderTopColor: colors.border, paddingBottom: 4, height: 56 },
            tabBarLabelStyle: { fontFamily: typography.sans, fontSize: 11, fontWeight: '500' },
          }}
        >
          <Tab.Screen name="Chat" component={ChatScreen} />
          <Tab.Screen name="Files" component={FilesScreen} />
          <Tab.Screen name="Settings">
            {() => <SettingsScreen onWiped={() => setOnboarded(false)} />}
          </Tab.Screen>
        </Tab.Navigator>
      </NavigationContainer>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: colors.bg },
  splash: { flex: 1, backgroundColor: colors.bg },
});
