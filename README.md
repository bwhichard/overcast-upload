# overcast-upload

A macOS CLI and Finder Quick Action for uploading podcast episodes directly to [Overcast](https://overcast.fm/uploads) without opening a browser.

## What It Does

Overcast lets you upload private audio files to your account so you can listen before publishing. Normally you have to log into the web UI, navigate to the uploads page, and manually select a file. This tool automates that entire flow from the command line or with a right-click in Finder.

```bash
overcast-upload "SDT 570.mp3"
# Uploading SDT 570.mp3 (44.2 MB)...
# Done! SDT 570.mp3 uploaded to Overcast.
```

## Requirements

- macOS
- Python 3.9+
- [requests](https://pypi.org/project/requests/) (`pip3 install requests`)

## Installation

### 1. Install the dependency

```bash
pip3 install requests
```

### 2. Install the CLI

Copy `overcast-upload` somewhere on your PATH:

```bash
sudo cp overcast-upload /usr/local/bin/overcast-upload
sudo chmod +x /usr/local/bin/overcast-upload
```

Or run `install.sh` which does this plus installs the Finder Quick Action:

```bash
bash install.sh
```

### 3. Save your credentials

```bash
overcast-upload --setup
```

This prompts for your Overcast email and password and saves them to `~/.config/overcast-upload/credentials` (chmod 600). It then tests the login to confirm everything works.

## Usage

### Command line

```bash
overcast-upload "episode.mp3"
```

### Finder Quick Action

Right-click any `.mp3`, `.m4a`, `.aac`, `.wav`, or `.m4b` file in Finder → **Quick Actions** → **Upload to Overcast**.

A macOS notification appears when the upload completes (or fails).

To install the Quick Action:

```bash
cp -r "Upload to Overcast.workflow" ~/Library/Services/
/System/Library/CoreServices/pbs -update
killall Finder
```

The first time you use it, macOS may ask Python for permission to access files in your Downloads folder — click Allow once and it won't ask again.

### Flags

| Flag | Description |
|---|---|
| `--setup` | Save Overcast credentials and verify they work |
| `--notify` | Show macOS notification on completion (used by Quick Action) |

## Credentials

Credentials are stored in `~/.config/overcast-upload/credentials`:

```
email=you@example.com
password=yourpassword
```

You can also set them as environment variables, which take precedence:

```bash
export OVERCAST_EMAIL="you@example.com"
export OVERCAST_PASSWORD="yourpassword"
```

Environment variables are useful for automation, CI, or if you prefer to manage secrets with a tool like [1Password CLI](https://developer.1password.com/docs/cli/) (`op run`).

## How It Works

The tool reverse-engineers Overcast's web upload flow:

1. **Login** — POSTs credentials to `overcast.fm/login` and holds the session cookie.
2. **Fetch upload form** — GETs `overcast.fm/uploads` and parses the HTML for a presigned AWS S3 form. Overcast generates fresh S3 credentials on each page load (time-limited, user-scoped).
3. **Upload to S3** — POSTs the file directly to `uploads-overcast.s3.amazonaws.com` as multipart/form-data using the presigned credentials. The S3 key includes a user-specific inbox path.
4. **Notify Overcast** — POSTs to `overcast.fm/podcasts/upload_succeeded` with the S3 key. This is the step the browser's JavaScript does after the S3 upload completes — it's what actually makes the file appear in your Overcast library.

## Troubleshooting

**"Login failed. Check your Overcast email and password."**
Verify your credentials with `overcast-upload --setup`. If your password contains special characters, check that the credentials file saved them correctly.

**"Could not find upload form"**
Overcast may have changed their site structure. Open an issue.

**Quick Action doesn't appear in Finder**
Right-click → Quick Actions → Customize and enable "Upload to Overcast". If it's not listed, re-run the install and restart Finder.

**Quick Action fails with "No module named 'requests'"**
The Automator environment uses a different Python than your terminal. This happens most often with [pyenv](https://github.com/pyenv/pyenv). Fix it by adding your pyenv shims to the Quick Action's PATH. Open `~/Library/Services/Upload to Overcast.workflow/Contents/document.wflow` in a text editor and change the PATH export to:

```
export PATH="/usr/local/bin:/opt/homebrew/bin:$HOME/.pyenv/shims:$PATH"
```

## File structure

```
overcast-upload                         # Python CLI script
install.sh                              # One-command installer
requirements.txt                        # Python dependencies
LICENSE
Upload to Overcast.workflow/            # Finder Quick Action bundle
  Contents/
    Info.plist                          # Service metadata (file types, menu name)
    document.wflow                      # Automator workflow (shell script action)
```

## License

MIT — see [LICENSE](LICENSE).
