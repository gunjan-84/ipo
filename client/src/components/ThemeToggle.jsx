import { useTheme } from '../useTheme';

export default function ThemeToggle() {
  const [theme, setTheme] = useTheme();
  const isDark = theme === 'dark';

  return (
    <button
      type="button"
      className="secondary-btn theme-toggle-btn"
      title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      onClick={() => setTheme(isDark ? 'light' : 'dark')}
    >
      {isDark ? '☾' : '☀'}
    </button>
  );
}
