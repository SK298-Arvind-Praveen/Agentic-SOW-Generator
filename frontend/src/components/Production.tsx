import React from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';

const Production: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div style={{ 
      padding: '40px', 
      textAlign: 'center', 
      minHeight: '100vh', 
      backgroundColor: '#f8fafc',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center'
    }}>
      <button 
        onClick={() => navigate('/dashboard')}
        style={{
          position: 'absolute',
          top: '20px',
          left: '20px',
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          padding: '10px 16px',
          backgroundColor: '#02adef',
          color: 'white',
          border: 'none',
          borderRadius: '8px',
          cursor: 'pointer'
        }}
      >
        <ArrowLeft size={16} />
        Back to Dashboard
      </button>
      
      <h1 style={{ 
        fontSize: '48px', 
        color: '#1f2937', 
        marginBottom: '16px',
        fontWeight: 'bold'
      }}>
        Production
      </h1>
      
      <p style={{ 
        fontSize: '18px', 
        color: '#6b7280',
        maxWidth: '600px',
        lineHeight: '1.6'
      }}>
        This is the Production page. SOW documents moved to production will be managed here.
      </p>
    </div>
  );
};

export default Production;