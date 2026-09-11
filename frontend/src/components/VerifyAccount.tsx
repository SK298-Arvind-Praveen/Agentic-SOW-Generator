import React, { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { CheckCircle2, MailCheck, XCircle } from 'lucide-react';
import apiService from '../services/apiService';
import ShellkodeLogo from './ShellkodeLogo';
import './Login.css';
import './ShellkodeLogo.css';

const VerifyAccount: React.FC = () => {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [state, setState] = useState<'working' | 'success' | 'error'>('working');
  const [message, setMessage] = useState('Verifying your account...');

  useEffect(() => {
    const token = params.get('token');
    if (!token) {
      setState('error'); setMessage('Verification link is missing its token.'); return;
    }
    apiService.verifyAccount(token)
      .then(response => { setState('success'); setMessage(response.message || 'Account verified.'); })
      .catch(error => { setState('error'); setMessage(error instanceof Error ? error.message : 'Unable to verify account'); });
  }, [params]);

  return <div className="login-container auth-centered">
    <div className="login-card verification-card">
      <ShellkodeLogo size="large" />
      <div className={`verification-icon ${state}`}>
        {state === 'working' ? <MailCheck /> : state === 'success' ? <CheckCircle2 /> : <XCircle />}
      </div>
      <h2>{state === 'working' ? 'Verifying Account' : state === 'success' ? 'Account Verified' : 'Verification Failed'}</h2>
      <p>{message}</p>
      {state !== 'working' && <button className="login-button" onClick={() => navigate('/login')}>Go to Sign In</button>}
    </div>
  </div>;
};

export default VerifyAccount;
