#!/usr/bin/env node
// Prueba del hook .claude/hooks/guard-destructive.mjs: ejecuta el script real con JSON por stdin
// y compara la decisión con la esperada. No ejecuta ningún comando de la tabla.
// Uso: node tools/test_guard_destructive.mjs  (o npm.cmd --prefix frontend run test:guard)

import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import os from 'node:os'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const hook = path.join(root, '.claude', 'hooks', 'guard-destructive.mjs')
const dataAbs = path.join(root, 'data')
const tmp = os.tmpdir()

const CASES = [
  // Worktrees fuera de la carpeta temporal -> ask (el remove --force se deniega más abajo).
  ['ask', 'git worktree add ../SIGARD-bench entrenamiento-ML'],
  ['ask', 'git worktree prune'],

  // data/ -> deny
  ['deny', 'rm -rf data/interim/official'],
  ['deny', 'rm -rf data/__prueba_guard_inexistente'],
  ['deny', 'Remove-Item -Recurse .\\data\\interim'],
  ['deny', `rd /s /q ${dataAbs}`],
  ['deny', 'rd /s /q C:\\Users\\usuario\\Documents\\Proyectos\\SIGARD\\data'],
  ['deny', 'rm -fr ./data'],
  ['deny', 'rm -R /c/Users/usuario/Documents/Proyectos/SIGARD/data/processed'],
  ['deny', 'cd data && rm -rf interim'],
  ['deny', 'cd frontend; rm -rf ../data/interim'],
  ['deny', 'rmdir data'],
  ['deny', 'del /s /q data\\interim\\*'],
  ['deny', 'ri -r -fo .\\data\\interim\\official'],
  ['deny', 'powershell -Command "Remove-Item -LiteralPath \'data/interim\' -Recurse -Force"'],
  ['deny', 'cmd /c "rd /s /q data"'],
  ['deny', 'python -c "import shutil; shutil.rmtree(\'data/interim/official\')"'],
  ['deny', 'python -c "import os,glob; [os.remove(f) for f in glob.glob(\'data/interim/**\', recursive=True)]"'],
  ['deny', 'node -e "require(\'fs\').rmSync(\'data/interim\', {recursive: true, force: true})"'],
  ['deny', 'npx rimraf data/interim'],
  ['deny', 'robocopy C:\\vacio data\\interim /MIR'],
  ['deny', 'git clean -fdx'],
  ['deny', 'git clean -fd data/'],
  ['deny', 'rm -rf "$CLAUDE_PROJECT_DIR/data"'],
  ['deny', 'R`e`move-Item -Recurse data\\interim'],
  ['deny', 'mv data/interim /tmp/x'],
  ['deny', 'Move-Item .\\data\\processed C:\\otro'],
  ['deny', 'rm -rf .'],
  ['deny', 'rm -rf *'],
  ['deny', 'rm -rf d*'],
  ['deny', `rm -rf ${root}`],
  ['deny', 'find data -name "*.db" -delete'],
  ['deny', 'Get-ChildItem data\\interim | Remove-Item -Recurse -Force'],

  // Otros borrados -> ask
  ['ask', 'rm -rf frontend/node_modules'],
  ['ask', 'python -c "import shutil; shutil.rmtree(\'backend/.venv\')"'],
  ['ask', 'Remove-Item -Recurse -Force backend\\.venv'],
  ['ask', 'rd /s /q frontend\\node_modules'],
  ['ask', 'rm -rf C:/Users/usuario/AppData/Local/Temp/descartable'],
  ['ask', 'node -e "require(\'fs\').rmSync(\'frontend/dist\', {recursive: true})"'],
  ['ask', 'npx rimraf frontend/dist'],
  ['ask', 'git clean -fd'],
  ['ask', 'robocopy a b /PURGE'],
  ['ask', 'ls && rm -r build'],
  ['ask', 'find . -name "*.pyc" -delete'],
  ['ask', 'bash -c "rm -rf frontend/dist"'],
  ['ask', 'Get-ChildItem frontend\\dist | Remove-Item -Recurse'],

  // Enlaces que tocan el repositorio -> deny
  ['deny', 'cmd /c mklink /J ..\\bench\\node_modules frontend\\node_modules'],
  ['deny', 'mklink /J __guard_link backend\\.venv'],
  ['deny', 'mklink /D bench\\data data'],
  ['deny', 'mklink /H copia.txt README.md'],
  ['deny', `mklink /J ${tmp}\\bench\\data ${dataAbs}`],
  ['deny', 'New-Item -ItemType Junction -Path ..\\bench\\data -Target .\\data'],
  ['deny', 'New-Item -ItemType SymbolicLink -Path x -Target y'],
  ['deny', 'New-Item -ItemType HardLink -Path x -Target y'],
  ['deny', `New-Item -ItemType Junction -Path ${tmp}\\b\\venv -Target ${path.join(root, 'backend', '.venv')}`],
  ['deny', 'ln -s ../SIGARD/frontend/node_modules node_modules'],
  ['deny', `ln -s ${root.replace(/\\/g, '/')}/frontend/node_modules ${tmp.replace(/\\/g, '/')}/b/node_modules`],
  ['deny', 'python -c "import os; os.symlink(\'data\', \'C:/otro/data\')"'],
  ['deny', 'node -e "require(\'fs\').symlinkSync(\'backend/.venv\', \'C:/otro/venv\', \'junction\')"'],
  // Enlaces totalmente fuera del repositorio -> ask
  ['ask', `mklink /J ${tmp}\\a ${tmp}\\b`],
  ['ask', 'ln -s /c/otro/a /c/otro/b'],

  // Escenario completo del accidente (worktree en carpeta temporal + junctions + remove --force)
  ['deny', `git worktree add ${tmp}\\SIGARD-f0-bench entrenamiento-ML`],
  ['deny', 'git worktree add -b bench $env:TEMP\\SIGARD-f0-bench'],
  ['deny', 'git worktree add /tmp/SIGARD-f0-bench'],
  ['deny', `cmd /c mklink /J ${tmp}\\SIGARD-f0-bench\\data ${dataAbs}`],
  ['deny', `New-Item -ItemType Junction -Path ${tmp}\\SIGARD-f0-bench\\frontend\\node_modules -Target ${path.join(root, 'frontend', 'node_modules')}`],
  ['deny', 'git worktree remove --force ../SIGARD-f0-bench'],
  ['deny', `git worktree remove -f ${tmp}\\SIGARD-f0-bench`],
  ['deny', 'git -C ../SIGARD worktree remove --force ../SIGARD-f0-bench'],
  ['ask', 'git worktree remove ../SIGARD-f0-bench'],

  // Git destructivo -> ask
  ['ask', 'git reset --hard HEAD~1'],
  ['ask', 'git checkout -- .'],
  ['ask', 'git restore .'],
  ['ask', 'git push --force origin entrenamiento-ML'],
  ['ask', 'git push -f'],
  ['ask', 'git push --force-with-lease'],
  ['ask', 'git push origin --delete feature'],
  ['ask', 'git branch -D feature'],
  ['ask', 'git tag -d v1'],
  ['ask', 'powershell -EncodedCommand UgBlAG0AbwB2AGUALQBJAHQAZQBtAA=='],

  // Inofensivos -> sin salida
  ['allow', 'git status'],
  ['allow', 'git log --oneline -5'],
  ['allow', 'git pull'],
  ['allow', 'git push'],
  ['allow', 'git push origin entrenamiento-ML'],
  ['allow', 'git add .claude/settings.json tools/test_guard_destructive.mjs'],
  ['allow', 'git commit -m "docs: visor del mapa predictivo"'],
  ['allow', 'git diff --check'],
  ['allow', 'git checkout -b nueva-rama'],
  ['allow', 'git branch --show-current'],
  ['allow', 'git restore --staged AGENTS.md'],
  ['allow', 'npm.cmd --prefix frontend run dev'],
  ['allow', 'npm ci'],
  ['allow', 'npm.cmd --prefix frontend run lint'],
  ['allow', 'npm.cmd --prefix frontend run build'],
  ['allow', 'npm.cmd --prefix frontend run test:security'],
  ['allow', 'npm.cmd --prefix frontend run test:research'],
  ['allow', 'npm.cmd --prefix frontend run test:public-map'],
  ['allow', 'npm.cmd --prefix frontend run test:dev'],
  ['allow', 'npm.cmd --prefix frontend run test:alerts:browser'],
  ['allow', '.\\backend\\.venv\\Scripts\\python.exe -B -m pytest backend/tests -p no:cacheprovider'],
  ['allow', '.\\backend\\.venv\\Scripts\\python.exe -B backend/tests/publication_isolated.py --backend-regression'],
  ['allow', '.\\backend\\.venv\\Scripts\\python.exe -B tools/alerts_local.py create-admin'],
  ['allow', 'rg -n "rm -rf" docs'],
  ['allow', 'grep -rn "Remove-Item" AGENTS.md'],
  ['allow', 'ls data/interim'],
  ['allow', 'cat data/README.md'],
  ['allow', 'Get-ChildItem data\\interim'],
  ['allow', 'docker run --rm hello'],
  ['allow', 'mkdir -p C:/tmp/x'],
  ['allow', 'cp data/README.md C:/tmp/readme.md'],
  ['allow', 'mv frontend/dist frontend/dist-old'],
  ['allow', ''],

  // Falsos positivos reales de F4: los patrones de lenguaje en búsquedas y el texto de un heredoc
  // de mensaje de commit (líneas que empiezan con "del") no son comandos.
  ['allow', 'grep -n "emptyOutDir\\|rmSync\\|rm(\\|unlink" frontend/scripts/performance.browser.mjs'],
  ['allow', 'rg -n "rmSync|rmdirSync|shutil.rmtree|os.remove" data/interim/official/README.md'],
  ['allow', 'git log -S"rmSync" --oneline -- frontend/scripts'],
  ['allow', "sed -n '60,80p' frontend/scripts/performance.browser.mjs | grep -n \"fs.rm\\|rmSync\""],
  ['allow', 'git grep -n "shutil.rmtree" -- ml'],
  ['allow', `git commit -q -F - <<'EOF'
docs: marco de Administración v2
del visor predictivo: «Datos hasta» sale de data/interim/official
rm -rf y Remove-Item quedan documentados como prohibidos
EOF`],
  ['allow', `cat > C:/tmp/msg.txt <<'EOF'
fix(frontend): ajustes
del mapa público; rd /s data no se usa
EOF`],
  ['allow', 'git commit -m "fix: del visor; rm -rf data/interim ya no se ejecuta" -m "detalle: Remove-Item"'],
  ['allow', `git commit -m @'
docs: del manual
rm -rf data
'@`],

  // Las denegaciones sobre data/ no se debilitan: heredoc a un intérprete, script, código en línea.
  ['deny', `bash <<'EOF'
rm -rf data/interim/official
EOF`],
  ['deny', `python - <<'EOF'
import shutil
shutil.rmtree('data/interim/official')
EOF`],
  ['deny', `cat <<EOF | sh
del /s /q data\\interim
EOF`],
  ['deny', `cat > borrar.sh <<'EOF'
rm -rf data/interim
EOF`],
  ['deny', `node <<'EOF'
require('fs').rmSync('data/interim', { recursive: true })
EOF`],
  ['deny', 'git commit -m "docs: limpieza" && rm -rf data/interim'],
  ['deny', 'git commit -F msg.txt; Remove-Item -Recurse .\\data\\processed'],
  ['deny', '.\\backend\\.venv\\Scripts\\python.exe -c "import shutil; shutil.rmtree(\'data/interim\')"'],
  ['deny', 'powershell -Command "[System.IO.Directory]::Delete(\'data\\interim\', $true)"'],
  ['deny', "[System.IO.Directory]::Delete('data\\interim', $true)", 'PowerShell'],
  ['allow', "[System.IO.Directory]::Delete('data\\interim', $true)", 'Bash'],
  ['ask', 'node -e "require(\'fs\').rmSync(\'frontend/dist\', { recursive: true })"'],
  ['ask', `bash <<'EOF'
rm -rf frontend/dist
EOF`],
]

function run(stdin) {
  const result = spawnSync(process.execPath, [hook], {
    input: stdin,
    encoding: 'utf8',
    env: { ...process.env, CLAUDE_PROJECT_DIR: root },
    timeout: 10000,
  })
  if (result.status !== 0) return { decision: `exit ${result.status}`, reason: result.stderr }
  const out = result.stdout.trim()
  if (!out) return { decision: 'allow', reason: '' }
  try {
    const parsed = JSON.parse(out).hookSpecificOutput
    return { decision: parsed.permissionDecision, reason: parsed.permissionDecisionReason }
  } catch {
    return { decision: 'salida ilegible', reason: out }
  }
}

const payload = (tool, command) => JSON.stringify({
  session_id: 'test', hook_event_name: 'PreToolUse', cwd: root, tool_name: tool, tool_input: { command },
})

let failures = 0
let total = 0
const check = (expected, label, stdin) => {
  total += 1
  const got = run(stdin)
  const ok = got.decision === expected
  if (!ok) failures += 1
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${expected.padEnd(5)} ${ok ? '' : `(obtuvo ${got.decision}) `}${label}`)
  if (!ok && got.reason) console.log(`       ${got.reason}`)
}

// A third column limits a case to one tool (e.g. .NET calls are PowerShell code only there).
for (const [expected, command, tool] of CASES) {
  for (const name of tool ? [tool] : ['Bash', 'PowerShell']) check(expected, `[${name}] ${command || '(vacío)'}`, payload(name, command))
}
check('ask', 'JSON inválido', '{"tool_input": {"command": "rm -rf x"')
check('ask', 'entrada vacía', '')
check('ask', 'sin tool_input.command', JSON.stringify({ tool_name: 'Bash', tool_input: {} }))

console.log(`\n${total - failures}/${total} casos correctos`)
process.exitCode = failures ? 1 : 0
