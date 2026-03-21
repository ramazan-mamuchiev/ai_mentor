import { useCallback, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  FileWarning,
  GitBranch,
  BrainCircuit,
  CodeXml,
  Database,
  ShieldCheck,
  MessageSquareCode,
  Languages,
  Zap,
  Upload,
  RefreshCw,
  HardDrive,
  Cpu,
  Terminal,
  Menu,
  X,
  ArrowRight,
  Sun,
  Moon,
  Globe,
  Rocket,
} from 'lucide-react'
import { useTheme } from '../hooks/useTheme'
import '../styles/landing.css'

const AUTHOR_LINKEDIN = 'https://www.linkedin.com/in/aleh-vaitsekhovich-067557a9/'

const PROBLEM_ICONS = [FileWarning, GitBranch, BrainCircuit, CodeXml] as const
const PROBLEM_KEYS = ['formatChaos', 'noVersioning', 'aiCantHelp', 'codingBlind'] as const

const GOAL_ICONS = [Database, ShieldCheck, MessageSquareCode, MessageSquareCode, Languages, Zap] as const
const GOAL_KEYS = ['storage', 'audit', 'aiCode', 'aiChat', 'multilingual', 'speedup'] as const

const STEP_ICONS = [Upload, RefreshCw, HardDrive, Cpu, Terminal] as const
const STEP_KEYS = ['step1', 'step2', 'step3', 'step4', 'step5'] as const

export function LandingPage() {
  const { t, i18n } = useTranslation()
  const { theme, toggle: toggleTheme } = useTheme()
  const [activeStep, setActiveStep] = useState(0)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  const toggleLang = () => {
    const next = i18n.language === 'ru' ? 'en' : 'ru'
    i18n.changeLanguage(next)
  }

  const scrollTo = useCallback((id: string) => {
    setMobileMenuOpen(false)
    setTimeout(() => {
      const el = document.getElementById(id)
      if (el) {
        const headerHeight = 64
        const y = el.getBoundingClientRect().top + window.scrollY - headerHeight
        window.scrollTo({ top: y, behavior: 'smooth' })
      }
    }, 10)
  }, [])

  const handleAnchorClick = useCallback((e: React.MouseEvent<HTMLAnchorElement>, id: string) => {
    e.preventDefault()
    e.stopPropagation()
    scrollTo(id)
  }, [scrollTo])

  return (
    <div className="landing">
      {/* Header */}
      <header className="landing-header">
        <a
          href="/"
          className="landing-header-logo"
          onClick={e => { e.preventDefault(); window.scrollTo({ top: 0, behavior: 'smooth' }) }}
        >
          <img src="/logo-on-light.svg" alt="IPCodex" className="logo-light" />
          <img src="/logo-on-dark.svg" alt="IPCodex" className="logo-dark" />
          <span>IPCodex</span>
        </a>

        <nav className="landing-nav">
          <a href="#problems" onClick={e => handleAnchorClick(e, 'problems')}>
            {t('landing.nav.problems')}
          </a>
          <a href="#goals" onClick={e => handleAnchorClick(e, 'goals')}>
            {t('landing.nav.goals')}
          </a>
          <a href="#how-it-works" onClick={e => handleAnchorClick(e, 'how-it-works')}>
            {t('landing.nav.howItWorks')}
          </a>
        </nav>

        <div className="landing-header-actions">
          <button className="landing-btn-ghost" onClick={toggleLang} aria-label={t('lang.toggle')}>
            <Globe size={18} />
          </button>
          <button className="landing-btn-ghost" onClick={toggleTheme} aria-label={t('theme.toggle')}>
            {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
          </button>
          <Link to="/app" className="landing-btn-primary">
            {t('landing.nav.openApp')}
            <ArrowRight size={16} />
          </Link>
          <button
            className="landing-hamburger"
            onClick={() => setMobileMenuOpen(v => !v)}
            aria-label="Menu"
          >
            {mobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
          </button>
        </div>
      </header>

      {/* Mobile nav overlay */}
      <div className={`landing-mobile-nav${mobileMenuOpen ? ' open' : ''}`}>
        <a href="#problems" onClick={e => handleAnchorClick(e, 'problems')}>
          {t('landing.nav.problems')}
        </a>
        <a href="#goals" onClick={e => handleAnchorClick(e, 'goals')}>
          {t('landing.nav.goals')}
        </a>
        <a href="#how-it-works" onClick={e => handleAnchorClick(e, 'how-it-works')}>
          {t('landing.nav.howItWorks')}
        </a>
        <Link to="/app" className="landing-btn-primary" style={{ marginTop: 12, justifyContent: 'center' }}>
          {t('landing.nav.openApp')}
          <ArrowRight size={16} />
        </Link>
      </div>

      {/* Hero */}
      <section className="landing-hero">
        <div className="landing-hero-badge">
          <Cpu size={14} />
          {t('landing.hero.badge')}
        </div>
        <h1 className="landing-hero-title">{t('landing.hero.title')}</h1>
        <p className="landing-hero-slogan">{t('landing.hero.slogan')}</p>
        <p className="landing-hero-subslogan">{t('landing.hero.subslogan')}</p>
        <p className="landing-hero-description">{t('landing.hero.description')}</p>
        <div className="landing-hero-cta">
          <Link to="/app" className="landing-btn-primary">
            {t('landing.hero.cta')}
            <ArrowRight size={16} />
          </Link>
        </div>
        <p className="landing-hero-author">
          {t('landing.hero.author')}{' '}
          <a href={AUTHOR_LINKEDIN} target="_blank" rel="noopener noreferrer">
            {t('landing.footer.author')}
          </a>
        </p>
      </section>

      {/* Elevator Pitch */}
      <section className="landing-section">
        <div className="landing-elevator">
          <span className="landing-elevator-label">
            <Rocket size={14} />
            {t('landing.elevator.label')}
          </span>
          <p dangerouslySetInnerHTML={{ __html: t('landing.elevator.text') }} />
        </div>
      </section>

      {/* Why This Matters */}
      <section className="landing-section" id="why">
        <h2 className="landing-section-title">{t('landing.why.title')}</h2>
        <p className="landing-section-text">{t('landing.why.text')}</p>
      </section>

      {/* Problems Today */}
      <section className="landing-section" id="problems">
        <h2 className="landing-section-title">{t('landing.problems.title')}</h2>
        <div className="landing-cards">
          {PROBLEM_KEYS.map((key, i) => {
            const Icon = PROBLEM_ICONS[i]
            return (
              <div className="landing-card" key={key}>
                <div className="landing-card-icon">
                  <Icon size={22} />
                </div>
                <h3>{t(`landing.problems.${key}.title`)}</h3>
                <p>{t(`landing.problems.${key}.text`)}</p>
              </div>
            )
          })}
        </div>
      </section>

      {/* Goals */}
      <section className="landing-section" id="goals">
        <h2 className="landing-section-title">{t('landing.goals.title')}</h2>
        <div className="landing-cards landing-cards-3">
          {GOAL_KEYS.map((key, i) => {
            const Icon = GOAL_ICONS[i]
            return (
              <div className="landing-card" key={key}>
                <div className="landing-card-icon">
                  <Icon size={22} />
                </div>
                <h3>{t(`landing.goals.${key}.title`)}</h3>
                <p>{t(`landing.goals.${key}.text`)}</p>
              </div>
            )
          })}
        </div>
      </section>

      {/* How It Works */}
      <section className="landing-section" id="how-it-works">
        <h2 className="landing-section-title">{t('landing.howItWorks.title')}</h2>
        <p className="landing-section-text">{t('landing.howItWorks.subtitle')}</p>

        <div className="landing-steps">
          {STEP_KEYS.map((key, i) => {
            const Icon = STEP_ICONS[i]
            return (
              <div
                className={`landing-step${activeStep === i ? ' active' : ''}`}
                key={key}
                onClick={() => setActiveStep(i)}
              >
                <div className="landing-step-number">
                  <Icon size={20} />
                </div>
                {i < STEP_KEYS.length - 1 && <div className="landing-step-connector" />}
                <h4>{t(`landing.howItWorks.${key}.title`)}</h4>
              </div>
            )
          })}
        </div>

        <div className="landing-step-detail">
          <h4>
            {t('landing.howItWorks.step', { defaultValue: 'Step' })} {activeStep + 1}:{' '}
            {t(`landing.howItWorks.${STEP_KEYS[activeStep]}.title`)}
          </h4>
          <p>{t(`landing.howItWorks.${STEP_KEYS[activeStep]}.text`)}</p>
          <pre className="landing-code-block">
            <code>{t(`landing.howItWorks.${STEP_KEYS[activeStep]}.code`)}</code>
          </pre>
        </div>
      </section>

      {/* Footer */}
      <footer className="landing-footer">
        {t('landing.footer.copyright')} · {t('landing.footer.by')}{' '}
        <a href={AUTHOR_LINKEDIN} target="_blank" rel="noopener noreferrer">
          {t('landing.footer.author')}
        </a>
      </footer>
    </div>
  )
}
