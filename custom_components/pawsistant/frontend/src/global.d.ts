/* Type declarations for external modules */

declare module 'card-version' {
  export const CARD_VERSION: string;
}

interface Window {
  customCards?: Array<{
    type: string;
    name: string;
    description: string;
    preview?: boolean;
  }>;
}