import asyncio
import os
import shutil
import logging
from functions.file_processing import FileConvertToText
from pathlib import Path

# Setup simple logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Verification")

async def test_processing():
    converter = FileConvertToText()
    
    # Create dummy files for verification
    api_dir = "tmp/verification"
    os.makedirs(api_dir, exist_ok=True)
    
    # 1. Test Text File
    text_file = os.path.join(api_dir, "test.txt")
    with open(text_file, "w") as f:
        f.write("This is a simple text file verification.")
    
    logger.info(f"Testing TXT: {text_file}")
    res_txt = await converter.convert_to_text(text_file)
    logger.info(f"TXT Result: {res_txt['status']} - {res_txt.get('text', '')[:50]}")

    # 2. Test Word File (if possible to create dummy, or skip)
    # Since we can't easily create a valid docx without dependencies, we assume user has test files.
    # But we can try to find existing files in the project.
    
    files_dir = "files" 
    if os.path.exists(files_dir):
        files = [os.path.join(files_dir, f) for f in os.listdir(files_dir) if os.path.isfile(os.path.join(files_dir, f))]
        
        for f in files:
            ext = Path(f).suffix.lower()
            if ext in ['.pdf', '.docx', '.png', '.jpg']:
                logger.info(f"Testing Real File: {f}")
                res = await converter.convert_to_text(f)
                logger.info(f"Result for {f}: {res['status']} | Source: {res.get('metadata', {}).get('source', 'N/A')}")
                if res['status'] == 'error':
                    logger.error(f"Error details: {res.get('text')}")

    # Check for poppler/tesseract availability
    tess_cmd = shutil.which("tesseract")
    pdf_cmd = shutil.which("pdftoppm")
    logger.info(f"Tesseract Path: {tess_cmd}")
    logger.info(f"Poppler Path: {pdf_cmd}")
    
    if not tess_cmd or not pdf_cmd:
         logger.warning("WARNING: External dependencies for OCR/PDF-Images missing!")

if __name__ == "__main__":
    try:
        asyncio.run(test_processing())
    except KeyboardInterrupt:
        pass
