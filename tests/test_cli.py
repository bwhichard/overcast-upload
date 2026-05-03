import typer
import pytest
from typer.testing import CliRunner

from overcast_upload.cli import (
    UploadFormParser,
    filter_filename,
    read_credentials_file,
    _run,
    VERSION,
)

runner = CliRunner()


@pytest.fixture
def app():
    a = typer.Typer()
    a.command()(_run)
    return a


# --- filter_filename ---

def test_filter_filename_passthrough():
    assert filter_filename("episode.mp3") == "episode.mp3"

def test_filter_filename_strips_commas():
    assert filter_filename("ep,1.mp3") == "ep1.mp3"

def test_filter_filename_strips_slashes():
    assert filter_filename("path/to/ep.mp3") == "pathtoep.mp3"

def test_filter_filename_empty_becomes_upload():
    assert filter_filename("") == "Upload"

def test_filter_filename_strips_leading_space():
    assert filter_filename(" ep.mp3") == "ep.mp3"

def test_filter_filename_leading_dot_single_ext():
    # Only one dot — preserve it by prepending "Upload"
    assert filter_filename(".mp3") == "Upload.mp3"

def test_filter_filename_leading_dot_multiple():
    # Two dots — strip the leading dot
    assert filter_filename(".ep.mp3") == "ep.mp3"

def test_filter_filename_comma_leaves_leading_dot():
    # Comma stripped first, leaving a leading dot with one remaining dot
    assert filter_filename(",.mp3") == "Upload.mp3"


# --- UploadFormParser ---

S3_FORM_HTML = """
<html><body>
<form action="https://uploads-overcast.s3.amazonaws.com/" method="post"
      enctype="multipart/form-data">
  <input type="hidden" name="key" value="inbox/user123/${filename}">
  <input type="hidden" name="policy" value="eyJleHBpcmF0aW9uIjoiMjAyNS0wMS0wMVQwMDowMDowMFoifQ==">
  <input type="hidden" name="x-amz-credential" value="AKIA.../20250101/us-east-1/s3/aws4_request">
  <input type="hidden" name="x-amz-algorithm" value="AWS4-HMAC-SHA256">
  <input type="hidden" name="x-amz-date" value="20250101T000000Z">
  <input type="hidden" name="x-amz-signature" value="abc123">
  <input type="file" name="file">
  <input type="submit" value="Upload">
</form>
</body></html>
"""

DELETE_FORM_HTML = """
<form action="https://overcast.fm/delete" method="post">
  <input type="hidden" name="token" value="xyz">
  <input type="submit" value="Delete">
</form>
"""

def test_upload_form_parser_finds_action():
    p = UploadFormParser()
    p.feed(S3_FORM_HTML)
    assert p.form_action == "https://uploads-overcast.s3.amazonaws.com/"

def test_upload_form_parser_captures_hidden_fields():
    p = UploadFormParser()
    p.feed(S3_FORM_HTML)
    assert p.hidden_fields["key"] == "inbox/user123/${filename}"
    assert p.hidden_fields["policy"].startswith("eyJ")

def test_upload_form_parser_captures_file_field():
    p = UploadFormParser()
    p.feed(S3_FORM_HTML)
    assert p.file_field_name == "file"

def test_upload_form_parser_picks_s3_form_over_delete():
    p = UploadFormParser()
    p.feed(DELETE_FORM_HTML + S3_FORM_HTML)
    assert "s3.amazonaws.com" in p.form_action

def test_upload_form_parser_relative_action():
    html = """
    <form action="/uploads">
      <input type="hidden" name="key" value="k">
      <input type="hidden" name="policy" value="p">
      <input type="file" name="file">
    </form>
    """
    p = UploadFormParser()
    p.feed(html)
    assert p.form_action == "https://overcast.fm/uploads"

def test_upload_form_parser_no_form():
    p = UploadFormParser()
    p.feed("<html><body>nothing here</body></html>")
    assert p.form_action is None


# --- read_credentials_file ---

def test_read_credentials_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("overcast_upload.cli.CREDENTIALS_PATH", tmp_path / "credentials")
    email, password = read_credentials_file()
    assert email is None
    assert password is None

def test_read_credentials_file_email_only(tmp_path, monkeypatch):
    creds = tmp_path / "credentials"
    creds.write_text("email=test@example.com\n")
    monkeypatch.setattr("overcast_upload.cli.CREDENTIALS_PATH", creds)
    email, password = read_credentials_file()
    assert email == "test@example.com"
    assert password is None

def test_read_credentials_file_both(tmp_path, monkeypatch):
    creds = tmp_path / "credentials"
    creds.write_text("email=test@example.com\npassword=hunter2\n")
    monkeypatch.setattr("overcast_upload.cli.CREDENTIALS_PATH", creds)
    email, password = read_credentials_file()
    assert email == "test@example.com"
    assert password == "hunter2"

def test_read_credentials_file_ignores_comments(tmp_path, monkeypatch):
    creds = tmp_path / "credentials"
    creds.write_text("# this is a comment\nemail=test@example.com\n")
    monkeypatch.setattr("overcast_upload.cli.CREDENTIALS_PATH", creds)
    email, password = read_credentials_file()
    assert email == "test@example.com"


# --- CLI (typer) ---

def test_cli_version(app):
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert f"overcast-upload {VERSION}" in result.output

def test_cli_no_args_exits_nonzero(app):
    result = runner.invoke(app, [])
    assert result.exit_code != 0

def test_cli_file_not_found(app, tmp_path):
    result = runner.invoke(app, [str(tmp_path / "nonexistent.mp3")])
    assert result.exit_code != 0
    assert "File not found" in result.output
