"""Unpack stem packs (ZIP, RAR or a plain folder) into a destination folder.

Packs come from the internet, so every entry is checked: no absolute paths, no "..",
no links, only audio files. The folder structure inside the pack is flattened, since
packs usually wrap the stems in one folder named after the song.
"""
import shutil
import zipfile
from pathlib import Path, PurePosixPath

AUDIO_EXT = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".aif", ".aiff", ".ogg"}
MAX_ENTRY_BYTES = 2 * 1024 ** 3     # a single stem bigger than 2 GB is not a stem


class PackError(Exception):
    pass


def _safe_name(entry_name):
    """Base name of a pack entry if it is an audio file we accept, else None."""
    p = PurePosixPath(entry_name.replace("\\", "/"))
    if p.is_absolute() or ".." in p.parts:
        raise PackError(f"Ruta no permitida dentro del paquete: {entry_name}")
    if any(part.startswith("__MACOSX") or part.startswith("._") for part in p.parts):
        return None
    return p.name if p.suffix.lower() in AUDIO_EXT else None


def _unique(dest, name):
    target = dest / name
    i = 2
    while target.exists():
        target = dest / f"{Path(name).stem} ({i}){Path(name).suffix}"
        i += 1
    return target


def _write(dest, name, size, read):
    if size > MAX_ENTRY_BYTES:
        raise PackError(f"Archivo demasiado grande dentro del paquete: {name}")
    target = _unique(dest, name)
    target.write_bytes(read())
    return target


def extract_pack(source, dest):
    """Copy the audio files of `source` into `dest`. Returns the list of written paths."""
    source, dest = Path(source), Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    written = []
    if source.is_dir():
        for f in sorted(source.rglob("*")):
            if f.is_file() and not f.is_symlink() and (name := _safe_name(str(f.relative_to(source)))):
                target = _unique(dest, name)
                shutil.copy2(f, target)
                written.append(target)
    elif source.suffix.lower() == ".zip":
        with zipfile.ZipFile(source) as z:
            for info in z.infolist():
                if info.is_dir() or (info.external_attr >> 16) & 0o170000 == 0o120000:   # dir or symlink
                    continue
                if name := _safe_name(info.filename):
                    written.append(_write(dest, name, info.file_size, lambda i=info: z.read(i)))
    elif source.suffix.lower() == ".rar":
        try:
            from unrar.cffi import rarfile
        except ImportError as e:
            raise PackError("Falta soporte para RAR (unrar-cffi).") from e
        r = rarfile.RarFile(str(source))
        for info in r.infolist():
            if info.file_size == 0 or info.filename.endswith("/"):
                continue
            if name := _safe_name(info.filename):
                written.append(_write(dest, name, info.file_size, lambda i=info: r.read(i)))
    else:
        raise PackError(f"Formato de paquete no soportado: {source.suffix or source.name}")
    if not written:
        raise PackError("El paquete no tiene archivos de audio.")
    return sorted(written)
