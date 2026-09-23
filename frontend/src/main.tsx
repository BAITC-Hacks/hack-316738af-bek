import { Component, StrictMode, type ErrorInfo, type ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import './styles.css';

class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Qurylym UI error', error.name, info.componentStack);
  }
  render() {
    return this.state.failed ? (
      <main className="fatal-error">
        <h1>Бетті көрсету мүмкін болмады</h1>
        <p>Сервердегі талдау сақталады. Бетті жаңартып көріңіз.</p>
        <button className="button primary" onClick={() => location.reload()}>
          Бетті жаңарту
        </button>
      </main>
    ) : (
      this.props.children
    );
  }
}
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>,
);
