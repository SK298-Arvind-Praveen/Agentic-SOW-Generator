"""
Run Flask app with self-signed SSL certificate for local HTTPS testing
"""
from app.core.server import app

if __name__ == '__main__':
    # Generate self-signed certificate if not exists
    import os
    if not os.path.exists('cert.pem') or not os.path.exists('key.pem'):
        print("Generating self-signed SSL certificate...")
        os.system('openssl req -x509 -newkey rsa:4096 -nodes -out cert.pem -keyout key.pem -days 365 -subj "/CN=localhost"')
    
    print("Starting Flask with HTTPS on port 9000...")
    print("Access at: https://localhost:9000")
    print("Note: Browser will show security warning - click 'Advanced' and 'Proceed'")
    
    app.run(
        host='0.0.0.0',
        port=9000,
        ssl_context=('cert.pem', 'key.pem'),
        debug=True
    )
