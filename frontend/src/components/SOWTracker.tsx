import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  FileText,
  TrendingUp,
  Calendar,
  Search,
  Filter,
  Download,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  Loader
} from 'lucide-react';
import { toast } from 'react-toastify';
import apiService from '../services/apiService';
import { downloadWithNativeSaveAs } from '../utils/downloadFile';
import { formatTokenCount } from '../utils/tokenUsage';
import './SOWTracker.css';
import { BUSINESS_UNITS, useAuth } from '../contexts/AuthContext';

interface SOWRecord {
  sow_id: string;
  document_id: string;
  project_name: string;
  customer_name: string;
  author_name: string;
  mode: string;
  document_date: string;
  s3_url: string;
  drive_link: string;
  created_at?: string;
  business_unit?: string;
  total_tokens?: number | string;
}

interface Statistics {
  totalSOWs: number;
  thisMonthSOWs: number;
  pocCount: number;
  prodCount: number;
  pocToProdCount: number;
}

const SOWTracker: React.FC = () => {
  const navigate = useNavigate();
  const { user, isAdmin } = useAuth();
  const [loading, setLoading] = useState(true);
  const [sowRecords, setSOWRecords] = useState<SOWRecord[]>([]);
  const [filteredRecords, setFilteredRecords] = useState<SOWRecord[]>([]);
  const [statistics, setStatistics] = useState<Statistics>({
    totalSOWs: 0,
    thisMonthSOWs: 0,
    pocCount: 0,
    prodCount: 0,
    pocToProdCount: 0
  });

  // Filter states
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedMode, setSelectedMode] = useState<string>('all');
  const [selectedBusinessUnit, setSelectedBusinessUnit] = useState<string>('all');
  const [sortConfig, setSortConfig] = useState<{ key: string; direction: 'asc' | 'desc' } | null>(null);

  useEffect(() => {
    fetchSOWRecords();
  }, [selectedBusinessUnit]);

  useEffect(() => {
    applyFilters();
  }, [searchQuery, selectedMode, sowRecords]);

  const fetchSOWRecords = async () => {
    try {
      setLoading(true);

      // Fetch all SOW records from history API
      const response = await apiService.fetchDocuments({
        businessUnit: isAdmin && selectedBusinessUnit !== 'all' ? selectedBusinessUnit : undefined,
      });

      if (response.success && response.documents) {
        const records: SOWRecord[] = response.documents.map((item: any) => {
          const doc = item.document || item;
          const taskMetadata = item.task?.metadata || {};
          return {
            sow_id: doc.document_id || doc.id,
            document_id: doc.document_id || doc.doc_id || doc.id,
            project_name: doc.project_name || doc.name || 'N/A',
            customer_name: doc.customer_name || doc.company || doc.company_name || 'N/A',
            author_name: doc.author_name || doc.author || 'N/A',
            mode: doc.mode || 'POC',
            document_date: doc.document_date || doc.date || doc.created_at || new Date().toISOString().split('T')[0],
            s3_url: doc.s3_url || doc.download_url || '',
            drive_link: doc.drive_link || '',
            created_at: doc.timestamp || doc.created_at,
            business_unit: doc.business_unit || taskMetadata.business_unit,
            total_tokens: doc.total_tokens ?? taskMetadata.total_tokens,
          };
        });

        setSOWRecords(records);
        calculateStatistics(records);
      }
    } catch (error) {
      console.error('Error fetching SOW records:', error);
      toast.error('Failed to fetch SOW records', {
        position: 'top-right',
        autoClose: 3000
      });
    } finally {
      setLoading(false);
    }
  };

  const calculateStatistics = (records: SOWRecord[]) => {
    const now = new Date();
    const currentMonth = now.getMonth();
    const currentYear = now.getFullYear();

    const stats = {
      totalSOWs: records.length,
      thisMonthSOWs: records.filter(record => {
        const recordDate = new Date(record.document_date || record.created_at || '');
        return recordDate.getMonth() === currentMonth && recordDate.getFullYear() === currentYear;
      }).length,
      pocCount: records.filter(r => r.mode === 'POC').length,
      prodCount: records.filter(r => r.mode === 'PROD' || r.mode === 'PRODUCTION').length,
      pocToProdCount: records.filter(r => r.mode === 'POC_TO_PROD' || r.mode === 'POC-TO-PRODUCTION').length
    };

    setStatistics(stats);
  };

  const applyFilters = () => {
    let filtered = [...sowRecords];

    // Apply search filter
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(record =>
        record.customer_name.toLowerCase().includes(query) ||
        record.project_name.toLowerCase().includes(query)
      );
    }

    // Apply mode filter
    if (selectedMode !== 'all') {
      filtered = filtered.filter(record => {
        if (selectedMode === 'POC') return record.mode === 'POC';
        if (selectedMode === 'PROD') return record.mode === 'PROD' || record.mode === 'PRODUCTION';
        if (selectedMode === 'POC_TO_PROD') return record.mode === 'POC_TO_PROD' || record.mode === 'POC-TO-PRODUCTION';
        return true;
      });
    }

    setFilteredRecords(filtered);
  };

  const handleSort = (key: string) => {
    let direction: 'asc' | 'desc' = 'asc';

    if (sortConfig && sortConfig.key === key && sortConfig.direction === 'asc') {
      direction = 'desc';
    }

    setSortConfig({ key, direction });
  };

  const getSortedRecords = () => {
    if (!sortConfig) {
      return filteredRecords;
    }

    const sorted = [...filteredRecords].sort((a, b) => {
      let aValue: any;
      let bValue: any;

      if (sortConfig.key === 'date') {
        aValue = new Date(a.document_date || 0).getTime();
        bValue = new Date(b.document_date || 0).getTime();
      } else if (sortConfig.key === 'project') {
        aValue = a.project_name.toLowerCase();
        bValue = b.project_name.toLowerCase();
      } else if (sortConfig.key === 'customer') {
        aValue = a.customer_name.toLowerCase();
        bValue = b.customer_name.toLowerCase();
      } else if (sortConfig.key === 'author') {
        aValue = a.author_name.toLowerCase();
        bValue = b.author_name.toLowerCase();
      } else {
        return 0;
      }

      if (aValue < bValue) {
        return sortConfig.direction === 'asc' ? -1 : 1;
      }
      if (aValue > bValue) {
        return sortConfig.direction === 'asc' ? 1 : -1;
      }
      return 0;
    });

    return sorted;
  };

  const renderSortIcon = (columnKey: string) => {
    if (!sortConfig || sortConfig.key !== columnKey) {
      return <ArrowUpDown size={14} className="sort-icon-inactive" />;
    }
    return sortConfig.direction === 'asc'
      ? <ArrowUp size={14} className="sort-icon-active" />
      : <ArrowDown size={14} className="sort-icon-active" />;
  };

  const handleDownload = async (record: SOWRecord) => {
    const s3Url = record.s3_url || record.drive_link;

    if (!s3Url) {
      toast.error('No download URL available', {
        position: 'top-right',
        autoClose: 3000
      });
      return;
    }

    const toastId = toast.loading('Downloading document...', {
      position: 'top-right'
    });

    try {
      const urlParts = s3Url.split('/');
      const s3Filename = urlParts[urlParts.length - 1].split('?')[0];
      const filename = s3Filename || `${record.project_name}_${record.mode}.pdf`;
      const saved = await downloadWithNativeSaveAs(
        () => apiService.downloadDocument(s3Url, record.document_id),
        filename,
      );

      toast.update(toastId, {
        render: saved ? 'Document downloaded successfully!' : 'Download cancelled',
        type: saved ? 'success' : 'info',
        isLoading: false,
        autoClose: 3000
      });
    } catch (error) {
      console.error('Download error:', error);
      toast.update(toastId, {
        render: `Failed to download: ${error instanceof Error ? error.message : 'Unknown error'}`,
        type: 'error',
        isLoading: false,
        autoClose: 5000
      });
    }
  };

  const getModeLabel = (mode: string) => {
    if (mode === 'POC') return 'POC';
    if (mode === 'PROD' || mode === 'PRODUCTION') return 'Production';
    if (mode === 'POC_TO_PROD' || mode === 'POC-TO-PRODUCTION') return 'POC to Prod';
    return mode;
  };

  const getModeColor = (mode: string) => {
    if (mode === 'POC') return '#2563eb';
    if (mode === 'PROD' || mode === 'PRODUCTION') return '#059669';
    if (mode === 'POC_TO_PROD' || mode === 'POC-TO-PRODUCTION') return '#7c3aed';
    return '#6b7280';
  };

  return (
    <div className="sow-tracker">
      <div className="tracker-header">
        <div className="header-content">
          <h1>SOW Tracker Dashboard</h1>
          <p>{isAdmin ? 'Monitor and manage SOWs across all business units' : `Monitor and manage ${user?.business_unit} SOWs`}</p>
        </div>
      </div>

      {/* Statistics Cards */}
      <div className="statistics-grid">
        <div className="stat-card stat-card-primary">
          <div className="stat-icon">
            <FileText size={32} />
          </div>
          <div className="stat-content">
            <h3>Total SOWs</h3>
            <p className="stat-value">{statistics.totalSOWs}</p>
            <span className="stat-label">All time documents</span>
          </div>
        </div>

        <div className="stat-card stat-card-success">
          <div className="stat-icon">
            <TrendingUp size={32} />
          </div>
          <div className="stat-content">
            <h3>This Month</h3>
            <p className="stat-value">{statistics.thisMonthSOWs}</p>
            <span className="stat-label">Generated in {new Date().toLocaleString('default', { month: 'long' })}</span>
          </div>
        </div>

        <div className="stat-card stat-card-blue">
          <div className="stat-icon">
            <FileText size={32} />
          </div>
          <div className="stat-content">
            <h3>POC SOWs</h3>
            <p className="stat-value">{statistics.pocCount}</p>
            <span className="stat-label">Proof of Concept</span>
          </div>
        </div>

        <div className="stat-card stat-card-green">
          <div className="stat-icon">
            <FileText size={32} />
          </div>
          <div className="stat-content">
            <h3>Production SOWs</h3>
            <p className="stat-value">{statistics.prodCount}</p>
            <span className="stat-label">Production ready</span>
          </div>
        </div>

        <div className="stat-card stat-card-purple">
          <div className="stat-icon">
            <FileText size={32} />
          </div>
          <div className="stat-content">
            <h3>POC to Prod</h3>
            <p className="stat-value">{statistics.pocToProdCount}</p>
            <span className="stat-label">Transition documents</span>
          </div>
        </div>
      </div>

      {/* Filters and Search */}
      <div className="tracker-controls">
        <div className="search-container">
          <Search size={18} className="search-icon" />
          <input
            type="text"
            placeholder="Search by customer or project name..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="search-input"
          />
        </div>

        {isAdmin && (
          <select
            className="search-input bu-filter-select"
            value={selectedBusinessUnit}
            onChange={(event) => setSelectedBusinessUnit(event.target.value)}
            aria-label="Filter by business unit"
          >
            <option value="all">All Business Units</option>
            {BUSINESS_UNITS.map(unit => <option key={unit} value={unit}>{unit}</option>)}
          </select>
        )}

        <div className="filter-buttons">
          <button
            className={`filter-btn ${selectedMode === 'all' ? 'active' : ''}`}
            onClick={() => setSelectedMode('all')}
          >
            <Filter size={16} />
            All
          </button>
          <button
            className={`filter-btn ${selectedMode === 'POC' ? 'active' : ''}`}
            onClick={() => setSelectedMode('POC')}
          >
            POC
          </button>
          <button
            className={`filter-btn ${selectedMode === 'PROD' ? 'active' : ''}`}
            onClick={() => setSelectedMode('PROD')}
          >
            Production
          </button>
          <button
            className={`filter-btn ${selectedMode === 'POC_TO_PROD' ? 'active' : ''}`}
            onClick={() => setSelectedMode('POC_TO_PROD')}
          >
            POC to Prod
          </button>
        </div>
      </div>

      {/* Records Table */}
      <div className="tracker-table-container">
        {loading ? (
          <div className="loading-state">
            <Loader className="spinner" size={48} />
            <p>Loading SOW records...</p>
          </div>
        ) : (
          <table className="tracker-table">
            <thead>
              <tr>
                <th onClick={() => handleSort('project')} className="sortable-header">
                  <span className="header-content">
                    Project Name
                    {renderSortIcon('project')}
                  </span>
                </th>
                <th onClick={() => handleSort('customer')} className="sortable-header">
                  <span className="header-content">
                    Customer Name
                    {renderSortIcon('customer')}
                  </span>
                </th>
                <th onClick={() => handleSort('author')} className="sortable-header">
                  <span className="header-content">
                    Author
                    {renderSortIcon('author')}
                  </span>
                </th>
                <th>Type</th>
                {isAdmin && <th>Business Unit</th>}
                <th onClick={() => handleSort('date')} className="sortable-header">
                  <span className="header-content">
                    Date
                    {renderSortIcon('date')}
                  </span>
                </th>
                <th>Total Tokens</th>
                <th className="actions-column">Actions</th>
              </tr>
            </thead>
            <tbody>
              {getSortedRecords().length > 0 ? (
                getSortedRecords().map((record) => (
                  <tr key={record.sow_id}>
                    <td className="project-name">{record.project_name}</td>
                    <td>{record.customer_name}</td>
                    <td>{record.author_name}</td>
                    <td>
                      <span
                        className="type-badge"
                        style={{
                          backgroundColor: `${getModeColor(record.mode)}20`,
                          color: getModeColor(record.mode)
                        }}
                      >
                        {getModeLabel(record.mode)}
                      </span>
                    </td>
                    {isAdmin && <td>{record.business_unit || 'Unassigned'}</td>}
                    <td>{new Date(record.document_date).toLocaleDateString()}</td>
                    <td>{formatTokenCount(record.total_tokens)}</td>
                    <td className="actions-column">
                      {(record.s3_url || record.drive_link) && (
                        <button
                          onClick={() => handleDownload(record)}
                          className="download-icon-btn"
                          title="Download document"
                        >
                          <Download size={16} />
                        </button>
                      )}
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={isAdmin ? 8 : 7} className="no-records">
                    No SOW records found
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>

      <div className="tracker-footer">
        <p>Showing {filteredRecords.length} of {sowRecords.length} records</p>
      </div>
    </div>
  );
};

export default SOWTracker;
