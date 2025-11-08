from pathlib import Path
import mimetypes


FORMATS = ['.png', '.jpg', '.jpeg', '.tiff', '.bmp', '.webp', '.jfif','.docx','.csv','.pdf' ]
MAX_SIZE_BYTES = 10 * 1024 * 1024


async def get_file_format(self, file_path: str) -> dict:  
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        return {"error": "File does not exist"}
    
    file_size = path.stat().st_size
    if file_size > MAX_SIZE_BYTES:
        return {"error": "File is too large (max 10 MB)"}
    
    mime_type, _ = mimetypes.guess_type(file_path)
    file_extension = str(path.suffix.lower())
    
    if file_extension not in FORMATS:
        return {"error": f"Unsupported file extension: {file_extension}"}
    
    return {"extension": file_extension, "mime_type": mime_type}


