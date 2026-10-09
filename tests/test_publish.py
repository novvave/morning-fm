import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import publish_briefing as p
import generate_feed as feed


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.audio = self.root / 'briefings'
        self.audio.mkdir()
        self.patches = [patch.object(p, 'STATE', self.root / 'state.json'),
                        patch.object(p.briefing, 'OUTPUT_DIR', str(self.audio)),
                        patch.object(feed, 'BRIEFINGS_DIR', str(self.audio)),
                        patch.object(feed, 'FEED_PATH', str(self.root / 'feed.xml')),
                        patch.dict('os.environ', ANTHROPIC_API_KEY='test', ELEVENLABS_API_KEY='test')]
        for item in self.patches:
            item.start()
        self.article = {'title': 'A column', 'date': '2026-10-09',
                        'url': 'https://monocle.com/the-weekend-opener/example/', 'body': 'Text ' * 100}

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.tmp.cleanup()

    def tts(self, article, summary):
        path = self.audio / (article['filename'] + '.mp3')
        path.write_bytes(b'ID3test')
        return str(path)

    def test_publish_then_repeat_no_api_or_feed_change(self):
        with patch.object(p.briefing, 'summarize_with_claude', return_value='• summary') as summary, patch.object(p.briefing, 'generate_tts', side_effect=self.tts) as tts:
            self.assertTrue(p.publish(self.article))
            before = (self.root / 'feed.xml').read_bytes()
            self.assertFalse(p.publish(dict(self.article, url=self.article['url']+'?utm_source=x')))
            summary.assert_called_once()
            tts.assert_called_once()
            self.assertEqual(before, (self.root / 'feed.xml').read_bytes())
            self.assertEqual(len(ET.fromstring(before).findall('./channel/item')), 1)

    def test_ambiguous_tts_failure_blocks_retry(self):
        with patch.object(p.briefing, 'summarize_with_claude', return_value='• summary') as summary, patch.object(p.briefing, 'generate_tts', side_effect=TimeoutError) as tts:
            with self.assertRaises(TimeoutError): p.publish(self.article)
            with self.assertRaises(RuntimeError): p.publish(self.article)
            summary.assert_called_once()
            tts.assert_called_once()
            self.assertFalse((self.root / 'feed.xml').exists())

    def test_checkpoint_failure_prevents_paid_call(self):
        with patch.object(p, 'checkpoint', side_effect=RuntimeError), patch.object(p.briefing, 'summarize_with_claude') as summary:
            with self.assertRaises(RuntimeError): p.publish(self.article, push=True)
            summary.assert_not_called()

    def test_dry_run_and_missing_secret_no_cost(self):
        with patch.object(p.briefing, 'summarize_with_claude') as summary:
            self.assertFalse(p.publish(self.article, dry_run=True))
            with patch.dict('os.environ', {}, clear=True):
                with self.assertRaises(RuntimeError): p.publish(self.article)
            summary.assert_not_called()
            self.assertFalse(p.STATE.exists())

    def test_audio_ready_recovers_without_paid_calls(self):
        key = p.source_id(self.article, 'web')
        name = 'monocle_briefing_2026-10-09_'+key[:16]
        self.tts(dict(self.article, filename=name), '')
        p.STATE.write_text(json.dumps({'version': 1, 'articles': {key: {'status': 'audio_ready', 'article': self.article, 'filename': name}}}))
        with patch.object(p.briefing, 'summarize_with_claude') as summary, patch.object(p.briefing, 'generate_tts') as tts:
            self.assertTrue(p.publish(self.article))
            summary.assert_not_called(); tts.assert_not_called()

    def test_legacy_episode_skipped_and_guid_preserved(self):
        name = 'monocle_briefing_2026-04-13'
        (self.audio / (name+'.txt')).write_text('■ 원문\n  '+self.article['url'])
        (self.audio / (name+'.mp3')).write_bytes(b'ID3test')
        with patch.object(p.briefing, 'summarize_with_claude') as summary:
            self.assertFalse(p.publish(self.article))
            summary.assert_not_called()
        feed.generate_feed()
        self.assertEqual(ET.parse(feed.FEED_PATH).findtext('./channel/item/guid'), 'morning-fm-2026-04-13')

    def test_same_day_new_article_deferred(self):
        with patch.object(p.briefing, 'summarize_with_claude', return_value='summary') as summary, patch.object(p.briefing, 'generate_tts', side_effect=self.tts):
            p.publish(self.article)
            self.assertFalse(p.publish(dict(self.article, url='https://monocle.com/the-weekend-opener/other/')))
            summary.assert_called_once()

    def test_index_skips_navigation(self):
        with patch.object(p.briefing.requests, 'get') as get:
            get.return_value.text = '<a href="/the-weekend-opener/">Index</a><a href="/the-weekend-opener/new/">New</a>'
            self.assertEqual(p.briefing.fetch_latest_article_url()[1], 'https://monocle.com/the-weekend-opener/new/')

    def test_short_content_rejected(self):
        with patch.object(p.briefing, 'summarize_with_claude') as summary:
            with self.assertRaises(ValueError): p.publish(dict(self.article, body=''))
            summary.assert_not_called()

    def test_summary_failure_blocks_retry(self):
        with patch.object(p.briefing, 'summarize_with_claude', side_effect=TimeoutError) as summary:
            with self.assertRaises(TimeoutError): p.publish(self.article)
            with self.assertRaises(RuntimeError): p.publish(self.article)
            summary.assert_called_once()

    def test_summary_ready_reuses_summary(self):
        key = p.source_id(self.article, 'web')
        name = 'monocle_briefing_2026-10-09_'+key[:16]
        p.STATE.write_text(json.dumps({'version': 1, 'articles': {key: {'status': 'summary_ready', 'article': self.article, 'filename': name, 'summary': 'saved'}}}))
        with patch.object(p.briefing, 'summarize_with_claude') as summary, patch.object(p.briefing, 'generate_tts', side_effect=self.tts) as tts:
            p.publish(self.article)
            summary.assert_not_called(); tts.assert_called_once()
