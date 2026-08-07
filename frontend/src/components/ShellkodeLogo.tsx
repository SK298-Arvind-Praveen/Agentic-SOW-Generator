import React from 'react';
import logoSvg from '../assets/Images/logo.svg';

interface ShellkodeLogoProps {
  size?: 'small' | 'medium' | 'large';
  className?: string;
  logoOnly?: boolean;
}

const ShellkodeLogo: React.FC<ShellkodeLogoProps> = ({ size = 'medium', className = '', logoOnly = false }) => {
  const sizeClasses = {
    small: 'logo-small',
    medium: 'logo-medium', 
    large: 'logo-large'
  };

  return (
    <div className={`shellkode-logo ${sizeClasses[size]} ${logoOnly ? 'logo-only' : ''} ${className}`}>
      <img 
        src={logoSvg} 
        alt="Shellkode" 
        className="logo-image"
      />
    </div>
  );
};

export default ShellkodeLogo;