from pathlib import Path

def print_tree(directory, ignore_names=None, ignore_extensions=None, prefix=""):
    """
    Структураи директорияро ба шакли дарахт (tree) чоп мекунад.
    """
    if ignore_names is None:
        # Номи аниқи папкаҳо ва файлҳое, ки набояд нишон дода шаванд
        ignore_names = {'.venv', '__pycache__', '.git', '.idea', 'temp', 'test.py', '.log', 'logs'}
        
    if ignore_extensions is None:
        # Формати файлҳое, ки набояд нишон дода шаванд (масалан ҳамаи файлҳои .md)
        ignore_extensions = {'.md'}

    path = Path(directory)
    
    try:
        # Филтр кардан ҳам аз рӯи ном ва ҳам аз рӯи формат (suffix)
        entries = sorted([
            e for e in path.iterdir() 
            if e.name not in ignore_names and e.suffix not in ignore_extensions
        ])
    except PermissionError:
        return

    for i, entry in enumerate(entries):
        is_last = i == (len(entries) - 1)
        connector = "└── " if is_last else "├── "
        
        print(f"{prefix}{connector}{entry.name}")
        
        if entry.is_dir():
            extension = "    " if is_last else "│   "
            print_tree(entry, ignore_names, ignore_extensions, prefix + extension)

if __name__ == "__main__":
    current_dir = "."
    print(f"Сохтори лоиҳа: {Path(current_dir).resolve().name}")
    print_tree(current_dir)