"""
S3 Upload Module for ShellKodeSOW LangGraph Agent
Saves generated documents to AWS S3 bucket
FIXED: Correct folder paths for all modes
"""
import boto3
import os
from pathlib import Path
from datetime import datetime
from urllib.parse import unquote, urlparse
from botocore.exceptions import NoCredentialsError, ClientError
from dotenv import load_dotenv

# Load environment variables
load_dotenv(Path(__file__).resolve().parents[2] / "config" / ".env")

# AWS Configuration
S3_BUCKET_NAME = os.getenv('S3_BUCKET_NAME', 'agentic-sow-files')


def parse_s3_location(s3_url, expected_bucket=None):
    """Parse an S3/HTTPS URL and restrict it to the configured bucket."""
    expected_bucket = expected_bucket or os.getenv(
        'S3_BUCKET_NAME', 'agentic-sow-files'
    )
    parsed = urlparse(str(s3_url).strip())

    if parsed.scheme == 's3':
        bucket = parsed.netloc
        key = unquote(parsed.path.lstrip('/'))
    elif parsed.scheme in {'http', 'https'}:
        host = (parsed.hostname or '').lower()
        key = unquote(parsed.path.lstrip('/'))
        if host.endswith('.amazonaws.com') and '.s3' in host:
            bucket = host.split('.s3', 1)[0]
        elif host == 's3.amazonaws.com' or (
            host.endswith('.amazonaws.com') and host.startswith(('s3.', 's3-'))
        ):
            path_parts = key.split('/', 1)
            if len(path_parts) != 2:
                raise ValueError('S3 URL does not contain an object key')
            bucket, key = path_parts
        else:
            raise ValueError('Only Amazon S3 URLs are supported')
    else:
        raise ValueError('Only s3:// or https:// S3 URLs are supported')

    if bucket != expected_bucket:
        raise ValueError('The requested object is not in the configured S3 bucket')
    if not key:
        raise ValueError('S3 URL does not contain an object key')

    return bucket, key

# ✅ FIXED: Correct S3 folder structure matching FOLDER_MAPPING in main.py
S3_FOLDER_STRUCTURE = {
    'poc': 'POC',                    
    'production': 'Production',      
    'poc_to_prod': 'POC_to_Production' 
}

class S3Uploader:
    def __init__(self):
        """Initialize S3 client with explicit credentials from environment"""
        try:
            # Explicitly use environment variables
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
                aws_session_token=os.getenv('AWS_SESSION_TOKEN'),
                region_name=os.getenv('AWS_REGION', 'us-east-1')
            )
            # Test connection
            self.s3_client.head_bucket(Bucket=S3_BUCKET_NAME)
            print(f"✓ Connected to S3 bucket: {S3_BUCKET_NAME}")
        except NoCredentialsError:
            print("❌ Error: AWS credentials not found")
            print("   Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables")
            raise
        except ClientError as e:
            print(f"❌ Error connecting to S3 bucket: {e}")
            raise
            raise
    
    def get_s3_folder_path(self, mode):
        """
        Get S3 folder path based on mode
        
        Args:
            mode: 'poc', 'production', or 'poc_to_prod'
        
        Returns:
            Correct S3 folder name
        """
        # Normalize mode name
        mode_normalized = mode.lower().strip()
        
        # Use mapping, default to POC if unknown
        folder = S3_FOLDER_STRUCTURE.get(mode_normalized, 'POC')
        
        print(f"   📁 S3 Folder: {folder}")
        return folder
    
    def generate_s3_key(self, file_name, mode):
        """
        Generate S3 key with folder structure
        
        Format: {folder}/{timestamp}_{original_filename}
        Examples:
            - POC/2025-01-05_120345_SOW_Acme_Corp.docx
            - Production/2025-01-05_120345_SOW_Client_Inc.docx
            - POC_to_Production/2025-01-05_120345_SOW_Upgrade.docx
        
        Args:
            file_name: Original file name
            mode: 'poc', 'production', or 'poc_to_prod'
        
        Returns:
            Full S3 key path
        """
        folder = self.get_s3_folder_path(mode)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        
        # Keep original filename, add timestamp prefix
        file_key = f"{folder}/{timestamp}_{file_name}"
        
        return file_key
    
    def upload_file_to_s3(self, file_path, mode='poc', custom_name=None):
        """
        Upload a file to S3
        
        Args:
            file_path (str): Full path to the file to upload
            mode (str): 'poc', 'production', or 'poc_to_prod' (normalized to lowercase)
            custom_name (str): Optional custom file name for S3
        
        Returns:
            dict: Upload result info with keys:
                - bucket: S3 bucket name
                - key: S3 object key (full path)
                - file_name: File name in S3
                - s3_url: s3://bucket/key format
                - https_url: https://bucket.s3.amazonaws.com/key format
                - mode: Mode used for upload
                OR None if failed
        """
        file_path = Path(file_path)
        
        # Validate file exists
        if not file_path.exists():
            print(f"❌ Error: File not found at {file_path}")
            return None
        
        try:
            # Normalize mode to lowercase
            mode = mode.lower().strip()
            
            # Generate S3 key
            file_name = custom_name if custom_name else file_path.name
            s3_key = self.generate_s3_key(file_name, mode)
            
            # Determine content type
            content_type = self._get_content_type(file_path)
            
            # Upload file
            print(f"\n📤 Uploading to S3...")
            print(f"   File: {file_path.name}")
            print(f"   Mode: {mode}")
            print(f"   S3 Path: s3://{S3_BUCKET_NAME}/{s3_key}")
            
            self.s3_client.upload_file(
                str(file_path),
                S3_BUCKET_NAME,
                s3_key,
                ExtraArgs={'ContentType': content_type}
            )
            
            # Generate URLs
            s3_url = f"s3://{S3_BUCKET_NAME}/{s3_key}"
            https_url = f"https://{S3_BUCKET_NAME}.s3.amazonaws.com/{s3_key}"
            
            result = {
                'bucket': S3_BUCKET_NAME,
                'key': s3_key,
                'file_name': file_name,
                's3_url': s3_url,
                'https_url': https_url,
                'mode': mode
            }
            
            print(f'\n✅ File uploaded successfully!')
            print(f'   File Name: {file_name}')
            print(f'   S3 Path: {s3_url}')
            print(f'   HTTPS URL: {https_url}')
            
            return result
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_msg = e.response['Error']['Message']
            print(f"❌ S3 Error ({error_code}): {error_msg}")
            return None
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def upload_generated_document(self, output_file_path, mode='poc'):
        """
        Upload the final document generated by DocumentBuilder
        Main function to call after document generation
        
        Args:
            output_file_path (str): Path returned from document generation
            mode (str): 'poc', 'production', or 'poc_to_prod'
        
        Returns:
            dict: Upload result info or None
        """
        if not output_file_path:
            print("❌ Error: No output file path provided")
            return None
        
        print("\n" + "="*60)
        print("🔄 Starting Document Upload to S3")
        print("="*60)
        
        result = self.upload_file_to_s3(output_file_path, mode)
        
        if result:
            print("\n" + "="*60)
            print("✅ S3 Upload Complete!")
            print("="*60)
            return result
        else:
            print("\n" + "="*60)
            print("❌ S3 Upload Failed")
            print("="*60)
            return None
    
    def upload_multiple_files(self, file_paths, mode='poc'):
        """
        Upload multiple files at once
        
        Args:
            file_paths (list): List of file paths to upload
            mode (str): 'poc', 'production', or 'poc_to_prod'
        
        Returns:
            list: List of upload results
        """
        results = []
        
        print("\n" + "="*60)
        print(f"🔄 Uploading {len(file_paths)} files to S3...")
        print("="*60)
        
        for file_path in file_paths:
            result = self.upload_file_to_s3(file_path, mode)
            if result:
                results.append(result)
        
        print(f"\n✅ Batch upload complete: {len(results)}/{len(file_paths)} files uploaded")
        
        return results
    
    @staticmethod
    def _get_content_type(file_path):
        """Determine MIME type based on file extension"""
        ext = file_path.suffix.lower()
        
        mime_types = {
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.doc': 'application/msword',
            '.pdf': 'application/pdf',
            '.json': 'application/json',
            '.txt': 'text/plain',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '.csv': 'text/csv',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg'
        }
        
        return mime_types.get(ext, 'application/octet-stream')


def upload_to_s3(file_path, mode='poc'):
    """
    Convenience function for single file upload
    
    Args:
        file_path (str): Path to file to upload
        mode (str): 'poc', 'production', or 'poc_to_prod'
    
    Returns:
        dict: Upload result or None
    """
    try:
        uploader = S3Uploader()
        return uploader.upload_generated_document(file_path, mode)
    except Exception as e:
        print(f"❌ S3 upload failed: {e}")
        import traceback
        traceback.print_exc()
        return None


# For standalone testing
if __name__ == '__main__':
    print("\n📝 S3 Document Upload Tool - Standalone Mode")
    print("="*60)
    
    try:
        uploader = S3Uploader()
        
        file_to_upload = input("Enter the full path to the file to upload: ").strip()
        
        if file_to_upload:
            print("\nAvailable modes:")
            print("  • poc                  (POC folder)")
            print("  • production           (Production folder)")
            print("  • poc_to_prod          (POC_to_Production folder)")
            
            mode = input("\nEnter mode (default: poc): ").strip().lower() or 'poc'
            
            result = uploader.upload_generated_document(file_to_upload, mode)
            
            if result:
                print("\n✅ Upload successful!")
                print(f"S3 URL: {result['s3_url']}")
                print(f"HTTPS: {result['https_url']}")
        else:
            print("❌ No file path provided")
            
    except Exception as e:
        print(f"❌ Error: {e}")
