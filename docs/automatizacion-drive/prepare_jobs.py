"""Prepara trabajos completos de las últimas 48 h, sin llamar a modelos ni a Drive.

python3 docs/automatizacion-drive/prepare_jobs.py --output /tmp/cryptoreport-drive-48h
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'services/analysis'))
from cranalysis.request import build_payload, load_prompt, load_schema, sha256
from cranalysis.config import PROMPT_VERSION
from cranalysis.validate import validate

def prepare(transcripts, analyses, output, hours=48):
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)
    prompt, schema = load_prompt(), load_schema()
    prompt_hash, schema_hash = sha256(prompt), sha256(json.dumps(schema, sort_keys=True))
    output.mkdir(parents=True, exist_ok=True)
    jobs, reused = [], []
    for path in sorted(transcripts.glob('*/*.json')):
        raw = path.read_bytes()
        doc = json.loads(raw)
        if datetime.fromisoformat(doc['video']['published_at']) < cutoff:
            continue
        existing = analyses / path.parent.name / path.name
        if existing.exists():
            saved = json.loads(existing.read_text())
            meta = saved.get('meta') or {}
            if (meta.get('status') == 'ok' and meta.get('prompt_sha256') == prompt_hash
                    and meta.get('schema_sha256') == schema_hash
                    and not validate(saved['analysis'], build_payload(doc, meta['analyzed_at']), schema)):
                reused.append(doc['video']['video_id'])
                continue
        meta = {'video_id':doc['video']['video_id'], 'channel':doc['video']['channel']['slug'],
                'transcript_sha256':hashlib.sha256(raw).hexdigest(), 'prompt_version':PROMPT_VERSION,
                'prompt_sha256':prompt_hash, 'schema_sha256':schema_hash}
        identity = sha256(json.dumps(meta, sort_keys=True))
        job_id = meta['video_id'] + '__' + identity
        job = {'job_id':job_id, 'meta':meta, 'payload':build_payload(doc, None)}
        dest = output / (job_id+'.json')
        dest.write_text(json.dumps(job, ensure_ascii=False, indent=2)+'\n')
        jobs.append({'job_id':job_id, 'video_id':meta['video_id'], 'channel':meta['channel'],
                     'file':str(dest), 'published_at':doc['video']['published_at']})
    report = {'prepared_at':now.isoformat(), 'cutoff':cutoff.isoformat(), 'hours':hours,
              'jobs':jobs, 'reused_valid_analysis_ids':reused}
    (output/'queue-manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    return report

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--hours', type=float, default=48)
    parser.add_argument('--transcripts', type=Path, default=Path('/var/lib/cryptoreport-transcripts/transcripts'))
    parser.add_argument('--analyses', type=Path, default=Path('/var/lib/cryptoreport-transcripts/analysis'))
    args = parser.parse_args()
    report = prepare(args.transcripts, args.analyses, args.output, args.hours)
    print(json.dumps({'jobs':len(report['jobs']), 'reused':report['reused_valid_analysis_ids'],
                      'cutoff':report['cutoff']}, ensure_ascii=False))
