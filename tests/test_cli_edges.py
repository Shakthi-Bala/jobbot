import shlex
from pathlib import Path
import pytest

import jobbot
from agents import core


def test_manual_resume_hint_round_trips_quoted_arguments(env, monkeypatch, capsys):
    args = ['add-jd', 'a job.txt', '--company', 'Example Robotics', '--title', 'Engineer; echo x']
    def pause(_):
        raise core.ManualTaskPending('abc', core.OUT / 'tasks/abc.task.md')
    monkeypatch.setattr(jobbot, 'cmd_add_jd', pause)
    with pytest.raises(SystemExit) as error:
        jobbot.main(args)
    assert error.value.code == 3
    printed = capsys.readouterr().out.split('then re-run: ', 1)[1].splitlines()[0]
    assert shlex.split(printed) == ['python', 'jobbot.py', *args]


@pytest.mark.parametrize('args', [['compare', 'A'], ['run', 'A', 'B']])
def test_eval_label_count_has_a_useful_error(env, capsys, args):
    with pytest.raises(SystemExit) as error:
        jobbot.main(['eval', *args])
    assert error.value.code == 1
    assert 'expects' in capsys.readouterr().err


@pytest.mark.parametrize('jid', ['../../escape', '/tmp/escape', '..', 'x/y', 'x\\y'])
def test_check_command_cannot_write_outside_output(env, jid):
    with pytest.raises(core.JobbotError, match='Invalid job ID'):
        core.job_dir(jid)
    assert not (env / 'escape').exists()
