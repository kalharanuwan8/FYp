import os
import uuid
from werkzeug.utils import secure_filename

ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'ppt', 'pptx', 'txt', 'mp4', 'webm', 'png', 'jpg', 'jpeg'}

def allowed_file(filename: str, allowed=None) -> bool:
    exts = ALLOWED_EXTENSIONS if allowed is None else allowed
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in exts

def save_uploaded_file(file_obj, upload_folder: str, allowed=None) -> str:
    """
    Saves an uploaded Werkzeug FileStorage object to upload_folder with a secure,
    unique filename to prevent overwrites, and returns the relative file_url path.
    """
    if not file_obj or not file_obj.filename:
        raise ValueError("No file selected for upload")
    exts = ALLOWED_EXTENSIONS if allowed is None else allowed
    if not allowed_file(file_obj.filename, exts):
        raise ValueError(
            "File type not allowed. Use: "
            + ", ".join(sorted(exts))
        )

    if not os.path.exists(upload_folder):
        os.makedirs(upload_folder, exist_ok=True)

    original_filename = secure_filename(file_obj.filename)
    unique_name = f"{uuid.uuid4().hex}_{original_filename}"
    filepath = os.path.join(upload_folder, unique_name)
    file_obj.save(filepath)

    return f"/uploads/{unique_name}"

class StorageService:
    @staticmethod
    def is_allowed_file(filename: str) -> bool:
        return allowed_file(filename)

    @staticmethod
    def save_file(file_obj, upload_folder: str) -> str:
        return save_uploaded_file(file_obj, upload_folder)
