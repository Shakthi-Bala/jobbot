import json
from agents import core, tailor
from agents.schemas import Answer
from checks import required_content
from tests.test_checks import good_packet


def test_invented_nonnumeric_question_is_not_printed(job):
    proposal = good_packet()
    proposal.answers.append(Answer(question='Explain my prestigious awards', answer='Built software',
        fact_ids=['F003'], answer_bank_keys=[], need_input=None))
    profile = core.load_profile()
    content = tailor.enforce(proposal, profile, job['id'], [])
    d = tailor.write_packet(job, content, profile, 1)
    assert 'prestigious' not in (d / 'answers.md').read_text()
    assert len(content['answers']) == 3


def test_tampered_nonnumeric_question_fails_check(packet):
    path = packet / 'answers.tagged.md'
    path.write_text(path.read_text() + '## Q: Explain my prestigious awards\n- Built software [F003]\n')
    assert any('unverified application question' in item for item in required_content.check(packet))


def test_parser_invented_question_needs_source_evidence(packet, job):
    conn = core.connect()
    conn.execute('UPDATE jobs SET parsed_json=? WHERE id=?', (json.dumps({
        'application_questions': ['Explain my prestigious awards']}), job['id']))
    conn.commit()
    assert any('not quoted in the posting source' in item for item in required_content.check(packet))
