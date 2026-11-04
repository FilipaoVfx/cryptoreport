"""Explicit X credentials only. Never inspect browsers or log cookie values."""
import getpass
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile


def validate(doc):
    if not isinstance(doc,dict) or set(doc)!={'auth_token','ct0'}:
        raise ValueError('Se requieren auth_token y ct0')
    if any(not isinstance(v,str) or not re.fullmatch(r'[A-Za-z0-9._~%-]{8,4096}',v) for v in doc.values()):
        raise ValueError('Formato de sesión inválido')
    return doc


def read_session(path):
    path=Path(path)
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd) as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_size>16384:
            raise ValueError('Sesión debe ser un archivo privado (600) de menos de 16 KB')
        return validate(json.load(stream))


def configure(path, text=None):
    # Hidden terminal input, never a command argument or a chat message.
    if text is None and not sys.stdin.isatty():raise ValueError('Usa una terminal interactiva para evitar mostrar la sesión')
    raw=text if text is not None else getpass.getpass('Pega el Header String de Cookie-Editor para x.com (oculto): ')
    if not isinstance(raw,str) or len(raw)>65536:raise ValueError('Exportación demasiado grande')
    cookies={}
    if raw.lstrip().startswith('['):
        rows=json.loads(raw)
        for row in rows:
            if not isinstance(row,dict):raise ValueError('Cookie inválida')
            if str(row.get('domain','')).lstrip('.') in ('x.com','twitter.com') and row.get('name') in ('auth_token','ct0'):
                if row['name'] in cookies:raise ValueError('Cookie duplicada; exporta solo una sesión de x.com')
                cookies[row['name']]=row.get('value')
    else:
        for pair in raw.split(';'):
            name,sep,value=pair.strip().partition('=')
            if sep and name in ('auth_token','ct0'):
                if name in cookies:raise ValueError('Cookie duplicada')
                cookies[name]=value
    validate(cookies)
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if path.is_symlink():raise ValueError('Sesión no puede ser un enlace')
    fd,temp=tempfile.mkstemp(prefix='.x-session-',dir=path.parent)
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,'w') as stream:
            json.dump(cookies,stream);stream.flush();os.fsync(stream.fileno())
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)
    return {'status':'configured','live_verified':False,'path':str(path)}
