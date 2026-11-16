import json
import pytest
from agents import core, discover, evals, tailor
from agents.schemas import BlindVerdict
from checks import run_all


def case_files(tmp_path, monkeypatch):
    folder = tmp_path / 'cases/example'
    folder.mkdir(parents=True)
    (folder / 'posting.txt').write_text('Engineer, Python required')
    (folder / 'meta.yaml').write_text('company: Example Co\ntitle: Engineer\n')
    monkeypatch.setattr(evals, 'EVALS', folder.parent)


def test_evaluation_compares_rendered_packet_directories_and_isolates_logs(env, monkeypatch):
    case_files(env, monkeypatch)
    monkeypatch.setattr(discover, 'parse_posting', lambda *a: (_ for _ in ()).throw(core.JobbotError('deferred')))
    def build(conn, jid):
        d = core.job_dir(jid, conn)
        (d / 'resume.json').write_text(json.dumps({'summary': core.OUT.name + ' actual resume'}))
        return d
    monkeypatch.setattr(tailor, 'build', build)
    monkeypatch.setattr(run_all, 'run', lambda *a, **k: {})
    paths = core.DB_PATH, core.OUT, core.DECISIONS_PATH
    evals.run('A')
    evals.run('B')
    assert not paths[2].exists()
    assert (core.OUT / 'evals/A/decisions.tsv').exists()
    inputs = []
    def judge(role, system, user, schema, **kw):
        inputs.append(user)
        core.log_decision('llm', None, 'usage', 'test')
        return BlindVerdict(winner='tie', reason='Both contain the real material')
    monkeypatch.setattr(core, 'llm_json', judge)
    assert 'ties 1' in evals.compare('A', 'B')
    assert 'A actual resume' in inputs[0] and 'B actual resume' in inputs[0]
    assert not paths[2].exists()
    assert (core.DB_PATH, core.OUT, core.DECISIONS_PATH) == paths
    assert (core.OUT / 'evals/compare_A_vs_B/decisions.tsv').exists()


def test_missing_eval_artifact_is_not_judged(env):
    with pytest.raises(core.JobbotError, match='missing a resume'):
        evals._packet_text(env / 'missing')
    with pytest.raises(core.JobbotError, match='summary missing'):
        evals.compare('A', 'B')


def test_eval_restores_paths_after_failure(env, monkeypatch):
    case_files(env, monkeypatch)
    paths = core.DB_PATH, core.OUT, core.DECISIONS_PATH
    monkeypatch.setattr(discover, 'add_manual', lambda *a: (_ for _ in ()).throw(core.JobbotError('failure')))
    with pytest.raises(core.JobbotError):
        evals.run('broken')
    assert (core.DB_PATH, core.OUT, core.DECISIONS_PATH) == paths


def test_eval_paths_are_confined_to_run(env):
    with pytest.raises(core.JobbotError):
        evals.run('../../outside')
    with pytest.raises(core.JobbotError):
        evals.packet_path(env, {'packet_dir': '../outside'})
