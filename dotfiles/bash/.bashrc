# =============================================================================
#  ~/.bashrc  --  main interactive Bash configuration (the "hub")
#
#  This file is the entry point for every interactive Bash session.
#  It is intentionally tiny and delegates to focused files so that you never
#  have to dig through one giant blob:
#
#    ~/.bash_env        -> PATH + environment variables  (JAVA_HOME, ...)
#    ~/.bash_aliases    -> command shortcuts  (ll, la, gs, ...)
#    ~/.bash_functions  -> reusable functions (mkcd, extract, ...)
#    ~/.bash_prompt     -> the fancy git-aware prompt
#
#  Rule of thumb: if you want a *variable* or *PATH* entry, it goes in
#  ~/.bash_env.  If you want a *shortcut*, it goes in ~/.bash_aliases.
#  Never edit this hub for personal settings.
# =============================================================================

# --- If not running interactively, don't do anything -------------------------
case $- in
    *i*) ;;
      *) return;;
esac

# --- Detect WSL (used a few places below) --------------------------------------
IS_WSL=""
if [ -r /proc/version ] && grep -qiE "microsoft|wsl" /proc/version; then
    IS_WSL="true"
fi

# --- Bash completion (Ubuntu provides /usr/share/bash-completion) --------------
if [ -r /etc/bash_completion ]; then
    . /etc/bash_completion
elif [ -r /usr/share/bash-completion/bash_completion ]; then
    . /usr/share/bash-completion/bash_completion
fi

# --- Colored ls/grep ------------------------------------------------------------
if [ -x /usr/bin/dircolors ]; then
    test -r ~/.dircolors && eval "$(dircolors -b ~/.dircolors)" || eval "$(dircolors -b)"
    alias ls='ls --color=auto'
    alias grep='grep --color=auto'
    alias egrep='egrep --color=auto'
    alias fgrep='fgrep --color=auto'
    alias dir='dir --color=auto'
    alias vdir='vdir --color=auto'
fi

# --- Environment variables & PATH  (JAVA_HOME, MAVEN_HOME, your PATHs) ---------
[ -f ~/.bash_env ] && . ~/.bash_env

# --- Aliases ----------------------------------------------------------------------
[ -f ~/.bash_aliases ] && . ~/.bash_aliases

# --- Functions ----------------------------------------------------------------------
[ -f ~/.bash_functions ] && . ~/.bash_functions

# --- Prompt ---------------------------------------------------------------------------
[ -f ~/.bash_prompt ] && . ~/.bash_prompt

# --- History ---------------------------------------------------------------------------
HISTCONTROL=ignoreboth        # ignore duplicates + lines starting with a space
HISTSIZE=10000                # lines kept in the session
HISTFILESIZE=20000            # lines kept in ~/.bash_history
HISTTIMEFORMAT='%F %T  '      # timestamp every history entry
shopt -s histappend           # append (don't overwrite) history file
# Merge history from other terminals on every prompt (needs bash >= 4.3)
if (( ${BASH_VERSINFO[0]} > 4 || (${BASH_VERSINFO[0]} == 4 && ${BASH_VERSINFO[1]} >= 3) )); then
    history -n
fi
# Prevent dupes while a command is running
set -o no_empty_cmd_completion 2>/dev/null || true

# --- Shell options ----------------------------------------------------------------------
shopt -s checkwinsize          # fix line wrap after terminal resize
shopt -s globstar              # enable **  (e.g. ls **/*.java)
shopt -s autocd 2>/dev/null || true   # type a directory name to cd into it

# Key bindings: default is emacs-style. Prefer vim-style? Uncomment:
# set -o vi
# (The .inputrc file also controls completion behaviour.)

# --- Tool hooks (enabled only if the tool is installed) ------------------------------
# zoxide  -- smart "cd", use `z <fragment>` to jump.  apt: sudo apt install zoxide
if command -v zoxide >/dev/null 2>&1; then
    eval "$(zoxide init bash)"
fi

# fzf -- fuzzy finder. Ctrl-R = history, Ctrl-T = files, Alt-C = cd. apt: sudo apt install fzf
if command -v fzf >/dev/null 2>&1; then
    eval "$(fzf --bash 2>/dev/null)" || eval "$(fzf --shell)" 2>/dev/null || true
fi

# --- WSL extras ----------------------------------------------------------------------------
if [ -n "$IS_WSL" ]; then
    # Make Windows executables reachable even if /mnt/c is not mounted yet
    WINPATH="/mnt/c/Windows/System32"
    case ":$PATH:" in
        *":$WINPATH:"*) ;;
        *) export PATH="$WINPATH:$PATH" ;;
    esac
    # Keep SSH agent for Windows tools working
    export DISPLAY="${DISPLAY:-:0}" 2>/dev/null || true
fi

# --- Misc defaults --------------------------------------------------------------------------
export EDITOR="${EDITOR:-nano}"
export PAGER="${PAGER:-less}"
export BROWSER="${BROWSER:-xdg-open}"
export LESS="${LESS:--R -F -X}"      # -R colours, -F quit if one screen, -X keep on exit

# Minimal fix for the "locale not supported by C library" warning
if [ -z "${LANG:-}" ] && command -v locale-gen >/dev/null 2>&1; then
    export LANG=C.UTF-8
fi

export DOTFILES_BASH_LOADED="yes"
