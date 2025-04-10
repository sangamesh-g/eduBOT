import os
from pathlib import Path
from django.utils.text import slugify
from django.conf import settings
import uuid

def get_profile_picture_path(instance, filename):
    """
    Generate a unique file path for profile pictures.
    Format: profile_pics/username/username.extension
    """
    # Get the file extension from the original filename
    ext = Path(filename).suffix.lower()
    
    # Create a safe username-based filename
    safe_username = slugify(instance.user.username)
    
    # Create the filename using username
    filename = f"{safe_username}{ext}"
    
    # Ensure the directory exists
    profile_dir = os.path.join('profile_pics', safe_username)
    full_dir = os.path.join(settings.MEDIA_ROOT, profile_dir)
    if not os.path.exists(full_dir):
        os.makedirs(full_dir)
    
    # Return the complete path
    return os.path.join(profile_dir, filename)

def get_message_file_path(instance, filename):
    """
    Generate a unique file path for message attachments.
    Format: messages/user_id/YYYY-MM/unique_filename.extension
    """
    # Get the file extension from the original filename
    ext = Path(filename).suffix.lower()
    
    # Create a unique filename using UUID
    unique_filename = f"{uuid.uuid4().hex}{ext}"
    
    # Create directory structure: messages/user_id/YYYY-MM/
    from django.utils import timezone
    now = timezone.now()
    dir_path = os.path.join(
        'messages',
        str(instance.sender.id),
        now.strftime('%Y-%m')
    )
    
    # Ensure the directory exists
    full_dir = os.path.join(settings.MEDIA_ROOT, dir_path)
    if not os.path.exists(full_dir):
        os.makedirs(full_dir)
    
    # Return the complete path
    return os.path.join(dir_path, unique_filename)

def delete_old_profile_picture(profile):
    """
    Delete the old profile picture if it exists
    """
    if profile.profile_picture:
        try:
            # Get the full path of the old picture
            old_path = profile.profile_picture.path
            if os.path.exists(old_path):
                # Try to remove the file
                try:
                    os.remove(old_path)
                except PermissionError:
                    # If we can't delete the file, just log it and continue
                    print(f"Could not delete file {old_path} due to permission error")
                    return
                
                # Try to remove the parent directory if it's empty
                try:
                    parent_dir = os.path.dirname(old_path)
                    if os.path.exists(parent_dir) and not os.listdir(parent_dir):
                        os.rmdir(parent_dir)
                except (PermissionError, OSError):
                    # If we can't remove the directory, just log it and continue
                    print(f"Could not remove directory {parent_dir} due to permission error")
        except Exception as e:
            print(f"Error handling old profile picture: {e}")

def delete_message_file(message):
    """
    Delete a message's attached file if it exists
    """
    if message.file:
        try:
            # Get the full path of the file
            file_path = message.file.path
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except PermissionError:
                    print(f"Could not delete file {file_path} due to permission error")
                    return
                
                # Try to remove parent directory if empty
                try:
                    parent_dir = os.path.dirname(file_path)
                    if os.path.exists(parent_dir) and not os.listdir(parent_dir):
                        os.rmdir(parent_dir)
                except (PermissionError, OSError):
                    print(f"Could not remove directory {parent_dir} due to permission error")
        except Exception as e:
            print(f"Error handling message file deletion: {e}") 