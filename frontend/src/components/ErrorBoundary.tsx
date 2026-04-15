import { Component, type ErrorInfo, type ReactNode } from 'react'
import { AlertCircle, RefreshCw } from 'lucide-react'

interface Props {
  children: ReactNode
  fallback?: ReactNode
  onError?: (error: Error, info: ErrorInfo) => void
}

interface State {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[ErrorBoundary]', error, info.componentStack)
    this.props.onError?.(error, info)
  }

  private handleReset = () => {
    this.setState({ hasError: false, error: null })
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback
      return (
        <div className="error-boundary-fallback">
          <AlertCircle size={32} />
          <p className="error-boundary-title">Something went wrong</p>
          {this.state.error && (
            <details className="error-boundary-details">
              <summary>Details</summary>
              <code>{this.state.error.message}</code>
            </details>
          )}
          <button className="error-boundary-retry" onClick={this.handleReset}>
            <RefreshCw size={14} />
            Try again
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
