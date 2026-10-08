import { Component } from 'react'

// One page failing must not blank the whole app: show a message and keep the navigation.
export default class ErrorBoundary extends Component {
  state = { error: null }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    console.error('Page crashed', error, info.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-5 text-sm text-red-800" role="alert">
        <p className="font-medium">This page ran into a problem.</p>
        <p className="mt-1">Your data is safe. Try another page or reload.</p>
        <button type="button" className="mt-3 rounded-lg border border-red-200 bg-white px-3 py-1.5 font-medium" onClick={() => window.location.reload()}>
          Reload
        </button>
      </div>
    )
  }
}
