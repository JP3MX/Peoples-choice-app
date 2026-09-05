import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.jp3aviation.peopleschoice',
  appName: 'Squawk King IA - Peoples Choice',
  webDir: 'build',
  plugins: {
    // The backend has no CORS headers configured, so the in-app WebView
    // (origin https://localhost) blocks every XHR/fetch to it by default.
    // Routing requests through Capacitor's native HTTP layer bypasses
    // browser CORS enforcement entirely.
    CapacitorHttp: {
      enabled: true,
    },
  },
};

export default config;
