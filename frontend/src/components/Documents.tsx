import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

const Documents: React.FC = () => {
  const navigate = useNavigate();

  useEffect(() => {
    navigate('/dashboard', { state: { view: 'documents' }, replace: true });
  }, [navigate]);

  return null;
};

export default Documents;
