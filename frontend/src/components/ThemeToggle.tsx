import { Moon, Sun } from 'lucide-react'

interface Props {
  theme: 'light' | 'dark'
  onToggle: () => void
}

export function ThemeToggle({ theme, onToggle }: Props) {
  return (
    <button className="theme-toggle" onClick={onToggle} title="Toggle theme">
      {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
    </button>
  )
}
