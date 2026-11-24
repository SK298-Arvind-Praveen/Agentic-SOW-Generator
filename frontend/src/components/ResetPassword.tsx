import React from 'react';
import { Navigate } from 'react-router-dom';

// Historical links now lead to Google Workspace sign-in.
const ResetPassword: React.FC = () => <Navigate to="/login" replace />;
export default ResetPassword;
