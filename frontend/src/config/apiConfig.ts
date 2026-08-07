/**
 * API Configuration
 * Centralized configuration for API endpoints and settings
 */

const API_CONFIG = {
  BASE_URL: process.env.REACT_APP_API_URL || 'http://localhost:9000',
  ENDPOINTS: {
    GENERATE_SOW: '/api/generate'
  },
  TIMEOUT: 30000,  // 30 seconds — for long-running generation only
  FAST_TIMEOUT: 8000, // 8 seconds for simple CRUD calls
  RETRY_ATTEMPTS: 2,  // was 3 — third retry added 2s dead time on real failures
  RETRY_DELAY: 500    // was 1000ms — halved to reduce wait on transient errors
};

export default API_CONFIG;
