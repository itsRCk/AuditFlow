import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';

type Theme = 'light' | 'dark';
const storageKey = 'auditflow.theme';
const ThemeContext = createContext<{ theme: Theme; toggleTheme: () => void } | null>(null);

function storedTheme(): Theme | null {
  try {
    const value = localStorage.getItem(storageKey);
    return value === 'light' || value === 'dark' ? value : null;
  } catch {
    return null;
  }
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(() =>
    document.documentElement.classList.contains('dark') ? 'dark' : 'light',
  );

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark');
    document.documentElement.style.colorScheme = theme;
    document
      .querySelector('meta[name="theme-color"]')
      ?.setAttribute('content', theme === 'dark' ? '#000000' : '#ffffff');
  }, [theme]);

  useEffect(() => {
    const system = matchMedia('(prefers-color-scheme: dark)');
    const syncSystem = () => {
      if (!storedTheme()) setTheme(system.matches ? 'dark' : 'light');
    };
    const syncStorage = (event: StorageEvent) => {
      if (event.key === storageKey) {
        setTheme(storedTheme() ?? (system.matches ? 'dark' : 'light'));
      }
    };
    system.addEventListener('change', syncSystem);
    window.addEventListener('storage', syncStorage);
    return () => {
      system.removeEventListener('change', syncSystem);
      window.removeEventListener('storage', syncStorage);
    };
  }, []);

  function toggleTheme() {
    const next = theme === 'light' ? 'dark' : 'light';
    try {
      localStorage.setItem(storageKey, next);
    } catch {
      // The toggle still works when browser storage is unavailable.
    }
    setTheme(next);
  }

  return <ThemeContext.Provider value={{ theme, toggleTheme }}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) throw new Error('useTheme must be used within ThemeProvider');
  return context;
}
