import { useCallback, useEffect, useRef, useState } from 'react'
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
  Rocket,
  MessageSquare,
  FileCode,
  CheckCircle2,
  Wrench,
  FileText,
  Timer,
  Globe,
} from 'lucide-react'
import { useTheme } from '../hooks/useTheme'
import { useRotatingSlogan } from '../hooks/useRotatingSlogan'
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
  const { line1, line2, accent, visible: sloganVisible } = useRotatingSlogan()
  const [activeStep, setActiveStep] = useState(0)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  const [headerHidden, setHeaderHidden] = useState(false)
  const scrollRef = useRef({ lastY: 0, anchor: 0, direction: 'up' as 'up' | 'down' })
  const landingRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const HIDE_AFTER = 60
    const SHOW_AFTER = 5
    const handleScroll = () => {
      const y = window.scrollY
      const s = scrollRef.current

      if (y < 64) {
        setHeaderHidden(false)
        s.anchor = y
        s.direction = 'up'
      } else if (y > s.lastY) {
        if (s.direction === 'up') {
          s.anchor = y
          s.direction = 'down'
        }
        if (y - s.anchor > HIDE_AFTER) {
          setHeaderHidden(true)
          setMobileMenuOpen(false)
        }
      } else if (y < s.lastY) {
        if (s.direction === 'down') {
          s.anchor = y
          s.direction = 'up'
        }
        if (s.anchor - y > SHOW_AFTER) {
          setHeaderHidden(false)
        }
      }

      s.lastY = y
    }
    window.addEventListener('scroll', handleScroll, { passive: true })
    return () => window.removeEventListener('scroll', handleScroll)
  }, [])

  useEffect(() => {
    const root = landingRef.current
    if (!root) return
    const observer = new IntersectionObserver(
      entries => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            entry.target.classList.add('visible')
          }
        })
      },
      { threshold: 0.1, rootMargin: '0px 0px -40px 0px' }
    )
    root.querySelectorAll('.landing-reveal, .landing-reveal-card').forEach(el => observer.observe(el))
    return () => observer.disconnect()
  }, [])

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
    <div className="landing" ref={landingRef}>
      {/* Header */}
      <header className={`landing-header${headerHidden ? ' landing-header-hidden' : ''}`}>
        <a
          href="/"
          className="landing-header-logo"
          onClick={e => { e.preventDefault(); window.scrollTo({ top: 0, behavior: 'smooth' }) }}
        >
          <img src="/logo-on-light.svg" alt="AI Mentor" className="logo-light" />
          <img src="/logo-on-dark.svg" alt="AI Mentor" className="logo-dark" />
          <span>AI Mentor</span>
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
          <Link to="/kb">{t('landing.nav.kb')}</Link>
        </nav>

        <div className="landing-header-actions">
          <button className="landing-toggle-btn" onClick={toggleLang} aria-label={t('lang.toggle')}>
            {i18n.language?.startsWith('ru') ? 'RU' : 'EN'}
          </button>
          <button className="landing-toggle-btn" onClick={toggleTheme} aria-label={t('theme.toggle')}>
            {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
          </button>
          <Link to="/app" className="landing-btn-primary landing-header-cta">
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
        <nav className="landing-mobile-links">
          <a href="#problems" onClick={e => handleAnchorClick(e, 'problems')}>
            {t('landing.nav.problems')}
          </a>
          <a href="#goals" onClick={e => handleAnchorClick(e, 'goals')}>
            {t('landing.nav.goals')}
          </a>
          <a href="#how-it-works" onClick={e => handleAnchorClick(e, 'how-it-works')}>
            {t('landing.nav.howItWorks')}
          </a>
          <Link to="/kb" onClick={() => setMobileMenuOpen(false)}>
            {t('landing.nav.kb')}
          </Link>
        </nav>
        <div className="landing-mobile-divider" />
        <Link
          to="/app"
          className="landing-btn-primary landing-mobile-cta"
          onClick={() => setMobileMenuOpen(false)}
        >
          {t('landing.nav.openApp')}
          <ArrowRight size={16} />
        </Link>
      </div>

      {/* Hero */}
      <section className="landing-hero">
        <img src="/logo-on-light.svg" alt="" className="landing-hero-logo logo-light" />
        <img src="/logo-on-dark.svg" alt="" className="landing-hero-logo logo-dark" />
        <div className="landing-hero-badge">
          <Cpu size={14} />
          {t('landing.hero.badge')}
        </div>
        <h1 className="landing-hero-title">{t('landing.hero.title')}</h1>
        <p className={`landing-hero-slogan${sloganVisible ? '' : ' fading'}`}>{line1}</p>
        <div className="landing-hero-divider">
          <span /><span className="landing-hero-dot">·</span><span />
        </div>
        <p className={`landing-hero-subslogan${sloganVisible ? '' : ' fading'}`}>
          {line2}{' '}
          <em>{accent}</em>
        </p>
        <p className="landing-hero-description">{t('landing.hero.description')}</p>
        <div className="landing-hero-cta">
          <Link to="/app" className="landing-btn-primary">
            {t('landing.hero.cta')}
            <ArrowRight size={16} />
          </Link>
        </div>

        {/* Product mockup */}
        <div className="hero-mockup">
          <div className="hero-mockup-window">
            <div className="hero-mockup-titlebar">
              <div className="hero-mockup-dots">
                <span /><span /><span />
              </div>
              <span className="hero-mockup-url">ai-mentor.ru</span>
            </div>
            <div className="hero-mockup-body">
              <aside className="hero-mockup-sidebar">
                <div className="hero-mockup-sidebar-logo">
                  <img src="/logo-on-light.svg" alt="" className="logo-light" />
                  <img src="/logo-on-dark.svg" alt="" className="logo-dark" />
                  <span>AI Mentor</span>
                </div>
                <div className="hero-mockup-sidebar-nav">
                  <div className="hero-mockup-nav-item active"><MessageSquare size={14} /> {t('nav.chat')}</div>
                  <div className="hero-mockup-nav-item"><FileCode size={14} /> {t('nav.products')}</div>
                </div>
              </aside>
              <div className="hero-mockup-chat">
                <div className="hero-mockup-msg hero-mockup-msg--user">
                  <div className="hero-mockup-bubble">{t('landing.mockup.question')}</div>
                </div>
                <div className="hero-mockup-msg hero-mockup-msg--ai">
                  <div className="hero-mockup-bubble">
                    <p>{t('landing.mockup.answer')}</p>
                    <pre className="hero-mockup-code"><code>{`import requests
from requests.auth import HTTPDigestAuth

url = f"http://{host}/ISAPI/System/Video/inputs/channels"
r = requests.get(url, auth=HTTPDigestAuth(user, pwd))
channels = r.json()["VideoInputChannelList"]`}</code></pre>
                    <div className="hero-mockup-sources">
                      <CheckCircle2 size={12} />
                      <span>{t('landing.mockup.sources')}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Elevator Pitch */}
      <section className="landing-elevator-section landing-reveal">
        <div className="landing-elevator">
          <span className="landing-elevator-label">
            <Rocket size={14} />
            {t('landing.elevator.label')}
          </span>
          <p dangerouslySetInnerHTML={{ __html: t('landing.elevator.text') }} />
        </div>
      </section>

      {/* Problems Today */}
      <section className="landing-section" id="problems">
        <h2 className="landing-section-title landing-reveal">{t('landing.problems.title')}</h2>
        <div className="landing-cards">
          {PROBLEM_KEYS.map((key, i) => {
            const Icon = PROBLEM_ICONS[i]
            return (
              <div
                className="landing-card landing-card--warning landing-reveal-card"
                key={key}
                style={{ transitionDelay: `${i * 100}ms` }}
              >
                <div className="landing-card-icon landing-card-icon--warning">
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
        <h2 className="landing-section-title landing-reveal">{t('landing.goals.title')}</h2>
        <div className="landing-cards landing-cards-3">
          {GOAL_KEYS.map((key, i) => {
            const Icon = GOAL_ICONS[i]
            return (
              <div
                className="landing-card landing-card--success landing-reveal-card"
                key={key}
                style={{ transitionDelay: `${i * 100}ms` }}
              >
                <div className="landing-card-icon landing-card-icon--success">
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
      <section className="landing-section landing-reveal" id="how-it-works">
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

      {/* Metrics */}
      <section className="landing-metrics landing-reveal">
        <div className="landing-metrics-grid">
          <div className="landing-metric">
            <Wrench size={20} className="landing-metric-icon" />
            <span className="landing-metric-value">9</span>
            <span className="landing-metric-label">{t('landing.metrics.mcpTools')}</span>
          </div>
          <div className="landing-metric">
            <FileText size={20} className="landing-metric-icon" />
            <span className="landing-metric-value">12+</span>
            <span className="landing-metric-label">{t('landing.metrics.formats')}</span>
          </div>
          <div className="landing-metric">
            <Timer size={20} className="landing-metric-icon" />
            <span className="landing-metric-value">&lt;3s</span>
            <span className="landing-metric-label">{t('landing.metrics.responseTime')}</span>
          </div>
          <div className="landing-metric">
            <Globe size={20} className="landing-metric-icon" />
            <span className="landing-metric-value">30+</span>
            <span className="landing-metric-label">{t('landing.metrics.languages')}</span>
          </div>
        </div>
      </section>

      {/* Closing CTA */}
      <section className="landing-closing-cta landing-reveal">
        <h2>{t('landing.closingCta.title')}</h2>
        <p>{t('landing.closingCta.text')}</p>
        <Link to="/app" className="landing-btn-primary landing-closing-cta-btn">
          {t('landing.hero.cta')}
          <ArrowRight size={16} />
        </Link>
      </section>

      {/* Footer */}
      <footer className="landing-footer">
        <div className="landing-footer-grid">
          <div className="landing-footer-brand">
            <div className="landing-footer-logo">
              <img src="/logo-on-light.svg" alt="AI Mentor" className="logo-light" />
              <img src="/logo-on-dark.svg" alt="AI Mentor" className="logo-dark" />
              <span>AI Mentor</span>
            </div>
            <p className="landing-footer-tagline">{t('landing.footer.tagline')}</p>
          </div>
          <div className="landing-footer-col">
            <h4>{t('landing.footer.product')}</h4>
            <Link to="/app">{t('landing.footer.webChat')}</Link>
            <Link to="/kb">{t('landing.nav.kb')}</Link>
          </div>
          <div className="landing-footer-col">
            <h4>{t('landing.footer.resources')}</h4>
            <a href="#how-it-works" onClick={e => handleAnchorClick(e, 'how-it-works')}>
              {t('landing.nav.howItWorks')}
            </a>
            <Link to="/kb">{t('landing.footer.docs')}</Link>
          </div>
          <div className="landing-footer-col">
            <h4>{t('landing.footer.company')}</h4>
            <a href={AUTHOR_LINKEDIN} target="_blank" rel="noopener noreferrer">
              LinkedIn
            </a>
          </div>
        </div>
        <div className="landing-footer-bottom">
          {t('landing.footer.copyright')} · {t('landing.footer.by')}{' '}
          <a href={AUTHOR_LINKEDIN} target="_blank" rel="noopener noreferrer">
            {t('landing.footer.author')}
          </a>
        </div>
      </footer>
    </div>
  )
}
