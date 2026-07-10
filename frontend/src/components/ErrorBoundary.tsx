import { Component, type ErrorInfo, type ReactNode } from 'react'

interface Props { children: ReactNode }
interface State { error: Error | null }

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[ErrorBoundary]', error, info.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children

    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-stone-950 text-stone-300 p-6">
        <div className="max-w-md text-center">
          <h1 className="text-2xl font-bold text-red-400 mb-3">Algo deu errado</h1>
          <p className="text-sm text-stone-500 mb-6 break-all font-mono">
            {this.state.error.message}
          </p>
          <button
            onClick={() => this.setState({ error: null })}
            className="px-6 py-2.5 rounded-xl text-sm font-semibold bg-amber-600 text-stone-50
                       hover:bg-amber-500 transition-colors"
          >
            Tentar novamente
          </button>
        </div>
      </div>
    )
  }
}
