# =============================================================================
#  ~/.bash_functions  --  reusable shell functions
#  Sourced automatically by ~/.bashrc. Add your own below.
# =============================================================================

# --- cd + ls ---------------------------------------------------------------
# cdl <dir>  -> change directory, then list it
cdl() { cd "$1" && ll; }

# mkcd <dir> -> make a directory (and parents) then cd into it
mkcd() { mkdir -p -- "$1" && cd -- "$1"; }

# up [n] -> go up n directories (default 1)
up() {
    local depth="${1:-1}" pwd_old="$PWD"
    for ((i = 0; i < depth; i++)); do
        pwd_old="${pwd_old%/*}"
    done
    [ -n "$pwd_old" ] && cd "$pwd_old" || cd /
}

# --- Archives ---------------------------------------------------------------
# extract <file> -> unpack whatever it is
extract() {
    if [ $# -ne 1 ]; then
        echo "usage: extract <archive-file>" >&2
        return 1
    fi
    case "$1" in
        *.tar.bz2 | *.tbz2)   tar xjf    "$1" ;;
        *.tar.gz | *.tgz)     tar xzf    "$1" ;;
        *.tar.xz | *.txz)     tar xJf    "$1" ;;
        *.tar.zst)            tar --zstd -xf "$1" ;;
        *.tar)                tar xf     "$1" ;;
        *.zip)                unzip      "$1" ;;
        *.7z)                 7z x       "$1" ;;
        *.rar)                unrar x    "$1" ;;
        *.gz)                 gunzip     "$1" ;;
        *.bz2)                bunzip2    "$1" ;;
        *.xz)                 unxz       "$1" ;;
        *.zst)                zstd -d    "$1" ;;
        *.z)                  uncompress "$1" ;;
        *) echo "extract: unsupported archive type: $1" >&2; return 1 ;;
    esac
}

# --- Files --------------------------------------------------------------------
# backup <file>... -> make timestamped .bak copies
backup() {
    for f in "$@"; do
        [ -e "$f" ] || { echo "backup: no such file: $f" >&2; continue; }
        cp -p "$f" "$f.bak.$(date +%Y%m%d-%H%M%S)"
    done
}

# findhere <pattern> -> case-insensitive filename search, ignoring .git
findhere() {
    find . -not -path './.git/*' -iname "*$1*" 2>/dev/null | head -n 50
}

# --- Dev ----------------------------------------------------------------------
# serve [port] -> static file server in the current directory
serve() {
    local port="${1:-8000}"
    python3 -m http.server "$port"
}

# showenv <cmd> -> print the first lines of a command's `env` output
showenv() {
    command -v "$1" >/dev/null 2>&1 || { echo "showenv: $1 not found" >&2; return 1; }
    env -i "$1" 2>&1 | head -n "${2:-5}" || true
}

# whichc <cmd> -> show every match (aliases, functions, paths)
whichc() {
    type -a -- "$1" 2>/dev/null || echo "not found: $1"
}

# --- System ----------------------------------------------------------------------
# repeat <seconds> <cmd...> -> run a command every N seconds
repeat() {
    local interval="${1:-2}"; shift
    while true; do
        clear
        "$@"
        sleep "$interval"
    done
}

# motd-ish summary of the machine
sysinfo() {
    echo "== host ==";   hostnamectl 2>/dev/null | sed -n '1,8p' || hostname
    echo "== cpu ==";   lscpu 2>/dev/null | grep -E '^CPU\(s\)|Model name' || true
    echo "== mem ==";   free -h
    echo "== disk ==";  df -hT / 2>/dev/null
}
