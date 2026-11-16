from agents import core, tailor, packet, panel, review
from agents.schemas import ParagraphRewrite, ParagraphRewrites
from tests.test_checks import good_packet


def test_unslop_matches_identity_not_position_and_preserves_missing(job, monkeypatch):
    before = [{'text': f'Original {i}', 'fact_ids': ['F003']} for i in range(3)]
    monkeypatch.setattr(core, 'llm_json', lambda *a, **k: ParagraphRewrites(paragraphs=[
        ParagraphRewrite(source_index=2, text='Third rewrite', fact_ids=['F003']),
        ParagraphRewrite(source_index=0, text='First rewrite', fact_ids=['F003'])]))
    assert [p['text'] for p in tailor.unslop(before, core.load_profile())] == [
        'First rewrite', 'Original 1', 'Third rewrite']


def test_unslop_duplicate_identity_falls_back(job, monkeypatch):
    before = [{'text': 'Original', 'fact_ids': ['F003']}]
    monkeypatch.setattr(core, 'llm_json', lambda *a, **k: ParagraphRewrites(paragraphs=[
        ParagraphRewrite(source_index=0, text=t, fact_ids=['F003']) for t in ['A', 'B']]))
    assert tailor.unslop(before, core.load_profile()) == before


def test_repeated_resume_entries_are_not_rendered_twice(job):
    proposal = good_packet()
    proposal.experience *= 2
    proposal.projects *= 2
    content = tailor.enforce(proposal, core.load_profile(), job['id'], [])
    assert len(content['experience']) == 1
    assert len(content['projects']) == 2


def test_rejected_panel_without_actions_stops_after_one_round(job, monkeypatch):
    conn = core.connect()
    conn.execute("INSERT INTO fit(job_id,score,decision) VALUES (?,90,'shortlist')", (job['id'],))
    conn.commit()
    monkeypatch.setattr(tailor, 'draft', lambda *a: good_packet())
    monkeypatch.setattr(tailor, 'unslop', lambda ps, p: ps)
    from agents.schemas import LeadJudgment
    monkeypatch.setattr(review, 'review', lambda *a: LeadJudgment(overall='pass', findings=[]))
    calls = []
    def verdict(*args):
        calls.append(1)
        return {'done': False, 'revisions': [], 'plan': {'needs_new_evidence': []}}
    monkeypatch.setattr(panel, 'run', verdict)
    result = packet.build(job['id'], offline=True)
    assert result['status'] == 'needs_input'
    assert len(calls) == 1


def test_latex_bracket_prose_cannot_become_a_bullet_label(tmp_path):
    from agents import latex
    resume = {'person': {'name': 'Alex Example'}, 'experience': [], 'projects': [
        {'heading': 'Example', 'bullets': ['[C++] Implemented a planner'], 'dates': ''}]}
    tex = latex.render_tex(resume, tmp_path / 'resume.tex').read_text()
    assert r'\item {}[C++] Implemented a planner' in tex
