import os
import json
import requests
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from google.oauth2.credentials import Credentials
import io


def get_drive_credentials():
    """Get Google Drive credentials from Replit connector."""
    hostname = os.environ.get('REPLIT_CONNECTORS_HOSTNAME')
    x_replit_token = None
    
    if os.environ.get('REPL_IDENTITY'):
        x_replit_token = 'repl ' + os.environ['REPL_IDENTITY']
    elif os.environ.get('WEB_REPL_RENEWAL'):
        x_replit_token = 'depl ' + os.environ['WEB_REPL_RENEWAL']
    
    if not x_replit_token or not hostname:
        raise Exception('Replit authentication tokens not found')
    
    url = f'https://{hostname}/api/v2/connection?include_secrets=true&connector_names=google-drive'
    headers = {
        'Accept': 'application/json',
        'X_REPLIT_TOKEN': x_replit_token
    }
    
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    
    data = response.json()
    items = data.get('items', [])
    
    if not items:
        raise Exception('Google Drive connection not found. Please set up the connection first.')
    
    connection_settings = items[0]
    access_token = connection_settings.get('settings', {}).get('access_token')
    
    if not access_token:
        oauth_creds = connection_settings.get('settings', {}).get('oauth', {}).get('credentials', {})
        access_token = oauth_creds.get('access_token')
    
    if not access_token:
        raise Exception('Access token not found in Google Drive connection')
    
    credentials = Credentials(token=access_token)
    return credentials


def get_drive_service():
    """Get authenticated Google Drive service."""
    credentials = get_drive_credentials()
    service = build('drive', 'v3', credentials=credentials)
    return service


def find_or_create_folder(folder_name, parent_id=None):
    """Find a folder by name or create it if it doesn't exist in My Drive.
    
    Args:
        folder_name: Name of the folder to find/create
        parent_id: ID of the parent folder (None for root)
    
    Returns:
        Folder ID
    """
    service = get_drive_service()
    
    query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"
    
    results = service.files().list(
        q=query,
        spaces='drive',
        fields='files(id, name)'
    ).execute()
    
    files = results.get('files', [])
    
    if files:
        return files[0]['id']
    
    file_metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder'
    }
    
    if parent_id:
        file_metadata['parents'] = [parent_id]
    
    folder = service.files().create(
        body=file_metadata,
        fields='id'
    ).execute()
    
    return folder.get('id')


def find_or_create_property_files_folder():
    """Find or create the 'Property Files' folder in My Drive.
    
    Returns:
        folder_id
    """
    service = get_drive_service()
    
    try:
        query = "name='Property Files' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        results = service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name)'
        ).execute()
        
        files = results.get('files', [])
        if files:
            print("Found 'Property Files' folder in My Drive")
            return files[0]['id']
        
        print("Creating 'Property Files' folder in My Drive")
        file_metadata = {
            'name': 'Property Files',
            'mimeType': 'application/vnd.google-apps.folder'
        }
        
        folder = service.files().create(
            body=file_metadata,
            fields='id'
        ).execute()
        
        print(f"Created 'Property Files' folder with ID: {folder.get('id')}")
        return folder.get('id')
        
    except Exception as e:
        print(f"Error finding/creating Property Files folder: {e}")
        raise Exception(f"Could not find or create 'Property Files' folder in My Drive: {str(e)}")


def create_client_folder_structure(client_name, client_address):
    """Create the folder structure for a new client in My Drive.
    
    Structure:
    My Drive/
        Property Files/
            [Client Name - Address]/
                Property Images/
                Documents/
                Contracts/
    
    All folders are made accessible to anyone with the link.
    
    Args:
        client_name: Name of the client
        client_address: Address of the property
    
    Returns:
        Dictionary with folder IDs
    """
    property_files_id = find_or_create_property_files_folder()
    make_folder_shareable(property_files_id)
    
    client_folder_name = f"{client_name} - {client_address}"
    client_folder_id = find_or_create_folder(client_folder_name, property_files_id)
    make_folder_shareable(client_folder_id)
    
    property_images_id = find_or_create_folder('Property Images', client_folder_id)
    make_folder_shareable(property_images_id)
    
    documents_id = find_or_create_folder('Documents', client_folder_id)
    make_folder_shareable(documents_id)
    
    contracts_id = find_or_create_folder('Contracts', client_folder_id)
    make_folder_shareable(contracts_id)
    
    return {
        'client_folder_id': client_folder_id,
        'property_images_id': property_images_id,
        'documents_id': documents_id,
        'contracts_id': contracts_id
    }


def upload_file_to_drive(file_content, filename, folder_id, mime_type='application/octet-stream'):
    """Upload a file to Google Drive (My Drive).
    
    Args:
        file_content: File content as bytes or file-like object
        filename: Name for the file in Google Drive
        folder_id: ID of the folder to upload to
        mime_type: MIME type of the file
    
    Returns:
        Dictionary with file ID and web view link
    """
    service = get_drive_service()
    
    file_metadata = {
        'name': filename,
        'parents': [folder_id]
    }
    
    if isinstance(file_content, bytes):
        file_content = io.BytesIO(file_content)
    
    media = MediaIoBaseUpload(
        file_content,
        mimetype=mime_type,
        resumable=True
    )
    
    file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id, webViewLink, webContentLink'
    ).execute()
    
    return {
        'id': file.get('id'),
        'web_view_link': file.get('webViewLink'),
        'web_content_link': file.get('webContentLink')
    }


def make_file_public(file_id):
    """Make a file publicly accessible (anyone with link can view).
    
    Args:
        file_id: ID of the file to make public
    """
    service = get_drive_service()
    
    try:
        service.permissions().create(
            fileId=file_id,
            body={
                'type': 'anyone',
                'role': 'reader'
            }
        ).execute()
    except Exception as e:
        print(f"Warning: Could not make file public: {e}")


def make_folder_shareable(folder_id):
    """Make a folder accessible to anyone with the link (viewer access).
    
    Args:
        folder_id: ID of the folder to make shareable
    """
    service = get_drive_service()
    
    try:
        service.permissions().create(
            fileId=folder_id,
            body={
                'type': 'anyone',
                'role': 'reader'
            },
            fields='id'
        ).execute()
        print(f"Folder {folder_id} is now accessible to anyone with the link")
    except Exception as e:
        print(f"Warning: Could not make folder shareable: {e}")


def update_existing_folders_permissions():
    """Update all existing client folders to be shareable with anyone who has the link.
    This is a utility function to fix folders created before the sharing feature was added.
    
    Returns:
        Number of folders updated
    """
    from models import Client, db
    
    clients = Client.query.all()
    updated_count = 0
    
    for client in clients:
        if client.gdrive_client_folder_id:
            make_folder_shareable(client.gdrive_client_folder_id)
            updated_count += 1
        
        if client.gdrive_property_images_id:
            make_folder_shareable(client.gdrive_property_images_id)
            updated_count += 1
        
        if client.gdrive_documents_id:
            make_folder_shareable(client.gdrive_documents_id)
            updated_count += 1
        
        if client.gdrive_contracts_id:
            make_folder_shareable(client.gdrive_contracts_id)
            updated_count += 1
    
    return updated_count


def delete_file_from_drive(file_id):
    """Delete a file from Google Drive (My Drive).
    
    Args:
        file_id: ID of the file to delete
    """
    service = get_drive_service()
    
    try:
        service.files().delete(fileId=file_id).execute()
        return True
    except Exception as e:
        print(f"Error deleting file from Drive: {e}")
        return False


def get_file_content(file_id):
    """Get file content from Google Drive (My Drive).
    
    Args:
        file_id: ID of the file to retrieve
    
    Returns:
        File content as bytes
    """
    service = get_drive_service()
    
    request = service.files().get_media(fileId=file_id)
    file_content = io.BytesIO()
    
    from googleapiclient.http import MediaIoBaseDownload
    downloader = MediaIoBaseDownload(file_content, request)
    
    done = False
    while not done:
        status, done = downloader.next_chunk()
    
    file_content.seek(0)
    return file_content.read()
