import React, { createContext, useContext, useState, ReactNode, useEffect } from 'react';
import apiService from '../services/apiService';

export const BUSINESS_UNITS = ['GenAI', 'Database Management', 'Data Engineering', 'Cloud', 'MLOps'] as const;
export type BusinessUnit = typeof BUSINESS_UNITS[number];
export type UserRole = 'ADMIN' | 'GENAI' | 'DATABASE_MANAGEMENT' | 'DATA_ENGINEERING' | 'CLOUD' | 'MLOPS' | 'USER';

export interface AuthUser {
  email: string;
  name: string;
  role: UserRole;
  roles: UserRole[];
  business_unit: BusinessUnit | null;
  business_units: BusinessUnit[];
  employee_id?: number | null;
}

interface AuthContextType {
  isAuthenticated: boolean;
  user: AuthUser | null;
  isAdmin: boolean;
  isIndividualUser: boolean;
  canAccessAccounts: boolean;
  isLoading: boolean;
  sessionError: string;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within an AuthProvider');
  return context;
};

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const normaliseUser = (value: AuthUser): AuthUser => {
    const roles = (value.roles?.length ? value.roles : [value.role])
      .map((role) => String(role).trim().toUpperCase() as UserRole)
      .filter(Boolean);
    return ({
    ...value,
    role: (roles.includes('ADMIN') ? 'ADMIN' : roles[0] || 'USER') as UserRole,
    roles,
    business_units: value.business_units?.length
      ? value.business_units
      : value.business_unit ? [value.business_unit] : [],
    });
  };
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [sessionError, setSessionError] = useState('');
  const authenticatedEmail = user?.email;

  const logout = async () => {
    await apiService.logout();
    setUser(null);
  };

  useEffect(() => {
    const expired = () => setUser(null);
    window.addEventListener('sow-auth-expired', expired);
    return () => window.removeEventListener('sow-auth-expired', expired);
  }, []);

  useEffect(() => {
    // Retire credentials left by the old password login; trust only the server.
    localStorage.removeItem('authToken');
    localStorage.removeItem('authUser');
    let active = true;
    apiService.getCurrentUser().then(response => {
      if (active && response.user) setUser(normaliseUser(response.user));
    }).catch(error => {
      if (active && !/Authentication required|Session expired|Invalid session|inactive|no longer exists/i.test(error?.message || '')) {
        setSessionError('Unable to check your session. You can try signing in again.');
      }
    }).finally(() => { if (active) setIsLoading(false); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (authenticatedEmail) void apiService.prepareSemanticIndex().catch(() => {});
  }, [authenticatedEmail]);

  const isIndividualUser = Boolean(user && user.role === 'USER');

  return (
    <AuthContext.Provider value={{
      isAuthenticated: Boolean(user),
      isLoading,
      sessionError,
      user,
      isAdmin: Boolean(user?.roles.includes('ADMIN')),
      isIndividualUser,
      canAccessAccounts: Boolean(user && (user.roles.includes('ADMIN') || user.role !== 'USER')),
      logout,
    }}>
      {children}
    </AuthContext.Provider>
  );
};
