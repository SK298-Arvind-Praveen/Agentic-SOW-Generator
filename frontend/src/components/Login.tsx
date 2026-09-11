import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { Lock, User } from 'lucide-react';
import ShellkodeLogo from './ShellkodeLogo';
import './Login.css';
import './ShellkodeLogo.css';

const Login: React.FC = () => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError('');

    const result = await login(username, password);
    if (result.success) navigate('/dashboard');
    else setError(result.error || 'Invalid email or password');
    setIsLoading(false);
  };

  return (
    <div className="login-container">
      {/* Left Side - Content */}
      <div className="login-left">
        <div className="login-content">
          <div className="brand-section">
            <ShellkodeLogo size="large" />
          </div>
          
          <div className="content-section">
            <h1>SOW Management Portal</h1>
            <p>Streamline your Statement of Work creation and management with our comprehensive solution.</p>
            
            <div className="features-list">
              <div className="feature-item">
                <div className="feature-icon">
                  <User className="icon" />
                </div>
                <div className="feature-content">
                  <h3>Client Management</h3>
                  <p>Organize and track all your client information in one place</p>
                </div>
              </div>
              
              <div className="feature-item">
                <div className="feature-icon">
                  <Lock className="icon" />
                </div>
                <div className="feature-content">
                  <h3>Secure Templates</h3>
                  <p>Professional SOW templates with enterprise-grade security</p>
                </div>
              </div>
            </div>
          </div>
          

        </div>
      </div>

      {/* Right Side - Login Form */}
      <div className="login-right">
        <div className="login-card">
          <div className="login-header">
            <h2>Welcome Back</h2>
            <p>Please sign in to continue</p>
          </div>

          <form onSubmit={handleSubmit} className="login-form">
            <div className="form-group">
              <label htmlFor="username">Email Address</label>
              <div className="input-group">
                <User className="input-icon" />
                <input
                  type="text"
                  id="username"
                  placeholder="your.email@company.com"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                  className="login-input"
                />
              </div>
            </div>

            <div className="form-group">
              <label htmlFor="password">Password</label>
              <div className="input-group">
                <Lock className="input-icon" />
                <input
                  type="password"
                  id="password"
                  placeholder="Enter your password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  className="login-input"
                />
              </div>
            </div>

            {error && <div className="error-message">{error}</div>}

            <button 
              type="submit" 
              className={`login-button ${isLoading ? 'loading' : ''}`}
              disabled={isLoading}
            >
              {isLoading ? 'Signing In...' : 'Sign In to Dashboard'}
            </button>
          </form>

          <div className="login-footer">
            <p><button type="button" className="auth-text-link" onClick={() => navigate('/forgot-password')}>Forgot password?</button></p>
            <p>New to the portal? <button type="button" className="auth-text-link" onClick={() => navigate('/signup')}>Create an account</button></p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Login;
