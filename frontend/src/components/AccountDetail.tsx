import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { toast } from '../utils/toast';
import {
  ChevronRight,
  Plus,
  Folder,
  FileText,
  Calendar,
  X,
  Edit,
  ArrowLeft,
  Trash2,
  AlertCircle
} from 'lucide-react';
import apiService from '../services/apiService';
import './AccountDetail.css';

interface Project {
  project_id: string;
  project_name: string;
  description: string;
  sow_count: number;
  created_at: string;
  updated_at: string;
  status: string;
}

interface Account {
  account_id: string;
  account_name: string;
  segment: string;
  priority: string;
  project_count: number;
  sow_count: number;
  demo_count: number;
  created_at: string;
  status: string;
}

const AccountDetail: React.FC = () => {
  const { accountId } = useParams<{ accountId: string }>();
  const navigate = useNavigate();
  const [account, setAccount] = useState<Account | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showDeleteProjectModal, setShowDeleteProjectModal] = useState(false);
  const [projectToDelete, setProjectToDelete] = useState<Project | null>(null);
  const [formData, setFormData] = useState({
    project_name: '',
    description: ''
  });

  useEffect(() => {
    if (accountId) {
      fetchAccountAndProjects();
    }
  }, [accountId]);

  const fetchAccountAndProjects = async () => {
    try {
      setLoading(true);

      // Fetch account details
      const accountResponse = await apiService.fetchAccount(accountId!);
      if (accountResponse.success) {
        setAccount(accountResponse.account);
      }

      // Fetch projects for this account
      const projectsResponse = await apiService.fetchProjectsForAccount(accountId!);
      if (projectsResponse.success) {
        const projectsList = projectsResponse.projects || [];
        
        // ✅ Fetch real SOW count for each project
        const projectsWithRealCounts = await Promise.all(
          projectsList.map(async (project: Project) => {
            try {
              const sowsResponse = await apiService.fetchSOWsForProject(project.project_id);
              const realCount = sowsResponse.success ? (sowsResponse.sows || []).length : project.sow_count;
              return {
                ...project,
                sow_count: realCount  // Override with real count
              };
            } catch (error) {
              console.error(`Error fetching SOWs for project ${project.project_id}:`, error);
              return project;  // Return original if fetch fails
            }
          })
        );
        
        setProjects(projectsWithRealCounts);
      }
    } catch (error) {
      toast.error('Failed to fetch account details');
      console.error('Error fetching account:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateProject = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!formData.project_name.trim()) {
      toast.error('Please enter a project name');
      return;
    }

    try {
      const response = await apiService.createProject(accountId!, formData);
      if (response.success) {
        toast.success(`Project "${formData.project_name}" created successfully!`);
        setShowCreateModal(false);
        setFormData({ project_name: '', description: '' });
        fetchAccountAndProjects();
      } else {
        toast.error(response.error || 'Failed to create project');
      }
    } catch (error) {
      toast.error('Failed to create project');
      console.error('Error creating project:', error);
    }
  };

  const handleDeleteProjectClick = (project: Project, e: React.MouseEvent) => {
    e.stopPropagation();
    setProjectToDelete(project);
    setShowDeleteProjectModal(true);
  };

  const handleDeleteProjectConfirm = async () => {
    if (!projectToDelete) return;

    try {
      const response = await apiService.deleteProject(projectToDelete.project_id);
      if (response.success) {
        toast.success(`Project "${projectToDelete.project_name}" deleted successfully!`);
        setShowDeleteProjectModal(false);
        setProjectToDelete(null);
        fetchAccountAndProjects();
      } else {
        toast.error(response.error || 'Failed to delete project');
      }
    } catch (error) {
      toast.error('Failed to delete project');
      console.error('Error deleting project:', error);
    }
  };

  const getSegmentColor = (segment: string) => {
    switch (segment) {
      case 'Enterprise':
        return '#2563eb';
      case 'Startup':
        return '#8b5cf6';
      default:
        return '#6b7280';
    }
  };

  const getPriorityColor = (priority: string) => {
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

  if (loading) {
    return (
      <div className="account-detail-loading">
        <div className="spinner"></div>
        <p>Loading account details...</p>
      </div>
    );
  }

  if (!account) {
    return (
      <div className="account-detail-error">
        <p>Account not found</p>
        <button onClick={() => navigate('/accounts')}>Back to Accounts</button>
      </div>
    );
  }

  return (
    <div className="account-detail-page">
      {/* Breadcrumb */}
      <div className="breadcrumb">
        <button onClick={() => navigate('/accounts')} className="breadcrumb-link">
          Accounts
        </button>
        <ChevronRight size={16} className="breadcrumb-separator" />
        <span className="breadcrumb-current">{account.account_name}</span>
      </div>

      {/* Account Header */}
      <div className="account-header-detail">
        <div className="account-header-content">
          <div className="account-header-top">
            <div className="account-header-left">
              <button onClick={() => navigate('/accounts')} className="back-button">
                <ArrowLeft size={16} />
              </button>
              <div className="account-info">
                <div className="account-avatar">
                  {account.account_name.slice(0, 2).toUpperCase()}
                </div>
                <div className="account-identity">
                  <h1>{account.account_name}</h1>
                  <div className="account-meta">
                    <span
                      className="segment-badge"
                      style={{
                        backgroundColor: `${getSegmentColor(account.segment)}18`,
                        color: getSegmentColor(account.segment)
                      }}
                    >
                      {account.segment}
                    </span>
                    <span
                      className="priority-badge"
                      style={{
                        backgroundColor: `${getPriorityColor(account.priority)}18`,
                        color: getPriorityColor(account.priority)
                      }}
                    >
                      {account.priority}
                    </span>
                    <span className="created-date">
                      <Calendar size={11} />
                      Created {formatDate(account.created_at)}
                    </span>
                  </div>
                </div>
              </div>
            </div>
            <div className="account-header-right">
              <button className="edit-account-btn">
                <Edit size={18} />
                <span>Edit Account</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Account Stats */}
      <div className="account-stats-mini">
        <div className="stat-item-mini">
          <Folder size={20} />
          <div>
            <div className="stat-value-mini">{projects.length}</div>
            <div className="stat-label-mini">Projects</div>
          </div>
        </div>
        <div className="stat-item-mini">
          <FileText size={20} />
          <div>
            <div className="stat-value-mini">{projects.reduce((sum, p) => sum + (p.sow_count || 0), 0)}</div>
            <div className="stat-label-mini">SOWs</div>
          </div>
        </div>
        <div className="stat-item-mini">
          <FileText size={20} />
          <div>
            <div className="stat-value-mini">{account.demo_count || 0}</div>
            <div className="stat-label-mini">Demos</div>
          </div>
        </div>
      </div>

      {/* Projects Section */}
      <div className="projects-section">
        <div className="section-header">
          <h2>Projects ({projects.length})</h2>
          <button className="create-project-btn" onClick={() => setShowCreateModal(true)}>
            <Plus size={20} />
            Create Project
          </button>
        </div>

        {projects.length > 0 ? (
          <div className="projects-grid">
            {projects.map((project) => (
              <div
                key={project.project_id}
                className="project-card"
              >
                <button
                  className="delete-project-btn"
                  onClick={(e) => handleDeleteProjectClick(project, e)}
                  title="Delete project"
                >
                  <Trash2 size={16} />
                </button>
                <div
                  className="project-card-content"
                  onClick={() => navigate(`/projects/${project.project_id}`)}
                >
                  <div className="project-card-header">
                    <div className="project-icon">
                      <Folder size={32} color="#ffffff" />
                    </div>
                  </div>
                  <div className="project-card-body">
                    <h3>{project.project_name}</h3>
                    <p>{project.description || 'No description provided'}</p>
                  </div>
                  <div className="project-card-footer">
                    <div className="project-stat">
                      <FileText size={14} />
                      <span>{project.sow_count} SOW{project.sow_count !== 1 ? 's' : ''}</span>
                    </div>
                    <div className="project-date">
                      {formatDate(project.created_at)}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty-state">
            <Folder size={64} color="#d1d5db" />
            <h3>No Projects Yet</h3>
            <p>Create your first project to start organizing SOWs</p>
            <button className="create-first-btn" onClick={() => setShowCreateModal(true)}>
              <Plus size={20} />
              Create First Project
            </button>
          </div>
        )}
      </div>

      {/* Create Project Modal */}
      {showCreateModal && (
        <div className="modal-overlay" onClick={() => setShowCreateModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Create New Project</h2>
              <button className="modal-close" onClick={() => setShowCreateModal(false)}>
                <X size={20} />
              </button>
            </div>
            <form onSubmit={handleCreateProject}>
              <div className="modal-body">
                <div className="form-group">
                  <label>Project Name *</label>
                  <input
                    type="text"
                    value={formData.project_name}
                    onChange={(e) => setFormData({ ...formData, project_name: e.target.value })}
                    placeholder="Enter project name"
                    className="form-input"
                    required
                  />
                </div>

                <div className="form-group">
                  <label>Description</label>
                  <textarea
                    value={formData.description}
                    onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                    placeholder="Enter project description (optional)"
                    className="form-textarea"
                    rows={4}
                  />
                </div>

                <div className="form-info">
                  <p>
                    <strong>Account:</strong> {account.account_name}
                  </p>
                </div>
              </div>

              <div className="modal-footer">
                <button type="button" className="btn-secondary" onClick={() => setShowCreateModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn-primary">
                  <Plus size={16} />
                  <span>Create Project</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete Project Confirmation Modal */}
      {showDeleteProjectModal && projectToDelete && (
        <div className="modal-overlay" onClick={() => setShowDeleteProjectModal(false)}>
          <div className="modal-content delete-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Delete Project</h2>
              <button className="modal-close" onClick={() => setShowDeleteProjectModal(false)}>
                <X size={20} />
              </button>
            </div>
            <div className="modal-body">
              <div className="warning-message">
                <AlertCircle size={48} color="#ef4444" />
                <p>Are you sure you want to delete <strong>"{projectToDelete.project_name}"</strong>?</p>
                <p className="warning-details">
                  This will permanently delete the project and all associated data including:
                </p>
                <ul className="warning-list">
                  <li>{projectToDelete.sow_count} SOW{projectToDelete.sow_count !== 1 ? 's' : ''}</li>
                  <li>Project description and metadata</li>
                </ul>
                <p className="warning-final">This action cannot be undone.</p>
              </div>
            </div>
            <div className="modal-footer">
              <button type="button" className="btn-secondary" onClick={() => setShowDeleteProjectModal(false)}>
                Cancel
              </button>
              <button type="button" className="btn-danger" onClick={handleDeleteProjectConfirm}>
                <Trash2 size={16} />
                <span>Delete Project</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AccountDetail;
