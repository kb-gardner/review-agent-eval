# PR pack: jetstreamapp/jetstream#2072
Title: build: fix dev server port detection on server restart fro mcode change
Merge commit: 6cc60fe016af65897a5a5d83ab3cba3d2f011299

## Diff
```diff
diff --git a/apps/jetstream/__tests__/vite.dev-port.spec.ts b/apps/jetstream/__tests__/vite.dev-port.spec.ts
new file mode 100644
index 000000000..bdfd7c70b
--- /dev/null
+++ b/apps/jetstream/__tests__/vite.dev-port.spec.ts
@@ -0,0 +1,62 @@
+// @vitest-environment node
+import { createServer, Server } from 'node:net';
+import { DEV_SERVER_HOST, resolveDevServerPort, RETAINED_PORT_ENV } from '../vite.dev-port.mts';
+
+/** Holds a port open, the way the running dev server does while Vite resolves the restarted config. */
+function occupyPort(port: number): Promise<Server> {
+  return new Promise((resolve, reject) => {
+    const server = createServer();
+    server.once('error', reject);
+    server.listen({ port, host: DEV_SERVER_HOST }, () => resolve(server));
+  });
+}
+
+function closeServer(server: Server): Promise<void> {
+  return new Promise((resolve) => server.close(() => resolve()));
+}
+
+describe('resolveDevServerPort', () => {
+  const openServers: Server[] = [];
+
+  beforeEach(() => {
+    // Nx loads .env into process.env, so a developer's pinned port must not leak into these tests
+    vi.stubEnv('JETSTREAM_DEV_PORT', '');
+    vi.stubEnv(RETAINED_PORT_ENV, '');
+  });
+
+  afterEach(async () => {
+    vi.unstubAllEnvs();
+    await Promise.all(openServers.splice(0).map(closeServer));
+  });
+
+  it('uses JETSTREAM_DEV_PORT when it is set', async () => {
+    vi.stubEnv('JETSTREAM_DEV_PORT', '4567');
+
+    await expect(resolveDevServerPort()).resolves.toBe(4567);
+  });
+
+  it('rejects a JETSTREAM_DEV_PORT that is not a port number', async () => {
+    vi.stubEnv('JETSTREAM_DEV_PORT', 'not-a-port');
+
+    await expect(resolveDevServerPort()).rejects.toThrow('JETSTREAM_DEV_PORT must be a port number');
+  });
+
+  it('skips a port that is already in use when searching', async () => {
+    const firstPort = await resolveDevServerPort();
+    openServers.push(await occupyPort(firstPort));
+    vi.stubEnv(RETAINED_PORT_ENV, '');
+
+    const secondPort = await resolveDevServerPort();
+
+    expect(secondPort).not.toBe(firstPort);
+  });
+
+  it('keeps the port chosen at startup across a server restart while that port is still bound', async () => {
+    const startupPort = await resolveDevServerPort();
+    // Vite resolves the restarted server's config before closing the old server, so the port
+    // chosen at startup is still bound by our own server when the config runs again.
+    openServers.push(await occupyPort(startupPort));
+
+    await expect(resolveDevServerPort()).resolves.toBe(startupPort);
+  });
+});
diff --git a/apps/jetstream/tsconfig.spec.json b/apps/jetstream/tsconfig.spec.json
index 1bdbf16dd..267ab5030 100644
--- a/apps/jetstream/tsconfig.spec.json
+++ b/apps/jetstream/tsconfig.spec.json
@@ -14,6 +14,7 @@
     "vite.config.mts",
     "vitest.config.ts",
     "vitest.config.mts",
+    "__tests__/**/*.spec.ts",
     "src/**/*.test.ts",
     "src/**/*.spec.ts",
     "src/**/*.test.tsx",
diff --git a/apps/jetstream/vite.config.mts b/apps/jetstream/vite.config.mts
index 443f13a88..b767dc0df 100644
--- a/apps/jetstream/vite.config.mts
+++ b/apps/jetstream/vite.config.mts
@@ -108,7 +108,7 @@ export default defineConfig(async ({ command }) => ({
     watch: false,
     globals: true,
     environment: 'jsdom',
-    include: ['{src,tests}/**/*.{test,spec}.{js,mjs,cjs,ts,mts,cts,jsx,tsx}'],
+    include: ['{src,tests,__tests__}/**/*.{test,spec}.{js,mjs,cjs,ts,mts,cts,jsx,tsx}'],
     reporters: ['default'],
     passWithNoTests: true,
     coverage: {
diff --git a/apps/jetstream/vite.dev-port.mts b/apps/jetstream/vite.dev-port.mts
index 6ad07c677..f4d67a947 100644
--- a/apps/jetstream/vite.dev-port.mts
+++ b/apps/jetstream/vite.dev-port.mts
@@ -23,6 +23,18 @@ export const DEV_SERVER_HOST = 'localhost';
  */
 const CANDIDATE_PORTS = [4200, ...Array.from({ length: 90 }, (_, index) => 4210 + index)];
 
+/**
+ * Process-scoped record of the port chosen by the first `resolveDevServerPort()` call.
+ *
+ * Vite re-evaluates the config file (and everything it imports, so module state is lost) whenever
+ * the dev server restarts — a config or `.env` change, or the `r` shortcut — and it resolves the
+ * new server's config *before* closing the old server. A fresh port scan at that point finds our
+ * own server on the port and drifts to the next candidate. `process.env` is the one thing that
+ * survives the config reload, so the chosen port is kept there and reused for the rest of the
+ * process. Not meant to be set by hand: use JETSTREAM_DEV_PORT to pin a port.
+ */
+export const RETAINED_PORT_ENV = 'JETSTREAM_DEV_PORT_RETAINED';
+
 function isPortAvailable(port: number): Promise<boolean> {
   return new Promise((resolve) => {
     const server = createServer();
@@ -36,6 +48,9 @@ function isPortAvailable(port: number): Promise<boolean> {
  * Finds a free dev server port so that several worktrees can run `pnpm start` at the same time
  * against one shared API. Set JETSTREAM_DEV_PORT to bypass the search and pin a specific port.
  *
+ * The search only runs once per process: a Vite server restart calls this again and must land on
+ * the port the server already owns (see RETAINED_PORT_ENV).
+ *
  * There is a small window between releasing the probed port and Vite binding it. `strictPort` is
  * enabled in vite.config.mts so that losing that race fails loudly rather than silently drifting
  * onto the desktop client's or canvas's port.
@@ -50,8 +65,14 @@ export async function resolveDevServerPort(): Promise<number> {
     return explicitPort;
   }
 
+  const retainedPort = Number(process.env[RETAINED_PORT_ENV]);
+  if (Number.isInteger(retainedPort) && retainedPort > 0) {
+    return retainedPort;
+  }
+
   for (const port of CANDIDATE_PORTS) {
     if (await isPortAvailable(port)) {
+      process.env[RETAINED_PORT_ENV] = String(port);
       return port;
     }
   }

```

## Touched files at the merge commit (window of up to 200 lines around the first changed hunk)

### apps/jetstream/__tests__/vite.dev-port.spec.ts (lines 1 to 63 of 63)
```
    1| // @vitest-environment node
    2| import { createServer, Server } from 'node:net';
    3| import { DEV_SERVER_HOST, resolveDevServerPort, RETAINED_PORT_ENV } from '../vite.dev-port.mts';
    4| 
    5| /** Holds a port open, the way the running dev server does while Vite resolves the restarted config. */
    6| function occupyPort(port: number): Promise<Server> {
    7|   return new Promise((resolve, reject) => {
    8|     const server = createServer();
    9|     server.once('error', reject);
   10|     server.listen({ port, host: DEV_SERVER_HOST }, () => resolve(server));
   11|   });
   12| }
   13| 
   14| function closeServer(server: Server): Promise<void> {
   15|   return new Promise((resolve) => server.close(() => resolve()));
   16| }
   17| 
   18| describe('resolveDevServerPort', () => {
   19|   const openServers: Server[] = [];
   20| 
   21|   beforeEach(() => {
   22|     // Nx loads .env into process.env, so a developer's pinned port must not leak into these tests
   23|     vi.stubEnv('JETSTREAM_DEV_PORT', '');
   24|     vi.stubEnv(RETAINED_PORT_ENV, '');
   25|   });
   26| 
   27|   afterEach(async () => {
   28|     vi.unstubAllEnvs();
   29|     await Promise.all(openServers.splice(0).map(closeServer));
   30|   });
   31| 
   32|   it('uses JETSTREAM_DEV_PORT when it is set', async () => {
   33|     vi.stubEnv('JETSTREAM_DEV_PORT', '4567');
   34| 
   35|     await expect(resolveDevServerPort()).resolves.toBe(4567);
   36|   });
   37| 
   38|   it('rejects a JETSTREAM_DEV_PORT that is not a port number', async () => {
   39|     vi.stubEnv('JETSTREAM_DEV_PORT', 'not-a-port');
   40| 
   41|     await expect(resolveDevServerPort()).rejects.toThrow('JETSTREAM_DEV_PORT must be a port number');
   42|   });
   43| 
   44|   it('skips a port that is already in use when searching', async () => {
   45|     const firstPort = await resolveDevServerPort();
   46|     openServers.push(await occupyPort(firstPort));
   47|     vi.stubEnv(RETAINED_PORT_ENV, '');
   48| 
   49|     const secondPort = await resolveDevServerPort();
   50| 
   51|     expect(secondPort).not.toBe(firstPort);
   52|   });
   53| 
   54|   it('keeps the port chosen at startup across a server restart while that port is still bound', async () => {
   55|     const startupPort = await resolveDevServerPort();
   56|     // Vite resolves the restarted server's config before closing the old server, so the port
   57|     // chosen at startup is still bound by our own server when the config runs again.
   58|     openServers.push(await occupyPort(startupPort));
   59| 
   60|     await expect(resolveDevServerPort()).resolves.toBe(startupPort);
   61|   });
   62| });
   63| 
```

### apps/jetstream/vite.dev-port.mts (lines 1 to 120 of 120)
```
    1| import { execFileSync } from 'node:child_process';
    2| import { createServer } from 'node:net';
    3| import { basename, join } from 'node:path';
    4| import { PluginOption } from 'vite';
    5| 
    6| /**
    7|  * The host Vite binds the dev server to. The availability probe below must bind the exact same
    8|  * host string, otherwise the probe and the real bind can disagree: vite.config.mts sets
    9|  * `dns.setDefaultResultOrder('verbatim')`, so `localhost` may resolve to `::1` while a probe
   10|  * against `127.0.0.1` reports the port free.
   11|  */
   12| export const DEV_SERVER_HOST = 'localhost';
   13| 
   14| /**
   15|  * Ports offered to the dev server, in order.
   16|  *
   17|  * 4200 comes first so that a single dev server behaves exactly as it always has — `.env` points
   18|  * NX_PUBLIC_CLIENT_URL at http://localhost:4200/app, which the API uses as the post-login redirect
   19|  * target, so the first server started should own that port.
   20|  *
   21|  * Additional worktrees running at the same time land on 4210+. 4201-4209 are deliberately skipped:
   22|  * jetstream-desktop-client uses 4201 and jetstream-canvas uses 4202.
   23|  */
   24| const CANDIDATE_PORTS = [4200, ...Array.from({ length: 90 }, (_, index) => 4210 + index)];
   25| 
   26| /**
   27|  * Process-scoped record of the port chosen by the first `resolveDevServerPort()` call.
   28|  *
   29|  * Vite re-evaluates the config file (and everything it imports, so module state is lost) whenever
   30|  * the dev server restarts — a config or `.env` change, or the `r` shortcut — and it resolves the
   31|  * new server's config *before* closing the old server. A fresh port scan at that point finds our
   32|  * own server on the port and drifts to the next candidate. `process.env` is the one thing that
   33|  * survives the config reload, so the chosen port is kept there and reused for the rest of the
   34|  * process. Not meant to be set by hand: use JETSTREAM_DEV_PORT to pin a port.
   35|  */
   36| export const RETAINED_PORT_ENV = 'JETSTREAM_DEV_PORT_RETAINED';
   37| 
   38| function isPortAvailable(port: number): Promise<boolean> {
   39|   return new Promise((resolve) => {
   40|     const server = createServer();
   41|     server.once('error', () => resolve(false));
   42|     server.once('listening', () => server.close(() => resolve(true)));
   43|     server.listen({ port, host: DEV_SERVER_HOST });
   44|   });
   45| }
   46| 
   47| /**
   48|  * Finds a free dev server port so that several worktrees can run `pnpm start` at the same time
   49|  * against one shared API. Set JETSTREAM_DEV_PORT to bypass the search and pin a specific port.
   50|  *
   51|  * The search only runs once per process: a Vite server restart calls this again and must land on
   52|  * the port the server already owns (see RETAINED_PORT_ENV).
   53|  *
   54|  * There is a small window between releasing the probed port and Vite binding it. `strictPort` is
   55|  * enabled in vite.config.mts so that losing that race fails loudly rather than silently drifting
   56|  * onto the desktop client's or canvas's port.
   57|  */
   58| export async function resolveDevServerPort(): Promise<number> {
   59|   const { JETSTREAM_DEV_PORT } = process.env;
   60|   if (JETSTREAM_DEV_PORT) {
   61|     const explicitPort = Number(JETSTREAM_DEV_PORT);
   62|     if (!Number.isInteger(explicitPort) || explicitPort < 1 || explicitPort > 65535) {
   63|       throw new Error(`JETSTREAM_DEV_PORT must be a port number between 1 and 65535, got "${JETSTREAM_DEV_PORT}".`);
   64|     }
   65|     return explicitPort;
   66|   }
   67| 
   68|   const retainedPort = Number(process.env[RETAINED_PORT_ENV]);
   69|   if (Number.isInteger(retainedPort) && retainedPort > 0) {
   70|     return retainedPort;
   71|   }
   72| 
   73|   for (const port of CANDIDATE_PORTS) {
   74|     if (await isPortAvailable(port)) {
   75|       process.env[RETAINED_PORT_ENV] = String(port);
   76|       return port;
   77|     }
   78|   }
   79| 
   80|   throw new Error(
   81|     `No free dev server port found in ${CANDIDATE_PORTS[0]}-${CANDIDATE_PORTS[CANDIDATE_PORTS.length - 1]}. ` +
   82|       `Stop an unused dev server or set JETSTREAM_DEV_PORT to choose one explicitly.`,
   83|   );
   84| }
   85| 
   86| const DIM = '\x1b[2m';
   87| const GREEN = '\x1b[32m';
   88| const RESET = '\x1b[0m';
   89| 
   90| function getCurrentBranch(workspaceRoot: string): string | null {
   91|   try {
   92|     return execFileSync('git', ['branch', '--show-current'], { cwd: workspaceRoot, encoding: 'utf8', timeout: 2000 }).trim() || null;
   93|   } catch {
   94|     return null;
   95|   }
   96| }
   97| 
   98| /**
   99|  * Prints which worktree this dev server belongs to and which API it proxies to. Vite's own URL
  100|  * banner only reports the port, which is ambiguous once several worktrees are running at once.
  101|  */
  102| export const devServerBannerPlugin: (apiServerUrl: string) => PluginOption = (apiServerUrl) => {
  103|   return {
  104|     name: 'jetstream-dev-server-banner',
  105|     apply: 'serve',
  106|     configureServer(server) {
  107|       const workspaceRoot = join(import.meta.dirname, '../..');
  108|       const branch = getCurrentBranch(workspaceRoot);
  109|       const worktree = basename(workspaceRoot);
  110| 
  111|       const printUrls = server.printUrls.bind(server);
  112|       server.printUrls = () => {
  113|         printUrls();
  114|         server.config.logger.info(`  ${GREEN}➜${RESET}  ${DIM}Worktree${RESET}: ${worktree}${branch ? ` ${DIM}(${branch})${RESET}` : ''}`);
  115|         server.config.logger.info(`  ${GREEN}➜${RESET}  ${DIM}API${RESET}:      ${apiServerUrl} ${DIM}(proxied)${RESET}`);
  116|       };
  117|     },
  118|   };
  119| };
  120| 
```

### apps/jetstream/vite.config.mts (lines 49 to 120 of 120)
```
   49| }
   50| 
   51| export default defineConfig(async ({ command }) => ({
   52|   plugins: [
   53|     react({
   54|       jsxImportSource: '@emotion/react',
   55|     }),
   56|     baseHrefPlugin(),
   57|     cspNoncePlugin(),
   58|     devServerBannerPlugin(API_SERVER_URL),
   59|     // Sentry plugin must be LAST per docs. Reads SENTRY_AUTH_TOKEN / SENTRY_ORG /
   60|     // SENTRY_PROJECT / SENTRY_URL from env automatically.
   61|     ...(uploadSourcemaps
   62|       ? [
   63|           sentryVitePlugin({
   64|             org: SENTRY_ORG,
   65|             project: SENTRY_PROJECT,
   66|             url: SENTRY_URL,
   67|             authToken: SENTRY_AUTH_TOKEN,
   68|             release: { name: releaseName },
   69|             sourcemaps: { filesToDeleteAfterUpload: ['./dist/apps/jetstream/**/*.map'] },
   70|             telemetry: false,
   71|           }),
   72|         ]
   73|       : []),
   74|   ],
   75| 
   76|   resolve: { tsconfigPaths: true },
   77|   root: import.meta.dirname,
   78|   cacheDir: '../../node_modules/.vite/jetstream',
   79|   envPrefix: 'NX',
   80| 
   81|   server: {
   82|     // Chosen at startup so multiple worktrees can each run a dev server against the shared API.
   83|     // Builds never serve, so don't spend a port scan on them.
   84|     port: command === 'serve' ? await resolveDevServerPort() : undefined,
   85|     // The port above is already known to be free; fail loudly rather than drifting onto 4201/4202,
   86|     // which belong to the desktop client and canvas dev servers.
   87|     strictPort: true,
   88|     host: DEV_SERVER_HOST,
   89|     open: '/app',
   90|     fs: {
   91|       allow: ['../../'],
   92|     },
   93|     proxy: Object.fromEntries(API_SERVER_PROXY_PATHS.map((path) => [path, { target: API_SERVER_URL, secure: false }])),
   94|   },
   95|   base: './',
   96|   build: {
   97|     outDir: '../../dist/apps/jetstream',
   98|     reportCompressedSize: true,
   99|     commonjsOptions: { transformMixedEsModules: true },
  100|     // Put all assets at the root of the app instead of under /assets
  101|     assetsDir: './',
  102|     sourcemap: uploadSourcemaps ? ('hidden' as const) : false,
  103|     emptyOutDir: true,
  104|     rolldownOptions: {},
  105|   },
  106|   test: {
  107|     name: 'jetstream',
  108|     watch: false,
  109|     globals: true,
  110|     environment: 'jsdom',
  111|     include: ['{src,tests,__tests__}/**/*.{test,spec}.{js,mjs,cjs,ts,mts,cts,jsx,tsx}'],
  112|     reporters: ['default'],
  113|     passWithNoTests: true,
  114|     coverage: {
  115|       reportsDirectory: '../../coverage/apps/jetstream',
  116|       provider: 'v8' as const,
  117|     },
  118|   },
  119| }));
  120| 
```

### apps/jetstream/tsconfig.spec.json (lines 1 to 34 of 34)
```
    1| {
    2|   "extends": "./tsconfig.json",
    3|   "compilerOptions": {
    4|     "outDir": "../../dist/out-tsc/apps/jetstream",
    5|     "types": ["vitest/globals", "vitest/importMeta", "vite/client", "node", "vitest"],
    6|     "allowImportingTsExtensions": true,
    7|     "emitDeclarationOnly": true
    8|   },
    9|   "include": [
   10|     "vite.dev-port.mts",
   11|     "vite.plugins.ts",
   12|     "vite.plugins.mts",
   13|     "vite.config.ts",
   14|     "vite.config.mts",
   15|     "vitest.config.ts",
   16|     "vitest.config.mts",
   17|     "__tests__/**/*.spec.ts",
   18|     "src/**/*.test.ts",
   19|     "src/**/*.spec.ts",
   20|     "src/**/*.test.tsx",
   21|     "src/**/*.spec.tsx",
   22|     "src/**/*.test.js",
   23|     "src/**/*.spec.js",
   24|     "src/**/*.test.jsx",
   25|     "src/**/*.spec.jsx",
   26|     "src/**/*.d.ts"
   27|   ],
   28|   "references": [
   29|     {
   30|       "path": "./tsconfig.app.json"
   31|     }
   32|   ]
   33| }
   34| 
```
