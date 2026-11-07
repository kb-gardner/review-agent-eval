# PR pack: tailwindlabs/tailwindcss#20379
Title: Prevent `@tailwindcss/vite` crash under Vite's experimental `bundledDev`
Merge commit: 50daebded0a7c0fc529fe2fd5ff138cae7229bde

## Diff
```diff
diff --git a/CHANGELOG.md b/CHANGELOG.md
index 59642fd84267..3d61b76ab196 100644
--- a/CHANGELOG.md
+++ b/CHANGELOG.md
@@ -19,6 +19,7 @@ and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0
 - Fix standalone declarations in `@scope`, wrap them in `:where(:scope)` ([#20369](https://github.com/tailwindlabs/tailwindcss/pull/20369))
 - Always emit a space for empty fallback values in CSS variables (e.g. `var(--tw-blur,)` → `var(--tw-blur, )`) ([#20373](https://github.com/tailwindlabs/tailwindcss/pull/20373))
 - Canonicalization: convert arbitrary breakpoint and container query variants to named equivalents (e.g. `max-[64rem]` → `max-lg`) ([#20380](https://github.com/tailwindlabs/tailwindcss/pull/20380))
+- Prevent `@tailwindcss/vite` from crashing on every edit under Vite's experimental `bundledDev` mode ([#20379](https://github.com/tailwindlabs/tailwindcss/pull/20379))
 
 ## [4.3.3] - 2026-07-16
 
diff --git a/integrations/vite/bundled-dev.test.ts b/integrations/vite/bundled-dev.test.ts
new file mode 100644
index 000000000000..9596693760c6
--- /dev/null
+++ b/integrations/vite/bundled-dev.test.ts
@@ -0,0 +1,164 @@
+import path from 'node:path'
+import { candidate, css, html, json, retryAssertion, test, ts, txt, yaml } from '../utils'
+
+// Vite's experimental `bundledDev` mode invokes the `hotUpdate` hook without a
+// `server`, which used to crash the plugin on every file edit.
+//
+// - https://github.com/tailwindlabs/tailwindcss/issues/20378
+// - https://vite.dev/blog/announcing-vite8-1#experimental-bundled-dev-mode
+test(
+  'dev mode (experimental `bundledDev`)',
+  {
+    fs: {
+      'package.json': json`{}`,
+      'pnpm-workspace.yaml': yaml`
+        #
+        packages:
+          - project-a
+      `,
+      'project-a/package.json': txt`
+        {
+          "type": "module",
+          "dependencies": {
+            "@tailwindcss/vite": "workspace:^",
+            "tailwindcss": "workspace:^"
+          },
+          "devDependencies": {
+            "vite": "^8.1"
+          }
+        }
+      `,
+      'project-a/vite.config.ts': ts`
+        import tailwindcss from '@tailwindcss/vite'
+        import { defineConfig } from 'vite'
+
+        export default defineConfig({
+          experimental: {
+            bundledDev: true,
+          },
+          plugins: [tailwindcss()],
+        })
+      `,
+      'project-a/index.html': html`
+        <head>
+          <link rel="stylesheet" href="./src/index.css" />
+        </head>
+        <body>
+          <div class="underline">Hello, world!</div>
+        </body>
+      `,
+      'project-a/src/index.css': css`
+        @reference 'tailwindcss/theme';
+        @import 'tailwindcss/utilities';
+        @source '../../project-b/src/**/*.html';
+      `,
+      'project-b/src/index.html': html`
+        <div class="flex" />
+      `,
+    },
+  },
+  async ({ root, spawn, fs, expect }) => {
+    let process = await spawn('pnpm vite dev', {
+      cwd: path.join(root, 'project-a'),
+    })
+
+    // `hotUpdate` errors don't kill the dev server, they are only printed to
+    // stderr. Track them explicitly so a crash fails the test even if the
+    // rebuild happens to succeed anyway.
+    let pluginErrors: string[] = []
+    process.onStderr((message) => {
+      if (message.includes('@tailwindcss/vite')) pluginErrors.push(message)
+      return false
+    })
+
+    await process.onStdout((m) => m.includes('ready in'))
+
+    let url = ''
+    await process.onStdout((m) => {
+      let match = /Local:\s*(http.*)\//.exec(m)
+      if (match) url = match[1]
+      return Boolean(url)
+    })
+
+    // In `bundledDev` mode the stylesheet is not served separately. Instead the
+    // generated CSS is embedded in the bundled JS and injected at runtime, so
+    // extract the bundle from the served HTML. While the bundle is being built,
+    // Vite serves a temporary fallback page instead.
+    //
+    // The bundle can be split into multiple chunks (e.g. the HMR client runtime
+    // and the app itself), and the chunk containing the CSS is not always the
+    // first one, so fetch every referenced script and stylesheet.
+    async function fetchBundledStyles(): Promise<string> {
+      let index = await fetch(`${url}/`)
+      let html = await index.text()
+      if (html.includes('__vite_is_fallback_page__')) {
+        throw new Error('Bundling still in progress')
+      }
+
+      let sources = [
+        ...html.matchAll(/<script[^>]*\ssrc="([^"]+)"/g),
+        ...html.matchAll(/<link[^>]*\srel="stylesheet"[^>]*\shref="([^"]+)"/g),
+      ].map((match) => match[1])
+      if (sources.length === 0) throw new Error(`No scripts or stylesheets found in:\n\n${html}`)
+
+      let contents = await Promise.all(
+        sources.map(async (src) => {
+          let response = await fetch(new URL(src, `${url}/`))
+          return await response.text()
+        }),
+      )
+      return contents.join('\n')
+    }
+
+    await retryAssertion(async () => {
+      let styles = await fetchBundledStyles()
+      expect(styles).toContain(candidate`underline`)
+      expect(styles).toContain(candidate`flex`)
+    })
+
+    // A file change is only picked up once rolldown's watcher is fully set up,
+    // which races with the first write on slow machines. Retried writes must
+    // also produce _different_ content each time, because rolldown compares
+    // module contents and treats a write of identical content as a no-op — so a
+    // lost first change could never be recovered by re-writing the same file.
+    let iteration = 0
+
+    await retryAssertion(async () => {
+      // Updates are additive and cause new candidates to be added.
+      await fs.write(
+        'project-a/index.html',
+        html`
+          <head>
+            <link rel="stylesheet" href="./src/index.css" />
+          </head>
+          <body>
+            <div class="underline m-2">Hello, world! (${++iteration})</div>
+          </body>
+        `,
+      )
+
+      let styles = await fetchBundledStyles()
+      expect(styles).toContain(candidate`underline`)
+      expect(styles).toContain(candidate`flex`)
+      expect(styles).toContain(candidate`m-2`)
+    })
+
+    await retryAssertion(async () => {
+      // Manually added `@source`s are watched and trigger a rebuild
+      await fs.write(
+        'project-b/src/index.html',
+        html`
+          <div class="flex font-bold" data-iteration="${++iteration}" />
+        `,
+      )
+
+      let styles = await fetchBundledStyles()
+      expect(styles).toContain(candidate`underline`)
+      expect(styles).toContain(candidate`flex`)
+      expect(styles).toContain(candidate`m-2`)
+      expect(styles).toContain(candidate`font-bold`)
+    })
+
+    expect(pluginErrors).toEqual([])
+  },
+)
diff --git a/packages/@tailwindcss-vite/src/index.test.ts b/packages/@tailwindcss-vite/src/index.test.ts
new file mode 100644
index 000000000000..ee050e83321d
--- /dev/null
+++ b/packages/@tailwindcss-vite/src/index.test.ts
@@ -0,0 +1,28 @@
+import { expect, test } from 'vitest'
+import tailwindcss from './index'
+
+// Vite's experimental `bundledDev` mode calls `hotUpdate` without a `server`,
+// so the handler must not dereference it.
+//
+// - https://github.com/vitejs/vite/discussions/22746
+// - https://github.com/tailwindlabs/tailwindcss/issues/20378
+// - https://vite.dev/blog/announcing-vite8-1#experimental-bundled-dev-mode
+test('hotUpdate does not crash when Vite omits the server (bundledDev)', () => {
+  let plugin = tailwindcss().find((plugin) => plugin.name === '@tailwindcss/vite:generate:serve')!
+
+  let hotUpdate = plugin.hotUpdate as unknown as (options: {
+    file: string
+    modules: unknown[]
+    timestamp: number
+    server: undefined
+  }) => unknown
+
+  expect(() =>
+    hotUpdate.call(plugin, {
+      file: '/app/template.html',
+      modules: [{ type: 'asset', id: undefined }],
+      timestamp: Date.now(),
+      server: undefined,
+    }),
+  ).not.toThrow()
+})
diff --git a/packages/@tailwindcss-vite/src/index.ts b/packages/@tailwindcss-vite/src/index.ts
index bd38f5272f69..58c69e1eb36a 100644
--- a/packages/@tailwindcss-vite/src/index.ts
+++ b/packages/@tailwindcss-vite/src/index.ts
@@ -258,6 +258,14 @@ export default function tailwindcss(opts: PluginOptions = {}): Plugin[] {
       },
 
       hotUpdate({ file, modules, timestamp, server }) {
+        // Vite's experimental `bundledDev` mode invokes `hotUpdate` without a
+        // `server`, so there are no sibling environments to inspect and no
+        // server-level `hot`/`ws` channel to reload through. Bail out early
+        // rather than dereferencing `undefined`.
+        //
+        // https://github.com/tailwindlabs/tailwindcss/issues/20378
+        if (!server) return
+
         // Ensure full-reloads are triggered for files that are being watched by
         // Tailwind but aren't part of the module graph (like PHP or HTML
         // files). If we don't do this, then changes to those files won't

```

## Touched files at the merge commit (window of up to 200 lines around the first changed hunk)

### integrations/vite/bundled-dev.test.ts (lines 1 to 165 of 165)
```
    1| import path from 'node:path'
    2| import { candidate, css, html, json, retryAssertion, test, ts, txt, yaml } from '../utils'
    3| 
    4| // Vite's experimental `bundledDev` mode invokes the `hotUpdate` hook without a
    5| // `server`, which used to crash the plugin on every file edit.
    6| //
    7| // - https://github.com/tailwindlabs/tailwindcss/issues/20378
    8| // - https://vite.dev/blog/announcing-vite8-1#experimental-bundled-dev-mode
    9| test(
   10|   'dev mode (experimental `bundledDev`)',
   11|   {
   12|     fs: {
   13|       'package.json': json`{}`,
   14|       'pnpm-workspace.yaml': yaml`
   15|         #
   16|         packages:
   17|           - project-a
   18|       `,
   19|       'project-a/package.json': txt`
   20|         {
   21|           "type": "module",
   22|           "dependencies": {
   23|             "@tailwindcss/vite": "workspace:^",
   24|             "tailwindcss": "workspace:^"
   25|           },
   26|           "devDependencies": {
   27|             "vite": "^8.1"
   28|           }
   29|         }
   30|       `,
   31|       'project-a/vite.config.ts': ts`
   32|         import tailwindcss from '@tailwindcss/vite'
   33|         import { defineConfig } from 'vite'
   34| 
   35|         export default defineConfig({
   36|           experimental: {
   37|             bundledDev: true,
   38|           },
   39|           plugins: [tailwindcss()],
   40|         })
   41|       `,
   42|       'project-a/index.html': html`
   43|         <head>
   44|           <link rel="stylesheet" href="./src/index.css" />
   45|         </head>
   46|         <body>
   47|           <div class="underline">Hello, world!</div>
   48|         </body>
   49|       `,
   50|       'project-a/src/index.css': css`
   51|         @reference 'tailwindcss/theme';
   52|         @import 'tailwindcss/utilities';
   53|         @source '../../project-b/src/**/*.html';
   54|       `,
   55|       'project-b/src/index.html': html`
   56|         <div class="flex" />
   57|       `,
   58|     },
   59|   },
   60|   async ({ root, spawn, fs, expect }) => {
   61|     let process = await spawn('pnpm vite dev', {
   62|       cwd: path.join(root, 'project-a'),
   63|     })
   64| 
   65|     // `hotUpdate` errors don't kill the dev server, they are only printed to
   66|     // stderr. Track them explicitly so a crash fails the test even if the
   67|     // rebuild happens to succeed anyway.
   68|     let pluginErrors: string[] = []
   69|     process.onStderr((message) => {
   70|       if (message.includes('@tailwindcss/vite')) pluginErrors.push(message)
   71|       return false
   72|     })
   73| 
   74|     await process.onStdout((m) => m.includes('ready in'))
   75| 
   76|     let url = ''
   77|     await process.onStdout((m) => {
   78|       let match = /Local:\s*(http.*)\//.exec(m)
   79|       if (match) url = match[1]
   80|       return Boolean(url)
   81|     })
   82| 
   83|     // In `bundledDev` mode the stylesheet is not served separately. Instead the
   84|     // generated CSS is embedded in the bundled JS and injected at runtime, so
   85|     // extract the bundle from the served HTML. While the bundle is being built,
   86|     // Vite serves a temporary fallback page instead.
   87|     //
   88|     // The bundle can be split into multiple chunks (e.g. the HMR client runtime
   89|     // and the app itself), and the chunk containing the CSS is not always the
   90|     // first one, so fetch every referenced script and stylesheet.
   91|     async function fetchBundledStyles(): Promise<string> {
   92|       let index = await fetch(`${url}/`)
   93|       let html = await index.text()
   94|       if (html.includes('__vite_is_fallback_page__')) {
   95|         throw new Error('Bundling still in progress')
   96|       }
   97| 
   98|       let sources = [
   99|         ...html.matchAll(/<script[^>]*\ssrc="([^"]+)"/g),
  100|         ...html.matchAll(/<link[^>]*\srel="stylesheet"[^>]*\shref="([^"]+)"/g),
  101|       ].map((match) => match[1])
  102|       if (sources.length === 0) throw new Error(`No scripts or stylesheets found in:\n\n${html}`)
  103| 
  104|       let contents = await Promise.all(
  105|         sources.map(async (src) => {
  106|           let response = await fetch(new URL(src, `${url}/`))
  107|           return await response.text()
  108|         }),
  109|       )
  110|       return contents.join('\n')
  111|     }
  112| 
  113|     await retryAssertion(async () => {
  114|       let styles = await fetchBundledStyles()
  115|       expect(styles).toContain(candidate`underline`)
  116|       expect(styles).toContain(candidate`flex`)
  117|     })
  118| 
  119|     // A file change is only picked up once rolldown's watcher is fully set up,
  120|     // which races with the first write on slow machines. Retried writes must
  121|     // also produce _different_ content each time, because rolldown compares
  122|     // module contents and treats a write of identical content as a no-op — so a
  123|     // lost first change could never be recovered by re-writing the same file.
  124|     let iteration = 0
  125| 
  126|     await retryAssertion(async () => {
  127|       // Updates are additive and cause new candidates to be added.
  128|       await fs.write(
  129|         'project-a/index.html',
  130|         html`
  131|           <head>
  132|             <link rel="stylesheet" href="./src/index.css" />
  133|           </head>
  134|           <body>
  135|             <div class="underline m-2">Hello, world! (${++iteration})</div>
  136|           </body>
  137|         `,
  138|       )
  139| 
  140|       let styles = await fetchBundledStyles()
  141|       expect(styles).toContain(candidate`underline`)
  142|       expect(styles).toContain(candidate`flex`)
  143|       expect(styles).toContain(candidate`m-2`)
  144|     })
  145| 
  146|     await retryAssertion(async () => {
  147|       // Manually added `@source`s are watched and trigger a rebuild
  148|       await fs.write(
  149|         'project-b/src/index.html',
  150|         html`
  151|           <div class="flex font-bold" data-iteration="${++iteration}" />
  152|         `,
  153|       )
  154| 
  155|       let styles = await fetchBundledStyles()
  156|       expect(styles).toContain(candidate`underline`)
  157|       expect(styles).toContain(candidate`flex`)
  158|       expect(styles).toContain(candidate`m-2`)
  159|       expect(styles).toContain(candidate`font-bold`)
  160|     })
  161| 
  162|     expect(pluginErrors).toEqual([])
  163|   },
  164| )
  165| 
```

### packages/@tailwindcss-vite/src/index.test.ts (lines 1 to 29 of 29)
```
    1| import { expect, test } from 'vitest'
    2| import tailwindcss from './index'
    3| 
    4| // Vite's experimental `bundledDev` mode calls `hotUpdate` without a `server`,
    5| // so the handler must not dereference it.
    6| //
    7| // - https://github.com/vitejs/vite/discussions/22746
    8| // - https://github.com/tailwindlabs/tailwindcss/issues/20378
    9| // - https://vite.dev/blog/announcing-vite8-1#experimental-bundled-dev-mode
   10| test('hotUpdate does not crash when Vite omits the server (bundledDev)', () => {
   11|   let plugin = tailwindcss().find((plugin) => plugin.name === '@tailwindcss/vite:generate:serve')!
   12| 
   13|   let hotUpdate = plugin.hotUpdate as unknown as (options: {
   14|     file: string
   15|     modules: unknown[]
   16|     timestamp: number
   17|     server: undefined
   18|   }) => unknown
   19| 
   20|   expect(() =>
   21|     hotUpdate.call(plugin, {
   22|       file: '/app/template.html',
   23|       modules: [{ type: 'asset', id: undefined }],
   24|       timestamp: Date.now(),
   25|       server: undefined,
   26|     }),
   27|   ).not.toThrow()
   28| })
   29| 
```

### packages/@tailwindcss-vite/src/index.ts (lines 199 to 398 of 764)
```
  199|       configureServer(server) {
  200|         servers.push(server)
  201|       },
  202| 
  203|       async configResolved(_config) {
  204|         config = _config
  205|         isSSR = config.build.ssr !== false && config.build.ssr !== undefined
  206| 
  207|         // By default we optimize CSS during the build phase but if the user
  208|         // provides explicit options we'll use those instead
  209|         if (opts.optimize !== undefined) {
  210|           shouldOptimize = opts.optimize !== false
  211|         }
  212| 
  213|         // Minification is also performed when optimizing as long as it's also
  214|         // enabled in Vite
  215|         minify = shouldOptimize && config.build.cssMinify !== false
  216| 
  217|         // But again, the user can override that choice explicitly
  218|         if (typeof opts.optimize === 'object') {
  219|           minify = opts.optimize.minify !== false
  220|         }
  221|       },
  222|     },
  223| 
  224|     {
  225|       // Step 2 (serve mode): Generate CSS
  226|       name: '@tailwindcss/vite:generate:serve',
  227|       apply: 'serve',
  228|       enforce: 'pre',
  229|       transform: {
  230|         filter: {
  231|           id: {
  232|             exclude: [/\/\.vite\//, SPECIAL_QUERY_RE, COMMON_JS_PROXY_RE],
  233|             include: [/\.css(?:\?.*)?$/, /&lang\.css/, INLINE_STYLE_ID_RE],
  234|           },
  235|         },
  236|         async handler(src, id) {
  237|           if (!isPotentialCssRootFile(id)) return
  238| 
  239|           using I = new Instrumentation()
  240|           DEBUG && I.start('[@tailwindcss/vite] Generate CSS (serve)')
  241| 
  242|           let roots = rootsByEnv.get(this.environment?.name ?? 'default')
  243|           let root = roots.get(id)
  244|           if (!root) {
  245|             root ??= createRoot(this.environment ?? null, id)
  246|             roots.set(id, root)
  247|           }
  248| 
  249|           let result = await root.generate(src, (file) => this.addWatchFile(file), I)
  250|           if (!result) {
  251|             roots.delete(id)
  252|             return
  253|           }
  254| 
  255|           DEBUG && I.end('[@tailwindcss/vite] Generate CSS (serve)')
  256|           return result
  257|         },
  258|       },
  259| 
  260|       hotUpdate({ file, modules, timestamp, server }) {
  261|         // Vite's experimental `bundledDev` mode invokes `hotUpdate` without a
  262|         // `server`, so there are no sibling environments to inspect and no
  263|         // server-level `hot`/`ws` channel to reload through. Bail out early
  264|         // rather than dereferencing `undefined`.
  265|         //
  266|         // https://github.com/tailwindlabs/tailwindcss/issues/20378
  267|         if (!server) return
  268| 
  269|         // Ensure full-reloads are triggered for files that are being watched by
  270|         // Tailwind but aren't part of the module graph (like PHP or HTML
  271|         // files). If we don't do this, then changes to those files won't
  272|         // trigger a reload at all since Vite doesn't know about them.
  273|         {
  274|           // It's a little bit confusing, because due to the `addWatchFile`
  275|           // calls, it _is_ part of the module graph but nothing is really
  276|           // handling those files. These modules typically have an id of
  277|           // undefined and/or have a type of 'asset'.
  278|           //
  279|           // If we call `addWatchFile` on a file that is part of the actual
  280|           // module graph, then we will see a module for it with a type of `js`
  281|           // and a type of `asset`. We are only interested if _all_ of them are
  282|           // missing an id and/or have a type of 'asset', which is a strong
  283|           // signal that the changed file is not being handled by Vite or any of
  284|           // the plugins.
  285|           //
  286|           // Note: in Vite v7.0.6 the modules here will have a type of `js`, not
  287|           // 'asset'. But it will also have a `HARD_INVALIDATED` state and will
  288|           // do a full page reload already.
  289|           //
  290|           // Empty modules can be skipped since it means it's not
  291|           // `addWatchFile`d and thus irrelevant to Tailwind.
  292|           let isExternalFile =
  293|             modules.length > 0 &&
  294|             modules.every((mod) => mod.type === 'asset' || mod.id === undefined)
  295|           if (!isExternalFile) return
  296| 
  297|           // Skip files that Vite (or one of its plugins) processes as a
  298|           // module — in this environment (e.g. a lazily-loaded route that
  299|           // hasn't been visited yet) or in another one (e.g. an SSR-only
  300|           // module). Such a file can only affect the page through Vite's own
  301|           // pipeline, so a full reload would only destroy client state. Any
  302|           // changes to the generated CSS still go through the regular
  303|           // `css-update` flow because the file is registered via
  304|           // `addWatchFile`.
  305|           //
  306|           // If the file exists as a real module in another environment, then
  307|           // that environment is responsible for it. E.g. an SSR framework
  308|           // has its own server side hmr/reload mechanism when handling
  309|           // server only modules. See https://v6.vite.dev/guide/migration.html
  310|           // > Updates to an SSR-only module no longer triggers a full page reload in the client. ...
  311|           for (let environment of Object.values(server.environments)) {
  312|             if (environment.name === this.environment.name) continue
  313| 
  314|             let modules = environment.moduleGraph.getModulesByFile(file)
  315|             if (modules) {
  316|               for (let mod of modules) {
  317|                 if (mod.type !== 'asset') {
  318|                   return
  319|                 }
  320|               }
  321|             }
  322|           }
  323| 
  324|           // Otherwise the file is not loaded as a module anywhere, so
  325|           // determine whether its file _type_ would be processed by Vite
  326|           // when requested by the browser (in which case the file just isn't
  327|           // loaded yet, e.g. a lazily-loaded route that hasn't been visited).
  328|           // Vite has no API to answer this without actually running the
  329|           // plugin pipeline, so instead:
  330|           //
  331|           // Files Vite handles natively (the JS/TS and CSS families) are always
  332|           // processed by Vite. This includes stylesheets that never show up as
  333|           // their own module because a framework plugin compiles them into a
  334|           // component (e.g. Angular), in which case that plugin owns their HMR.
  335|           let extension = path.extname(file)
  336|           if (JS_EXTENSIONS_RE.test(extension) || vite.isCSSRequest(file)) return
  337| 
  338|           // For any other file type (e.g. `.vue`, `.svelte`, or `.md` with an
  339|           // SSG plugin), if a file with the same extension exists as a real
  340|           // module in any environment's module graph, then a plugin evidently
  341|           // handles this file type and the changed file just isn't loaded
  342|           // (yet).
  343|           if (extension !== '') {
  344|             if (viteProcessedExtensions.has(extension)) return
  345| 
  346|             for (let environment of Object.values(server.environments)) {
  347|               for (let mod of environment.moduleGraph.idToModuleMap.values()) {
  348|                 if (!mod.file?.endsWith(extension)) continue
  349|                 if (mod.type === 'asset') continue
  350| 
  351|                 // Only count modules that the plugin pipeline actually
  352|                 // transformed. Vite also creates untransformed placeholder
  353|                 // nodes (e.g. for the file underlying a `?raw` import) that
  354|                 // are not evidence that a plugin handles this file type.
  355|                 if (mod.transformResult == null) continue
  356| 
  357|                 // Similarly, ignore query imports (e.g. `./template.html?raw`,
  358|                 // or the `?html-proxy` modules Vite creates for inline
  359|                 // scripts): they pull a file's _contents_ into the graph
  360|                 // without a plugin processing the file type. A scanned
  361|                 // `.html` template must still trigger a full reload even if
  362|                 // some other `.html` file is imported with `?raw`.
  363|                 if (!mod.id || mod.id.includes('?')) continue
  364| 
  365|                 viteProcessedExtensions.add(extension)
  366|                 return
  367|               }
  368|             }
  369|           }
  370| 
  371|           for (let env of new Set([this.environment.name, 'client'])) {
  372|             let roots = rootsByEnv.get(env)
  373|             if (roots.size === 0) continue
  374| 
  375|             // If the file is not being watched by any of the roots, then we can
  376|             // skip the reload since it's not relevant to Tailwind CSS.
  377|             if (!isScannedFile(file, modules, roots)) {
  378|               continue
  379|             }
  380| 
  381|             // https://vite.dev/changes/hotupdate-hook#migration-guide
  382|             let invalidatedModules = new Set<vite.EnvironmentModuleNode>()
  383|             for (let mod of modules) {
  384|               this.environment.moduleGraph.invalidateModule(
  385|                 mod,
  386|                 invalidatedModules,
  387|                 timestamp,
  388|                 true,
  389|               )
  390|             }
  391| 
  392|             if (env === this.environment.name) {
  393|               this.environment.hot.send({ type: 'full-reload' })
  394|             } else if (server.hot.send) {
  395|               server.hot.send({ type: 'full-reload' })
  396|             } else if (server.ws.send) {
  397|               server.ws.send({ type: 'full-reload' })
  398|             }
```

### CHANGELOG.md (lines 1 to 200 of 4417)
```
    1| # Changelog
    2| 
    3| All notable changes to this project will be documented in this file.
    4| 
    5| The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
    6| and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
    7| 
    8| ## [Unreleased]
    9| 
   10| ### Added
   11| 
   12| - Add `@tailwindcss/turbopack` package to run Tailwind CSS with Next.js ([20367](https://github.com/tailwindlabs/tailwindcss/pull/20367))
   13| 
   14| ### Fixed
   15| 
   16| - Ensure watch mode detects changes to symlinked `@source` files whose real paths aren't otherwise scanned ([#20356](https://github.com/tailwindlabs/tailwindcss/pull/20356))
   17| - Ensure custom variants using `@scope` wrap the generated utilities instead of nesting inside them ([#20369](https://github.com/tailwindlabs/tailwindcss/pull/20369))
   18| - Fix flattening of `@scope` at-rules ([#20369](https://github.com/tailwindlabs/tailwindcss/pull/20369))
   19| - Fix standalone declarations in `@scope`, wrap them in `:where(:scope)` ([#20369](https://github.com/tailwindlabs/tailwindcss/pull/20369))
   20| - Always emit a space for empty fallback values in CSS variables (e.g. `var(--tw-blur,)` → `var(--tw-blur, )`) ([#20373](https://github.com/tailwindlabs/tailwindcss/pull/20373))
   21| - Canonicalization: convert arbitrary breakpoint and container query variants to named equivalents (e.g. `max-[64rem]` → `max-lg`) ([#20380](https://github.com/tailwindlabs/tailwindcss/pull/20380))
   22| - Prevent `@tailwindcss/vite` from crashing on every edit under Vite's experimental `bundledDev` mode ([#20379](https://github.com/tailwindlabs/tailwindcss/pull/20379))
   23| 
   24| ## [4.3.3] - 2026-07-16
   25| 
   26| ### Fixed
   27| 
   28| - Support `--watch --poll[=ms]` in `@tailwindcss/cli` when filesystem events are unreliable or unavailable ([#20297](https://github.com/tailwindlabs/tailwindcss/pull/20297))
   29| - Canonicalization: match arbitrary hex colors against theme colors case-insensitively (e.g. `bg-[#fff]` and `bg-[#FFF]` → `bg-white`) ([#20298](https://github.com/tailwindlabs/tailwindcss/pull/20298))
   30| - Prevent Preflight from overriding Firefox's native `iframe:focus-visible` outline styles ([#20292](https://github.com/tailwindlabs/tailwindcss/pull/20292))
   31| - Ensure `theme('colors.foo')` in JS plugins resolves correctly when both `--color-foo` and `--color-foo-bar` exist ([#20299](https://github.com/tailwindlabs/tailwindcss/pull/20299))
   32| - Ensure fractional opacity modifiers work with named shadow sizes like `shadow-sm/12.5`, `text-shadow-sm/12.5`, `drop-shadow-sm/12.5`, and `inset-shadow-sm/12.5` ([#20302](https://github.com/tailwindlabs/tailwindcss/pull/20302))
   33| - Parse selectors like `[data-foo]div` as two selectors instead of one ([#20303](https://github.com/tailwindlabs/tailwindcss/pull/20303))
   34| - Ensure `@tailwindcss/postcss` rebuilds when a preprocessor like Sass changes the input CSS without changing the input file on disk ([#20310](https://github.com/tailwindlabs/tailwindcss/pull/20310))
   35| - Ensure CSS nesting is handled even when Lightning CSS isn't run, such as in `@tailwindcss/browser` and Tailwind Play ([#20124](https://github.com/tailwindlabs/tailwindcss/pull/20124))
   36| - Prevent achromatic theme colors from shifting hue when mixed in polar color spaces like `oklch` ([#20314](https://github.com/tailwindlabs/tailwindcss/pull/20314))
   37| - Ensure `--spacing(0)` is optimized to `0px` instead of `0` so it remains a `<length>` when used in `calc(…)` ([#20319](https://github.com/tailwindlabs/tailwindcss/pull/20319))
   38| - Load `@parcel/watcher` only when needed in `@tailwindcss/cli --watch` mode, so one-off builds and `--watch --poll` work when `@parcel/watcher` can't be loaded ([#20325](https://github.com/tailwindlabs/tailwindcss/pull/20325))
   39| - Use explicit platform fonts instead of `system-ui` and `ui-sans-serif` so CJK text respects the page's `lang` attribute on Windows ([#20318](https://github.com/tailwindlabs/tailwindcss/pull/20318))
   40| - Prevent `@tailwindcss/upgrade` from rewriting ignored files when run from a subdirectory ([#20329](https://github.com/tailwindlabs/tailwindcss/pull/20329))
   41| - Ensure earlier `@source` rules pointing to nested files are scanned when later `@source` rules point to files in parent folders ([#20335](https://github.com/tailwindlabs/tailwindcss/pull/20335))
   42| - Prevent `@tailwindcss/vite` from triggering full page reloads when scanned files are processed by Vite but haven't been loaded as modules yet ([#20336](https://github.com/tailwindlabs/tailwindcss/pull/20336))
   43| 
   44| ## [4.3.2] - 2026-06-26
   45| 
   46| ### Fixed
   47| 
   48| - Support bare spacing values for `auto-rows-*` and `auto-cols-*` utilities (e.g. `auto-rows-12` and `auto-cols-16`) ([#20229](https://github.com/tailwindlabs/tailwindcss/pull/20229))
   49| - Prevent `@tailwindcss/cli` in `--watch` mode from crashing on Windows when `@source` points to a directory that doesn't exist ([#20242](https://github.com/tailwindlabs/tailwindcss/pull/20242))
   50| - Prevent `@tailwindcss/vite` from crashing in Deno v2.8.x when `context.parentURL` is not a valid URL ([#20245](https://github.com/tailwindlabs/tailwindcss/pull/20245))
   51| - Ensure `@tailwindcss/cli` in `--watch` mode rebuilds when the input CSS file changes in an ignored directory ([#20246](https://github.com/tailwindlabs/tailwindcss/pull/20246))
   52| - Allow `@variant` rules used in `addBase(…)` to use custom variants defined later ([#20247](https://github.com/tailwindlabs/tailwindcss/pull/20247))
   53| - Prevent `@tailwindcss/vite` from crashing during HMR when scanned files or directories are deleted ([#20259](https://github.com/tailwindlabs/tailwindcss/pull/20259))
   54| - Generate `font-size` instead of `color` declarations for `text-[--spacing(…)]` ([#20260](https://github.com/tailwindlabs/tailwindcss/pull/20260))
   55| - Prevent `@source` patterns from scanning unrelated sibling files and folders ([#20263](https://github.com/tailwindlabs/tailwindcss/pull/20263))
   56| - Extract class candidates adjacent to Template Toolkit delimiters like `%]…[%` in `.tt`, `.tt2`, and `.tx` files ([#20269](https://github.com/tailwindlabs/tailwindcss/pull/20269))
   57| - Extract class candidates from conditional Maud syntax like `p.text-black[condition]` ([#20269](https://github.com/tailwindlabs/tailwindcss/pull/20269))
   58| - Prevent `@position-try` rules from triggering unknown at-rule warnings when optimizing CSS ([#20277](https://github.com/tailwindlabs/tailwindcss/pull/20277))
   59| - Support class suggestions for named opacity modifiers from `--opacity` theme values ([#20287](https://github.com/tailwindlabs/tailwindcss/pull/20287))
   60| - Prevent type errors in `@tailwindcss/postcss` when used with newer PostCSS patch releases ([#20289](https://github.com/tailwindlabs/tailwindcss/pull/20289))
   61| 
   62| ## [4.3.1] - 2026-06-12
   63| 
   64| ### Added
   65| 
   66| - Add `--silent` option to suppress output in `@tailwindcss/cli` ([#20100](https://github.com/tailwindlabs/tailwindcss/pull/20100))
   67| 
   68| ### Fixed
   69| 
   70| - Remove deprecation warnings by using `Module#registerHooks` instead of `Module#register` on Node 26+ ([#20028](https://github.com/tailwindlabs/tailwindcss/pull/20028))
   71| - Canonicalization: don't crash when plugin utilities throw for unsupported values ([#20052](https://github.com/tailwindlabs/tailwindcss/pull/20052))
   72| - Allow `@apply` to be used with CSS mixins ([#19427](https://github.com/tailwindlabs/tailwindcss/pull/19427))
   73| - Ensure `not-*` correctly negates `@container` queries, including `style(…)` queries ([#20059](https://github.com/tailwindlabs/tailwindcss/pull/20059))
   74| - Ensure `drop-shadow-*` color utilities work with custom shadow values containing `calc(…)` ([#20080](https://github.com/tailwindlabs/tailwindcss/pull/20080))
   75| - Fix 'Sourcemap is likely to be incorrect' warnings when using `@tailwindcss/vite` ([#20103](https://github.com/tailwindlabs/tailwindcss/pull/20103))
   76| - Ensure `@tailwindcss/webpack` can be installed in Rspack projects without requiring `webpack` as a peer dependency ([#20027](https://github.com/tailwindlabs/tailwindcss/pull/20027))
   77| - Canonicalization: don't suggest invalid `calc(…)` expressions (e.g. `px-[calc(1rem+0px)]` → `px-[calc(1rem+0)]`) ([#20127](https://github.com/tailwindlabs/tailwindcss/pull/20127))
   78| - Canonicalization: avoid suggesting large spacing-scale values for arbitrary lengths (e.g. `left-[99999px]` → `left-[99999px]`, not `left-24999.75`) ([#20130](https://github.com/tailwindlabs/tailwindcss/pull/20130))
   79| - Ensure `@tailwindcss/cli` in `--watch` mode recovers when a tracked dependency is deleted and restored ([#20137](https://github.com/tailwindlabs/tailwindcss/pull/20137))
   80| - Ensure standalone `@tailwindcss/cli` binaries are ignored when scanning for class candidates ([#20139](https://github.com/tailwindlabs/tailwindcss/pull/20139))
   81| - Ensure class candidates are extracted from Twig `addClass(…)` and `removeClass(…)` calls ([#20198](https://github.com/tailwindlabs/tailwindcss/pull/20198))
   82| - Don't crash in the Ruby or Vue preprocessors when scanning files containing invalid UTF-8 bytes ([#19588](https://github.com/tailwindlabs/tailwindcss/pull/19588))
   83| - Allow `@variant` to be used inside `addBase` ([#19480](https://github.com/tailwindlabs/tailwindcss/pull/19480))
   84| - Ensure `@source` globs with symlinks are preserved ([#20203](https://github.com/tailwindlabs/tailwindcss/pull/20203))
   85| - Ensure later `@source` rules can re-include files excluded by earlier `@source not` rules ([#20203](https://github.com/tailwindlabs/tailwindcss/pull/20203))
   86| - Upgrade: don't migrate empty class rules to invalid `@utility` rules ([#20205](https://github.com/tailwindlabs/tailwindcss/pull/20205))
   87| - Ensure transitions between `inset-shadow-none` and other inset shadows work correctly ([#20208](https://github.com/tailwindlabs/tailwindcss/pull/20208))
   88| - Ensure explicitly referenced `@source` directories are scanned even when ignored by git ([#20214](https://github.com/tailwindlabs/tailwindcss/pull/20214))
   89| - Ensure `@source` globs ending in `**/*` preserve dynamic path segments to avoid scanning too many files ([#20217](https://github.com/tailwindlabs/tailwindcss/pull/20217))
   90| - Canonicalization: don't fold `calc(…)` divisions when the result would require high precision (e.g. `w-[calc(100%/3.5)]` → `w-[calc(100%/3.5)]`, not `w-[28.571428571428573%]`) ([#20221](https://github.com/tailwindlabs/tailwindcss/pull/20221))
   91| - Serve ESM type declarations to ESM importers of `@tailwindcss/postcss` ([#20228](https://github.com/tailwindlabs/tailwindcss/pull/20228))
   92| 
   93| ### Changed
   94| 
   95| - Generate `0` instead of `calc(var(--spacing) * 0)` for spacing utilities like `m-0` and `left-0` ([#20196](https://github.com/tailwindlabs/tailwindcss/pull/20196))
   96| - Generate `var(--spacing)` instead of `calc(var(--spacing) * 1)` for spacing utilities like `m-1` and `left-1` ([#20196](https://github.com/tailwindlabs/tailwindcss/pull/20196))
   97| 
   98| ## [4.3.0] - 2026-05-08
   99| 
  100| ### Added
  101| 
  102| - Add `@container-size` utility ([#18901](https://github.com/tailwindlabs/tailwindcss/pull/18901))
  103| - Add `scrollbar-{auto,thin,none}` utilities for `scrollbar-width`, and `scrollbar-thumb-*` / `scrollbar-track-*` color utilities for `scrollbar-color` ([#19981](https://github.com/tailwindlabs/tailwindcss/pull/19981), [#20019](https://github.com/tailwindlabs/tailwindcss/pull/20019))
  104| - Add `scrollbar-gutter-*` utilities ([#20018](https://github.com/tailwindlabs/tailwindcss/pull/20018))
  105| - Add `zoom-*` utilities ([#20020](https://github.com/tailwindlabs/tailwindcss/pull/20020))
  106| - Add `tab-*` utilities ([#20022](https://github.com/tailwindlabs/tailwindcss/pull/20022))
  107| - Allow using `@variant` with stacked variants (e.g. `@variant hover:focus { … }`) ([#19996](https://github.com/tailwindlabs/tailwindcss/pull/19996))
  108| - Allow using `@variant` with compound variants (e.g. `@variant hover, focus { … }`) ([#19996](https://github.com/tailwindlabs/tailwindcss/pull/19996))
  109| - Support `--default(…)` in `--value(…)` and `--modifier(…)` for functional `@utility` definitions ([#19989](https://github.com/tailwindlabs/tailwindcss/pull/19989))
  110| 
  111| ### Fixed
  112| 
  113| - Ensure `@plugin` resolves package JavaScript entries instead of browser CSS entries when using `@tailwindcss/vite` ([#19949](https://github.com/tailwindlabs/tailwindcss/pull/19949))
  114| - Fix relative `@import` and `@plugin` paths resolving from the wrong directory when using `@tailwindcss/vite` ([#19965](https://github.com/tailwindlabs/tailwindcss/pull/19965))
  115| - Ensure CSS files containing `@variant` are processed by `@tailwindcss/vite` ([#19966](https://github.com/tailwindlabs/tailwindcss/pull/19966))
  116| - Resolve imports relative to `base` when `result.opts.from` is not provided when using `@tailwindcss/postcss` ([#19980](https://github.com/tailwindlabs/tailwindcss/pull/19980))
  117| - Canonicalization: preserve significant `_` whitespace in arbitrary values ([#19986](https://github.com/tailwindlabs/tailwindcss/pull/19986))
  118| - Canonicalization: add parentheses when removing whitespace from arbitrary values would hurt readability (e.g. `w-[calc(100%---spacing(60))]` → `w-[calc(100%-(--spacing(60)))]`) ([#19986](https://github.com/tailwindlabs/tailwindcss/pull/19986))
  119| - Canonicalization: preserve the original unit in arbitrary values instead of normalizing to base units (e.g. `-mt-[20in]` → `mt-[-20in]`, not `mt-[-1920px]`) ([#19988](https://github.com/tailwindlabs/tailwindcss/pull/19988))
  120| - Canonicalization: migrate arbitrary `:has()` variants from `[&:has(…)]` to `has-[…]` ([#19991](https://github.com/tailwindlabs/tailwindcss/pull/19991))
  121| - Upgrade: don’t migrate inline `style` attributes (e.g. `style="flex-grow: 1"` → `style="flex-grow: 1"`, not `style="grow: 1"`) ([#19918](https://github.com/tailwindlabs/tailwindcss/pull/19918))
  122| - Allow multiple `@utility` definitions with the same name but different value types ([#19777](https://github.com/tailwindlabs/tailwindcss/pull/19777))
  123| - Export missing `PluginWithConfig` type from `tailwindcss/plugin` to fix errors when inferring plugin config types ([#19707](https://github.com/tailwindlabs/tailwindcss/pull/19707))
  124| - Ensure `start` and `end` legacy utilities without values do not generate CSS ([#20003](https://github.com/tailwindlabs/tailwindcss/pull/20003))
  125| - Ensure `--value(…)` is required in functional `@utility` definitions ([#20005](https://github.com/tailwindlabs/tailwindcss/pull/20005))
  126| - Canonicalization: preserve required whitespace around operators in negated arbitrary values (e.g. `-left-[(var(--a)+var(--b))]`) ([#20011](https://github.com/tailwindlabs/tailwindcss/pull/20011))
  127| 
  128| ## [4.2.4] - 2026-04-21
  129| 
  130| ### Fixed
  131| 
  132| - Ensure imports in `@import` and `@plugin` still resolve correctly when using Vite aliases in `@tailwindcss/vite` ([#19947](https://github.com/tailwindlabs/tailwindcss/pull/19947))
  133| 
  134| ## [4.2.3] - 2026-04-20
  135| 
  136| ### Fixed
  137| 
  138| - Canonicalization: improve canonicalization for `tracking-*` utilities by preferring non-negative utilities (e.g. `-tracking-tighter` → `tracking-wider`) ([#19827](https://github.com/tailwindlabs/tailwindcss/pull/19827))
  139| - Fix crash due to invalid characters in candidate (exceeding valid unicode code point range) ([#19829](https://github.com/tailwindlabs/tailwindcss/pull/19829))
  140| - Ensure query params in imports are considered unique resources when using `@tailwindcss/webpack` ([#19723](https://github.com/tailwindlabs/tailwindcss/pull/19723))
  141| - Canonicalization: collapse arbitrary values into shorthand utilities (e.g. `px-[1.2rem] py-[1.2rem]` → `p-[1.2rem]`) ([#19837](https://github.com/tailwindlabs/tailwindcss/pull/19837))
  142| - Canonicalization: collapse `border-{t,b}-*` into `border-y-*`, `border-{l,r}-*` into `border-x-*`, and `border-{t,r,b,l}-*` into `border-*` ([#19842](https://github.com/tailwindlabs/tailwindcss/pull/19842))
  143| - Canonicalization: collapse `scroll-m{t,b}-*` into `scroll-my-*`, `scroll-m{l,r}-*` into `scroll-mx-*`, and `scroll-m{t,r,b,l}-*` into `scroll-m-*` ([#19842](https://github.com/tailwindlabs/tailwindcss/pull/19842))
  144| - Canonicalization: collapse `scroll-p{t,b}-*` into `scroll-py-*`, `scroll-p{l,r}-*` into `scroll-px-*`, and `scroll-p{t,r,b,l}-*` into `scroll-p-*` ([#19842](https://github.com/tailwindlabs/tailwindcss/pull/19842))
  145| - Canonicalization: collapse `overflow-{x,y}-*` into `overflow-*` ([#19842](https://github.com/tailwindlabs/tailwindcss/pull/19842))
  146| - Canonicalization: collapse `overscroll-{x,y}-*` into `overscroll-*` ([#19842](https://github.com/tailwindlabs/tailwindcss/pull/19842))
  147| - Read from `--placeholder-color` instead of `--background-color` for `placeholder-*` utilities ([#19843](https://github.com/tailwindlabs/tailwindcss/pull/19843))
  148| - Upgrade: ensure files are not emptied out when killing the upgrade process while it's running ([#19846](https://github.com/tailwindlabs/tailwindcss/pull/19846))
  149| - Upgrade: use `config.content` when migrating from Tailwind CSS v3 to Tailwind CSS v4 ([#19846](https://github.com/tailwindlabs/tailwindcss/pull/19846))
  150| - Upgrade: never migrate files that are ignored by git ([#19846](https://github.com/tailwindlabs/tailwindcss/pull/19846))
  151| - Add `.env` and `.env.*` to default ignored content files ([#19846](https://github.com/tailwindlabs/tailwindcss/pull/19846))
  152| - Canonicalization: migrate `overflow-ellipsis` into `text-ellipsis` ([#19849](https://github.com/tailwindlabs/tailwindcss/pull/19849))
  153| - Canonicalization: migrate `start-full` → `inset-s-full`, `start-auto` → `inset-s-auto`, `start-px` → `inset-s-px`, and `start-<number>` → `inset-s-<number>` as well as negative versions ([#19849](https://github.com/tailwindlabs/tailwindcss/pull/19849))
  154| - Canonicalization: migrate `end-full` → `inset-e-full`, `end-auto` → `inset-e-auto`, `end-px` → `inset-e-px`, and `end-<number>` → `inset-e-<number>` as well as negative versions ([#19849](https://github.com/tailwindlabs/tailwindcss/pull/19849))
  155| - Canonicalization: move the `-` sign inside the arbitrary value `-left-[9rem]` → `left-[-9rem]` ([#19858](https://github.com/tailwindlabs/tailwindcss/pull/19858))
  156| - Canonicalization: move the `-` sign outside the arbitrary value `ml-[calc(-1*var(--width))]` → `-ml-(--width)` ([#19858](https://github.com/tailwindlabs/tailwindcss/pull/19858))
  157| - Improve performance when scanning JSONL / NDJSON files ([#19862](https://github.com/tailwindlabs/tailwindcss/pull/19862))
  158| - Support `NODE_PATH` environment variable in standalone CLI ([#19617](https://github.com/tailwindlabs/tailwindcss/pull/19617))
  159| 
  160| ## [4.2.2] - 2026-03-18
  161| 
  162| ### Fixed
  163| 
  164| - Don't crash when candidates contain prototype properties like `row-constructor` ([#19725](https://github.com/tailwindlabs/tailwindcss/pull/19725))
  165| - Canonicalize `calc(var(--spacing)*…)` expressions into `--spacing(…)` ([#19769](https://github.com/tailwindlabs/tailwindcss/pull/19769))
  166| - Fix crash in canonicalization step when handling utilities containing `@property` at-rules (e.g. `shadow-sm border`) ([#19727](https://github.com/tailwindlabs/tailwindcss/pull/19727))
  167| - Skip full reload for server only modules scanned by client CSS when using `@tailwindcss/vite` ([#19745](https://github.com/tailwindlabs/tailwindcss/pull/19745))
  168| - Add support for Vite 8 in `@tailwindcss/vite` ([#19790](https://github.com/tailwindlabs/tailwindcss/pull/19790))
  169| - Improve canonicalization for bare values exceeding default spacing scale suggestions (e.g. `w-1234 h-1234` → `size-1234`) ([#19809](https://github.com/tailwindlabs/tailwindcss/pull/19809))
  170| - Fix canonicalization resulting in empty list (e.g. `w-5 h-5 size-5` → `''` instead of `size-5`) ([#19812](https://github.com/tailwindlabs/tailwindcss/pull/19812))
  171| - Resolve tsconfig paths to allow for `@import '@/path/to/file';` when using `@tailwindcss/vite` ([#19803](https://github.com/tailwindlabs/tailwindcss/pull/19803))
  172| 
  173| ## [4.2.1] - 2026-02-23
  174| 
  175| ### Fixed
  176| 
  177| - Allow trailing dash in functional utility names for backwards compatibility ([#19696](https://github.com/tailwindlabs/tailwindcss/pull/19696))
  178| - Properly detect classes containing `.` characters within curly braces in MDX files ([#19711](https://github.com/tailwindlabs/tailwindcss/pull/19711))
  179| 
  180| ## [4.2.0] - 2026-02-18
  181| 
  182| ### Added
  183| 
  184| - Add mauve, olive, mist, and taupe color palettes to the default theme ([#19627](https://github.com/tailwindlabs/tailwindcss/pull/19627))
  185| - Add `@tailwindcss/webpack` package to run Tailwind CSS as a webpack plugin ([#19610](https://github.com/tailwindlabs/tailwindcss/pull/19610))
  186| - Add `pbs-*` and `pbe-*` utilities for `padding-block-start` and `padding-block-end` ([#19601](https://github.com/tailwindlabs/tailwindcss/pull/19601))
  187| - Add `mbs-*` and `mbe-*` utilities for `margin-block-start` and `margin-block-end` ([#19601](https://github.com/tailwindlabs/tailwindcss/pull/19601))
  188| - Add `scroll-pbs-*` and `scroll-pbe-*` utilities for `scroll-padding-block-start` and `scroll-padding-block-end` ([#19601](https://github.com/tailwindlabs/tailwindcss/pull/19601))
  189| - Add `scroll-mbs-*` and `scroll-mbe-*` utilities for `scroll-margin-block-start` and `scroll-margin-block-end` ([#19601](https://github.com/tailwindlabs/tailwindcss/pull/19601))
  190| - Add `border-bs-*` and `border-be-*` utilities for `border-block-start` and `border-block-end` ([#19601](https://github.com/tailwindlabs/tailwindcss/pull/19601))
  191| - Add `inline-*`, `min-inline-*`, `max-inline-*` utilities for `inline-size`, `min-inline-size`, and `max-inline-size` ([#19612](https://github.com/tailwindlabs/tailwindcss/pull/19612))
  192| - Add `block-*`, `min-block-*`, `max-block-*` utilities for `block-size`, `min-block-size`, and `max-block-size` ([#19612](https://github.com/tailwindlabs/tailwindcss/pull/19612))
  193| - Add `inset-s-*`, `inset-e-*`, `inset-bs-*`, `inset-be-*` utilities for `inset-inline-start`, `inset-inline-end`, `inset-block-start`, and `inset-block-end` ([#19613](https://github.com/tailwindlabs/tailwindcss/pull/19613))
  194| - Add `font-features-*` utility for `font-feature-settings` ([#19623](https://github.com/tailwindlabs/tailwindcss/pull/19623))
  195| 
  196| ### Fixed
  197| 
  198| - Prevent double `@supports` wrapper for `color-mix` values ([#19450](https://github.com/tailwindlabs/tailwindcss/pull/19450))
  199| - Allow whitespace around `@source inline()` argument ([#19461](https://github.com/tailwindlabs/tailwindcss/pull/19461))
  200| - Emit comment when source maps are saved to files when using `@tailwindcss/cli` ([#19447](https://github.com/tailwindlabs/tailwindcss/pull/19447))
```
