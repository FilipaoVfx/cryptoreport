"""No model credentials or inference configuration is needed by the feed."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
from .collector import handle

SERVICE = Path(__file__).resolve().parents[1]
REPO = SERVICE.parents[1]


def load_catalog(path):
    data = json.loads(Path(path).read_text())
    if data.get('version') != 1 or not isinstance(data.get('accounts'), list) or not data['accounts']:
        raise ValueError('Configuración de cuentas inválida')
    if len(data['accounts'])>16:raise ValueError('Máximo 16 cuentas de X')
    accounts, seen, identities = [], set(), set()
    for item in data['accounts']:
        name, days = handle(item['handle']), item['lookback_days']
        if type(days) is not int or not 1 <= days <= 30 or name in seen:
            raise ValueError('Ventana inválida o cuenta duplicada')
        author_id = item.get('author_id')
        if not isinstance(author_id, str) or not author_id.isdigit() or author_id in identities:
            raise ValueError('Falta ID de autor fijado')
        enabled=item.get('enabled',True)
        if type(enabled) is not bool:raise ValueError('Estado de cuenta inválido')
        for field,limit in (('name',80),('label',40)):
            value=item.get(field,name if field=='name' else 'Cripto')
            if not isinstance(value,str) or not value.strip() or len(value)>limit or any(ord(c)<32 for c in value):raise ValueError('Nombre o categoría inválidos')
        accounts.append(dict(item, handle=name,enabled=enabled))
        seen.add(name)
        identities.add(author_id)
    return accounts


def load_accounts(path):
    return [a for a in load_catalog(path) if a['enabled']]


@dataclass
class Config:
    data: Path
    public: Path
    accounts: list
    env_file: str
    max_calls: int = 24
    daily_calls: int = 320
    monthly_calls: int = 10000
    interval_hours: int = 3
    max_posts_per_account: int = 1000
    providers: tuple = ('scraper', 'agent-reach')
    x_python: str = '/opt/cryptoreport-social-tools/bin/python'
    x_session: Path = Path('/etc/cryptoreport-social/x-session.json')
    twitterapi_key_file: Path | None = None
    twitterapi_daily_credits: int = 12000
    twitterapi_backfill_daily_credits: int = 6000
    twitterapi_monthly_credits: int = 60000
    backfill: bool = False
    accounts_file: Path | None = None


def load_config():
    return Config(
        data=Path(os.environ.get('CR_SOCIAL_DATA_DIR', '/var/lib/cryptoreport-transcripts/social')),
        public=Path(os.environ.get('CR_MOBILE_DATA_DIR', str(REPO / 'prototypes/movil/data'))),
        accounts=load_accounts(os.environ.get('CR_SOCIAL_ACCOUNTS', str(SERVICE / 'accounts.json'))),
        env_file=os.environ.get('CR_SOCIAL_ENV_FILE', str(REPO / 'services/transcripts/.env')),
        max_calls=int(os.environ.get('CR_SOCIAL_MAX_CALLS', '24')),
        daily_calls=int(os.environ.get('CR_SOCIAL_DAILY_CALLS', '320')),
        monthly_calls=int(os.environ.get('CR_SOCIAL_MONTHLY_CALLS', '10000')),
        interval_hours=int(os.environ.get('CR_SOCIAL_INTERVAL_HOURS', '3')),
        providers=tuple(os.environ.get('CR_SOCIAL_PROVIDERS','twitterapi-io,scraper,agent-reach').split(',')),
        x_python=os.environ.get('CR_SOCIAL_X_PYTHON','/opt/cryptoreport-social-tools/bin/python'),
        x_session=Path(os.environ.get('CR_SOCIAL_X_SESSION','/etc/cryptoreport-social/x-session.json')),
        twitterapi_key_file=Path(os.environ.get('CR_SOCIAL_TWITTERAPI_KEY_FILE','/etc/cryptoreport-social/twitterapi-io.json')),
        twitterapi_daily_credits=int(os.environ.get('CR_SOCIAL_TWITTERAPI_DAILY_CREDITS','12000')),
        twitterapi_backfill_daily_credits=int(os.environ.get('CR_SOCIAL_TWITTERAPI_BACKFILL_DAILY_CREDITS','6000')),
        twitterapi_monthly_credits=int(os.environ.get('CR_SOCIAL_TWITTERAPI_MONTHLY_CREDITS','60000')),
        accounts_file=Path(os.environ.get('CR_SOCIAL_ACCOUNTS',str(SERVICE/'accounts.json'))),
    )
