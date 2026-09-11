import { useEffect, useState } from 'react';

const PREFIX = 'ez-ipo-';

// Same pattern as useTheme — remembers a filter/sort choice across reloads via
// localStorage, keyed per-caller so unrelated filters don't collide.
export function usePersistedState(key, defaultValue) {
  const storageKey = PREFIX + key;
  const [value, setValue] = useState(() => localStorage.getItem(storageKey) ?? defaultValue);

  useEffect(() => {
    localStorage.setItem(storageKey, value);
  }, [storageKey, value]);

  return [value, setValue];
}
