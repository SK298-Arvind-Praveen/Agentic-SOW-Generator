from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import os
import pickle
from pathlib import Path

SCOPES = ['https://www.googleapis.com/auth/drive']
TOKEN_FILE = 'token.pickle'
CREDENTIALS_FILE = 'credentials.json'

# Folder mapping for different modes
FOLDER_MAPPING = {
    'poc': 'poc',
    'production': 'production',
    'poc_to_prod': 'poc_to_prod'
}

def authenticate():
    """Authenticate with Google Drive using OAuth2"""
    creds = None
    
    # If token.pickle exists, use it
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'rb') as token:
            creds = pickle.load(token)
    
    # If no valid credentials, get new ones
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                print("🔄 Refreshing Google Drive credentials...")
                creds.refresh(Request())
                print("✓ Credentials refreshed successfully")
            except Exception as e:
                print(f"⚠️  Could not refresh token: {e}")
                print("🔄 Re-authenticating with fresh login...")
                # Token is invalid, need fresh authentication
                if os.path.exists(TOKEN_FILE):
                    os.remove(TOKEN_FILE)
                creds = None
        
        if not creds:
            # This will open your browser to login
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"❌ {CREDENTIALS_FILE} not found!\n"
                    f"Please:\n"
                    f"1. Go to Google Cloud Console\n"
                    f"2. Create OAuth 2.0 Client ID (Desktop app)\n"
                    f"3. Download and save as '{CREDENTIALS_FILE}'"
                )
            
            print("🌐 Opening browser for Google Drive authentication...")
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save credentials for next time
        with open(TOKEN_FILE, 'wb') as token:
            pickle.dump(creds, token)
            print("✓ Credentials saved for future use")
    
    return creds

def ensure_all_folders_exist(drive_service):
    """Ensure all required folders exist in Google Drive"""
    print("\n🔍 Checking/Creating required folders in Google Drive...")
    
    folder_ids = {}
    
    for key, folder_name in FOLDER_MAPPING.items():
        try:
            query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            results = drive_service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name)',
                pageSize=1
            ).execute()
            
            files = results.get('files', [])
            
            if files:
                folder_ids[key] = files[0]['id']
                print(f"   ✓ Found folder: {folder_name}")
            else:
                # Create new folder
                file_metadata = {
                    'name': folder_name,
                    'mimeType': 'application/vnd.google-apps.folder'
                }
                folder = drive_service.files().create(
                    body=file_metadata,
                    fields='id'
                ).execute()
                folder_ids[key] = folder.get('id')
                print(f"   ✓ Created new folder: {folder_name}")
        
        except Exception as e:
            print(f"   ❌ Error with folder '{folder_name}': {e}")
            folder_ids[key] = None
    
    return folder_ids

def get_or_create_folder(drive_service, folder_name):
    """Find existing folder or create a new one"""
    try:
        # Search for folder with the given name
        query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        results = drive_service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name)',
            pageSize=1
        ).execute()
        
        files = results.get('files', [])
        
        if files:
            print(f"   ✓ Using existing folder: {folder_name}")
            return files[0]['id']
        else:
            # Create new folder
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            folder = drive_service.files().create(
                body=file_metadata,
                fields='id'
            ).execute()
            print(f"   ✓ Created new folder: {folder_name}")
            return folder.get('id')
    except Exception as e:
        print(f"❌ Error managing folder: {e}")
        raise

def upload_file_to_drive(file_path, folder_name='poc'):
    """
    Upload a file to Google Drive in specified folder
    
    Args:
        file_path: Full path to the file to upload
        folder_name: Name of the folder in Google Drive
    
    Returns:
        dict: File info (id, name) or None if failed
    """
    
    file_path = Path(file_path)
    
    # Validate file exists
    if not file_path.exists():
        print(f"❌ Error: File not found at {file_path}")
        return None
    
    # Determine MIME type based on file extension
    file_ext = file_path.suffix.lower()
    mime_types = {
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        '.doc': 'application/msword',
        '.pdf': 'application/pdf',
        '.json': 'application/json',
        '.txt': 'text/plain'
    }
    mime_type = mime_types.get(file_ext, 'application/octet-stream')
    
    try:
        # Authenticate
        creds = authenticate()
        
        # Build Drive service
        drive_service = build('drive', 'v3', credentials=creds)
        
        # Get or create the folder
        folder_id = get_or_create_folder(drive_service, folder_name)
        
        file_name = file_path.name
        print(f"\n📤 Uploading {file_name} to '{folder_name}' folder...")
        
        # Upload the file to the folder
        file_metadata = {
            'name': file_name,
            'parents': [folder_id]
        }
        
        media = MediaFileUpload(
            str(file_path),
            mimetype=mime_type,
            resumable=True
        )
        
        file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, name, webViewLink'
        ).execute()
        
        file_id = file.get('id')
        
        print(f'✅ File uploaded successfully!')
        print(f'   File Name: {file_name}')
        print(f'   File ID: {file_id}')
        print(f'   View it here: https://drive.google.com/file/d/{file_id}/view')
        
        return {
            'id': file_id,
            'name': file_name,
            'link': f'https://drive.google.com/file/d/{file_id}/view'
        }
        
    except FileNotFoundError as e:
        print(f"❌ {e}")
        return None
    except Exception as error:
        print(f"❌ Error uploading file: {error}")
        import traceback
        traceback.print_exc()
        return None

def upload_generated_document(output_file_path, folder_name='poc'):
    """
    Upload the final document generated by DocumentBuilder
    This is the main function to call after document generation
    
    Args:
        output_file_path: Path returned from DocumentBuilder.build_document()
        folder_name: Google Drive folder name (supports: 'poc', 'production', 'poc_to_prod')
    
    Returns:
        dict: Upload result info or None
    """
    
    if not output_file_path:
        print("❌ Error: No output file path provided")
        return None
    
    # Normalize folder name
    folder_name = folder_name.lower().strip()
    
    # Validate folder name
    if folder_name not in FOLDER_MAPPING:
        print(f"⚠️  Warning: Unknown folder '{folder_name}'. Using 'poc' instead.")
        folder_name = 'poc'
    
    print("\n" + "="*60)
    print("🔄 Starting Document Upload to Google Drive")
    print(f"📁 Target Folder: {folder_name}")
    print("="*60)
    
    try:
        # Authenticate
        creds = authenticate()
        
        # Build Drive service
        drive_service = build('drive', 'v3', credentials=creds)
        
        # Ensure all folders exist first
        ensure_all_folders_exist(drive_service)
        
        # Then upload to the specific folder
        result = upload_file_to_drive(output_file_path, folder_name)
        
        if result:
            print("\n" + "="*60)
            print("✅ Document Upload Complete!")
            print("="*60)
            return result
        else:
            print("\n" + "="*60)
            print("❌ Document Upload Failed")
            print("="*60)
            return None
    
    except Exception as e:
        print(f"❌ Error during upload: {e}")
        import traceback
        traceback.print_exc()
        return None

# For standalone testing - if you want to upload an existing file
if __name__ == '__main__':
    # Example: Upload a file manually
    print("\n📝 Document Upload Tool - Standalone Mode")
    print("="*60)
    
    file_to_upload = input("Enter the full path to the file to upload: ").strip()
    
    print("\nAvailable folders:")
    for key, value in FOLDER_MAPPING.items():
        print(f"  • {key}")
    
    folder = input("\nSelect folder (default: poc): ").strip().lower() or 'poc'
    
    if file_to_upload:
        upload_file_to_drive(file_to_upload, folder)
    else:
        print("❌ No file path provided")