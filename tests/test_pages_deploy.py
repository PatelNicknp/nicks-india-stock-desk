"""Scheduled data commits must start the Pages deploy.

A push made with GITHUB_TOKEN does not start other workflows, so the data/** path
filter on Deploy site never sees the daily commit. The data jobs call Deploy site
after a commit that changes data/ or site/.
"""
import os
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def test_pages_workflow_can_be_called_with_the_new_commit():
    yml = _read(".github", "workflows", "pages.yml")
    assert "workflow_call:" in yml
    assert "data/**" in yml
    assert "cp -a data/. _site/data/" in yml
    assert "test -s _site/data/trends.csv" in yml
    assert "github.event_name == 'workflow_call' && inputs.ref" in yml
    assert "GITHUB_TOKEN" in yml or "Actions token" in yml
    assert "\u2014" not in yml


def test_data_jobs_call_deploy_after_a_data_commit():
    update = _read(".github", "workflows", "update.yml")
    backfill = _read(".github", "workflows", "fundamentals-backfill.yml")
    for text in (update, backfill):
        assert "bash scripts/mark_pages_publish.sh" in text
        assert "uses: ./.github/workflows/pages.yml" in text
        assert "needs" in text and "data_pushed == 'true'" in text
        assert "pages: write" in text and "id-token: write" in text
        assert "publish_sha" in text
        assert "\u2014" not in text
    # The daily crons stay put.
    for cron in ("30 2 * * 1-5", "0 11 * * 1-5", "0 13 * * 1-5"):
        assert 'cron: "%s"' % cron in update
    assert "actions: read" in update
    assert update.count("bash scripts/mark_pages_publish.sh") == 1
    assert backfill.count("bash scripts/mark_pages_publish.sh") == 2


def test_mark_script_only_flags_published_paths():
    script = os.path.join(ROOT, "scripts", "mark_pages_publish.sh")
    assert "\u2014" not in _read("scripts", "mark_pages_publish.sh")

    def run(files):
        work = subprocess.check_output(["mktemp", "-d"], text=True).strip()
        env = os.environ.copy()
        note = os.path.join(work, "pages_publish.env")
        out = os.path.join(work, "github_output")
        env["PAGES_PUBLISH_FILE"] = note
        env["GITHUB_OUTPUT"] = out
        subprocess.check_call(["git", "init", "-q"], cwd=work)
        subprocess.check_call(["git", "config", "user.email", "t@example.com"], cwd=work)
        subprocess.check_call(["git", "config", "user.name", "t"], cwd=work)
        for rel, body in files:
            path = os.path.join(work, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(body)
            subprocess.check_call(["git", "add", rel], cwd=work)
        subprocess.check_call(["git", "commit", "-qm", "test"], cwd=work)
        proc = subprocess.run(["bash", script], cwd=work, env=env, capture_output=True, text=True, check=True)
        note_text = open(note, encoding="utf-8").read() if os.path.exists(note) else ""
        out_text = open(out, encoding="utf-8").read() if os.path.exists(out) else ""
        return proc.stdout, note_text, out_text

    data_out, data_note, data_gh = run([("data/meta.json", "{}\n")])
    assert "data_pushed=true" in data_out
    assert "publish_sha=" in data_note and "data_pushed=true" in data_note
    assert data_note == data_gh

    cache_out, cache_note, cache_gh = run([("cache/holders.csv", "ticker\n")])
    assert "data_pushed=false" in cache_out
    assert cache_note == "" and cache_gh == ""

    site_out, site_note, _site_gh = run([("site/index.html", "<p>hi</p>\n")])
    assert "data_pushed=true" in site_out and "publish_sha=" in site_note

    # A later cache-only commit must not erase a data note. The script only
    # writes the note when data/ or site/ changed, so the caller keeps the file.
    both = subprocess.check_output(["mktemp", "-d"], text=True).strip()
    subprocess.check_call(["git", "init", "-q"], cwd=both)
    subprocess.check_call(["git", "config", "user.email", "t@example.com"], cwd=both)
    subprocess.check_call(["git", "config", "user.name", "t"], cwd=both)
    os.makedirs(os.path.join(both, "data"))
    with open(os.path.join(both, "data", "meta.json"), "w", encoding="utf-8") as f:
        f.write("{}\n")
    subprocess.check_call(["git", "add", "data/meta.json"], cwd=both)
    subprocess.check_call(["git", "commit", "-qm", "data"], cwd=both)
    env = os.environ.copy()
    env["PAGES_PUBLISH_FILE"] = os.path.join(both, "pages_publish.env")
    subprocess.check_call(["bash", script], cwd=both, env=env)
    first = open(env["PAGES_PUBLISH_FILE"], encoding="utf-8").read()
    os.makedirs(os.path.join(both, "cache"))
    with open(os.path.join(both, "cache", "x.csv"), "w", encoding="utf-8") as f:
        f.write("a\n")
    subprocess.check_call(["git", "add", "cache/x.csv"], cwd=both)
    subprocess.check_call(["git", "commit", "-qm", "cache"], cwd=both)
    subprocess.check_call(["bash", script], cwd=both, env=env)
    assert open(env["PAGES_PUBLISH_FILE"], encoding="utf-8").read() == first
