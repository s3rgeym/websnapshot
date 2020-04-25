# WebSnapshot

🐍 Python command-line tool for capture 📷 snapshots of web pages using Headless Chromium.

Features:

- Change viewport size;
- Full page snaphots;
- Custom headers and other (see `--help`).

```bash
# install
$ pip install websnapshot

# install in isolated environment using pipx
$ pipx install websnapshot

# full page snapshot
$ echo "https://ru.wikipedia.org/wiki/%D0%92%D0%B8%D0%BA%D0%B8" | websnapshot --full_page

# file with urls, each on a new line
$ websnapshot -i urls.txt

# help
$ websnapshot --help
```
