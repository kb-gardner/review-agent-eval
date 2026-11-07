# PR pack: tailwindlabs/tailwindcss#20399
Title: Make `createCompatConfig` theme mappings safe to spread when a namespace returns a string
Merge commit: 16e94cbf7f965c5ad697e90e940b5e178efad67c

## Diff
```diff
diff --git a/CHANGELOG.md b/CHANGELOG.md
index 79baa9c65ccb..5a18ebc87600 100644
--- a/CHANGELOG.md
+++ b/CHANGELOG.md
@@ -24,6 +24,7 @@ and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0
 - Detect classes in Ruby percent literals using angle brackets or custom delimiters (e.g. `%w<flex>`, `%w|flex|`), including in Slim and Haml templates ([#20387](https://github.com/tailwindlabs/tailwindcss/pull/20387))
 - Preserve whitespace in `--default(…)` values in custom functional utilities (e.g. `--default(box alphabetic)` no longer becomes `boxalphabetic`) ([#20392](https://github.com/tailwindlabs/tailwindcss/pull/20392))
 - Don't scan gitignored directories (e.g. `node_modules` and `.git`) when the project uses a safelist-style `.gitignore` (e.g. `/*` followed by `!/…` negations) ([#20397](https://github.com/tailwindlabs/tailwindcss/discussions/20397))
+- Ensure root `theme('…')` namespace lookups in JavaScript plugins and config files return the full namespace object instead of the value of its `DEFAULT` key ([#20399](https://github.com/tailwindlabs/tailwindcss/pull/20399))
 
 ## [4.3.3] - 2026-07-16
 
diff --git a/packages/tailwindcss/src/compat/apply-compat-hooks.ts b/packages/tailwindcss/src/compat/apply-compat-hooks.ts
index 6a9f580b6274..036b9d88ed0a 100644
--- a/packages/tailwindcss/src/compat/apply-compat-hooks.ts
+++ b/packages/tailwindcss/src/compat/apply-compat-hooks.ts
@@ -309,6 +309,19 @@ function upgradeToFullPluginSupport({
 
     let resolvedValue = sharedPluginApi.theme(path, undefined)
 
+    // If we're dealing with an object that has the `DEFAULT` key, unwrap it to
+    // the default value first. This happens for namespace root lookups where
+    // the CSS theme defines a bare value, e.g. `--shadow` resolved via
+    // `theme('shadow')`.
+    if (
+      typeof resolvedValue === 'object' &&
+      resolvedValue !== null &&
+      !Array.isArray(resolvedValue) &&
+      'DEFAULT' in resolvedValue
+    ) {
+      resolvedValue = resolvedValue.DEFAULT
+    }
+
     // When a tuple is returned, return the first element
     if (Array.isArray(resolvedValue) && resolvedValue.length === 2) {
       return resolvedValue[0]
@@ -319,16 +332,6 @@ function upgradeToFullPluginSupport({
       return resolvedValue.join(', ')
     }
 
-    // If we're dealing with an object that has the `DEFAULT` key, return the
-    // default value
-    else if (
-      typeof resolvedValue === 'object' &&
-      resolvedValue !== null &&
-      'DEFAULT' in resolvedValue
-    ) {
-      return resolvedValue.DEFAULT
-    }
-
     // Otherwise only allow string values here, objects (and namespace maps)
     // are treated as non-resolved values for the CSS `theme()` function.
     else if (typeof resolvedValue === 'string') {
diff --git a/packages/tailwindcss/src/compat/config/create-compat-config.test.ts b/packages/tailwindcss/src/compat/config/create-compat-config.test.ts
new file mode 100644
index 000000000000..aa1b21cb7e03
--- /dev/null
+++ b/packages/tailwindcss/src/compat/config/create-compat-config.test.ts
@@ -0,0 +1,189 @@
+import { describe, expect, test } from 'vitest'
+import { buildDesignSystem } from '../../design-system'
+import { Theme } from '../../theme'
+import { createCompatConfig } from './create-compat-config'
+import { resolveConfig } from './resolve-config'
+
+function buildCompatConfig(cssValues: Record<string, string>) {
+  let theme = new Theme()
+  for (let [key, value] of Object.entries(cssValues)) {
+    theme.add(key, value)
+  }
+  let design = buildDesignSystem(theme)
+
+  let { resolvedConfig } = resolveConfig(design, [
+    { config: createCompatConfig(design.theme), base: '/root', reference: true, src: undefined },
+  ])
+
+  return resolvedConfig
+}
+
+describe('theme namespace lookups', () => {
+  test('a namespace that only defines a bare value resolves to `{ DEFAULT: … }`, not a string', () => {
+    // When the CSS theme only defines `--text` (a single bare value),
+    // `theme('text', {})` used to return the string `'1rem'`.
+    //
+    // Spreading that string, like the compat config does, produced char-indexed
+    // garbage (`{ '0': '1', '1': 'r', … }`) instead of `{ DEFAULT: '1rem' }`.
+    let config = buildCompatConfig({ '--text': '1rem' })
+
+    expect(config.theme?.fontSize?.DEFAULT).toBe('1rem')
+    expect(config.theme?.fontSize).not.toHaveProperty('0')
+  })
+
+  test('a bare value is kept alongside suffixed values in the same namespace', () => {
+    let config = buildCompatConfig({
+      '--text': '1rem',
+      '--text-sm': '0.875rem',
+    })
+
+    expect(config.theme?.fontSize?.DEFAULT).toBe('1rem')
+    expect(config.theme?.fontSize?.sm).toBe('0.875rem')
+  })
+
+  test('a naive spread of a theme namespace in a user config is safe', () => {
+    let theme = new Theme()
+    theme.add('--text', '1rem')
+    let design = buildDesignSystem(theme)
+
+    let { resolvedConfig } = resolveConfig(design, [
+      {
+        config: {
+          theme: {
+            extend: {
+              fontSize: ({ theme }: any) => ({ ...theme('text', {}) }),
+            },
+          },
+        },
+        base: '/root',
+        reference: true,
+        src: undefined,
+      },
+    ])
+
+    expect(resolvedConfig.theme?.fontSize?.DEFAULT).toBe('1rem')
+    expect(resolvedConfig.theme?.fontSize).not.toHaveProperty('0')
+  })
+
+  test('namespace root lookups resolve to an object, key lookups resolve to the value', () => {
+    let theme = new Theme()
+    theme.add('--text', '1rem')
+    theme.add('--animate-spin', 'spin 1s linear infinite')
+    let design = buildDesignSystem(theme)
+
+    let root: unknown
+    let rootWithDefault: unknown
+    let leaf: unknown
+
+    resolveConfig(design, [
+      {
+        config: {
+          theme: {
+            extend: {
+              fontSize: ({ theme }: any) => {
+                root = theme('text')
+                rootWithDefault = theme('text', {})
+                leaf = theme('animate.spin')
+                return {}
+              },
+            },
+          },
+        },
+        base: '/root',
+        reference: true,
+        src: undefined,
+      },
+    ])
+
+    // A namespace root lookup always resolves to an object, like in v3, even
+    // when the namespace only contains a bare value
+    expect(root).toMatchObject({ DEFAULT: '1rem' })
+    expect(rootWithDefault).toMatchObject({ DEFAULT: '1rem' })
+
+    // Lookups of a specific key resolve to the value itself
+    expect(leaf).toBe('spin 1s linear infinite')
+  })
+
+  test('lookups of a specific key still resolve to the value itself', () => {
+    let theme = new Theme()
+    theme.add('--animate-spin', 'spin 1s linear infinite')
+    let design = buildDesignSystem(theme)
+
+    let { resolvedConfig } = resolveConfig(design, [
+      {
+        config: {
+          theme: {
+            extend: {
+              animation: ({ theme }: any) => ({ spin: theme('animate.spin') }),
+            },
+          },
+        },
+        base: '/root',
+        reference: true,
+        src: undefined,
+      },
+    ])
+
+    expect(resolvedConfig.theme?.animation?.spin).toBe('spin 1s linear infinite')
+  })
+})
+
+describe('createCompatConfig namespace mappings', () => {
+  test('fontSize maps from CSS text namespace', () => {
+    let config = buildCompatConfig({ '--text-base': '1rem' })
+    expect(config.theme?.fontSize?.base).toBe('1rem')
+  })
+
+  test('boxShadow maps from CSS shadow namespace', () => {
+    let config = buildCompatConfig({ '--shadow-md': '0 4px 6px #000' })
+    expect(config.theme?.boxShadow?.md).toBe('0 4px 6px #000')
+  })
+
+  test('animation maps from CSS animate namespace', () => {
+    let config = buildCompatConfig({ '--animate-spin': 'spin 1s linear infinite' })
+    expect(config.theme?.animation?.spin).toBe('spin 1s linear infinite')
+  })
+
+  test('aspectRatio maps from CSS aspect namespace', () => {
+    let config = buildCompatConfig({ '--aspect-square': '1 / 1' })
+    expect(config.theme?.aspectRatio?.square).toBe('1 / 1')
+  })
+
+  test('borderRadius maps from CSS radius namespace', () => {
+    let config = buildCompatConfig({ '--radius-lg': '0.5rem' })
+    expect(config.theme?.borderRadius?.lg).toBe('0.5rem')
+  })
+
+  test('screens maps from CSS breakpoint namespace', () => {
+    let config = buildCompatConfig({ '--breakpoint-sm': '640px' })
+    expect(config.theme?.screens?.sm).toBe('640px')
+  })
+
+  test('letterSpacing maps from CSS tracking namespace', () => {
+    let config = buildCompatConfig({ '--tracking-wide': '0.025em' })
+    expect(config.theme?.letterSpacing?.wide).toBe('0.025em')
+  })
+
+  test('lineHeight maps from CSS leading namespace', () => {
+    let config = buildCompatConfig({ '--leading-relaxed': '1.75' })
+    expect(config.theme?.lineHeight?.relaxed).toBe('1.75')
+  })
+
+  test('maxWidth maps from the container namespace in the default theme', () => {
+    let config = buildCompatConfig({})
+    // The default theme has container.sm = '24rem'
+    expect(config.theme?.maxWidth?.sm).toBe('24rem')
+  })
+
+  test('transitionDuration gets DEFAULT from --default-transition-duration', () => {
+    let config = buildCompatConfig({ '--default-transition-duration': '150ms' })
+    expect(config.theme?.transitionDuration?.DEFAULT).toBe('150ms')
+  })
+
+  test('transitionTimingFunction gets DEFAULT from --default-transition-timing-function', () => {
+    let config = buildCompatConfig({
+      '--default-transition-timing-function': 'cubic-bezier(0.4, 0, 0.2, 1)',
+    })
+    expect(config.theme?.transitionTimingFunction?.DEFAULT).toBe('cubic-bezier(0.4, 0, 0.2, 1)')
+  })
+})
diff --git a/packages/tailwindcss/src/compat/plugin-functions.ts b/packages/tailwindcss/src/compat/plugin-functions.ts
index ee795c40f16d..bbd5fac466a7 100644
--- a/packages/tailwindcss/src/compat/plugin-functions.ts
+++ b/packages/tailwindcss/src/compat/plugin-functions.ts
@@ -108,7 +108,12 @@ export function createThemeFn(
       // ```
       //
       // Prefer `DEFAULT` instead of exposing the object to plugin code.
+      //
+      // This only applies to lookups of a specific key (e.g. `colors.foo`). A
+      // namespace root lookup (e.g. `theme('shadow')`) resolves to the whole
+      // namespace as an object, like in v3.
       if (
+        keypath.length > 1 &&
         cssValue !== null &&
         typeof cssValue === 'object' &&
         !Array.isArray(cssValue) &&
@@ -225,7 +230,12 @@ function readFromCss(
   // The request looked like `theme('animation.spin')` and was turned into a
   // lookup for `--animation-spin-*` which had only one entry which means it
   // should be returned directly.
-  if ('DEFAULT' in obj && Object.keys(obj).length === 1) {
+  //
+  // This only applies to lookups of a specific key (`path.length > 1`). A
+  // namespace root lookup like `theme('shadow')` resolves to the whole
+  // namespace as an object, like in v3, so it must keep the object shape (`{
+  // DEFAULT: … }`).
+  if (path.length > 1 && 'DEFAULT' in obj && Object.keys(obj).length === 1) {
     return [obj.DEFAULT as any, optionsObj.DEFAULT ?? ThemeOptions.NONE] as const
   }
 

```

## Touched files at the merge commit (window of up to 200 lines around the first changed hunk)

### packages/tailwindcss/src/compat/config/create-compat-config.test.ts (lines 1 to 190 of 190)
```
    1| import { describe, expect, test } from 'vitest'
    2| import { buildDesignSystem } from '../../design-system'
    3| import { Theme } from '../../theme'
    4| import { createCompatConfig } from './create-compat-config'
    5| import { resolveConfig } from './resolve-config'
    6| 
    7| function buildCompatConfig(cssValues: Record<string, string>) {
    8|   let theme = new Theme()
    9|   for (let [key, value] of Object.entries(cssValues)) {
   10|     theme.add(key, value)
   11|   }
   12|   let design = buildDesignSystem(theme)
   13| 
   14|   let { resolvedConfig } = resolveConfig(design, [
   15|     { config: createCompatConfig(design.theme), base: '/root', reference: true, src: undefined },
   16|   ])
   17| 
   18|   return resolvedConfig
   19| }
   20| 
   21| describe('theme namespace lookups', () => {
   22|   test('a namespace that only defines a bare value resolves to `{ DEFAULT: … }`, not a string', () => {
   23|     // When the CSS theme only defines `--text` (a single bare value),
   24|     // `theme('text', {})` used to return the string `'1rem'`.
   25|     //
   26|     // Spreading that string, like the compat config does, produced char-indexed
   27|     // garbage (`{ '0': '1', '1': 'r', … }`) instead of `{ DEFAULT: '1rem' }`.
   28|     let config = buildCompatConfig({ '--text': '1rem' })
   29| 
   30|     expect(config.theme?.fontSize?.DEFAULT).toBe('1rem')
   31|     expect(config.theme?.fontSize).not.toHaveProperty('0')
   32|   })
   33| 
   34|   test('a bare value is kept alongside suffixed values in the same namespace', () => {
   35|     let config = buildCompatConfig({
   36|       '--text': '1rem',
   37|       '--text-sm': '0.875rem',
   38|     })
   39| 
   40|     expect(config.theme?.fontSize?.DEFAULT).toBe('1rem')
   41|     expect(config.theme?.fontSize?.sm).toBe('0.875rem')
   42|   })
   43| 
   44|   test('a naive spread of a theme namespace in a user config is safe', () => {
   45|     let theme = new Theme()
   46|     theme.add('--text', '1rem')
   47|     let design = buildDesignSystem(theme)
   48| 
   49|     let { resolvedConfig } = resolveConfig(design, [
   50|       {
   51|         config: {
   52|           theme: {
   53|             extend: {
   54|               fontSize: ({ theme }: any) => ({ ...theme('text', {}) }),
   55|             },
   56|           },
   57|         },
   58|         base: '/root',
   59|         reference: true,
   60|         src: undefined,
   61|       },
   62|     ])
   63| 
   64|     expect(resolvedConfig.theme?.fontSize?.DEFAULT).toBe('1rem')
   65|     expect(resolvedConfig.theme?.fontSize).not.toHaveProperty('0')
   66|   })
   67| 
   68|   test('namespace root lookups resolve to an object, key lookups resolve to the value', () => {
   69|     let theme = new Theme()
   70|     theme.add('--text', '1rem')
   71|     theme.add('--animate-spin', 'spin 1s linear infinite')
   72|     let design = buildDesignSystem(theme)
   73| 
   74|     let root: unknown
   75|     let rootWithDefault: unknown
   76|     let leaf: unknown
   77| 
   78|     resolveConfig(design, [
   79|       {
   80|         config: {
   81|           theme: {
   82|             extend: {
   83|               fontSize: ({ theme }: any) => {
   84|                 root = theme('text')
   85|                 rootWithDefault = theme('text', {})
   86|                 leaf = theme('animate.spin')
   87|                 return {}
   88|               },
   89|             },
   90|           },
   91|         },
   92|         base: '/root',
   93|         reference: true,
   94|         src: undefined,
   95|       },
   96|     ])
   97| 
   98|     // A namespace root lookup always resolves to an object, like in v3, even
   99|     // when the namespace only contains a bare value
  100|     expect(root).toMatchObject({ DEFAULT: '1rem' })
  101|     expect(rootWithDefault).toMatchObject({ DEFAULT: '1rem' })
  102| 
  103|     // Lookups of a specific key resolve to the value itself
  104|     expect(leaf).toBe('spin 1s linear infinite')
  105|   })
  106| 
  107|   test('lookups of a specific key still resolve to the value itself', () => {
  108|     let theme = new Theme()
  109|     theme.add('--animate-spin', 'spin 1s linear infinite')
  110|     let design = buildDesignSystem(theme)
  111| 
  112|     let { resolvedConfig } = resolveConfig(design, [
  113|       {
  114|         config: {
  115|           theme: {
  116|             extend: {
  117|               animation: ({ theme }: any) => ({ spin: theme('animate.spin') }),
  118|             },
  119|           },
  120|         },
  121|         base: '/root',
  122|         reference: true,
  123|         src: undefined,
  124|       },
  125|     ])
  126| 
  127|     expect(resolvedConfig.theme?.animation?.spin).toBe('spin 1s linear infinite')
  128|   })
  129| })
  130| 
  131| describe('createCompatConfig namespace mappings', () => {
  132|   test('fontSize maps from CSS text namespace', () => {
  133|     let config = buildCompatConfig({ '--text-base': '1rem' })
  134|     expect(config.theme?.fontSize?.base).toBe('1rem')
  135|   })
  136| 
  137|   test('boxShadow maps from CSS shadow namespace', () => {
  138|     let config = buildCompatConfig({ '--shadow-md': '0 4px 6px #000' })
  139|     expect(config.theme?.boxShadow?.md).toBe('0 4px 6px #000')
  140|   })
  141| 
  142|   test('animation maps from CSS animate namespace', () => {
  143|     let config = buildCompatConfig({ '--animate-spin': 'spin 1s linear infinite' })
  144|     expect(config.theme?.animation?.spin).toBe('spin 1s linear infinite')
  145|   })
  146| 
  147|   test('aspectRatio maps from CSS aspect namespace', () => {
  148|     let config = buildCompatConfig({ '--aspect-square': '1 / 1' })
  149|     expect(config.theme?.aspectRatio?.square).toBe('1 / 1')
  150|   })
  151| 
  152|   test('borderRadius maps from CSS radius namespace', () => {
  153|     let config = buildCompatConfig({ '--radius-lg': '0.5rem' })
  154|     expect(config.theme?.borderRadius?.lg).toBe('0.5rem')
  155|   })
  156| 
  157|   test('screens maps from CSS breakpoint namespace', () => {
  158|     let config = buildCompatConfig({ '--breakpoint-sm': '640px' })
  159|     expect(config.theme?.screens?.sm).toBe('640px')
  160|   })
  161| 
  162|   test('letterSpacing maps from CSS tracking namespace', () => {
  163|     let config = buildCompatConfig({ '--tracking-wide': '0.025em' })
  164|     expect(config.theme?.letterSpacing?.wide).toBe('0.025em')
  165|   })
  166| 
  167|   test('lineHeight maps from CSS leading namespace', () => {
  168|     let config = buildCompatConfig({ '--leading-relaxed': '1.75' })
  169|     expect(config.theme?.lineHeight?.relaxed).toBe('1.75')
  170|   })
  171| 
  172|   test('maxWidth maps from the container namespace in the default theme', () => {
  173|     let config = buildCompatConfig({})
  174|     // The default theme has container.sm = '24rem'
  175|     expect(config.theme?.maxWidth?.sm).toBe('24rem')
  176|   })
  177| 
  178|   test('transitionDuration gets DEFAULT from --default-transition-duration', () => {
  179|     let config = buildCompatConfig({ '--default-transition-duration': '150ms' })
  180|     expect(config.theme?.transitionDuration?.DEFAULT).toBe('150ms')
  181|   })
  182| 
  183|   test('transitionTimingFunction gets DEFAULT from --default-transition-timing-function', () => {
  184|     let config = buildCompatConfig({
  185|       '--default-transition-timing-function': 'cubic-bezier(0.4, 0, 0.2, 1)',
  186|     })
  187|     expect(config.theme?.transitionTimingFunction?.DEFAULT).toBe('cubic-bezier(0.4, 0, 0.2, 1)')
  188|   })
  189| })
  190| 
```

### packages/tailwindcss/src/compat/apply-compat-hooks.ts (lines 250 to 427 of 427)
```
  250|         base: detail.base,
  251|         reference: detail.reference,
  252|         src: detail.src,
  253|       }
  254|     }
  255| 
  256|     if ('__isOptionsFunction' in detail.plugin) {
  257|       return {
  258|         config: { plugins: [detail.plugin(detail.options)] },
  259|         base: detail.base,
  260|         reference: detail.reference,
  261|         src: detail.src,
  262|       }
  263|     }
  264| 
  265|     throw new Error(`The plugin "${detail.path}" does not accept options`)
  266|   })
  267| 
  268|   let userConfig = [...pluginConfigs, ...configs]
  269| 
  270|   let { resolvedConfig } = resolveConfig(designSystem, [
  271|     { config: createCompatConfig(designSystem.theme), base, reference: true, src: undefined },
  272|     ...userConfig,
  273|     { config: { plugins: [darkModePlugin] }, base, reference: true, src: undefined },
  274|   ])
  275|   let { resolvedConfig: resolvedUserConfig, replacedThemeKeys } = resolveConfig(
  276|     designSystem,
  277|     userConfig,
  278|   )
  279| 
  280|   let pluginApiConfig = {
  281|     designSystem,
  282|     ast,
  283|     resolvedConfig,
  284|     featuresRef: {
  285|       set current(value: number) {
  286|         features |= value
  287|       },
  288|     },
  289|   }
  290| 
  291|   let sharedPluginApi = buildPluginApi({
  292|     ...pluginApiConfig,
  293|     referenceMode: false,
  294|     src: undefined,
  295|   })
  296| 
  297|   // Replace `resolveThemeValue` with a version that is backwards compatible
  298|   // with dot-notation but also aware of any JS theme configurations registered
  299|   // by plugins or JS config files. This is significantly slower than just
  300|   // upgrading dot-notation keys so we only use this version if plugins or
  301|   // config files are actually being used. In the future we may want to optimize
  302|   // this further by only doing this if plugins or config files _actually_
  303|   // registered JS config objects.
  304|   let defaultResolveThemeValue = designSystem.resolveThemeValue
  305|   designSystem.resolveThemeValue = function resolveThemeValue(path: string, forceInline?: boolean) {
  306|     if (path[0] === '-' && path[1] === '-') {
  307|       return defaultResolveThemeValue(path, forceInline)
  308|     }
  309| 
  310|     let resolvedValue = sharedPluginApi.theme(path, undefined)
  311| 
  312|     // If we're dealing with an object that has the `DEFAULT` key, unwrap it to
  313|     // the default value first. This happens for namespace root lookups where
  314|     // the CSS theme defines a bare value, e.g. `--shadow` resolved via
  315|     // `theme('shadow')`.
  316|     if (
  317|       typeof resolvedValue === 'object' &&
  318|       resolvedValue !== null &&
  319|       !Array.isArray(resolvedValue) &&
  320|       'DEFAULT' in resolvedValue
  321|     ) {
  322|       resolvedValue = resolvedValue.DEFAULT
  323|     }
  324| 
  325|     // When a tuple is returned, return the first element
  326|     if (Array.isArray(resolvedValue) && resolvedValue.length === 2) {
  327|       return resolvedValue[0]
  328|     }
  329| 
  330|     // Arrays get serialized into a comma-separated lists
  331|     else if (Array.isArray(resolvedValue)) {
  332|       return resolvedValue.join(', ')
  333|     }
  334| 
  335|     // Otherwise only allow string values here, objects (and namespace maps)
  336|     // are treated as non-resolved values for the CSS `theme()` function.
  337|     else if (typeof resolvedValue === 'string') {
  338|       return resolvedValue
  339|     }
  340|   }
  341| 
  342|   for (let { handler, reference, src } of resolvedConfig.plugins) {
  343|     // Each plugin gets its own instance of the plugin API because nodes added
  344|     // to the AST may need to point to the `@config` or `@plugin` that they
  345|     // originated from
  346|     let api = buildPluginApi({
  347|       ...pluginApiConfig,
  348|       referenceMode: reference ?? false,
  349|       src,
  350|     })
  351| 
  352|     handler(api)
  353|   }
  354| 
  355|   // Merge the user-configured theme keys into the design system. The compat
  356|   // config would otherwise expand into namespaces like `background-color` which
  357|   // core utilities already read from.
  358|   applyConfigToTheme(designSystem, resolvedUserConfig, replacedThemeKeys)
  359|   applyKeyframesToTheme(designSystem, resolvedUserConfig)
  360| 
  361|   registerThemeVariantOverrides(resolvedUserConfig, designSystem)
  362|   registerScreensConfig(resolvedUserConfig, designSystem)
  363|   registerContainerCompat(resolvedUserConfig, designSystem)
  364| 
  365|   // If a prefix has already been set in CSS don't override it
  366|   if (!designSystem.theme.prefix && resolvedConfig.prefix) {
  367|     if (resolvedConfig.prefix.endsWith('-')) {
  368|       resolvedConfig.prefix = resolvedConfig.prefix.slice(0, -1)
  369| 
  370|       console.warn(
  371|         `The prefix "${resolvedConfig.prefix}" is invalid. Prefixes must be lowercase ASCII letters (a-z) only and is written as a variant before all utilities. We have fixed up the prefix for you. Remove the trailing \`-\` to silence this warning.`,
  372|       )
  373|     }
  374| 
  375|     if (!IS_VALID_PREFIX.test(resolvedConfig.prefix)) {
  376|       throw new Error(
  377|         `The prefix "${resolvedConfig.prefix}" is invalid. Prefixes must be lowercase ASCII letters (a-z) only.`,
  378|       )
  379|     }
  380| 
  381|     designSystem.theme.prefix = resolvedConfig.prefix
  382|   }
  383| 
  384|   // If an important strategy has already been set in CSS don't override it
  385|   if (!designSystem.important && resolvedConfig.important === true) {
  386|     designSystem.important = true
  387|   }
  388| 
  389|   if (typeof resolvedConfig.important === 'string') {
  390|     let wrappingSelector = resolvedConfig.important
  391| 
  392|     walk(ast, (node, _ctx) => {
  393|       if (node.kind !== 'at-rule') return
  394|       if (node.name !== '@tailwind' || node.params !== 'utilities') return
  395| 
  396|       let ctx = cssContext(_ctx)
  397| 
  398|       // The AST node was already manually wrapped so there's nothing to do
  399|       if (ctx.parent?.kind === 'rule' && ctx.parent.selector === wrappingSelector) {
  400|         return WalkAction.Stop
  401|       }
  402| 
  403|       return WalkAction.ReplaceStop(styleRule(wrappingSelector, [node]))
  404|     })
  405|   }
  406| 
  407|   for (let candidate of resolvedConfig.blocklist) {
  408|     designSystem.invalidCandidates.add(candidate)
  409|   }
  410| 
  411|   for (let file of resolvedConfig.content.files) {
  412|     if ('raw' in file) {
  413|       throw new Error(
  414|         `Error in the config file/plugin/preset. The \`content\` key contains a \`raw\` entry:\n\n${JSON.stringify(file, null, 2)}\n\nThis feature is not currently supported.`,
  415|       )
  416|     }
  417| 
  418|     let negated = false
  419|     if (file.pattern[0] == '!') {
  420|       negated = true
  421|       file.pattern = file.pattern.slice(1)
  422|     }
  423|     sources.push({ ...file, negated })
  424|   }
  425|   return features
  426| }
  427| 
```

### packages/tailwindcss/src/compat/plugin-functions.ts (lines 49 to 248 of 282)
```
   49|           // value. Ideally we use `structuredClone` here, but it's not possible
   50|           // because it can contain functions.
   51|           deepMerge({}, [configValue], (_, b) => b)
   52| 
   53|         // There is no `cssValue`, which means we can back-fill it with values
   54|         // from the `configValue`.
   55|         if (cssValue === null && Object.hasOwn(configValue, '__CSS_VALUES__')) {
   56|           let localCssValue: Record<string, unknown> = {}
   57|           for (let key in configValue.__CSS_VALUES__) {
   58|             localCssValue[key] = configValue[key]
   59|             delete configValueCopy[key]
   60|           }
   61|           cssValue = localCssValue
   62|         }
   63| 
   64|         for (let key in cssValue) {
   65|           if (key === '__CSS_VALUES__') continue
   66| 
   67|           // If the value is coming from a default source (`@theme default`),
   68|           // then we keep the value from the JS config (which is also a
   69|           // default source, but wins over the built-in defaults).
   70|           if (
   71|             configValue?.__CSS_VALUES__?.[key] & ThemeOptions.DEFAULT &&
   72|             get(configValueCopy, key.split('-')) !== undefined
   73|           ) {
   74|             continue
   75|           }
   76| 
   77|           // CSS values from `@theme` win over values from the config
   78|           configValueCopy[unescape(key)] = cssValue[key]
   79|         }
   80| 
   81|         return configValueCopy
   82|       }
   83| 
   84|       // Handle the tuple case
   85|       if (Array.isArray(cssValue) && Array.isArray(options) && Array.isArray(configValue)) {
   86|         let base = cssValue[0]
   87|         let extra = cssValue[1]
   88| 
   89|         // Values from the config overwrite any default values from the CSS theme
   90|         if (options[0] & ThemeOptions.DEFAULT) {
   91|           base = configValue[0] ?? base
   92|         }
   93| 
   94|         for (let key of Object.keys(extra)) {
   95|           if (options[1][key] & ThemeOptions.DEFAULT) {
   96|             extra[key] = configValue[1][key] ?? extra[key]
   97|           }
   98|         }
   99| 
  100|         return [base, extra]
  101|       }
  102| 
  103|       // If `--color-foo` and `--color-foo-bar` are both defined, `colors.foo`
  104|       // produces a synthetic object:
  105|       //
  106|       // ```ts
  107|       // { DEFAULT: 'red', bar: 'blue', __CSS_VALUES__: { DEFAULT: 0, bar: 0 } }
  108|       // ```
  109|       //
  110|       // Prefer `DEFAULT` instead of exposing the object to plugin code.
  111|       //
  112|       // This only applies to lookups of a specific key (e.g. `colors.foo`). A
  113|       // namespace root lookup (e.g. `theme('shadow')`) resolves to the whole
  114|       // namespace as an object, like in v3.
  115|       if (
  116|         keypath.length > 1 &&
  117|         cssValue !== null &&
  118|         typeof cssValue === 'object' &&
  119|         !Array.isArray(cssValue) &&
  120|         'DEFAULT' in cssValue
  121|       ) {
  122|         return cssValue.DEFAULT
  123|       }
  124| 
  125|       // Values from CSS take precedence over values from the config
  126|       return cssValue ?? configValue
  127|     })()
  128| 
  129|     // Apply the opacity modifier if present
  130|     if (modifier && typeof resolvedValue === 'string') {
  131|       resolvedValue = withAlpha(resolvedValue, modifier)
  132|     }
  133| 
  134|     return resolvedValue ?? defaultValue
  135|   }
  136| }
  137| 
  138| function readFromCss(
  139|   theme: Theme,
  140|   path: string[],
  141| ):
  142|   | [value: string | null | Record<string, unknown>, options: number]
  143|   | [value: Record<string, unknown>, options: Record<string, number>] {
  144|   // `--color-red-500` should resolve to the theme variable directly, no look up
  145|   // and handling of nested objects is required.
  146|   if (path.length === 1 && path[0].startsWith('--')) {
  147|     return [theme.get([path[0] as ThemeKey]), theme.getOptions(path[0])] as const
  148|   }
  149| 
  150|   type ThemeValue =
  151|     // A normal string value
  152|     | string
  153| 
  154|     // A nested tuple with additional data
  155|     | [main: string, extra: Record<string, string>]
  156| 
  157|   let themeKey = keyPathToCssProperty(path)
  158| 
  159|   let map = new Map<string | null, ThemeValue>()
  160|   let nested = new DefaultMap<string | null, Map<string, [value: string, options: number]>>(
  161|     () => new Map(),
  162|   )
  163| 
  164|   let ns = theme.namespace(`--${themeKey}`)
  165|   if (ns.size === 0) {
  166|     return [null, ThemeOptions.NONE]
  167|   }
  168| 
  169|   let options = new Map()
  170| 
  171|   for (let [key, value] of ns) {
  172|     // Non-nested values can be set directly
  173|     if (!key || !key.includes('--')) {
  174|       map.set(key, value)
  175|       options.set(key, theme.getOptions(!key ? `--${themeKey}` : `--${themeKey}-${key}`))
  176|       continue
  177|     }
  178| 
  179|     // Nested values are stored separately
  180|     let nestedIndex = key.indexOf('--')
  181| 
  182|     let mainKey = key.slice(0, nestedIndex)
  183|     let nestedKey = key.slice(nestedIndex + 2)
  184| 
  185|     // Make `nestedKey` camel case:
  186|     nestedKey = nestedKey.replace(/-([a-z])/g, (_, a) => a.toUpperCase())
  187| 
  188|     nested
  189|       .get(mainKey === '' ? null : mainKey)
  190|       .set(nestedKey, [value, theme.getOptions(`--${themeKey}${key}`)])
  191|   }
  192| 
  193|   let baseOptions = theme.getOptions(`--${themeKey}`)
  194|   for (let [key, extra] of nested) {
  195|     let value = map.get(key)
  196|     if (typeof value !== 'string') continue
  197| 
  198|     let extraObj: Record<string, string> = {}
  199|     let extraOptionsObj: Record<string, number> = {}
  200| 
  201|     for (let [nestedKey, [nestedValue, nestedOptions]] of extra) {
  202|       extraObj[nestedKey] = nestedValue
  203|       extraOptionsObj[nestedKey] = nestedOptions
  204|     }
  205| 
  206|     map.set(key, [value, extraObj])
  207|     options.set(key, [baseOptions, extraOptionsObj])
  208|   }
  209| 
  210|   // We have to turn the map into object-like structure for v3 compatibility
  211|   let obj: Record<string, unknown> = {}
  212|   let optionsObj: Record<string, number> = {}
  213| 
  214|   for (let [key, value] of map) {
  215|     set(obj, [key ?? 'DEFAULT'], value)
  216|   }
  217| 
  218|   for (let [key, value] of options) {
  219|     set(optionsObj, [key ?? 'DEFAULT'], value)
  220|   }
  221| 
  222|   // If the request looked like `theme('animation.DEFAULT')` it would have been
  223|   // turned into a lookup for `--animation-*` so we should extract the value for
  224|   // the `DEFAULT` key from the list of possible values. If there is no
  225|   // `DEFAULT` in the list, there is no match so return `null`.
  226|   if (path[path.length - 1] === 'DEFAULT') {
  227|     return [(obj?.DEFAULT ?? null) as any, optionsObj.DEFAULT ?? ThemeOptions.NONE] as const
  228|   }
  229| 
  230|   // The request looked like `theme('animation.spin')` and was turned into a
  231|   // lookup for `--animation-spin-*` which had only one entry which means it
  232|   // should be returned directly.
  233|   //
  234|   // This only applies to lookups of a specific key (`path.length > 1`). A
  235|   // namespace root lookup like `theme('shadow')` resolves to the whole
  236|   // namespace as an object, like in v3, so it must keep the object shape (`{
  237|   // DEFAULT: … }`).
  238|   if (path.length > 1 && 'DEFAULT' in obj && Object.keys(obj).length === 1) {
  239|     return [obj.DEFAULT as any, optionsObj.DEFAULT ?? ThemeOptions.NONE] as const
  240|   }
  241| 
  242|   // Attach the CSS values to the object for later use. This object could be
  243|   // mutated by the user so we want to keep the original CSS values around.
  244|   obj.__CSS_VALUES__ = optionsObj
  245| 
  246|   return [obj, optionsObj] as const
  247| }
  248| 
```

### CHANGELOG.md (lines 1 to 200 of 4422)
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
   23| - Ensure `@tailwindcss/oxide` falls back to WASM on platforms without native bindings ([#20383](https://github.com/tailwindlabs/tailwindcss/pull/20383))
   24| - Detect classes in Ruby percent literals using angle brackets or custom delimiters (e.g. `%w<flex>`, `%w|flex|`), including in Slim and Haml templates ([#20387](https://github.com/tailwindlabs/tailwindcss/pull/20387))
   25| - Preserve whitespace in `--default(…)` values in custom functional utilities (e.g. `--default(box alphabetic)` no longer becomes `boxalphabetic`) ([#20392](https://github.com/tailwindlabs/tailwindcss/pull/20392))
   26| - Don't scan gitignored directories (e.g. `node_modules` and `.git`) when the project uses a safelist-style `.gitignore` (e.g. `/*` followed by `!/…` negations) ([#20397](https://github.com/tailwindlabs/tailwindcss/discussions/20397))
   27| - Ensure root `theme('…')` namespace lookups in JavaScript plugins and config files return the full namespace object instead of the value of its `DEFAULT` key ([#20399](https://github.com/tailwindlabs/tailwindcss/pull/20399))
   28| 
   29| ## [4.3.3] - 2026-07-16
   30| 
   31| ### Fixed
   32| 
   33| - Support `--watch --poll[=ms]` in `@tailwindcss/cli` when filesystem events are unreliable or unavailable ([#20297](https://github.com/tailwindlabs/tailwindcss/pull/20297))
   34| - Canonicalization: match arbitrary hex colors against theme colors case-insensitively (e.g. `bg-[#fff]` and `bg-[#FFF]` → `bg-white`) ([#20298](https://github.com/tailwindlabs/tailwindcss/pull/20298))
   35| - Prevent Preflight from overriding Firefox's native `iframe:focus-visible` outline styles ([#20292](https://github.com/tailwindlabs/tailwindcss/pull/20292))
   36| - Ensure `theme('colors.foo')` in JS plugins resolves correctly when both `--color-foo` and `--color-foo-bar` exist ([#20299](https://github.com/tailwindlabs/tailwindcss/pull/20299))
   37| - Ensure fractional opacity modifiers work with named shadow sizes like `shadow-sm/12.5`, `text-shadow-sm/12.5`, `drop-shadow-sm/12.5`, and `inset-shadow-sm/12.5` ([#20302](https://github.com/tailwindlabs/tailwindcss/pull/20302))
   38| - Parse selectors like `[data-foo]div` as two selectors instead of one ([#20303](https://github.com/tailwindlabs/tailwindcss/pull/20303))
   39| - Ensure `@tailwindcss/postcss` rebuilds when a preprocessor like Sass changes the input CSS without changing the input file on disk ([#20310](https://github.com/tailwindlabs/tailwindcss/pull/20310))
   40| - Ensure CSS nesting is handled even when Lightning CSS isn't run, such as in `@tailwindcss/browser` and Tailwind Play ([#20124](https://github.com/tailwindlabs/tailwindcss/pull/20124))
   41| - Prevent achromatic theme colors from shifting hue when mixed in polar color spaces like `oklch` ([#20314](https://github.com/tailwindlabs/tailwindcss/pull/20314))
   42| - Ensure `--spacing(0)` is optimized to `0px` instead of `0` so it remains a `<length>` when used in `calc(…)` ([#20319](https://github.com/tailwindlabs/tailwindcss/pull/20319))
   43| - Load `@parcel/watcher` only when needed in `@tailwindcss/cli --watch` mode, so one-off builds and `--watch --poll` work when `@parcel/watcher` can't be loaded ([#20325](https://github.com/tailwindlabs/tailwindcss/pull/20325))
   44| - Use explicit platform fonts instead of `system-ui` and `ui-sans-serif` so CJK text respects the page's `lang` attribute on Windows ([#20318](https://github.com/tailwindlabs/tailwindcss/pull/20318))
   45| - Prevent `@tailwindcss/upgrade` from rewriting ignored files when run from a subdirectory ([#20329](https://github.com/tailwindlabs/tailwindcss/pull/20329))
   46| - Ensure earlier `@source` rules pointing to nested files are scanned when later `@source` rules point to files in parent folders ([#20335](https://github.com/tailwindlabs/tailwindcss/pull/20335))
   47| - Prevent `@tailwindcss/vite` from triggering full page reloads when scanned files are processed by Vite but haven't been loaded as modules yet ([#20336](https://github.com/tailwindlabs/tailwindcss/pull/20336))
   48| 
   49| ## [4.3.2] - 2026-06-26
   50| 
   51| ### Fixed
   52| 
   53| - Support bare spacing values for `auto-rows-*` and `auto-cols-*` utilities (e.g. `auto-rows-12` and `auto-cols-16`) ([#20229](https://github.com/tailwindlabs/tailwindcss/pull/20229))
   54| - Prevent `@tailwindcss/cli` in `--watch` mode from crashing on Windows when `@source` points to a directory that doesn't exist ([#20242](https://github.com/tailwindlabs/tailwindcss/pull/20242))
   55| - Prevent `@tailwindcss/vite` from crashing in Deno v2.8.x when `context.parentURL` is not a valid URL ([#20245](https://github.com/tailwindlabs/tailwindcss/pull/20245))
   56| - Ensure `@tailwindcss/cli` in `--watch` mode rebuilds when the input CSS file changes in an ignored directory ([#20246](https://github.com/tailwindlabs/tailwindcss/pull/20246))
   57| - Allow `@variant` rules used in `addBase(…)` to use custom variants defined later ([#20247](https://github.com/tailwindlabs/tailwindcss/pull/20247))
   58| - Prevent `@tailwindcss/vite` from crashing during HMR when scanned files or directories are deleted ([#20259](https://github.com/tailwindlabs/tailwindcss/pull/20259))
   59| - Generate `font-size` instead of `color` declarations for `text-[--spacing(…)]` ([#20260](https://github.com/tailwindlabs/tailwindcss/pull/20260))
   60| - Prevent `@source` patterns from scanning unrelated sibling files and folders ([#20263](https://github.com/tailwindlabs/tailwindcss/pull/20263))
   61| - Extract class candidates adjacent to Template Toolkit delimiters like `%]…[%` in `.tt`, `.tt2`, and `.tx` files ([#20269](https://github.com/tailwindlabs/tailwindcss/pull/20269))
   62| - Extract class candidates from conditional Maud syntax like `p.text-black[condition]` ([#20269](https://github.com/tailwindlabs/tailwindcss/pull/20269))
   63| - Prevent `@position-try` rules from triggering unknown at-rule warnings when optimizing CSS ([#20277](https://github.com/tailwindlabs/tailwindcss/pull/20277))
   64| - Support class suggestions for named opacity modifiers from `--opacity` theme values ([#20287](https://github.com/tailwindlabs/tailwindcss/pull/20287))
   65| - Prevent type errors in `@tailwindcss/postcss` when used with newer PostCSS patch releases ([#20289](https://github.com/tailwindlabs/tailwindcss/pull/20289))
   66| 
   67| ## [4.3.1] - 2026-06-12
   68| 
   69| ### Added
   70| 
   71| - Add `--silent` option to suppress output in `@tailwindcss/cli` ([#20100](https://github.com/tailwindlabs/tailwindcss/pull/20100))
   72| 
   73| ### Fixed
   74| 
   75| - Remove deprecation warnings by using `Module#registerHooks` instead of `Module#register` on Node 26+ ([#20028](https://github.com/tailwindlabs/tailwindcss/pull/20028))
   76| - Canonicalization: don't crash when plugin utilities throw for unsupported values ([#20052](https://github.com/tailwindlabs/tailwindcss/pull/20052))
   77| - Allow `@apply` to be used with CSS mixins ([#19427](https://github.com/tailwindlabs/tailwindcss/pull/19427))
   78| - Ensure `not-*` correctly negates `@container` queries, including `style(…)` queries ([#20059](https://github.com/tailwindlabs/tailwindcss/pull/20059))
   79| - Ensure `drop-shadow-*` color utilities work with custom shadow values containing `calc(…)` ([#20080](https://github.com/tailwindlabs/tailwindcss/pull/20080))
   80| - Fix 'Sourcemap is likely to be incorrect' warnings when using `@tailwindcss/vite` ([#20103](https://github.com/tailwindlabs/tailwindcss/pull/20103))
   81| - Ensure `@tailwindcss/webpack` can be installed in Rspack projects without requiring `webpack` as a peer dependency ([#20027](https://github.com/tailwindlabs/tailwindcss/pull/20027))
   82| - Canonicalization: don't suggest invalid `calc(…)` expressions (e.g. `px-[calc(1rem+0px)]` → `px-[calc(1rem+0)]`) ([#20127](https://github.com/tailwindlabs/tailwindcss/pull/20127))
   83| - Canonicalization: avoid suggesting large spacing-scale values for arbitrary lengths (e.g. `left-[99999px]` → `left-[99999px]`, not `left-24999.75`) ([#20130](https://github.com/tailwindlabs/tailwindcss/pull/20130))
   84| - Ensure `@tailwindcss/cli` in `--watch` mode recovers when a tracked dependency is deleted and restored ([#20137](https://github.com/tailwindlabs/tailwindcss/pull/20137))
   85| - Ensure standalone `@tailwindcss/cli` binaries are ignored when scanning for class candidates ([#20139](https://github.com/tailwindlabs/tailwindcss/pull/20139))
   86| - Ensure class candidates are extracted from Twig `addClass(…)` and `removeClass(…)` calls ([#20198](https://github.com/tailwindlabs/tailwindcss/pull/20198))
   87| - Don't crash in the Ruby or Vue preprocessors when scanning files containing invalid UTF-8 bytes ([#19588](https://github.com/tailwindlabs/tailwindcss/pull/19588))
   88| - Allow `@variant` to be used inside `addBase` ([#19480](https://github.com/tailwindlabs/tailwindcss/pull/19480))
   89| - Ensure `@source` globs with symlinks are preserved ([#20203](https://github.com/tailwindlabs/tailwindcss/pull/20203))
   90| - Ensure later `@source` rules can re-include files excluded by earlier `@source not` rules ([#20203](https://github.com/tailwindlabs/tailwindcss/pull/20203))
   91| - Upgrade: don't migrate empty class rules to invalid `@utility` rules ([#20205](https://github.com/tailwindlabs/tailwindcss/pull/20205))
   92| - Ensure transitions between `inset-shadow-none` and other inset shadows work correctly ([#20208](https://github.com/tailwindlabs/tailwindcss/pull/20208))
   93| - Ensure explicitly referenced `@source` directories are scanned even when ignored by git ([#20214](https://github.com/tailwindlabs/tailwindcss/pull/20214))
   94| - Ensure `@source` globs ending in `**/*` preserve dynamic path segments to avoid scanning too many files ([#20217](https://github.com/tailwindlabs/tailwindcss/pull/20217))
   95| - Canonicalization: don't fold `calc(…)` divisions when the result would require high precision (e.g. `w-[calc(100%/3.5)]` → `w-[calc(100%/3.5)]`, not `w-[28.571428571428573%]`) ([#20221](https://github.com/tailwindlabs/tailwindcss/pull/20221))
   96| - Serve ESM type declarations to ESM importers of `@tailwindcss/postcss` ([#20228](https://github.com/tailwindlabs/tailwindcss/pull/20228))
   97| 
   98| ### Changed
   99| 
  100| - Generate `0` instead of `calc(var(--spacing) * 0)` for spacing utilities like `m-0` and `left-0` ([#20196](https://github.com/tailwindlabs/tailwindcss/pull/20196))
  101| - Generate `var(--spacing)` instead of `calc(var(--spacing) * 1)` for spacing utilities like `m-1` and `left-1` ([#20196](https://github.com/tailwindlabs/tailwindcss/pull/20196))
  102| 
  103| ## [4.3.0] - 2026-05-08
  104| 
  105| ### Added
  106| 
  107| - Add `@container-size` utility ([#18901](https://github.com/tailwindlabs/tailwindcss/pull/18901))
  108| - Add `scrollbar-{auto,thin,none}` utilities for `scrollbar-width`, and `scrollbar-thumb-*` / `scrollbar-track-*` color utilities for `scrollbar-color` ([#19981](https://github.com/tailwindlabs/tailwindcss/pull/19981), [#20019](https://github.com/tailwindlabs/tailwindcss/pull/20019))
  109| - Add `scrollbar-gutter-*` utilities ([#20018](https://github.com/tailwindlabs/tailwindcss/pull/20018))
  110| - Add `zoom-*` utilities ([#20020](https://github.com/tailwindlabs/tailwindcss/pull/20020))
  111| - Add `tab-*` utilities ([#20022](https://github.com/tailwindlabs/tailwindcss/pull/20022))
  112| - Allow using `@variant` with stacked variants (e.g. `@variant hover:focus { … }`) ([#19996](https://github.com/tailwindlabs/tailwindcss/pull/19996))
  113| - Allow using `@variant` with compound variants (e.g. `@variant hover, focus { … }`) ([#19996](https://github.com/tailwindlabs/tailwindcss/pull/19996))
  114| - Support `--default(…)` in `--value(…)` and `--modifier(…)` for functional `@utility` definitions ([#19989](https://github.com/tailwindlabs/tailwindcss/pull/19989))
  115| 
  116| ### Fixed
  117| 
  118| - Ensure `@plugin` resolves package JavaScript entries instead of browser CSS entries when using `@tailwindcss/vite` ([#19949](https://github.com/tailwindlabs/tailwindcss/pull/19949))
  119| - Fix relative `@import` and `@plugin` paths resolving from the wrong directory when using `@tailwindcss/vite` ([#19965](https://github.com/tailwindlabs/tailwindcss/pull/19965))
  120| - Ensure CSS files containing `@variant` are processed by `@tailwindcss/vite` ([#19966](https://github.com/tailwindlabs/tailwindcss/pull/19966))
  121| - Resolve imports relative to `base` when `result.opts.from` is not provided when using `@tailwindcss/postcss` ([#19980](https://github.com/tailwindlabs/tailwindcss/pull/19980))
  122| - Canonicalization: preserve significant `_` whitespace in arbitrary values ([#19986](https://github.com/tailwindlabs/tailwindcss/pull/19986))
  123| - Canonicalization: add parentheses when removing whitespace from arbitrary values would hurt readability (e.g. `w-[calc(100%---spacing(60))]` → `w-[calc(100%-(--spacing(60)))]`) ([#19986](https://github.com/tailwindlabs/tailwindcss/pull/19986))
  124| - Canonicalization: preserve the original unit in arbitrary values instead of normalizing to base units (e.g. `-mt-[20in]` → `mt-[-20in]`, not `mt-[-1920px]`) ([#19988](https://github.com/tailwindlabs/tailwindcss/pull/19988))
  125| - Canonicalization: migrate arbitrary `:has()` variants from `[&:has(…)]` to `has-[…]` ([#19991](https://github.com/tailwindlabs/tailwindcss/pull/19991))
  126| - Upgrade: don’t migrate inline `style` attributes (e.g. `style="flex-grow: 1"` → `style="flex-grow: 1"`, not `style="grow: 1"`) ([#19918](https://github.com/tailwindlabs/tailwindcss/pull/19918))
  127| - Allow multiple `@utility` definitions with the same name but different value types ([#19777](https://github.com/tailwindlabs/tailwindcss/pull/19777))
  128| - Export missing `PluginWithConfig` type from `tailwindcss/plugin` to fix errors when inferring plugin config types ([#19707](https://github.com/tailwindlabs/tailwindcss/pull/19707))
  129| - Ensure `start` and `end` legacy utilities without values do not generate CSS ([#20003](https://github.com/tailwindlabs/tailwindcss/pull/20003))
  130| - Ensure `--value(…)` is required in functional `@utility` definitions ([#20005](https://github.com/tailwindlabs/tailwindcss/pull/20005))
  131| - Canonicalization: preserve required whitespace around operators in negated arbitrary values (e.g. `-left-[(var(--a)+var(--b))]`) ([#20011](https://github.com/tailwindlabs/tailwindcss/pull/20011))
  132| 
  133| ## [4.2.4] - 2026-04-21
  134| 
  135| ### Fixed
  136| 
  137| - Ensure imports in `@import` and `@plugin` still resolve correctly when using Vite aliases in `@tailwindcss/vite` ([#19947](https://github.com/tailwindlabs/tailwindcss/pull/19947))
  138| 
  139| ## [4.2.3] - 2026-04-20
  140| 
  141| ### Fixed
  142| 
  143| - Canonicalization: improve canonicalization for `tracking-*` utilities by preferring non-negative utilities (e.g. `-tracking-tighter` → `tracking-wider`) ([#19827](https://github.com/tailwindlabs/tailwindcss/pull/19827))
  144| - Fix crash due to invalid characters in candidate (exceeding valid unicode code point range) ([#19829](https://github.com/tailwindlabs/tailwindcss/pull/19829))
  145| - Ensure query params in imports are considered unique resources when using `@tailwindcss/webpack` ([#19723](https://github.com/tailwindlabs/tailwindcss/pull/19723))
  146| - Canonicalization: collapse arbitrary values into shorthand utilities (e.g. `px-[1.2rem] py-[1.2rem]` → `p-[1.2rem]`) ([#19837](https://github.com/tailwindlabs/tailwindcss/pull/19837))
  147| - Canonicalization: collapse `border-{t,b}-*` into `border-y-*`, `border-{l,r}-*` into `border-x-*`, and `border-{t,r,b,l}-*` into `border-*` ([#19842](https://github.com/tailwindlabs/tailwindcss/pull/19842))
  148| - Canonicalization: collapse `scroll-m{t,b}-*` into `scroll-my-*`, `scroll-m{l,r}-*` into `scroll-mx-*`, and `scroll-m{t,r,b,l}-*` into `scroll-m-*` ([#19842](https://github.com/tailwindlabs/tailwindcss/pull/19842))
  149| - Canonicalization: collapse `scroll-p{t,b}-*` into `scroll-py-*`, `scroll-p{l,r}-*` into `scroll-px-*`, and `scroll-p{t,r,b,l}-*` into `scroll-p-*` ([#19842](https://github.com/tailwindlabs/tailwindcss/pull/19842))
  150| - Canonicalization: collapse `overflow-{x,y}-*` into `overflow-*` ([#19842](https://github.com/tailwindlabs/tailwindcss/pull/19842))
  151| - Canonicalization: collapse `overscroll-{x,y}-*` into `overscroll-*` ([#19842](https://github.com/tailwindlabs/tailwindcss/pull/19842))
  152| - Read from `--placeholder-color` instead of `--background-color` for `placeholder-*` utilities ([#19843](https://github.com/tailwindlabs/tailwindcss/pull/19843))
  153| - Upgrade: ensure files are not emptied out when killing the upgrade process while it's running ([#19846](https://github.com/tailwindlabs/tailwindcss/pull/19846))
  154| - Upgrade: use `config.content` when migrating from Tailwind CSS v3 to Tailwind CSS v4 ([#19846](https://github.com/tailwindlabs/tailwindcss/pull/19846))
  155| - Upgrade: never migrate files that are ignored by git ([#19846](https://github.com/tailwindlabs/tailwindcss/pull/19846))
  156| - Add `.env` and `.env.*` to default ignored content files ([#19846](https://github.com/tailwindlabs/tailwindcss/pull/19846))
  157| - Canonicalization: migrate `overflow-ellipsis` into `text-ellipsis` ([#19849](https://github.com/tailwindlabs/tailwindcss/pull/19849))
  158| - Canonicalization: migrate `start-full` → `inset-s-full`, `start-auto` → `inset-s-auto`, `start-px` → `inset-s-px`, and `start-<number>` → `inset-s-<number>` as well as negative versions ([#19849](https://github.com/tailwindlabs/tailwindcss/pull/19849))
  159| - Canonicalization: migrate `end-full` → `inset-e-full`, `end-auto` → `inset-e-auto`, `end-px` → `inset-e-px`, and `end-<number>` → `inset-e-<number>` as well as negative versions ([#19849](https://github.com/tailwindlabs/tailwindcss/pull/19849))
  160| - Canonicalization: move the `-` sign inside the arbitrary value `-left-[9rem]` → `left-[-9rem]` ([#19858](https://github.com/tailwindlabs/tailwindcss/pull/19858))
  161| - Canonicalization: move the `-` sign outside the arbitrary value `ml-[calc(-1*var(--width))]` → `-ml-(--width)` ([#19858](https://github.com/tailwindlabs/tailwindcss/pull/19858))
  162| - Improve performance when scanning JSONL / NDJSON files ([#19862](https://github.com/tailwindlabs/tailwindcss/pull/19862))
  163| - Support `NODE_PATH` environment variable in standalone CLI ([#19617](https://github.com/tailwindlabs/tailwindcss/pull/19617))
  164| 
  165| ## [4.2.2] - 2026-03-18
  166| 
  167| ### Fixed
  168| 
  169| - Don't crash when candidates contain prototype properties like `row-constructor` ([#19725](https://github.com/tailwindlabs/tailwindcss/pull/19725))
  170| - Canonicalize `calc(var(--spacing)*…)` expressions into `--spacing(…)` ([#19769](https://github.com/tailwindlabs/tailwindcss/pull/19769))
  171| - Fix crash in canonicalization step when handling utilities containing `@property` at-rules (e.g. `shadow-sm border`) ([#19727](https://github.com/tailwindlabs/tailwindcss/pull/19727))
  172| - Skip full reload for server only modules scanned by client CSS when using `@tailwindcss/vite` ([#19745](https://github.com/tailwindlabs/tailwindcss/pull/19745))
  173| - Add support for Vite 8 in `@tailwindcss/vite` ([#19790](https://github.com/tailwindlabs/tailwindcss/pull/19790))
  174| - Improve canonicalization for bare values exceeding default spacing scale suggestions (e.g. `w-1234 h-1234` → `size-1234`) ([#19809](https://github.com/tailwindlabs/tailwindcss/pull/19809))
  175| - Fix canonicalization resulting in empty list (e.g. `w-5 h-5 size-5` → `''` instead of `size-5`) ([#19812](https://github.com/tailwindlabs/tailwindcss/pull/19812))
  176| - Resolve tsconfig paths to allow for `@import '@/path/to/file';` when using `@tailwindcss/vite` ([#19803](https://github.com/tailwindlabs/tailwindcss/pull/19803))
  177| 
  178| ## [4.2.1] - 2026-02-23
  179| 
  180| ### Fixed
  181| 
  182| - Allow trailing dash in functional utility names for backwards compatibility ([#19696](https://github.com/tailwindlabs/tailwindcss/pull/19696))
  183| - Properly detect classes containing `.` characters within curly braces in MDX files ([#19711](https://github.com/tailwindlabs/tailwindcss/pull/19711))
  184| 
  185| ## [4.2.0] - 2026-02-18
  186| 
  187| ### Added
  188| 
  189| - Add mauve, olive, mist, and taupe color palettes to the default theme ([#19627](https://github.com/tailwindlabs/tailwindcss/pull/19627))
  190| - Add `@tailwindcss/webpack` package to run Tailwind CSS as a webpack plugin ([#19610](https://github.com/tailwindlabs/tailwindcss/pull/19610))
  191| - Add `pbs-*` and `pbe-*` utilities for `padding-block-start` and `padding-block-end` ([#19601](https://github.com/tailwindlabs/tailwindcss/pull/19601))
  192| - Add `mbs-*` and `mbe-*` utilities for `margin-block-start` and `margin-block-end` ([#19601](https://github.com/tailwindlabs/tailwindcss/pull/19601))
  193| - Add `scroll-pbs-*` and `scroll-pbe-*` utilities for `scroll-padding-block-start` and `scroll-padding-block-end` ([#19601](https://github.com/tailwindlabs/tailwindcss/pull/19601))
  194| - Add `scroll-mbs-*` and `scroll-mbe-*` utilities for `scroll-margin-block-start` and `scroll-margin-block-end` ([#19601](https://github.com/tailwindlabs/tailwindcss/pull/19601))
  195| - Add `border-bs-*` and `border-be-*` utilities for `border-block-start` and `border-block-end` ([#19601](https://github.com/tailwindlabs/tailwindcss/pull/19601))
  196| - Add `inline-*`, `min-inline-*`, `max-inline-*` utilities for `inline-size`, `min-inline-size`, and `max-inline-size` ([#19612](https://github.com/tailwindlabs/tailwindcss/pull/19612))
  197| - Add `block-*`, `min-block-*`, `max-block-*` utilities for `block-size`, `min-block-size`, and `max-block-size` ([#19612](https://github.com/tailwindlabs/tailwindcss/pull/19612))
  198| - Add `inset-s-*`, `inset-e-*`, `inset-bs-*`, `inset-be-*` utilities for `inset-inline-start`, `inset-inline-end`, `inset-block-start`, and `inset-block-end` ([#19613](https://github.com/tailwindlabs/tailwindcss/pull/19613))
  199| - Add `font-features-*` utility for `font-feature-settings` ([#19623](https://github.com/tailwindlabs/tailwindcss/pull/19623))
  200| 
```
