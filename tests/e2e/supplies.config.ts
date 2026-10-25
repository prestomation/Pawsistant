/** Config for the supplies screenshot capture (see supplies.capture.ts). */
import baseConfig from './playwright.config';

export default {
  ...baseConfig,
  testDir: '.',
  testMatch: 'supplies.capture.ts',
};
