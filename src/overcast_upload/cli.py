"""Upload a podcast episode to Overcast.fm."""

import getpass
import os
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional

import requests
import typer

VERSION = "1.0"
BASE_URL = "https://overcast.fm"
LOGIN_URL = f"{BASE_URL}/login"
UPLOADS_URL = f"{BASE_URL}/uploads"
UPLOAD_SUCCEEDED_URL = f"{BASE_URL}/podcasts/upload_succeeded"

CREDENTIALS_PATH = Path("~/.config/overcast-upload/credentials").expanduser()
S3_REQUIRED_FIELDS = {"key", "policy"}


class UploadFormParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.form_action = None
        self.hidden_fields = {}
        self.file_field_name = "file"
        self._in_form = False
        self._current_action = None
        self._current_hidden = {}
        self._current_file_field = None
        self._best_score = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form":
            self._in_form = True
            action = attrs.get("action", "/uploads")
            self._current_action = action if action.startswith("http") else BASE_URL + action
            self._current_hidden = {}
            self._current_file_field = None
        elif tag == "input" and self._in_form:
            input_type = attrs.get("type", "").lower()
            name = attrs.get("name", "")
            if input_type == "hidden" and name:
                self._current_hidden[name] = attrs.get("value", "")
            elif input_type == "file" and name:
                self._current_file_field = name

    def handle_endtag(self, tag):
        if tag == "form":
            self._in_form = False
            # Pick the form with the most hidden fields + file input.
            # The S3 upload form has 7 hidden fields; the delete form has very few.
            score = (10 if self._current_file_field else 0) + len(self._current_hidden)
            if score > self._best_score:
                self._best_score = score
                self.form_action = self._current_action
                self.hidden_fields = dict(self._current_hidden)
                if self._current_file_field:
                    self.file_field_name = self._current_file_field


def filter_filename(filename):
    """Replicate Overcast's JS filterFilename: strip chars that S3 rejects."""
    filename = filename.replace(",", "").replace("/", "")
    if not filename:
        filename = "Upload"
    while filename and (filename[0] == "." or filename[0] == " "):
        if filename[0] == "." and filename.find(".") == filename.rfind("."):
            filename = "Upload" + filename
        else:
            filename = filename[1:]
    return filename


def _send_notification(title, message):
    subprocess.run(
        ["/usr/bin/osascript", "-e",
         f'display notification "{message}" with title "{title}" sound name "Glass"'],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _keychain_save(email, password):
    result = subprocess.run(
        ["security", "add-generic-password",
         "-s", "overcast-upload", "-a", email, "-w", password, "-U"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def _keychain_get(email):
    result = subprocess.run(
        ["security", "find-generic-password",
         "-s", "overcast-upload", "-a", email, "-w"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def read_credentials_file():
    if not CREDENTIALS_PATH.exists():
        return None, None
    data = {}
    for line in CREDENTIALS_PATH.read_text().splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            data[k.strip()] = v.strip()
    return data.get("email"), data.get("password")


def save_credentials(email, password):
    CREDENTIALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    if _keychain_save(email, password):
        CREDENTIALS_PATH.write_text(f"email={email}\n")
        CREDENTIALS_PATH.chmod(0o600)
        print(f"Email saved to {CREDENTIALS_PATH}; password saved to macOS Keychain.")
    else:
        print(
            "Warning: Could not save password to Keychain. Falling back to plaintext (chmod 600).",
            file=sys.stderr,
        )
        CREDENTIALS_PATH.write_text(f"email={email}\npassword={password}\n")
        CREDENTIALS_PATH.chmod(0o600)
        print(f"Credentials saved to {CREDENTIALS_PATH}")


def prompt_for_credentials():
    print("Enter your Overcast credentials:")
    email = input("Email: ").strip()
    if not email:
        print("Error: Email is required.", file=sys.stderr)
        sys.exit(1)
    password = getpass.getpass("Password: ")
    if not password:
        print("Error: Password is required.", file=sys.stderr)
        sys.exit(1)
    save_credentials(email, password)
    return email, password


def get_credentials():
    # 1. Env vars (useful for automation or `op run` power users)
    email = os.environ.get("OVERCAST_EMAIL")
    password = os.environ.get("OVERCAST_PASSWORD")
    if email and password:
        return email, password

    # 2. Credentials file email + Keychain password (plaintext fallback for old installs)
    email, file_password = read_credentials_file()
    if email:
        password = _keychain_get(email) or file_password
        if password:
            return email, password

    # 3. Prompt and save
    print("No credentials found. Run `overcast-upload --setup` to configure.")
    print("Or set OVERCAST_EMAIL and OVERCAST_PASSWORD environment variables.\n")
    return prompt_for_credentials()


def login(session, email, password):
    try:
        resp = session.post(
            LOGIN_URL,
            data={"email": email, "password": password, "then": "podcasts"},
            allow_redirects=True,
            timeout=30,
        )
    except requests.ConnectionError:
        print("Error: Could not reach overcast.fm. Check your connection.", file=sys.stderr)
        sys.exit(1)

    if "/login" in resp.url:
        print("Error: Login failed. Check your Overcast email and password.", file=sys.stderr)
        sys.exit(1)


def get_upload_form(session, debug=False):
    try:
        resp = session.get(UPLOADS_URL, timeout=30)
    except requests.ConnectionError:
        print("Error: Could not reach overcast.fm. Check your connection.", file=sys.stderr)
        sys.exit(1)

    if "/login" in resp.url:
        print("Error: Session expired or login failed.", file=sys.stderr)
        sys.exit(1)

    parser = UploadFormParser()
    parser.feed(resp.text)

    if not parser.form_action:
        print(
            "Error: Could not find upload form. Overcast may have changed their site.",
            file=sys.stderr,
        )
        sys.exit(1)

    if "s3.amazonaws.com" not in parser.form_action:
        print(
            f"Error: Upload form action does not look like an S3 endpoint "
            f"({parser.form_action!r}). Overcast may have changed their site.",
            file=sys.stderr,
        )
        sys.exit(1)

    if debug:
        print(f"[debug] form action: {parser.form_action}", file=sys.stderr)
        print(f"[debug] hidden field keys: {sorted(parser.hidden_fields)}", file=sys.stderr)
        print(f"[debug] file field name: {parser.file_field_name!r}", file=sys.stderr)

    missing = S3_REQUIRED_FIELDS - {k.lower() for k in parser.hidden_fields}
    if missing:
        print(
            f"Error: Upload form is missing required S3 fields: {sorted(missing)}. "
            "Overcast may have changed their site.",
            file=sys.stderr,
        )
        sys.exit(1)

    return parser


def upload_file(session, filepath, form, debug=False):
    raw_filename = Path(filepath).name
    filename = filter_filename(raw_filename)
    if filename != raw_filename:
        print(f"Filename adjusted: {raw_filename!r} → {filename!r}")
    key_prefix = form.hidden_fields.get("key", "").replace("${filename}", "")
    s3_key = key_prefix + filename

    if debug:
        print(f"[debug] S3 key: {s3_key!r}", file=sys.stderr)

    size_mb = Path(filepath).stat().st_size / 1_000_000
    print(f"Uploading {filename} ({size_mb:.1f} MB)...")

    # Build fields: all hidden fields with the resolved key, then the file last.
    # S3 presigned POST requires the file field to be last.
    hidden = dict(form.hidden_fields)
    hidden["key"] = s3_key
    try:
        fields = [(k, (None, v)) for k, v in hidden.items()]
        with open(filepath, "rb") as f:
            fields.append((form.file_field_name, (filename, f)))
            s3_resp = session.post(form.form_action, files=fields, timeout=300)
    except requests.ConnectionError:
        print("Error: Connection lost during upload. Check your connection.", file=sys.stderr)
        sys.exit(1)

    if s3_resp.status_code >= 400:
        print(f"Error: Upload failed (HTTP {s3_resp.status_code}).", file=sys.stderr)
        excerpt = s3_resp.text[:2000].strip()
        if excerpt:
            print(f"Server response:\n{excerpt}", file=sys.stderr)
        sys.exit(1)

    # Notify Overcast that the S3 upload is complete — this makes the file appear in the library.
    try:
        notify_resp = session.post(UPLOAD_SUCCEEDED_URL, data={"key": s3_key}, timeout=30)
    except requests.ConnectionError:
        print("Error: Upload to S3 succeeded but could not notify Overcast.", file=sys.stderr)
        sys.exit(1)

    if notify_resp.status_code >= 400:
        print(
            f"Error: S3 upload succeeded but Overcast notification failed "
            f"(HTTP {notify_resp.status_code}).",
            file=sys.stderr,
        )
        excerpt = notify_resp.text[:2000].strip()
        if excerpt:
            print(f"Server response:\n{excerpt}", file=sys.stderr)
        sys.exit(1)


def run_setup(do_notify=False, debug=False):
    print("overcast-upload setup\n")

    email, password = prompt_for_credentials()
    print()

    print("Testing login...")
    session = requests.Session()
    session.headers["User-Agent"] = "overcast-upload/1.0"
    login(session, email, password)
    print("Login successful.\n")

    form = get_upload_form(session, debug=debug)
    print(f"Upload form: {form.form_action}")
    print("\nSetup complete.")
    if do_notify:
        _send_notification("Overcast Upload", "Setup complete.")


def _version_callback(value: bool):
    if value:
        typer.echo(f"overcast-upload {VERSION}")
        raise typer.Exit()


def _run(
    file: Optional[Path] = typer.Argument(None, help="Path to the episode file to upload"),
    setup: bool = typer.Option(False, "--setup", help="Save Overcast credentials and verify they work"),
    notify: bool = typer.Option(False, "--notify", help="Show macOS notification on completion (used by Finder Quick Action)"),
    debug: bool = typer.Option(False, "--debug", help="Print diagnostic information to stderr"),
    version: Optional[bool] = typer.Option(None, "--version", callback=_version_callback, is_eager=True, help="Show version and exit"),
):
    if setup:
        run_setup(do_notify=notify, debug=debug)
        return

    if not file:
        typer.echo("Usage: overcast-upload [--setup] [--notify] FILE", err=True)
        raise typer.Exit(1)

    filepath = file
    if not filepath.exists():
        msg = f"File not found: {file}"
        typer.echo(f"Error: {msg}", err=True)
        if notify:
            _send_notification("Overcast Upload Failed", msg)
        raise typer.Exit(1)

    email, password = get_credentials()

    session = requests.Session()
    session.headers["User-Agent"] = "overcast-upload/1.0"

    try:
        login(session, email, password)
        form = get_upload_form(session, debug=debug)
        upload_file(session, filepath, form, debug=debug)
    except SystemExit:
        if notify:
            _send_notification("Overcast Upload Failed", f"Could not upload {filepath.name}.")
        raise

    print(f"Done! {filepath.name} uploaded to Overcast.")
    if notify:
        _send_notification("Overcast Upload", f"{filepath.name} uploaded successfully.")


def main():
    typer.run(_run)


if __name__ == "__main__":
    main()
