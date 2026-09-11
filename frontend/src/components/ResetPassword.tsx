import React, { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Lock } from 'lucide-react';
import apiService from '../services/apiService';
import ShellkodeLogo from './ShellkodeLogo';
import './Login.css';
import './ShellkodeLogo.css';

const ResetPassword: React.FC = () => {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault(); setError('');
    const token = params.get('token') || '';
    if (!token) return setError('Password reset link is missing its token.');
    if (password.length < 6) return setError('Password must contain at least 6 characters');
    if (password !== confirmation) return setError('Passwords do not match');
    try {
      setLoading(true);
      const response = await apiService.resetPassword({ token, password, confirm_password: confirmation });
      setMessage(response.message);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to reset password');
    } finally { setLoading(false); }
  };

  return <div className="login-container auth-centered">
    <div className="login-card verification-card auth-action-card">
      <ShellkodeLogo size="large" />
      <div className="login-header"><h2>Choose a New Password</h2><p>Use at least six characters</p></div>
      <form onSubmit={submit} className="login-form">
        <label className="form-group"><span>New Password</span><div className="input-group"><Lock className="input-icon" /><input className="login-input" type="password" minLength={6} required value={password} onChange={event => setPassword(event.target.value)} /></div></label>
        <label className="form-group"><span>Confirm Password</span><div className="input-group"><Lock className="input-icon" /><input className="login-input" type="password" minLength={6} required value={confirmation} onChange={event => setConfirmation(event.target.value)} /></div></label>
        {error && <div className="error-message">{error}</div>}
        {message && <div className="auth-success-message">{message}</div>}
        {!message && <button className="login-button" disabled={loading}>{loading ? 'Updating...' : 'Update Password'}</button>}
      </form>
      <div className="login-footer"><p><button type="button" className="auth-text-link" onClick={() => navigate('/login')}>{message ? 'Continue to sign in' : 'Back to sign in'}</button></p></div>
    </div>
  </div>;
};

export default ResetPassword;
