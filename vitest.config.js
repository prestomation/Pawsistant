import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'jsdom',
    globals: true,
    include: [
      'tests/frontend/**/*.test.js',
      'custom_components/pawsistant/frontend/test/**/*.test.js',
    ],
  },
});