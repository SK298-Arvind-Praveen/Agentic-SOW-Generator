import React, { useState } from 'react';
import { Navigate, useSearchParams } from 'react-router-dom';
import apiService from '../services/apiService';
import { useAuth } from '../contexts/AuthContext';

import ShellkodeLogo from './ShellkodeLogo';
import './Login.css';
import './ShellkodeLogo.css';

const Login: React.FC = () => {
  const [isLoading, setIsLoading] = useState(false);
  const { isAuthenticated, isLoading: checking, sessionError } = useAuth();
  const [params] = useSearchParams();
  const messages: Record<string, string> = {
    GOOGLE_NOT_CONFIGURED: 'Google sign-in is not configured yet. Contact your administrator.',
    GOOGLE_CANCELLED: 'Google sign-in was cancelled. You can try again.',
    GOOGLE_STATE_INVALID: 'This sign-in attempt expired. Please start again.',
    GOOGLE_IDENTITY_REJECTED: 'Use an active Shellkode Google Workspace account to sign in.',
    AUTH_SERVICE_UNAVAILABLE: 'Sign-in is temporarily unavailable. Please try again shortly.',
  };
  const error = messages[params.get('error') || ''] || (params.has('error') ? 'Unable to sign in. Please try again.' : sessionError);
  if (isAuthenticated) return <Navigate to="/" replace />;

  return (
    <main className="login-container login-centered">
      <section className="login-welcome" aria-labelledby="login-title">
        <ShellkodeLogo size="large" className="login-brand" />
        <h1 id="login-title">SOW Creation Portal</h1>
        <p className="login-intro">Sign in with your Shellkode Google account to continue.</p>
        {error && <div className="error-message" role="alert">{error}</div>}
        <button type="button" className="google-login-button" disabled={isLoading || checking}
          onClick={() => { setIsLoading(true); window.location.assign(apiService.googleSignInUrl()); }}>
          <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
            <path fill="#4285F4" d="M21.6 12.23c0-.71-.06-1.39-.18-2.05H12v3.88h5.38a4.6 4.6 0 0 1-2 3.02v2.51h3.24c1.9-1.75 2.98-4.33 2.98-7.36Z" />
            <path fill="#34A853" d="M12 22c2.7 0 4.96-.9 6.62-2.41l-3.24-2.51c-.9.6-2.05.96-3.38.96-2.6 0-4.81-1.76-5.6-4.12H3.06v2.59A10 10 0 0 0 12 22Z" />
            <path fill="#FBBC05" d="M6.4 13.92a6 6 0 0 1 0-3.84V7.49H3.06a10 10 0 0 0 0 9.02l3.34-2.59Z" />
            <path fill="#EA4335" d="M12 5.96c1.47 0 2.79.51 3.83 1.51l2.87-2.87A9.6 9.6 0 0 0 12 2a10 10 0 0 0-8.94 5.49l3.34 2.59C7.19 7.72 9.4 5.96 12 5.96Z" />
          </svg>
          <span>{checking ? 'Checking your session…' : isLoading ? 'Opening Google…' : 'Continue with Google'}</span>
        </button>
      </section>
    </main>
  );
};

export default Login;
