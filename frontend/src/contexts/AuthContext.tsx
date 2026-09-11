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
  login: (email: string, password: string) => Promise<{ success: boolean; error?: string }>;
  logout: () => void;
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
  const [user, setUser] = useState<AuthUser | null>(() => {
    try {
      const stored = localStorage.getItem('authUser');
      return stored ? normaliseUser(JSON.parse(stored)) : null;
    } catch {
      return null;
    }
  });

  const logout = () => {
    setUser(null);
    localStorage.removeItem('authToken');
    localStorage.removeItem('authUser');
  };

  useEffect(() => {
    const expired = () => logout();
    window.addEventListener('sow-auth-expired', expired);
    return () => window.removeEventListener('sow-auth-expired', expired);
  }, []);

  useEffect(() => {
    if (!localStorage.getItem('authToken')) return;
    let active = true;
    apiService.getCurrentUser()
      .then((response) => {
        if (!active || !response.user) return;
        const refreshedUser = normaliseUser(response.user);
        localStorage.setItem('authUser', JSON.stringify(refreshedUser));
        setUser(refreshedUser);
      })
      .catch(() => {
        // authenticatedFetch emits sow-auth-expired for invalid sessions.
      });
    return () => { active = false; };
  }, []);

  const login = async (email: string, password: string) => {
    try {
      const response = await apiService.login(email, password);
      localStorage.setItem('authToken', response.token);
      const authenticatedUser = normaliseUser(response.user);
      localStorage.setItem('authUser', JSON.stringify(authenticatedUser));
      setUser(authenticatedUser);
      return { success: true };
    } catch (error) {
      return { success: false, error: error instanceof Error ? error.message : 'Unable to sign in' };
    }
  };

  const isIndividualUser = Boolean(user && user.role === 'USER');

  return (
    <AuthContext.Provider value={{
      isAuthenticated: Boolean(user && localStorage.getItem('authToken')),
      user,
      isAdmin: Boolean(user?.roles.includes('ADMIN')),
      isIndividualUser,
      canAccessAccounts: Boolean(user && (user.roles.includes('ADMIN') || user.role !== 'USER')),
      login,
      logout,
    }}>
      {children}
    </AuthContext.Provider>
  );
};
