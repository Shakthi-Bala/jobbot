from types import SimpleNamespace as NS
from contextlib import contextmanager
import csv
import json

import anthropic
import httpx
import pytest

from agents import core, discover
from agents.schemas import Rewrite


@pytest.fixture
def api(env, monkeypatch):
    monkeypatch.setenv('JOBBOT_MODE', 'api')
    monkeypatch.setattr(core, 'model_for', lambda _: {'model': 'test-model'})
    def install(response=None, error=None):
        @contextmanager
        def stream(**kwargs):
            if error:
                raise error
            yield NS(get_final_message=lambda: response)
        monkeypatch.setattr(core, 'client', lambda: NS(messages=NS(stream=stream)))
    return install


def response(text=None, stop='end_turn'):
    return NS(stop_reason=stop, content=[] if text is None else [NS(type='text', text=text)],
              usage=NS(input_tokens=100, output_tokens=12, cache_read_input_tokens=7))


@pytest.mark.parametrize('reply,reason', [
    (response('not json'), 'invalid Rewrite JSON'),
    (response('{"wrong": 2}'), 'invalid Rewrite JSON'),
    (response(), 'no text'),
    (response('', 'refusal'), 'declined'),
    (response('{', 'max_tokens'), 'truncated'),
])
def test_invalid_replies_become_recoverable_errors(api, reply, reason):
    api(reply)
    with pytest.raises(core.JobbotError, match=reason):
        core.llm_json('writing', 'system', 'prompt', Rewrite)


def test_provider_errors_do_not_echo_request_or_secret(api):
    api(error=anthropic.APIConnectionError(message='secret-request', request=httpx.Request('POST', 'https://api.example.com')))
    with pytest.raises(core.JobbotError, match='provider request failed') as error:
        core.llm_json('writing', 'system', 'prompt', Rewrite)
    assert 'secret-request' not in str(error.value)
    assert 'secret-request' not in core.DECISIONS_PATH.read_text()


def test_usage_is_recorded_even_for_invalid_json(api):
    api(response('invalid'))
    with pytest.raises(core.JobbotError):
        core.llm_json('writing', 'system', 'prompt', Rewrite)
    rows = list(csv.DictReader(core.DECISIONS_PATH.open(), delimiter='\t'))
    usage = json.loads(rows[0]['reason'])
    assert rows[0]['decision'] == 'usage'
    assert usage['input_tokens'] == 100 and usage['output_tokens'] == 12
    assert usage['cache_read_input_tokens'] == 7


def test_one_invalid_parse_does_not_stop_remaining_jobs(api):
    api(response('invalid'))
    jobs = [dict(company='Acme', title='Engineer', location='', req_id=str(i),
                 raw_text='Example posting', source='manual') for i in range(2)]
    assert len(discover.upsert_jobs(core.connect(), jobs, {})) == 2


def test_daily_run_continues_after_expected_stage_failure(env, monkeypatch):
    import run_daily
    monkeypatch.setattr(run_daily.discover, 'run', lambda **kw: (_ for _ in ()).throw(core.JobbotError('offline')))
    calls = []
    monkeypatch.setattr(run_daily.fit, 'run', lambda: calls.append('fit') or [])
    monkeypatch.setattr(run_daily.tracker, 'daily_log', lambda *a: 'done')
    run_daily.main(['--no-packets'])
    assert calls == ['fit']
