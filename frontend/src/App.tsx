import React from 'react';
// import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { HashRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { ToastContainer } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import Login from './components/Login';
import Dashboard from './components/Dashboard';
import Production from './components/Production';
import Accounts from './components/Accounts';
import AccountDetail from './components/AccountDetail';
import ProjectDetail from './components/ProjectDetail';
import SOWTracker from './components/SOWTracker';
import SOWRecords from './components/SOWRecords';
import UserManagement from './components/UserManagement';
import Layout from './components/Layout';
import './App.css';

const ProtectedLayout: React.FC = () => {
  const { isAuthenticated, isLoading } = useAuth();
  if (isLoading) return <div role="status">Checking your session…</div>;
  return isAuthenticated ? <Layout /> : <Navigate to="/login" />;
};

const AdminOnly: React.FC<{ children: React.ReactElement }> = ({ children }) => {
  const { isAdmin } = useAuth();
  return isAdmin ? children : <Navigate to="/dashboard" replace />;
};

const AccountsAllowed: React.FC<{ children: React.ReactElement }> = ({ children }) => {
  const { canAccessAccounts } = useAuth();
  return canAccessAccounts ? children : <Navigate to="/dashboard" replace />;
};

const HomeRedirect: React.FC = () => {
  const { isAuthenticated, canAccessAccounts, isLoading } = useAuth();
  if (isLoading) return <div role="status">Checking your session…</div>;
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return <Navigate to={canAccessAccounts ? '/accounts' : '/dashboard'} replace />;
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
            <Route path="/signup" element={<Navigate to="/login" replace />} />
            <Route path="/verify-account" element={<Navigate to="/login" replace />} />
            <Route path="/forgot-password" element={<Navigate to="/login" replace />} />
            <Route path="/reset-password" element={<Navigate to="/login" replace />} />

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
              <Route path="/accounts" element={<AccountsAllowed><Accounts /></AccountsAllowed>} />
              <Route path="/accounts/:accountId" element={<AccountsAllowed><AccountDetail /></AccountsAllowed>} />
              <Route path="/projects/:projectId" element={<AccountsAllowed><ProjectDetail /></AccountsAllowed>} />

              {/* Legacy Routes */}
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/production" element={<Production />} />
            </Route>

            {/* Default Route - Redirect to Accounts */}
            <Route path="/" element={<HomeRedirect />} />
          </Routes>
        </div>
      </Router>
    </AuthProvider>
  );
};

export default App;
