import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { BriefcaseBusiness, IdCard, Lock, Mail, User } from 'lucide-react';
import apiService from '../services/apiService';
import { BUSINESS_UNITS } from '../contexts/AuthContext';
import ShellkodeLogo from './ShellkodeLogo';
import './Login.css';
import './ShellkodeLogo.css';

const Signup: React.FC = () => {
  const navigate = useNavigate();
  const [form, setForm] = useState({
    first_name: '', last_name: '', email: '', employee_id: '', business_unit: '',
    password: '', confirm_password: '',
  });
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [resending, setResending] = useState(false);
  const [verificationAttempted, setVerificationAttempted] = useState(false);
  const update = (field: keyof typeof form, value: string) => setForm(current => ({ ...current, [field]: value }));

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError('');
    setMessage('');
    if (!form.email.toLowerCase().endsWith('@shellkode.com')) return setError('Email address must end with @shellkode.com');
    if (form.password.length < 6) return setError('Password must contain at least 6 characters');
    if (form.password !== form.confirm_password) return setError('Passwords do not match');
    try {
      setLoading(true);
      const response = await apiService.signup({
        ...form,
        employee_id: Number(form.employee_id),
      });
      setVerificationAttempted(Boolean(response.verification_attempted));
      setMessage(response.message || 'Account created. Check your email to verify your account.');
    } catch (caught) {
      if ((caught as Error & { verificationAttempted?: boolean }).verificationAttempted) {
        setVerificationAttempted(true);
      }
      setError(caught instanceof Error ? caught.message : 'Unable to create account');
    } finally {
      setLoading(false);
    }
  };

  const resend = async () => {
    if (!form.email) return setError('Enter your ShellKode email address first');
    try {
      setResending(true); setError('');
      const response = await apiService.resendVerification(form.email);
      setMessage(response.message || 'Verification email sent.');
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to resend verification');
    } finally {
      setResending(false);
    }
  };

  return <div className="login-container">
    <div className="login-left">
      <div className="login-content">
        <div className="brand-section"><ShellkodeLogo size="large" /></div>
        <div className="content-section">
          <h1>Join the SOW Management Portal</h1>
          <p>Create your verified ShellKode account to securely build and manage Statements of Work.</p>
          <div className="features-list">
            <div className="feature-item"><div className="feature-icon"><BriefcaseBusiness className="icon" /></div><div className="feature-content"><h3>Business Unit Access</h3><p>Your initial access is assigned to the business unit selected here.</p></div></div>
            <div className="feature-item"><div className="feature-icon"><Mail className="icon" /></div><div className="feature-content"><h3>Verified Accounts</h3><p>Access begins only after verification through your ShellKode email.</p></div></div>
          </div>
        </div>
      </div>
    </div>
    <div className="login-right signup-right">
      <div className="login-card signup-card">
        <div className="login-header"><h2>Create Account</h2><p>Use your official ShellKode details</p></div>
        <form onSubmit={submit} className="login-form">
          <div className="auth-form-grid">
            <label className="form-group"><span>First Name <span className="required-asterisk">*</span></span><div className="input-group"><User className="input-icon" /><input className="login-input" required value={form.first_name} onChange={e => update('first_name', e.target.value)} /></div></label>
            <label className="form-group"><span>Last Name <span className="required-asterisk">*</span></span><div className="input-group"><User className="input-icon" /><input className="login-input" required value={form.last_name} onChange={e => update('last_name', e.target.value)} /></div></label>
            <label className="form-group auth-span"><span>Email Address <span className="required-asterisk">*</span></span><div className="input-group"><Mail className="input-icon" /><input className="login-input" type="email" placeholder="name@shellkode.com" required value={form.email} onChange={e => update('email', e.target.value)} /></div></label>
            <label className="form-group"><span>Employee ID <span className="required-asterisk">*</span></span><div className="input-group employee-id-group"><IdCard className="input-icon" /><span className="employee-id-prefix" aria-hidden="true">SK-</span><input className="login-input" type="number" inputMode="numeric" min="1" step="1" required value={form.employee_id} onKeyDown={event => ['e', 'E', '+', '-', '.'].includes(event.key) && event.preventDefault()} onChange={e => update('employee_id', e.target.value.replace(/\D/g, ''))} /></div></label>
            <label className="form-group"><span>Business Unit <span className="required-asterisk">*</span></span><div className="input-group"><BriefcaseBusiness className="input-icon" /><select className="login-input" required value={form.business_unit} onChange={e => update('business_unit', e.target.value)}><option value="">Select business unit</option>{BUSINESS_UNITS.map(unit => <option key={unit}>{unit}</option>)}</select></div></label>
            <label className="form-group"><span>Password <span className="required-asterisk">*</span></span><div className="input-group"><Lock className="input-icon" /><input className="login-input" type="password" minLength={6} required value={form.password} onChange={e => update('password', e.target.value)} /></div></label>
            <label className="form-group"><span>Confirm Password <span className="required-asterisk">*</span></span><div className="input-group"><Lock className="input-icon" /><input className="login-input" type="password" minLength={6} required value={form.confirm_password} onChange={e => update('confirm_password', e.target.value)} /></div></label>
          </div>
          {error && <div className="error-message">{error}</div>}
          {message && <div className="auth-success-message">{message}</div>}
          {!message && <button className="login-button" disabled={loading}>{loading ? 'Creating Account...' : 'Create Account'}</button>}
        </form>
        <div className="login-footer">
          <p>Already verified? <button type="button" className="auth-text-link" onClick={() => navigate('/login')}>Sign in</button></p>
          {verificationAttempted && <p>Didn't receive the email? <button type="button" className="auth-text-link" disabled={resending} onClick={resend}>{resending ? 'Sending...' : 'Resend verification'}</button></p>}
        </div>
      </div>
    </div>
  </div>;
};

export default Signup;
