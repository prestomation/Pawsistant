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

declare class HaIconPicker extends HTMLElement { value?: string; }
declare class HaDialog extends HTMLElement { open?: boolean; heading?: string; }