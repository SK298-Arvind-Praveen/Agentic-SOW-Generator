import React, { useEffect, useState } from 'react';
import { Outlet, useNavigate } from 'react-router-dom';
import { User, ChevronDown, Database, FileText, LogOut } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import Sidebar from './Sidebar';
import './Layout.css';

const Layout: React.FC = () => {
  const { user, logout } = useAuth();
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

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const roleLabel = user?.role === 'ADMIN'
    ? 'Administrator'
    : user?.role === 'USER'
      ? `${user?.business_unit || 'BU'} User`
      : `${user?.business_unit || 'BU'} BU Head`;

  return (
    <div className="app-shell">
      <Sidebar />
      <div className="app-main">
        <div className="app-topbar">
          <div className="bu-context-badge">
            {user?.role === 'ADMIN' ? 'All Business Units' : user?.business_unit}
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
                <div className="dropdown-header">
                  <div className="dropdown-avatar">
                    <User size={20} />
                  </div>
                  <div className="dropdown-user-info">
                    <div className="dropdown-username">{user?.name}</div>
                    <div className="dropdown-role">{roleLabel}</div>
                  </div>
                </div>
                <div className="dropdown-divider"></div>
                <button className="dropdown-item" onClick={() => { setShowUserDropdown(false); navigate('/accounts'); }}>
                  <Database size={16} />
                  <span>Manage Accounts</span>
                </button>
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
