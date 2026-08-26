import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'react-toastify';
import {
  Building2,
  Plus,
  Search,
  Filter,
  TrendingUp,
  Briefcase,
  AlertCircle,
  ChevronRight,
  X,
  Sparkles,
  Zap,
  Target,
  BarChart3,
  ArrowUpRight,
  Trash2,
  MoreVertical,
  FileText
} from 'lucide-react';
import apiService from '../services/apiService';
import '../styles/modern-theme.css';
import './Accounts.css';
import { BUSINESS_UNITS, useAuth } from '../contexts/AuthContext';

interface Account {
  account_id: string;
  account_name: string;
  segment: string;
  priority: string;
  description?: string;
  project_count: number;
  sow_count: number;
  demo_count?: number;
  created_at: string;
  status: string;
  business_unit?: string;
}

interface Statistics {
  total: number;
  with_projects: number;
  without_projects: number;
  by_segment: { [key: string]: number };
  by_priority: { [key: string]: number };
}

const Accounts: React.FC = () => {
  const navigate = useNavigate();
  const { user, isAdmin } = useAuth();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [statistics, setStatistics] = useState<Statistics | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [segmentFilter, setSegmentFilter] = useState('');
  const [priorityFilter, setPriorityFilter] = useState('');
  const [businessUnitFilter, setBusinessUnitFilter] = useState('');
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [accountToDelete, setAccountToDelete] = useState<Account | null>(null);
  const [showEditModal, setShowEditModal] = useState(false);
  const [accountToEdit, setAccountToEdit] = useState<Account | null>(null);
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);

  // Form state
  const [formData, setFormData] = useState({
    account_name: '',
    segment: 'Others',
    priority: 'P3',
    description: ''
    ,business_unit: user?.business_unit || ''
  });

  useEffect(() => {
    fetchAccounts();
  }, [segmentFilter, priorityFilter, businessUnitFilter]);

  // Close menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (openMenuId) {
        const target = e.target as HTMLElement;
        if (!target.closest('.menu-icon-btn') && !target.closest('.action-menu')) {
          setOpenMenuId(null);
        }
      }
    };

    document.addEventListener('click', handleClickOutside);
    return () => document.removeEventListener('click', handleClickOutside);
  }, [openMenuId]);

  const fetchAccounts = async () => {
    try {
      setLoading(true);
      const params: any = {};
      if (segmentFilter) params.segment = segmentFilter;
      if (priorityFilter) params.priority = priorityFilter;
      if (isAdmin && businessUnitFilter) params.business_unit = businessUnitFilter;

      const [accountsRes, statsRes] = await Promise.all([
        apiService.fetchAccounts(params),
        apiService.fetchAccountStatistics(isAdmin ? businessUnitFilter : undefined)
      ]);

      if (accountsRes.success) setAccounts(accountsRes.accounts || []);
      if (statsRes.success) setStatistics(statsRes.statistics);
    } catch (error) {
      toast.error('Failed to fetch accounts');
      console.error('Error fetching accounts:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchStatistics = fetchAccounts;

  const handleCreateAccount = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!formData.account_name.trim()) {
      toast.error('Please enter an account name');
      return;
    }

    try {
      const response = await apiService.createAccount(formData);
      if (response.success) {
        toast.success(`Account "${formData.account_name}" created successfully!`);
        setShowCreateModal(false);
        setFormData({ account_name: '', segment: 'Others', priority: 'P3', description: '', business_unit: user?.business_unit || '' });
        fetchAccounts();
      } else {
        toast.error(response.error || 'Failed to create account');
      }
    } catch (error) {
      toast.error('Failed to create account');
      console.error('Error creating account:', error);
    }
  };

  const handleMenuToggle = (accountId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setOpenMenuId(openMenuId === accountId ? null : accountId);
  };

  const handleEditClick = (account: Account, e: React.MouseEvent) => {
    e.stopPropagation();
    setAccountToEdit(account);
    setFormData({
      account_name: account.account_name,
      segment: account.segment,
      priority: account.priority,
      description: account.description || ''
      ,business_unit: account.business_unit || ''
    });
    setShowEditModal(true);
    setOpenMenuId(null);
  };

  const handleDeleteClick = (account: Account, e: React.MouseEvent) => {
    e.stopPropagation();
    setAccountToDelete(account);
    setShowDeleteModal(true);
    setOpenMenuId(null);
  };

  const handleUpdateAccount = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!accountToEdit) return;

    try {
      const response = await apiService.updateAccount(accountToEdit.account_id, formData);
      if (response.success) {
        toast.success(`Account "${formData.account_name}" updated successfully!`);
        setShowEditModal(false);
        setAccountToEdit(null);
        setFormData({ account_name: '', segment: 'Others', priority: 'P3', description: '', business_unit: user?.business_unit || '' });
        fetchAccounts();
      } else {
        toast.error(response.error || 'Failed to update account');
      }
    } catch (error) {
      toast.error('Failed to update account');
      console.error('Error updating account:', error);
    }
  };

  const handleDeleteConfirm = async () => {
    if (!accountToDelete) return;

    try {
      const response = await apiService.deleteAccount(accountToDelete.account_id);
      if (response.success) {
        toast.success(`Account "${accountToDelete.account_name}" deleted successfully!`);
        setShowDeleteModal(false);
        setAccountToDelete(null);
        fetchAccounts();
      } else {
        toast.error(response.error || 'Failed to delete account');
      }
    } catch (error) {
      toast.error('Failed to delete account');
      console.error('Error deleting account:', error);
    }
  };

  const getFilteredAccounts = () => {
    return accounts.filter(account =>
      account.account_name.toLowerCase().includes(searchQuery.toLowerCase())
    );
  };

  const getSegmentBadgeColor = (segment: string) => {
    switch (segment) {
      case 'Enterprise':
        return '#2563eb';
      case 'Startup':
        return '#8b5cf6';
      case 'Others':
        return '#6b7280';
      default:
        return '#6b7280';
    }
  };

  const getPriorityBadgeColor = (priority: string) => {
    switch (priority) {
      case 'P1':
        return '#ef4444';
      case 'P2':
        return '#f59e0b';
      case 'P3':
        return '#10b981';
      default:
        return '#6b7280';
    }
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  };

  return (
    <div className="accounts-page">
      {/* Header */}
      <div className="accounts-header">
        <div className="header-left">
          <h1>Accounts</h1>
          <p>Manage customer accounts and track projects</p>
        </div>
        <div className="header-right">
          <button
            className="tracker-link-btn"
            onClick={() => navigate('/sow-tracker')}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '12px 20px',
              background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
              color: 'white',
              border: 'none',
              borderRadius: '12px',
              fontSize: '0.9375rem',
              fontWeight: '600',
              cursor: 'pointer',
              transition: 'all 0.3s ease',
              boxShadow: '0 4px 12px rgba(16, 185, 129, 0.3)'
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.transform = 'translateY(-2px)';
              e.currentTarget.style.boxShadow = '0 6px 16px rgba(16, 185, 129, 0.4)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.transform = 'translateY(0)';
              e.currentTarget.style.boxShadow = '0 4px 12px rgba(16, 185, 129, 0.3)';
            }}
          >
            <BarChart3 size={20} />
            <span>SOW Tracker</span>
          </button>
          <button className="create-account-btn" onClick={() => setShowCreateModal(true)}>
            <Plus size={20} />
            <span>Create Account</span>
          </button>
        </div>
      </div>

      {/* Statistics Cards */}
      <div className="statistics-section">
        <div className="stats-summary">
          <span>Total: <strong>{statistics?.total || 0}</strong></span>
          <span className="stats-divider">•</span>
          <span>With Projects: <strong>{statistics?.with_projects || 0}</strong></span>
          <span className="stats-divider">•</span>
          <span>Without Projects: <strong>{statistics?.without_projects || 0}</strong></span>
        </div>

        <div className="stats-grid">
          <div className="stat-card">
            <div className="stat-icon" style={{ backgroundColor: '#e0e7ff' }}>
              <Building2 size={24} color="#4f46e5" />
            </div>
            <div className="stat-content">
              <div className="stat-value">{statistics?.total || 0}</div>
              <div className="stat-label">Total Accounts</div>
            </div>
          </div>

          <div className="stat-card">
            <div className="stat-icon" style={{ backgroundColor: '#d1fae5' }}>
              <TrendingUp size={24} color="#059669" />
            </div>
            <div className="stat-content">
              <div className="stat-value">{statistics?.with_projects || 0}</div>
              <div className="stat-label">With Projects</div>
            </div>
          </div>

          <div className="stat-card">
            <div className="stat-icon" style={{ backgroundColor: '#fce7f3' }}>
              <Briefcase size={24} color="#be185d" />
            </div>
            <div className="stat-content">
              <div className="stat-value">{statistics?.without_projects || 0}</div>
              <div className="stat-label">Without Projects</div>
            </div>
          </div>

          <div className="stat-card">
            <div className="stat-icon" style={{ backgroundColor: '#dbeafe' }}>
              <Briefcase size={24} color="#1e40af" />
            </div>
            <div className="stat-content">
              <div className="stat-value">{statistics?.by_segment?.Enterprise || 0}</div>
              <div className="stat-label">Enterprise</div>
            </div>
          </div>

          <div className="stat-card">
            <div className="stat-icon" style={{ backgroundColor: '#fee2e2' }}>
              <AlertCircle size={24} color="#dc2626" />
            </div>
            <div className="stat-content">
              <div className="stat-value">{statistics?.by_priority?.P1 || 0}</div>
              <div className="stat-label">P1 Priority</div>
            </div>
          </div>
        </div>
      </div>

      {/* Toolbar */}
      <div className="accounts-toolbar">
        <div className="search-container">
          <Search className="search-icon" size={18} />
          <input
            type="text"
            placeholder="Search accounts..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="search-input"
          />
        </div>

        <div className="filter-controls">
          {isAdmin && (
            <select value={businessUnitFilter} onChange={(e) => setBusinessUnitFilter(e.target.value)} className="filter-select">
              <option value="">All Business Units</option>
              {BUSINESS_UNITS.map(unit => <option key={unit} value={unit}>{unit}</option>)}
            </select>
          )}
          <button
            className={`filter-btn ${showFilters ? 'active' : ''}`}
            onClick={() => setShowFilters(!showFilters)}
          >
            <Filter size={16} />
            <span>All Segments</span>
          </button>

          <select
            value={priorityFilter}
            onChange={(e) => setPriorityFilter(e.target.value)}
            className="filter-select"
          >
            <option value="">All Priorities</option>
            <option value="P1">P1</option>
            <option value="P2">P2</option>
            <option value="P3">P3</option>
          </select>

          <button className="sort-btn">
            <span>Name (A-Z)</span>
            <ChevronRight size={16} />
          </button>
        </div>
      </div>

      {/* Filters Dropdown */}
      {showFilters && (
        <div className="filters-dropdown" style={{ position: 'relative', zIndex: 200 }}>
          <button className={`filter-option ${segmentFilter === '' ? 'active' : ''}`} onClick={() => setSegmentFilter('')}>All Segments</button>
          <button className={`filter-option ${segmentFilter === 'Enterprise' ? 'active' : ''}`} onClick={() => setSegmentFilter('Enterprise')}>Enterprise</button>
          <button className={`filter-option ${segmentFilter === 'Startup' ? 'active' : ''}`} onClick={() => setSegmentFilter('Startup')}>Startup</button>
          <button className={`filter-option ${segmentFilter === 'Others' ? 'active' : ''}`} onClick={() => setSegmentFilter('Others')}>Others</button>
        </div>
      )}

      {/* Accounts Table */}
      <div className="accounts-table-wrapper">
      <div className="accounts-table-container">
        <table className="accounts-table">
          <thead>
            <tr>
              <th>Account Name</th>
              {isAdmin && <th>Business Unit</th>}
              <th>Segment</th>
              <th>Priority</th>
              <th>Projects</th>
              <th>SOWs</th>
              <th>Demos</th>
              <th>Created</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={isAdmin ? 9 : 8} className="loading-cell">Loading accounts...</td>
              </tr>
            ) : getFilteredAccounts().length > 0 ? (
              getFilteredAccounts().map((account) => (
                <tr
                  key={account.account_id}
                  onClick={() => navigate(`/accounts/${account.account_id}`)}
                  className="account-row"
                >
                  <td className="account-name-cell">{account.account_name}</td>
                  {isAdmin && <td>{account.business_unit || 'Unassigned'}</td>}
                  <td>
                    <span
                      className="segment-badge"
                      style={{ backgroundColor: `${getSegmentBadgeColor(account.segment)}20`, color: getSegmentBadgeColor(account.segment) }}
                    >
                      {account.segment}
                    </span>
                  </td>
                  <td>
                    <span
                      className="priority-badge"
                      style={{ backgroundColor: `${getPriorityBadgeColor(account.priority)}20`, color: getPriorityBadgeColor(account.priority) }}
                    >
                      {account.priority}
                    </span>
                  </td>
                  <td>{account.project_count} project{account.project_count !== 1 ? 's' : ''}</td>
                  <td>{account.sow_count}</td>
                  <td>{account.demo_count || 0}</td>
                  <td>{formatDate(account.created_at)}</td>
                  <td style={{ position: 'relative' }}>
                    <button
                      className="menu-icon-btn"
                      onClick={(e) => handleMenuToggle(account.account_id, e)}
                      title="Actions"
                    >
                      <MoreVertical size={18} />
                    </button>
                    {openMenuId === account.account_id && (
                      <div className="action-menu">
                        <button
                          className="menu-item menu-item-edit"
                          onClick={(e) => handleEditClick(account, e)}
                        >
                          <span className="menu-icon">✏️</span>
                          <span>Edit</span>
                        </button>
                        <button
                          className="menu-item menu-item-delete"
                          onClick={(e) => handleDeleteClick(account, e)}
                        >
                          <Trash2 size={14} />
                          <span>Delete</span>
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={isAdmin ? 9 : 8} className="no-data-cell">No accounts found</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      </div>

      {/* Create Account Modal */}
      {showCreateModal && (
        <div className="modal-overlay" onClick={() => setShowCreateModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Create New Account</h2>
              <button className="modal-close" onClick={() => setShowCreateModal(false)}>
                <X size={20} />
              </button>
            </div>
            <form onSubmit={handleCreateAccount}>
              <div className="modal-body">
                <div className="form-group">
                  <label>Account Name *</label>
                  <input
                    type="text"
                    value={formData.account_name}
                    onChange={(e) => setFormData({ ...formData, account_name: e.target.value })}
                    placeholder="Enter account name"
                    className="form-input"
                    required
                  />
                </div>

                <div className="form-row">
                  {isAdmin && (
                    <div className="form-group">
                      <label>Business Unit *</label>
                      <select
                        value={formData.business_unit}
                        onChange={(e) => setFormData({ ...formData, business_unit: e.target.value })}
                        className="form-select"
                        required
                      >
                        <option value="">Select business unit...</option>
                        {BUSINESS_UNITS.map(unit => <option key={unit} value={unit}>{unit}</option>)}
                      </select>
                    </div>
                  )}
                  <div className="form-group">
                    <label>Segment</label>
                    <select
                      value={formData.segment}
                      onChange={(e) => setFormData({ ...formData, segment: e.target.value })}
                      className="form-select"
                    >
                      <option value="Enterprise">Enterprise</option>
                      <option value="Startup">Startup</option>
                      <option value="Others">Others</option>
                    </select>
                  </div>

                  <div className="form-group">
                    <label>Priority</label>
                    <select
                      value={formData.priority}
                      onChange={(e) => setFormData({ ...formData, priority: e.target.value })}
                      className="form-select"
                    >
                      <option value="P1">P1 (High)</option>
                      <option value="P2">P2 (Medium)</option>
                      <option value="P3">P3 (Low)</option>
                    </select>
                  </div>
                </div>
              </div>

              <div className="modal-footer">
                <button type="button" className="btn-secondary" onClick={() => setShowCreateModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn-primary">
                  <Plus size={16} />
                  <span>Create Account</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Edit Account Modal */}
      {showEditModal && accountToEdit && (
        <div className="modal-overlay" onClick={() => setShowEditModal(false)}>
          <div className="modal-content modal-edit" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header modal-header-gradient">
              <div className="modal-title-section">
                <div className="modal-icon">
                  <Building2 size={24} />
                </div>
                <div>
                  <h2>Edit Account</h2>
                  <p className="modal-subtitle">Update account information and settings</p>
                </div>
              </div>
              <button className="modal-close" onClick={() => setShowEditModal(false)}>
                <X size={20} />
              </button>
            </div>
            <form onSubmit={handleUpdateAccount}>
              <div className="modal-body">
                <div className="form-group">
                  <label className="form-label-icon">
                    <Building2 size={16} />
                    <span>Account Name *</span>
                  </label>
                  <input
                    type="text"
                    className="form-input-modern"
                    value={formData.account_name}
                    onChange={(e) => setFormData({ ...formData, account_name: e.target.value })}
                    placeholder="Enter account name"
                    required
                  />
                </div>

                <div className="form-group">
                  <label className="form-label-icon">
                    <FileText size={16} />
                    <span>Description</span>
                  </label>
                  <textarea
                    className="form-textarea-modern"
                    value={formData.description}
                    onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                    placeholder="Enter account description (optional)"
                    rows={3}
                  />
                </div>

                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label-icon">
                      <Target size={16} />
                      <span>Segment *</span>
                    </label>
                    <select
                      className="form-select-modern"
                      value={formData.segment}
                      onChange={(e) => setFormData({ ...formData, segment: e.target.value })}
                      required
                    >
                      <option value="Strategic">🎯 Strategic</option>
                      <option value="Enterprise">🏢 Enterprise</option>
                      <option value="Mid-Market">📊 Mid-Market</option>
                      <option value="SMB">🏪 SMB</option>
                      <option value="Others">📦 Others</option>
                    </select>
                  </div>

                  <div className="form-group">
                    <label className="form-label-icon">
                      <Zap size={16} />
                      <span>Priority *</span>
                    </label>
                    <select
                      className="form-select-modern"
                      value={formData.priority}
                      onChange={(e) => setFormData({ ...formData, priority: e.target.value })}
                      required
                    >
                      <option value="P0">🔴 P0 - Critical</option>
                      <option value="P1">🟠 P1 - High</option>
                      <option value="P2">🟡 P2 - Medium</option>
                      <option value="P3">🟢 P3 - Low</option>
                    </select>
                  </div>
                </div>
              </div>

              <div className="modal-footer modal-footer-actions">
                <button type="button" className="btn-cancel" onClick={() => setShowEditModal(false)}>
                  <X size={18} />
                  <span>Cancel</span>
                </button>
                <button type="submit" className="btn-update">
                  <Sparkles size={18} />
                  <span>Update Account</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {showDeleteModal && accountToDelete && (
        <div className="modal-overlay" onClick={() => setShowDeleteModal(false)}>
          <div className="modal-content delete-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Delete Account</h2>
              <button className="modal-close" onClick={() => setShowDeleteModal(false)}>
                <X size={20} />
              </button>
            </div>
            <div className="modal-body">
              <div className="warning-message">
                <AlertCircle size={48} color="#ef4444" />
                <p>Are you sure you want to delete <strong>"{accountToDelete.account_name}"</strong>?</p>
                <p className="warning-details">
                  This will permanently delete the account and all associated data including:
                </p>
                <ul className="warning-list">
                  <li>{accountToDelete.project_count} project{accountToDelete.project_count !== 1 ? 's' : ''}</li>
                  <li>{accountToDelete.sow_count} SOW{accountToDelete.sow_count !== 1 ? 's' : ''}</li>
                  <li>{accountToDelete.demo_count || 0} demo{(accountToDelete.demo_count || 0) !== 1 ? 's' : ''}</li>
                </ul>
                <p className="warning-final">This action cannot be undone.</p>
              </div>
            </div>
            <div className="modal-footer">
              <button type="button" className="btn-secondary" onClick={() => setShowDeleteModal(false)}>
                Cancel
              </button>
              <button type="button" className="btn-danger" onClick={handleDeleteConfirm}>
                <Trash2 size={16} />
                <span>Delete Account</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Accounts;
