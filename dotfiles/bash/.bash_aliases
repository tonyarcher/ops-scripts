# =============================================================================
#  ~/.bash_aliases  --  command shortcuts
#
#  Sourced automatically by ~/.bashrc. (Ubuntu's *stock* ~/.bashrc sources
#  this file too, so it also works if you keep the default .bashrc.)
#  Add your own shortcuts here, one per line, with a short comment.
# =============================================================================

# --- ls -----------------------------------------------------------------------
alias ll='ls -lahF'          # long, human sizes, hidden files, type indicator
alias la='ls -A'             # everything except . and ..
alias l='ls -CF'             # columns + file-type indicator
alias lf='ls -lF'            # long listing, no hidden files
alias lr='ls -R'             # recursive
alias lt='ls -ltr'           # sorted by time (newest at the bottom)
alias lu='ls -ltu'           # sorted by last access time
alias l1='ls -1'             # one entry per line

# Modern replacement: `sudo apt install eza` (Ubuntu 24.04+)
if command -v eza >/dev/null 2>&1; then
    alias ll='eza -lah --group-directories-first --git'
    alias la='eza -a --group-directories-first'
    alias l='eza -1 --group-directories-first'
    alias lt='eza -lahT --level=2 --group-directories-first'   # 2-level tree
    alias tree='eza -lahT --group-directories-first'
fi

# --- Navigation ----------------------------------------------------------------
alias ..='cd ..'
alias ...='cd ../..'
alias ....='cd ../../..'
alias .....='cd ../../../..'
alias ~='cd ~'
alias cd..='cd ..'
alias home='cd ~'
alias back='cd -'            # jump to the previous directory

# --- grep ----------------------------------------------------------------------
alias rg='rg --smart-case --hidden'      # ripgrep (sudo apt install ripgrep)
alias gi='grep -i'
alias gn='grep -n'
alias gin='grep -in'
alias hg='history | grep -i'             # search command history

# --- File operations -------------------------------------------------------------
# Safety-first defaults
alias rm='rm -i'             # ask before deleting (use /bin/rm for a real override)
alias cp='cp -i -v'
alias mv='mv -i -v'
alias mkdir='mkdir -p'
alias rmf='rm -rf'           # unconditional recursive delete -- use with care

# --- Processes / system ----------------------------------------------------------
alias psg='ps aux | grep -v grep | grep -i'   # psg java  -> find a process
alias pkillf='pkill -9 -f'                    # kill by full command line
alias top='htop'                              # after: sudo apt install htop
alias mem='free -h'
alias disk='df -hT'
alias du1='du -h --max-depth=1 2>/dev/null | sort -h'
alias uptime='uptime && w'

# --- Network ----------------------------------------------------------------------
alias myip='curl -s ifconfig.me && echo'
alias ports='ss -tulpn'
alias ping='ping -c 5'

# --- Git --------------------------------------------------------------------------
alias g='git'
alias gs='git status'
alias gst='git stash'
alias gstp='git stash pop'
alias ga='git add'
alias gaa='git add --all'
alias gc='git commit -m'
alias gca='git commit --amend --no-edit'
alias gp='git push'
alias gpull='git pull --rebase'
alias gl='git log --oneline --graph --decorate -20'
alias gd='git diff'
alias gds='git diff --staged'
alias gb='git branch -vv'
alias gco='git checkout'
alias gcb='git checkout -b'
alias grm='git rm --cached'    # untrack a file but keep it on disk
alias gclean='git clean -fd'
alias glast='git log -1 --stat'
# DANGER ZONE -- discards ALL local changes and untracked files
alias gundo='git reset --hard HEAD && git clean -fd'

# --- Docker ------------------------------------------------------------------------
if command -v docker >/dev/null 2>&1; then
    alias dc='docker compose'
    alias dps='docker ps'
    alias dlogs='docker logs -f --tail 100'
    alias dsh='docker exec -it'    # dsh <container> bash
fi

# --- System management -----------------------------------------------------------------
alias update='sudo apt update && sudo apt upgrade -y && sudo apt autoremove -y'
alias install='sudo apt install'
alias search='apt search'
alias aptl='apt list --installed'

# --- Misc useful ------------------------------------------------------------------------
alias cls='clear'
alias clr='clear && printf "\033c"'        # full clear including scrollback
alias reload='source ~/.bashrc'
alias editbash='$EDITOR ~/.bash_env ~/.bash_aliases ~/.bash_functions ~/.bash_prompt ~/.bashrc'
alias wget='wget -c'                       # resume interrupted downloads
alias hist='history'
alias sudo='sudo '                         # let aliases expand under sudo
alias paths='echo -e "${PATH//:/\\n}"'     # print PATH one entry per line

# --- WSL / Windows interop --------------------------------------------------------------
if grep -qiE "microsoft|wsl" /proc/version 2>/dev/null; then
    alias explorer='explorer.exe .'        # open current dir in Windows Explorer
    alias open='explorer.exe'              # open a file with Windows default app
    alias notepad='notepad.exe'
    alias clip='clip.exe'                  # pipe stdout into the Windows clipboard
    alias winpath='wslpath -w'             # linux path -> windows path
    alias lpath='wslpath -u'               # windows path -> linux path
    alias ipconfig='ipconfig.exe'
    alias netstat='netstat.exe -a'         # includes Windows-side listening ports
    alias wslshutdown='wsl.exe --shutdown' # run from PowerShell to restart WSL
fi
