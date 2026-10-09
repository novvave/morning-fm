"""Cost-safe publisher. Checkpoints are pushed before each billable request."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import monocle_briefing as briefing

ROOT = Path(__file__).resolve().parent
STATE = ROOT / 'publication_state.json'


def canonical_url(url):
    parts = urlsplit(url)
    if parts.hostname not in ('monocle.com', 'www.monocle.com'):
        raise ValueError('Unexpected source host')
    return urlunsplit(('https', 'monocle.com', parts.path.rstrip('/') + '/', '', ''))


def source_id(article, source):
    identity = canonical_url(article['url'])
    if source == 'gmail':
        # Newsletters historically use the homepage URL; title/date identify each issue.
        identity += '\n' + article['title'] + '\n' + article['date']
    return hashlib.sha256(identity.encode()).hexdigest()


def load_state():
    if STATE.exists():
        state = json.loads(STATE.read_text())
        if state.get('version') != 1 or not isinstance(state.get('articles'), dict):
            raise ValueError('Invalid publication state; refusing paid calls')
        return state
    return {'version': 1, 'articles': {}}


def legacy_published(article, source):
    for txt in Path(briefing.OUTPUT_DIR).glob('*.txt'):
        if not txt.with_suffix('.mp3').exists():
            continue
        content = txt.read_text()
        match = re.search(r'■ 원문\n\s+(\S+)', content)
        if match and canonical_url(match[1]) == canonical_url(article['url']):
            if source == 'web' or (article['title'] in content and article['date'] in content):
                return True
    return False


def checkpoint(state, push):
    tmp = STATE.with_suffix('.tmp')
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n')
    tmp.replace(STATE)
    if push:
        def git(*args):
            return subprocess.run(['git', *args], cwd=ROOT, check=True, capture_output=True)
        # Never stage credentials or unrelated operator edits.
        git('add', 'publication_state.json', 'briefings', 'feed.xml')
        if subprocess.run(['git', 'diff', '--cached', '--quiet'], cwd=ROOT).returncode:
            git('commit', '-m', 'briefing: checkpoint publication')
        git('push', 'origin', 'HEAD')  # Abort before any paid call if persistence fails.


def publish(article, source='web', push=False, dry_run=False):
    state = load_state()
    key = source_id(article, source)
    entry = state['articles'].get(key)
    if (not entry and legacy_published(article, source)) or (entry and entry['status'] == 'published'):
        print('No new article: already published.')
        return False
    if entry and entry['status'] in ('summary_pending', 'tts_pending'):
        raise RuntimeError('Uncertain API outcome: inspect publication_state.json before retrying')
    if dry_run:
        print('New article available; dry run made no paid calls or file changes.')
        return False
    if not all(os.environ.get(k) for k in ('ANTHROPIC_API_KEY', 'ELEVENLABS_API_KEY')):
        raise RuntimeError('Both API secrets are required before generating an episode')
    if not article.get('title') or len(article.get('body', '').strip()) < 200:
        raise ValueError('Missing or insufficient article content; refusing paid calls')
    if len(article['body']) > 20000:
        raise ValueError('Article exceeds 20,000 character input limit')
    # Resume unfinished work only; never overwrite another article on the same day.
    if entry and entry['status'] not in ('reserved', 'summary_ready', 'audio_ready'):
        raise ValueError('Unknown publication status')
    if not entry:
        date = datetime.now(ZoneInfo('Asia/Seoul')).strftime('%Y-%m-%d')
        if any(e['filename'].startswith(f'monocle_briefing_{date}_') for e in state['articles'].values()):
            print('Daily episode limit reached; defer new article until tomorrow.')
            return False
        entry = {'status': 'reserved', 'article': article, 'source': source,
                 'filename': f'monocle_briefing_{date}_{key[:16]}'}
        state['articles'][key] = entry
    article = dict(entry['article'], filename=entry['filename'])
    Path(briefing.OUTPUT_DIR).mkdir(exist_ok=True)
    if entry['status'] == 'reserved':
        entry['status'] = 'summary_pending'
        checkpoint(state, push)
        summary = briefing.summarize_with_claude(article)
        if not summary.strip() or len(summary) > 4000:
            raise ValueError('Invalid or oversized summary')
        entry.update(status='summary_ready', summary=summary)
        checkpoint(state, push)
    if entry['status'] == 'summary_ready':
        briefing.save_briefing(article, entry['summary'])
        entry['status'] = 'tts_pending'
        checkpoint(state, push)
        audio = briefing.generate_tts(article, entry['summary'])
        if not audio:
            raise RuntimeError('Audio generation did not complete')
        entry['status'] = 'audio_ready'
        checkpoint(state, push)
    if entry['status'] == 'audio_ready':
        briefing.generate_feed()
        entry['status'] = 'published'
        checkpoint(state, push)
    print('Episode published.')
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', choices=['web', 'gmail'], default='web')
    parser.add_argument('--push', action='store_true', help='Persist each checkpoint to GitHub')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    # Pending episodes take priority over newer content, including after a source changes.
    state = load_state()
    unfinished = [e for e in state['articles'].values() if e['status'] != 'published']
    if unfinished:
        if len(unfinished) != 1:
            raise RuntimeError('Multiple unfinished episodes require operator review')
        article = unfinished[0]['article']
        source = unfinished[0].get('source', 'web')
    elif args.source == 'gmail':
        from gmail_reader import fetch_monocle_newsletter
        article = fetch_monocle_newsletter()
        source = 'gmail'
        if not article:
            raise RuntimeError('Newsletter not found')
    else:
        _, url = briefing.fetch_latest_article_url()
        article = briefing.scrape_article(canonical_url(url))
        source = 'web'
    publish(article, source, args.push, args.dry_run)


if __name__ == '__main__':
    main()
