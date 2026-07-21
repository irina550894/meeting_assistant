import type { TelegramTheme } from "./types";

type ThemeParams = {
  bg_color?: string;
  text_color?: string;
  button_color?: string;
  button_text_color?: string;
  secondary_bg_color?: string;
};

export type TelegramWebApp = {
  initData: string;
  initDataUnsafe?: {
    user?: {
      id?: number;
      first_name?: string;
      last_name?: string;
      username?: string;
      language_code?: string;
    };
  };
  colorScheme?: TelegramTheme;
  themeParams?: ThemeParams;
  ready: () => void;
  expand: () => void;
  enableClosingConfirmation?: () => void;
  openLink?: (url: string) => void;
  onEvent?: (eventType: string, eventHandler: () => void) => void;
  offEvent?: (eventType: string, eventHandler: () => void) => void;
  BackButton?: {
    show: () => void;
    hide: () => void;
    onClick: (handler: () => void) => void;
    offClick: (handler: () => void) => void;
  };
  MainButton?: {
    setParams: (params: { text: string; is_visible?: boolean; is_active?: boolean }) => void;
    show: () => void;
    hide: () => void;
  };
};

declare global {
  interface Window {
    Telegram?: {
      WebApp?: TelegramWebApp;
    };
  }
}

export function telegramApp(): TelegramWebApp | null {
  return window.Telegram?.WebApp ?? null;
}

export function initTelegramShell(): TelegramWebApp | null {
  const app = telegramApp();
  if (!app) {
    document.documentElement.dataset.telegram = "preview";
    return null;
  }

  app.ready();
  app.expand();
  app.enableClosingConfirmation?.();
  applyTelegramTheme(app);
  app.onEvent?.("themeChanged", () => applyTelegramTheme(app));
  app.onEvent?.("viewportChanged", () => document.documentElement.style.setProperty("--vh", "1vh"));
  return app;
}

export function applyTelegramTheme(app: TelegramWebApp): void {
  document.documentElement.dataset.theme = app.colorScheme ?? "light";

  const theme = app.themeParams ?? {};
  setCssVar("--tg-bg", theme.bg_color);
  setCssVar("--tg-text", theme.text_color);
  setCssVar("--tg-button", theme.button_color);
  setCssVar("--tg-button-text", theme.button_text_color);
  setCssVar("--tg-secondary-bg", theme.secondary_bg_color);
}

function setCssVar(name: string, value?: string): void {
  if (value) {
    document.documentElement.style.setProperty(name, value);
  }
}
