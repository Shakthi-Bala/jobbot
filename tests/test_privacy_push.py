import io
import json
import subprocess
import hashlib

from pypdf import PdfWriter
import pytest
from agents import privacy


@pytest.fixture
def repo(env):
    path = env / 'repo'
    path.mkdir()
    for args in (['init', '-q'], ['config', 'user.name', 'Test Author'],
                 ['config', 'user.email', 'test@example.invalid']):
        subprocess.run(['git', *args], cwd=path, check=True)
    return path


def git(repo, *args):
    return subprocess.check_output(['git', *args], cwd=repo, text=True).strip()


def commit(repo, message):
    git(repo, 'add', '.')
    git(repo, 'commit', '-qm', message)
    return git(repo, 'rev-parse', 'HEAD')


def update(head, old='0' * 40):
    return f'refs/heads/dev {head} refs/heads/dev {old}\n'


def test_push_scans_older_outgoing_commit_despite_clean_tip_and_worktree(repo):
    file = repo / 'notes.txt'
    file.write_text('Private alex@example.com')
    leak = commit(repo, 'first version')
    file.write_text('Clean version')
    head = commit(repo, 'cleaned version')
    assert privacy.run(repo) == []
    findings = privacy.scan_push(update(head), repo)
    assert any(leak[:12] in line and 'email' in line for line in findings)
    assert not any('alex@example.com' in line for line in findings)


def test_uncommitted_cleanup_cannot_hide_pushed_bytes(repo):
    file = repo / 'notes.txt'
    file.write_text('Alex Example')
    head = commit(repo, 'first version')
    file.write_text('Clean working copy')
    assert privacy.run(repo) == []
    assert privacy.scan_push(update(head), repo)


def test_unchanged_remote_history_and_deleted_refs_are_not_reintroduced(repo):
    (repo / 'notes.txt').write_text('Alex Example')
    old = commit(repo, 'already remote')
    (repo / 'notes.txt').write_text('Clean')
    head = commit(repo, 'cleanup')
    assert privacy.scan_push(update(head, old), repo) == []
    assert privacy.scan_push(update('0' * 40, head), repo) == []


def test_pdf_metadata_and_unreadable_binary_are_not_silently_skipped(repo):
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.add_metadata({'/Author': 'Alex Example'})
    stream = io.BytesIO()
    writer.write(stream)
    (repo / 'resume.pdf').write_bytes(stream.getvalue())
    (repo / 'unknown.bin').write_bytes(b'\xff\x00\xaa')
    head = commit(repo, 'documents')
    findings = privacy.scan_push(update(head), repo)
    assert any('resume.pdf' in line and 'name' in line for line in findings)
    assert any('unknown.bin' in line and 'review required' in line for line in findings)


def test_reviewed_public_media_requires_exact_committed_hash(repo):
    path = repo / 'docs/assets'
    path.mkdir(parents=True)
    gif = path / 'demo.gif'
    gif.write_bytes(b'GIF89a\x00\xff')
    manifest = path / 'public-assets.json'
    manifest.write_text(json.dumps({'docs/assets/demo.gif': {
        'sha256': [hashlib.sha256(gif.read_bytes()).hexdigest()]}}))
    old = commit(repo, 'reviewed synthetic media')
    assert privacy.scan_push(update(old), repo) == []
    gif.write_bytes(b'GIF89a\x00\xfe')
    head = commit(repo, 'unreviewed change')
    assert any('demo.gif' in line for line in privacy.scan_push(update(head, old), repo))


def test_missing_profile_still_blocks_private_paths(repo, monkeypatch):
    from agents import core
    monkeypatch.setattr(core, 'DATA', repo / 'data')
    (repo / '.env').write_text('PASSWORD=private')
    head = commit(repo, 'private file')
    assert any('private file' in line for line in privacy.scan_push(update(head), repo))


def test_public_repository_exception_is_limited_to_that_repository():
    ids = {'alex-example': 'account handle'}
    repository = 'https://github.com/alex-example/jobbot'
    def inspect(url):
        return privacy.inspect_blob(url.encode(), 'README.md', ids, {}, [], repository)
    assert inspect(repository + '/actions/workflows/tests.yml/badge.svg') == []
    assert inspect(repository.upper() + '/issues') == []
    assert inspect(repository + '-private-notes')
    assert inspect('https://github.com/alex-example/profile')


def test_oversized_worktree_files_are_not_loaded_into_memory(repo, monkeypatch):
    large = repo / 'large.bin'
    with large.open('wb') as file:
        file.truncate(privacy.MAX_BYTES + 1)
    original = type(large).read_bytes
    def read(path):
        assert path != large, 'Oversized data must not be loaded'
        return original(path)
    monkeypatch.setattr(type(large), 'read_bytes', read)
    assert 'size limit' in privacy.scan([large], {}, repo)[0]
