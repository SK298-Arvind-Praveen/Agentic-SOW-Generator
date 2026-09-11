import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Mail } from 'lucide-react';
import apiService from '../services/apiService';
import ShellkodeLogo from './ShellkodeLogo';
import './Login.css';
import './ShellkodeLogo.css';

const ForgotPassword: React.FC = () => {
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault(); setError('');
    try {
      setLoading(true);
      const response = await apiService.forgotPassword(email);
      setMessage(response.message);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to request a password reset');
    } finally { setLoading(false); }
  };

  return <div className="login-container auth-centered">
    <div className="login-card verification-card auth-action-card">
      <ShellkodeLogo size="large" />
      <div className="login-header"><h2>Reset Password</h2><p>Enter your ShellKode email address</p></div>
      <form onSubmit={submit} className="login-form">
        <label className="form-group"><span>Email Address</span><div className="input-group"><Mail className="input-icon" /><input className="login-input" type="email" placeholder="name@shellkode.com" required value={email} onChange={event => setEmail(event.target.value)} /></div></label>
        {error && <div className="error-message">{error}</div>}
        {message && <div className="auth-success-message">{message}</div>}
        {!message && <button className="login-button" disabled={loading}>{loading ? 'Sending...' : 'Send Reset Link'}</button>}
      </form>
      <div className="login-footer"><p><button type="button" className="auth-text-link" onClick={() => navigate('/login')}>Back to sign in</button></p></div>
    </div>
  </div>;
};

export default ForgotPassword;
