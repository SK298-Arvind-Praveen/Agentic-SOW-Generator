import React, { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { ChevronRight, FileText, BarChart3, Database } from 'lucide-react';
import ShellkodeLogo from './ShellkodeLogo';
import './Sidebar.css';

interface NavItem {
  path: string;
  label: string;
  description: string;
  icon: React.ComponentType<{ className?: string; style?: React.CSSProperties }>;
  color: string;
  isActive: (pathname: string) => boolean;
}

const NAV_ITEMS: NavItem[] = [
  {
    path: '/accounts',
    label: 'Accounts',
    description: 'Manage accounts and projects',
    icon: Database,
    color: '#8b5cf6',
    isActive: (p) => p.startsWith('/accounts') || p.startsWith('/projects')
  },
  {
    path: '/dashboard',
    label: 'SOW Generator',
    description: 'Generate and track SOW documents',
    icon: FileText,
    color: '#2563eb',
    isActive: (p) => p.startsWith('/dashboard') || p.startsWith('/documents') || p.startsWith('/production')
  },
  {
    path: '/sow-tracker',
    label: 'SOW Tracker',
    description: 'Track and analyze SOW documents',
    icon: BarChart3,
    color: '#10b981',
    isActive: (p) => p.startsWith('/sow-tracker')
  }
];

const Sidebar: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className={`app-sidebar ${collapsed ? 'collapsed' : ''}`}>
      <div className="sidebar-header">
        <div className="logo-section">
          <ShellkodeLogo size="medium" variant="onDark" />
        </div>
        <button
          className="sidebar-toggle"
          onClick={() => setCollapsed(!collapsed)}
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          <ChevronRight className={`toggle-icon ${collapsed ? 'collapsed' : ''}`} />
        </button>
      </div>

      <div className="sidebar-content">
        <nav className="sidebar-nav">
          {NAV_ITEMS.map((item) => {
            const IconComponent = item.icon;
            const isActive = item.isActive(location.pathname);

            return (
              <div key={item.path} className="nav-group">
                <button
                  className={`nav-item ${isActive ? 'active' : ''}`}
                  onClick={() => navigate(item.path)}
                  title={item.label}
                >
                  <div className="nav-icon-wrapper">
                    <IconComponent className="nav-icon" style={{ color: item.color }} />
                  </div>
                  {!collapsed && (
                    <div className="nav-content">
                      <span className="nav-title">{item.label}</span>
                      <span className="nav-description">{item.description}</span>
                    </div>
                  )}
                </button>
              </div>
            );
          })}
        </nav>
      </div>
    </div>
  );
};

export default Sidebar;
