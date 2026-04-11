import virtual from '@rollup/plugin-virtual';
import { readFileSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

// Read CARD_VERSION from const.py — single source of truth
const constPy = resolve(dirname(fileURLToPath(import.meta.url)), '../const.py');
let CARD_VERSION = '0.0.0';
try {
  const contents = readFileSync(constPy, 'utf8');
  const versionMatch = contents.match(/CARD_VERSION\s*=\s*"([^"]+)"/);
  if (versionMatch) {
    CARD_VERSION = versionMatch[1];
  } else {
    console.warn('Warning: CARD_VERSION not found in const.py, using default 0.0.0');
  }
} catch (err) {
  console.error(`Error reading CARD_VERSION from ${constPy}:`, err.message);
  throw new Error(`Failed to read version from const.py: ${err.message}`);
}

export default {
  input: 'src/index.js',
  output: {
    file: 'pawsistant-card.js',
    format: 'iife',
    // Single global variable — HA loads this as a plain <script>
    name: 'PawsistantCardBundle',
    banner: `/**\n * Pawsistant Card — All-in-one pet activity dashboard for Home Assistant\n * Bundled with the Pawsistant integration — no manual setup required.\n * Version: ${CARD_VERSION}\n * Built: ${new Date().toISOString().split('T')[0]}\n */`,
  },
  plugins: [
    virtual({
      // Inject version from const.py at build time
      'card-version': `export const CARD_VERSION = '${CARD_VERSION}';`,
    }),
  ],
};