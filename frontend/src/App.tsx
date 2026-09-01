import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { ToastContainer } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import Login from './components/Login';
import Dashboard from './components/Dashboard';
import Production from './components/Production';
import Documents from './components/Documents';
import Accounts from './components/Accounts';
import AccountDetail from './components/AccountDetail';
import ProjectDetail from './components/ProjectDetail';
import SOWTracker from './components/SOWTracker';
import SOWRecords from './components/SOWRecords';
import UserManagement from './components/UserManagement';
import Layout from './components/Layout';
import './App.css';

const ProtectedLayout: React.FC = () => {
  const { isAuthenticated } = useAuth();
  return isAuthenticated ? <Layout /> : <Navigate to="/login" />;
};

const AdminOnly: React.FC<{ children: React.ReactElement }> = ({ children }) => {
  const { isAdmin } = useAuth();
  return isAdmin ? children : <Navigate to="/dashboard" replace />;
};

const App: React.FC = () => {
  return (
    <AuthProvider>
      <Router>
        <div className="App">
          <ToastContainer
            position="top-right"
            autoClose={5000}
            hideProgressBar={false}
            newestOnTop={false}
            closeOnClick
            rtl={false}
            pauseOnFocusLoss
            draggable
            pauseOnHover
            theme="light"
          />
          <Routes>
            <Route path="/login" element={<Login />} />

            {/* All protected routes share the persistent sidebar + top bar */}
            <Route element={<ProtectedLayout />}>
              {/* SOW Tracker Route */}
              <Route path="/sow-tracker" element={<SOWTracker />} />
              <Route path="/sow-records" element={<SOWRecords />} />
              <Route
                path="/user-management"
                element={<AdminOnly><UserManagement /></AdminOnly>}
              />

              {/* Account Management Routes */}
              <Route path="/accounts" element={<Accounts />} />
              <Route path="/accounts/:accountId" element={<AccountDetail />} />
              <Route path="/projects/:projectId" element={<ProjectDetail />} />

              {/* Legacy Routes */}
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/production" element={<Production />} />
              <Route path="/documents" element={<Documents />} />
            </Route>

            {/* Default Route - Redirect to Accounts */}
            <Route path="/" element={<Navigate to="/accounts" />} />
          </Routes>
        </div>
      </Router>
    </AuthProvider>
  );
};

export default App;
