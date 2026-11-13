import { readFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import ts from 'typescript'

export async function loadTypeScriptModule(sourcePath, dependencies = {}) {
  // On Windows an absolute path (e.g. from path.resolve()) must be converted
  // to a file:// URL.  Relative paths are resolved against import.meta.url.
  let fileUrl
  if (path.isAbsolute(sourcePath)) {
    fileUrl = pathToFileURL(sourcePath)
  } else {
    fileUrl = new URL(sourcePath, import.meta.url)
  }
  const source = await readFile(fileUrl, 'utf8')
  let javascript = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText

  for (const [specifier, dependencyUrl] of Object.entries(dependencies)) {
    const escaped = specifier.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    javascript = javascript.replace(
      new RegExp(`from\\s+(['"])${escaped}\\1`, 'g'),
      `from ${JSON.stringify(dependencyUrl)}`,
    )
  }

  // Handle any relative imports to .ts files in the same directory by transpiling or rewriting
  // For types.js: if there are imports from './types', strip type-only imports or resolve to types.ts
  if (javascript.includes("from './types'") || javascript.includes('from "./types"')) {
    const typesPath = path.resolve(path.dirname(fileURLToPath(fileUrl)), 'types.ts')
    const typesModule = await loadTypeScriptModule(typesPath)
    javascript = javascript.replace(/from\s+['"]\.\/types['"]/g, `from ${JSON.stringify(typesModule.url)}`)
  }

  const url = `data:text/javascript;base64,${Buffer.from(javascript).toString('base64')}`
  return { module: await import(url), url }
}
