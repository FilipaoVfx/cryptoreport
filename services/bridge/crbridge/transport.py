"""Select one transport. Never fail over a write to a second provider."""
import hashlib
import json
import os
from pathlib import Path
from .drive import DriveError, RcloneDrive


def paths(data):
    return {
        'state_path':Path(os.environ.get('CR_DRIVE_STATE_FILE',str(Path(data)/'bridge/transport.sqlite'))),
        'client_file':Path(os.environ.get('CR_DRIVE_CLIENT_FILE','/etc/cryptoreport-drive/client.json')),
        'token_file':Path(os.environ.get('CR_DRIVE_TOKEN_FILE','/etc/cryptoreport-drive/token.json')),
    }


def api_drive(data, folders, **options):
    from .google_drive import GoogleDrive
    return GoogleDrive(folders=folders.values(),**paths(data),**options)


def make_drive(data, folders):
    backend=os.environ.get('CR_DRIVE_TRANSPORT','auto')
    if backend=='auto':
        marker=Path(data)/'bridge/drive-transport.json'
        backend='rclone'
        if marker.exists():
            try:
                selected=json.loads(marker.read_bytes())
                if selected['version']!=1 or selected['backend']!='google-api':raise ValueError()
                client=paths(data)['client_file']
                if selected['client_sha256']!=hashlib.sha256(client.read_bytes()).hexdigest():raise ValueError()
                backend='google-api'
            except (OSError,ValueError,KeyError,TypeError):
                raise DriveError('Selección de Drive requiere nueva verificación OAuth',category='drive_config') from None
    if backend=='google-api':return api_drive(data,folders)
    if backend=='rclone':return RcloneDrive(os.environ.get('CR_DRIVE_REMOTE','gdrive'),os.environ.get('RCLONE_CONFIG'))
    raise DriveError('CR_DRIVE_TRANSPORT debe ser auto, google-api o rclone',category='drive_config')
