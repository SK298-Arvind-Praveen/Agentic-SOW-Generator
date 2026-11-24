import React, { useEffect, useState } from 'react';
import { Outlet, useNavigate } from 'react-router-dom';
import { User, ChevronDown, Database, FileText, LogOut } from 'lucide-react';
import { toast } from '../utils/toast';
import { useAuth } from '../contexts/AuthContext';
import Sidebar from './Sidebar';
import './Layout.css';

const Layout: React.FC = () => {
  const { user, logout, canAccessAccounts } = useAuth();
  const navigate = useNavigate();
  const [showUserDropdown, setShowUserDropdown] = useState(false);

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

  const handleLogout = async () => {
    try {
      await logout();
      navigate('/login');
    } catch {
      toast.error('Unable to sign out. Please try again.');
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
