import React, { createContext, useContext, useState, ReactNode, useEffect } from 'react';
import apiService from '../services/apiService';

export const BUSINESS_UNITS = ['GenAI', 'Database Management', 'Data Engineering', 'Cloud', 'MLOps'] as const;
export type BusinessUnit = typeof BUSINESS_UNITS[number];

export interface AuthUser {
  email: string;
  name: string;
  role: 'ADMIN' | 'GENAI' | 'DATABASE_MANAGEMENT' | 'DATA_ENGINEERING' | 'CLOUD' | 'MLOPS';
  business_unit: BusinessUnit | null;
}

interface AuthContextType {
  isAuthenticated: boolean;
  user: AuthUser | null;
  isAdmin: boolean;
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
  const [user, setUser] = useState<AuthUser | null>(() => {
    try {
      const stored = localStorage.getItem('authUser');
      return stored ? JSON.parse(stored) : null;
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

  const login = async (email: string, password: string) => {
    try {
      const response = await apiService.login(email, password);
      localStorage.setItem('authToken', response.token);
      localStorage.setItem('authUser', JSON.stringify(response.user));
      setUser(response.user);
      return { success: true };
    } catch (error) {
      return { success: false, error: error instanceof Error ? error.message : 'Unable to sign in' };
    }
  };

  return (
    <AuthContext.Provider value={{
      isAuthenticated: Boolean(user && localStorage.getItem('authToken')),
      user,
      isAdmin: user?.role === 'ADMIN',
      login,
      logout,
    }}>
      {children}
    </AuthContext.Provider>
  );
};
