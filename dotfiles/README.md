# dotfiles

A clean, well-documented Bash setup for **Ubuntu** and **Ubuntu on WSL**.
Modular, safe to install, and every file is commented so you know exactly what
it does and where to change things.

## What's inside

```
dotfiles/
├── setup.sh            installer: backs up your current files, installs these
├── bash/
│   ├── .bashrc         the "hub" -- sources everything below (edit rarely)
│   ├── .bash_env       ENVIRONMENT VARIABLES & PATH  (JAVA_HOME, ...)   <-- you will edit this
│   ├── .bash_aliases   shortcuts: ll, la, git aliases, WSL aliases, ...
│   ├── .bash_functions reusable functions: mkcd, extract, serve, up, ...
│   ├── .bash_prompt    git-aware, colored prompt
│   └── .inputrc        tab-completion & line-editing behaviour
└── .gitattributes      keeps Unix line endings (safe on Windows)
```

**The golden rule:** the files are separated by *purpose*. If you want a
shortcut → `.bash_aliases`. A function → `.bash_functions`. An environment
variable or PATH entry → `.bash_env`. You should almost never touch
`.bashrc` itself.

## Quick start

```bash
git clone <your-repo-url> dotfiles
cd dotfiles
bash setup.sh            # backs up old files, installs new ones
source ~/.bashrc         # or just open a new terminal
```

Optionally install the recommended tools the config knows how to use:

```bash
bash setup.sh --install-tools   # ripgrep, eza, fzf, zoxide, htop, jq, tree, bat, fd-find...
```

Your previous `~/.bashrc`, `~/.bash_env`, etc. are never lost: they land in
`~/.dotfiles-backup/<timestamp>/`.

## Where to put environment variables (PATH, JAVA_HOME, ...)

**Everything goes in `~/.bash_env`.** Open that file; it has worked, commented
examples for JAVA_HOME, Maven, Node/nvm, Go, Rust, Android and your own PATH
entries. Below is the same information in prose.

### PATH in one paragraph

`PATH` is a colon-separated list of directories searched in order when you type
a command. The first match wins, so **prepend** to override a system tool and
**append** to only add it as a fallback:

```bash
export PATH="$HOME/bin:$PATH"    # prepend -> your tool wins
export PATH="$PATH:$HOME/bin"    # append  -> system tool wins
```

Three rules that trip everyone up:

1. Always use `export` or the variable dies when the shell exits.
2. Never forget `:$PATH` on the right side, or you erase every existing entry.
3. A tool's home directory is usually *not* its `bin`. The `bin` is what goes
   on PATH.

### JAVA_HOME

Ubuntu installs OpenJDK into `/usr/lib/jvm`. The recommended setup in
`~/.bash_env` auto-detects the newest installed JDK:

```bash
export JAVA_HOME="$(ls -d /usr/lib/jvm/java-*-openjdk-* 2>/dev/null | sort -V | tail -n 1)"
export PATH="$JAVA_HOME/bin:$PATH"
```

To pin a specific version instead, comment that out and write:

```bash
export JAVA_HOME="/usr/lib/jvm/java-17-openjdk-amd64"
export PATH="$JAVA_HOME/bin:$PATH"
```

If you manually unpacked a JDK (Temurin/Adoptium), point `JAVA_HOME` at that
folder, e.g. `export JAVA_HOME="$HOME/tools/jdk-21"`.

### The same pattern for other tools

```bash
export MAVEN_HOME="$HOME/tools/apache-maven-3.9.9"
export PATH="$MAVEN_HOME/bin:$PATH"
```

And the tool's runtime needs its own `_HOME` too (it looks it up itself, and
its `bin` gives you the CLI): `GRADLE_HOME`, `ANDROID_HOME`, `GOPATH`, etc. —
all have ready-to-uncomment examples at the bottom of `~/.bash_env`.

### Why you'll never run into "not found" again

`~/.bashrc` is loaded by every interactive terminal. Ubuntu's default
`~/.profile` also sources `~/.bashrc`, so login shells (SSH, `bash -l`) pick
up the same environment. Because everything hangs off `~/.bashrc`, a variable
you add to `~/.bash_env` is visible everywhere, every time.

## Aliases & functions cheatsheet

| Group        | Examples |
|--------------|----------|
| listing      | `ll` `la` `l` `lt` `lr` `l1` — upgraded to `eza` if installed |
| navigation   | `..` `...` `....` `back` `home` `cdl` `mkcd` `up [n]` |
| search       | `rg` `gi` `gn` `hg` `findhere <name>` |
| files        | `rm`(ask first) `cp` `mv` `backup <f>` `extract <archive>` |
| git          | `g` `gs` `ga` `gc` `gpull` `gl` `gco` `gundo`(⚠ discards changes) |
| docker       | `dc` `dps` `dlogs` `dsh <container>` |
| system       | `update` `install` `search` `psg <name>` `mem` `disk` `ports` `myip` |
| WSL only     | `explorer` `open` `notepad` `clip` `winpath` `lpath` `wslshutdown` |
| misc         | `reload` `editbash` `serve` `sysinfo` `repeat <s> <cmd>` |

## WSL notes

- Everything "just works"; the config detects WSL and enables the interop
  aliases (`explorer`, `clip`, `winpath`, ...) automatically.
- **Avoid editing files through Windows tools** (VS Code can write CRLF into
  scripts on a fresh checkout). The included `.gitattributes` forces LF line
  endings, which fixes the most common "weird `\r`" shell errors.
- Restart WSL after major changes: run `wsl --shutdown` from PowerShell, or use
  the `wslshutdown` alias. It's not something that can be triggered from inside
  the distro.

## Customizing

- **Colours of the prompt**: the `_bp_*` variables at the top of
  `~/.bash_prompt` (change `_bp_green` to `_bp_yellow`, etc.).
- **Prompt layout**: edit the `PS1=` line at the bottom of `~/.bash_prompt`.
- **Key bindings**: emacs-style by default; uncomment `set -o vi` in
  `~/.bashrc` for vi mode.
- **Turn things off**: everything is guarded (`if command -v ...`), so tools
  that aren't installed are simply ignored.

## Uninstall

```bash
mv ~/.dotfiles-backup/<timestamp>/* ~/
```

That restores whatever you had before running `setup.sh`. To keep just a couple
of files, delete the others.
