import React, { useEffect, useState } from 'react';
import { Outlet, useNavigate } from 'react-router-dom';
import { User, ChevronDown, Database, FileText, KeyRound, LogOut } from 'lucide-react';
import { toast } from 'react-toastify';
import apiService from '../services/apiService';
import { useAuth } from '../contexts/AuthContext';
import Sidebar from './Sidebar';
import './Layout.css';

const Layout: React.FC = () => {
  const { user, logout, canAccessAccounts, isIndividualUser } = useAuth();
  const navigate = useNavigate();
  const [showUserDropdown, setShowUserDropdown] = useState(false);
  const [requestingPasswordChange, setRequestingPasswordChange] = useState(false);

  useEffect(() => {
    if (!showUserDropdown) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (!(e.target as HTMLElement).closest('.header-profile')) {
        setShowUserDropdown(false);
      }
    };
    document.addEventListener('click', handleClickOutside);
    return () => document.removeEventListener('click', handleClickOutside);
  }, [showUserDropdown]);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const handleChangePassword = async () => {
    if (requestingPasswordChange) return;
    setRequestingPasswordChange(true);
    try {
      const response = await apiService.requestPasswordChange();
      toast.success(response.message || 'Password reset link sent to your email.');
      setShowUserDropdown(false);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Unable to send the password reset link');
    } finally {
      setRequestingPasswordChange(false);
    }
  };

  const roleLabel = user?.roles.includes('ADMIN')
    ? 'Administrator'
    : user?.business_units.length ? user.business_units.join(' · ') : 'User';

  return (
    <div className="app-shell">
      <Sidebar />
      <div className="app-main">
        <div className="app-topbar">
          <div className="bu-context-badge">
            {user?.roles.includes('ADMIN') ? 'Admin' : user?.business_units.join(' · ') || 'User'}
          </div>
          <div className="header-profile" onClick={() => setShowUserDropdown(!showUserDropdown)}>
            <div className="profile-avatar-small">
              <User className="profile-icon-small" />
            </div>
            <div className="header-user-info">
              <span className="header-username">{user?.name}</span>
              <span className="header-role">{roleLabel}</span>
            </div>
            <ChevronDown className="profile-dropdown-icon" />

            {showUserDropdown && (
              <div className="user-dropdown-menu" onClick={(e) => e.stopPropagation()}>
                {canAccessAccounts && <button className="dropdown-item" onClick={() => { setShowUserDropdown(false); navigate('/accounts'); }}>
                  <Database size={16} />
                  <span>Manage Accounts</span>
                </button>}
                {isIndividualUser && <button className="dropdown-item" onClick={handleChangePassword} disabled={requestingPasswordChange}>
                  <KeyRound size={16} />
                  <span>{requestingPasswordChange ? 'Sending link...' : 'Change Password'}</span>
                </button>}
                <button className="dropdown-item" onClick={() => { setShowUserDropdown(false); navigate('/dashboard'); }}>
                  <FileText size={16} />
                  <span>SOW Generator</span>
                </button>
                <div className="dropdown-divider"></div>
                <button className="dropdown-item logout-item" onClick={handleLogout}>
                  <LogOut size={16} />
                  <span>Logout</span>
                </button>
              </div>
            )}
          </div>
        </div>

        <div className="app-content">
          <Outlet />
        </div>
      </div>
    </div>
  );
};

export default Layout;
