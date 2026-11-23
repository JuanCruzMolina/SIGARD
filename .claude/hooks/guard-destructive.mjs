#!/usr/bin/env node
// SIGARD · control PreToolUse para Bash/PowerShell (Node, sin dependencias).
// Lee el JSON del hook por stdin y decide:
//   deny -> borrado o movimiento destructivo que alcanza data/ (o la raíz del repo o un ancestro).
//   ask  -> otros borrados, worktrees, enlaces, git destructivo y comandos no inspeccionables.
//   (sin salida) -> todo lo demás.
// Ante cualquier error o entrada ilegible responde "ask": nunca deja pasar en silencio.
// No desactivar, modificar ni esquivar este control (ver AGENTS.md).

import path from 'node:path'
import os from 'node:os'

// Posición de comando: inicio, separadores, subshells, cmd /c, -Command, bash -c, xargs, -exec, etc.
const CMD = String.raw`(?:^|[;&|(){}\n\x60]|\bcmd(?:\.exe)?\s+/[ck]|-command|\s-c|\b(?:do|then|else|xargs|sudo|exec|time|nohup|command|env|call|start)\b)\s*['"]?\s*`
const END = String.raw`(?=\s|$|['";&|)])`
const GIT = String.raw`\bgit(?:\.exe)?\s+(?:-c\s+\S+\s+|-C\s+\S+\s+)*`

const DELETE_PATTERNS = [
  [new RegExp(`${CMD}rm${END}`), 'rm'],
  [new RegExp(`${CMD}(?:rmdir|rd)${END}`), 'rmdir/rd'],
  [new RegExp(`${CMD}(?:del|erase|ri)${END}`), 'del/erase/ri'],
  [new RegExp(`${CMD}remove-item\\b`), 'Remove-Item'],
  [/(?:directory|file|fileinfo|directoryinfo)\]::delete\b|\.delete\(\s*(?:\$true|true)\s*\)/, '.NET Delete'],
  [new RegExp(`${GIT}clean\\b`, 'i'), 'git clean'],
  [/\brobocopy\b[^\n]*\/(?:mir|purge|move|mov)\b/, 'robocopy /MIR|/PURGE|/MOVE'],
  [/\brmtree\s*\(/, 'shutil.rmtree'],
  [/\bos\.(?:remove|unlink|rmdir|removedirs)\s*\(|\.unlink\s*\(|\.rmdir\s*\(/, 'os.remove/unlink/rmdir'],
  [/\bfs\.(?:promises\.)?(?:rm|rmdir|unlink)\b|\b(?:rmsync|rmdirsync|unlinksync)\b|\b(?:rm|rmdir)\s*\([^)]*recursive/, 'fs.rm/rmSync/rmdirSync'],
  [/\brimraf\b|\bdel-cli\b/, 'rimraf'],
  [/\bfind\b[^\n]*\s-delete\b/, 'find -delete'],
]

const MOVE_PATTERNS = [
  [new RegExp(`${CMD}(?:mv|move|mi|ren|rename)${END}`), 'mv/move'],
  [/\b(?:move|rename)-item\b/, 'Move-Item/Rename-Item'],
  [/\bshutil\.move\b|\bos\.(?:rename|replace)\s*\(|\bfs\.(?:promises\.)?rename\b|\brenamesync\b/, 'rename/move'],
]

const ASK_PATTERNS = [
  [new RegExp(`${GIT}worktree\\s+(?:add|remove|prune|move)\\b`, 'i'), 'git worktree add/remove/prune/move (un worktree con enlaces provocó el borrado de data/interim/official, .venv y node_modules)'],
  [new RegExp(`${CMD}mklink${END}`), 'crea un enlace (mklink)'],
  [/(?:new-item|\bni\b|\bmd\b|\bmkdir\b)[^\n]*(?:junction|symboliclink|hardlink)|-(?:itemtype|type|it)\s*:?\s*['"]?(?:junction|symboliclink|hardlink)/, 'crea un enlace (New-Item Junction/SymbolicLink/HardLink)'],
  [new RegExp(`${CMD}ln${END}`), 'crea un enlace (ln)'],
  [/\bos\.(?:symlink|link)\s*\(|\.(?:symlink_to|hardlink_to)\s*\(|\bfs\.(?:promises\.)?(?:symlink|link)\b|\b(?:symlinksync|linksync|createsymboliclink)\b|\bfsutil\s+hardlink\b|\bjunction(?:64)?(?:\.exe)?\s/, 'crea un enlace (symlink/junction/hardlink)'],
  [new RegExp(`${GIT}reset\\b[^;&|\\n]*--hard`, 'i'), 'git reset --hard descarta cambios locales'],
  [new RegExp(`${GIT}checkout\\b[^;&|\\n]*(?:\\s--(?=\\s|$)|\\s\\.(?=\\s|$)|\\s-f\\b|--force)`, 'i'), 'git checkout -- / . / -f descarta cambios locales'],
  [new RegExp(`${GIT}restore\\b(?![^;&|\\n]*--staged(?![^;&|\\n]*(?:--worktree|\\s-w\\b)))`, 'i'), 'git restore descarta cambios del árbol de trabajo'],
  [new RegExp(`${GIT}push\\b[^;&|\\n]*(?:\\s-[a-z]*f[a-z]*\\b|--force|--delete\\b|\\s-d\\b|--mirror\\b|--prune\\b|\\s\\+\\S|\\s:\\S)`, 'i'), 'git push forzado o borrado de ramas/etiquetas remotas'],
  [new RegExp(`${GIT}branch\\b[^;&|\\n]*(?:\\s-[a-z]*d[a-z]*\\b|--delete\\b)`, 'i'), 'git branch -D/-d/--delete borra ramas'],
  [new RegExp(`${GIT}tag\\b[^;&|\\n]*(?:\\s-d\\b|--delete\\b)`, 'i'), 'git tag -d borra etiquetas'],
  [/(?:^|\s)-(?:e|ec|en|enc|enco|encodedcommand)\s+['"]?[a-z0-9+/=]{16,}/, 'comando PowerShell codificado (-EncodedCommand), no inspeccionable'],
  [/(?:invoke-expression|\biex\b)[^\n]*(?:frombase64string|-join|\[char\])/, 'comando ofuscado (Invoke-Expression), no inspeccionable'],
]

const VERB_WORDS = new Set(['rm', 'rmdir', 'rd', 'del', 'erase', 'ri', 'remove-item', 'mv', 'move', 'mi', 'ren', 'rename',
  'move-item', 'rename-item', 'cmd', 'cmd.exe', 'python', 'python3', 'node', 'powershell', 'pwsh', 'bash', 'sh', 'git', 'clean',
  'sudo', 'xargs', 'find', 'robocopy', 'rimraf', 'npx', 'exec', 'do', 'done', 'then', 'fi', 'import', 'shutil', 'os', '{}'])

function emit(decision, reason) {
  process.stdout.write(JSON.stringify({
    hookSpecificOutput: {
      hookEventName: 'PreToolUse',
      permissionDecision: decision,
      permissionDecisionReason: `[guard-destructive] ${reason}`,
    },
  }))
}

const esc = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

// Ruta comparable: minúsculas, '/', '/c/...' (Git Bash) -> 'c:/...', sin '/' final.
function normPath(p) {
  let s = String(p).replace(/\\/g, '/').toLowerCase()
  const bash = /^\/([a-z])(\/|$)/.exec(s)
  if (bash) s = `${bash[1]}:/${s.slice(3)}`
  s = path.posix.normalize(s)
  if (s.length > 1 && s.endsWith('/') && !/^[a-z]:\/$/.test(s)) s = s.slice(0, -1)
  return s
}

const isWithin = (child, parent) => child === parent || child.startsWith(parent.endsWith('/') ? parent : `${parent}/`)

function variants(command) {
  const a = command.replace(/\\/g, '/').toLowerCase()
  // Sin escapes ni comillas: R`e`move-Item, r^d, "r"m, 'da''ta'.
  const b = a.replace(/[\x60^]/g, '').replace(/(\w)["']+(?=\w)/g, '$1').replace(/['"]/g, ' ')
  return [a, b]
}

function firstMatch(text, patterns) {
  for (const [re, label] of patterns) if (re.test(text)) return label
  return null
}

function context(input) {
  const project = normPath(process.env.CLAUDE_PROJECT_DIR || input.cwd || process.cwd())
  const cwd = normPath(input.cwd || process.env.CLAUDE_PROJECT_DIR || process.cwd())
  const names = [...new Set(['sigard', path.posix.basename(project)].filter(Boolean))].map(esc).join('|')
  return { project, cwd, data: `${project}/data`, home: normPath(os.homedir()), names }
}

// "data" como carpeta de la raíz: data, ./data, ../data, <...>/SIGARD*/data, $CLAUDE_PROJECT_DIR/data, $PWD/data.
function dataRegex(ctx) {
  const prefix = String.raw`(?:(?:\.{1,2}/)+|[^\s'"]*?(?:(?:${ctx.names})[^/\s'"]*|claude_project_dir\}?%?|\$pwd|\$\(pwd\)|%cd%|\$psscriptroot)/)?`
  return new RegExp(String.raw`(?:^|[\s;&|(){}\[\]'"=,:<>])${prefix}data(?=$|[/\s;&|(){}\[\]'",*:])`)
}

function resolveToken(token, ctx) {
  const t0 = token.replace(/^[(\[{]+|[)\]};,]+$/g, '')
  if (!t0 || t0.startsWith('-') || t0.startsWith('$_') || /^\/[a-z]{1,8}$/.test(t0)) return null // flags (-rf, /s, /q, /mir)
  const t = t0
    .replace(/^(?:\$\{?claude_project_dir\}?|\$env:claude_project_dir|%claude_project_dir%)/, ctx.project)
    .replace(/^(?:\$pwd|\$\(pwd\)|%cd%)/, ctx.cwd)
    .replace(/^(?:~|\$home|\$env:userprofile|%userprofile%)(?=\/|$)/, ctx.home)
  return normPath(/^[a-z]:/.test(t) || t.startsWith('/') ? t : `${ctx.cwd}/${t}`)
}

const globToRegex = (glob) => new RegExp(`^${[...glob].map((c) => (c === '*' ? '.*' : c === '?' ? '.' : esc(c))).join('')}$`)

function segments(text) {
  return text.split(/&&|\|\||[;&|\n]/)
}

function tokens(segment) {
  return segment.split(/[\s'"=,()]+/).filter(Boolean)
}

// Argumentos del segmento que resuelven a data/, algo dentro de data/, la raíz del repo o un ancestro.
function protectedTarget(segment, ctx) {
  for (const raw of tokens(segment)) {
    if (VERB_WORDS.has(raw)) continue
    const resolved = resolveToken(raw, ctx)
    if (!resolved) continue
    if (/[*?[]/.test(resolved)) {
      const dir = path.posix.dirname(resolved)
      if ((dir === ctx.project && globToRegex(path.posix.basename(resolved)).test('data')) || isWithin(dir, ctx.data)) return resolved
      if (isWithin(ctx.project, dir)) return resolved
      continue
    }
    if (isWithin(resolved, ctx.data) || isWithin(ctx.project, resolved)) return resolved
  }
  return null
}

function describeTargets(segs) {
  const found = []
  for (const seg of segs) {
    for (const raw of tokens(seg)) {
      if (VERB_WORDS.has(raw) || raw.startsWith('-') || /^\/[a-z]{1,8}$/.test(raw) || /\.(?:rmtree|remove|unlink|rmdir|rmsync|rm)$/.test(raw)) continue
      found.push(raw)
    }
  }
  return [...new Set(found)].slice(0, 8).join(', ')
}

function decide(input) {
  if (!input || typeof input !== 'object') return ['ask', 'entrada del hook ilegible; se requiere confirmación manual.']
  const command = input.tool_input && input.tool_input.command
  if (typeof command !== 'string') return ['ask', 'no se pudo leer el comando; se requiere confirmación manual.']
  if (!command.trim()) return null

  const ctx = context(input)
  const dataRe = dataRegex(ctx)
  const cwdInData = isWithin(ctx.cwd, ctx.data)
  const shown = command.length > 400 ? `${command.slice(0, 400)}…` : command
  let ask = null

  for (const text of variants(command)) {
    const del = firstMatch(text, DELETE_PATTERNS)
    const move = firstMatch(text, MOVE_PATTERNS)
    if (del || move) {
      const label = del || move
      const delSegs = segments(text).filter((s) => firstMatch(s, DELETE_PATTERNS) || firstMatch(s, MOVE_PATTERNS))
      const onlyGitClean = del === 'git clean' && delSegs.every((s) => firstMatch(s, DELETE_PATTERNS) === 'git clean')
      const ignoredClean = new RegExp(`${GIT}clean\\b[^;&|\\n]*\\s-[a-z]*x`, 'i').test(text)
      let target = null
      if (dataRe.test(text)) target = 'data/'
      else if (cwdInData) target = `${ctx.cwd} (directorio actual dentro de data/)`
      else if (ignoredClean) target = 'archivos ignorados por Git (incluye data/, .venv y node_modules)'
      else if (!onlyGitClean) {
        for (const seg of delSegs) {
          const hit = protectedTarget(seg, ctx)
          if (hit && !/\bfind\b/.test(seg)) { target = `${hit} (data/, la raíz del repositorio o un ancestro)`; break }
        }
      }
      if (target) {
        return ['deny', `BLOQUEADO: ${label} sobre ${target}. data/ no se borra ni se mueve desde Claude Code. Si es imprescindible, pedíselo al responsable explicando qué y por qué. Comando: ${shown}`]
      }
      if (del) ask = ask || `Borrado detectado (${label}). Se borraría: ${describeTargets(delSegs) || '(no determinado)'}. Comando: ${shown}`
    }
    const other = firstMatch(text, ASK_PATTERNS)
    if (other) ask = ask || `${other}. Se ejecutaría: ${shown}`
  }
  return ask ? ['ask', ask] : null
}

let raw = ''
try {
  process.stdin.setEncoding('utf8')
  for await (const chunk of process.stdin) raw += chunk
  const result = decide(JSON.parse(raw))
  if (result) emit(result[0], result[1])
} catch (error) {
  emit('ask', `no se pudo interpretar la entrada del hook (${error && error.message ? error.message : error}); se requiere confirmación manual.`)
}
