# PR pack: tailwindlabs/tailwindcss#20380
Title: Canonicalization: convert variants with arbitrary values to equivalent variants
Merge commit: 6def8205b5eeba95e697d790efba0d865c0e4b48

## Diff
```diff
diff --git a/CHANGELOG.md b/CHANGELOG.md
index f218684748be..59642fd84267 100644
--- a/CHANGELOG.md
+++ b/CHANGELOG.md
@@ -18,6 +18,7 @@ and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0
 - Fix flattening of `@scope` at-rules ([#20369](https://github.com/tailwindlabs/tailwindcss/pull/20369))
 - Fix standalone declarations in `@scope`, wrap them in `:where(:scope)` ([#20369](https://github.com/tailwindlabs/tailwindcss/pull/20369))
 - Always emit a space for empty fallback values in CSS variables (e.g. `var(--tw-blur,)` → `var(--tw-blur, )`) ([#20373](https://github.com/tailwindlabs/tailwindcss/pull/20373))
+- Canonicalization: convert arbitrary breakpoint and container query variants to named equivalents (e.g. `max-[64rem]` → `max-lg`) ([#20380](https://github.com/tailwindlabs/tailwindcss/pull/20380))
 
 ## [4.3.3] - 2026-07-16
 
diff --git a/packages/@tailwindcss-upgrade/src/codemods/template/migrate-arbitrary-variants.ts b/packages/@tailwindcss-upgrade/src/codemods/template/migrate-arbitrary-variants.ts
index 58efb0421253..258ba1b331cd 100644
--- a/packages/@tailwindcss-upgrade/src/codemods/template/migrate-arbitrary-variants.ts
+++ b/packages/@tailwindcss-upgrade/src/codemods/template/migrate-arbitrary-variants.ts
@@ -16,8 +16,8 @@ export function migrateArbitraryVariants(
   rawCandidate: string,
 ): string {
   let designSystem = prepareDesignSystemStorage(baseDesignSystem)
-  let signatures = designSystem.storage[VARIANT_SIGNATURE_KEY]
-  let variants = designSystem.storage[PRE_COMPUTED_VARIANTS_KEY]
+  let signatures = designSystem.storage[VARIANT_SIGNATURE_KEY].get(null)
+  let variants = designSystem.storage[PRE_COMPUTED_VARIANTS_KEY].get(null)
 
   for (let readonlyCandidate of designSystem.parseCandidate(rawCandidate)) {
     // We are only interested in the variants
@@ -35,7 +35,11 @@ export function migrateArbitraryVariants(
       if (typeof targetSignature !== 'string') continue
 
       let foundVariants = variants.get(targetSignature)
-      if (foundVariants.length !== 1) continue
+      if (foundVariants.length === 0) continue
+
+      // The variant is already in a canonical form, e.g.: `min-lg` and `lg`
+      // produce the same CSS, but both are valid so we keep them as-is.
+      if (foundVariants.includes(targetString)) continue
 
       let foundVariant = foundVariants[0]
       let parsedVariant = designSystem.parseVariant(foundVariant)
diff --git a/packages/tailwindcss/src/canonicalize-candidates.test.ts b/packages/tailwindcss/src/canonicalize-candidates.test.ts
index 03229f450bea..550a9c9a24ac 100644
--- a/packages/tailwindcss/src/canonicalize-candidates.test.ts
+++ b/packages/tailwindcss/src/canonicalize-candidates.test.ts
@@ -414,9 +414,11 @@ describe.each([['default'], ['with-variant'], ['important'], ['prefix']])('%s',
       // This should still migrate the `theme(…)` syntax to the modern syntax.
       ['bg-[theme(colors.red.500/50%)]/50', 'bg-[--theme(--color-red-500/50%)]/50'],
 
-      // Variants, we can't use `var(…)` especially inside of `@media(…)`. We can
-      // still upgrade the `theme(…)` to the modern syntax.
-      ['max-[theme(screens.lg)]:flex', 'max-[--theme(--breakpoint-lg)]:flex'],
+      // Variants, we can't use `var(…)` especially inside of `@media(…)`. But
+      // since the value matches the `lg` breakpoint exactly, we can migrate to
+      // the `max-lg` variant.
+      ['max-[theme(screens.lg)]:flex', 'max-lg:flex'],
+      ['min-[theme(screens.lg)]:flex', 'lg:flex'], // We could also map to `min-lg:flex`
       // There are no variables for `--spacing` multiples, so we can't convert this
       ['max-[theme(spacing.4)]:flex', 'max-[theme(spacing.4)]:flex'],
 
@@ -719,6 +721,7 @@ describe.each([['default'], ['with-variant'], ['important'], ['prefix']])('%s',
       @import 'tailwindcss';
       @theme {
         --*: initial;
+        --breakpoint-lg: 64rem;
       }
     `
 
@@ -735,6 +738,11 @@ describe.each([['default'], ['with-variant'], ['important'], ['prefix']])('%s',
       ['[@media(scripting:_none)]:flex', 'noscript:flex'],
       ['[@media_(scripting:_none)]:flex', 'noscript:flex'],
 
+      // Arbitrary variants with media queries cannot use `var(…)`, but if an
+      // equivalent variant exists we can use that one instead.
+      ['[@media(width>=theme(screens.lg))]:flex', 'lg:flex'], // `min-lg:flex` would also be valid
+      ['[@media(width<theme(screens.lg))]:flex', 'max-lg:flex'],
+
       // With compound variants
       ['has-[&:focus]:flex', 'has-focus:flex'],
       ['not-[&:focus]:flex', 'not-focus:flex'],
@@ -951,6 +959,67 @@ describe.each([['default'], ['with-variant'], ['important'], ['prefix']])('%s',
     })
   })
 
+  // https://github.com/tailwindlabs/tailwindcss/issues/20365
+  describe('media query and container query variants', () => {
+    test.each([
+      // Breakpoints (`--breakpoint-lg: 64rem`, `--breakpoint-md: 48rem`)
+      ['min-[64rem]:flex', 'lg:flex'],
+      ['max-[64rem]:flex', 'max-lg:flex'],
+      ['min-[48rem]:flex', 'md:flex'],
+      ['max-[48rem]:flex', 'max-md:flex'],
+
+      // With the `rem` option set, equivalent `px` values should also be
+      // canonicalized to the breakpoint variants.
+      ['min-[1024px]:flex', 'lg:flex'],
+      ['max-[1024px]:flex', 'max-lg:flex'],
+
+      // Container queries (`--container-md: 28rem`)
+      ['@min-[28rem]:flex', '@md:flex'],
+      ['@max-[28rem]:flex', '@max-md:flex'],
+      ['@min-[448px]:flex', '@md:flex'],
+      ['@max-[448px]:flex', '@max-md:flex'],
+
+      // Values that don't map to a known breakpoint or container size should
+      // stay as-is.
+      ['min-[123px]:flex', 'min-[123px]:flex'],
+      ['max-[123px]:flex', 'max-[123px]:flex'],
+      ['@min-[123px]:flex', '@min-[123px]:flex'],
+      ['@max-[123px]:flex', '@max-[123px]:flex'],
+
+      // Named variants that produce the same CSS should be kept as-is
+      ['min-lg:flex', 'min-lg:flex'],
+      ['@min-md:flex', '@min-md:flex'],
+    ])(testName, { timeout }, async (candidate, expected) => {
+      let input = css`
+        @import 'tailwindcss';
+      `
+
+      await expectCanonicalization(input, candidate, expected)
+    })
+
+    test.each([
+      // Without the `rem` option, `px` values cannot be safely converted to
+      // `rem` based breakpoints.
+      ['min-[1024px]:flex', 'min-[1024px]:flex'],
+      ['@min-[448px]:flex', '@min-[448px]:flex'],
+
+      // Same unit still works without the `rem` option
+      ['min-[64rem]:flex', 'lg:flex'],
+      ['max-[64rem]:flex', 'max-lg:flex'],
+      ['@min-[28rem]:flex', '@md:flex'],
+      ['@max-[28rem]:flex', '@max-md:flex'],
+    ])(`${testName} (no rem option)`, { timeout }, async (candidate, expected) => {
+      let input = css`
+        @import 'tailwindcss';
+      `
+
+      await expectCanonicalization(input, candidate, expected, {
+        collapse: true,
+        logicalToPhysical: true,
+      })
+    })
+  })
+
   describe('modernize arbitrary variants', () => {
     test.each([
       // Arbitrary variants
@@ -1546,4 +1615,27 @@ describe('regressions', () => {
       'bg-brand-purple',
     ])
   })
+
+  // https://github.com/tailwindlabs/tailwindcss/issues/20365
+  test('canonicalizes min/max media query and container query variants', async () => {
+    let designSystem = await __unstable__loadDesignSystem(
+      css`
+        @tailwind utilities;
+        @theme {
+          --breakpoint-lg: 64rem;
+          --container-lg: 32rem;
+          --spacing: 0.25rem;
+        }
+      `,
+      { base: __dirname },
+    )
+
+    expect(designSystem.canonicalizeCandidates(['min-[64rem]:flex'])).toEqual(['lg:flex'])
+    expect(designSystem.canonicalizeCandidates(['max-[64rem]:flex'])).toEqual(['max-lg:flex'])
+    expect(designSystem.canonicalizeCandidates(['@min-[32rem]:flex'])).toEqual(['@lg:flex'])
+    expect(designSystem.canonicalizeCandidates(['@max-[32rem]:flex'])).toEqual(['@max-lg:flex'])
+    expect(designSystem.canonicalizeCandidates(['min-[1024px]:flex'], { rem: 16 })).toEqual([
+      'lg:flex',
+    ])
+  })
 })
diff --git a/packages/tailwindcss/src/canonicalize-candidates.ts b/packages/tailwindcss/src/canonicalize-candidates.ts
index eb9d8697c824..ad2648e12af4 100644
--- a/packages/tailwindcss/src/canonicalize-candidates.ts
+++ b/packages/tailwindcss/src/canonicalize-candidates.ts
@@ -72,12 +72,11 @@ interface InternalCanonicalizeOptions {
   signatureOptions: SignatureOptions
 }
 
+type RemValue = number | null
+
 interface DesignSystem extends BaseDesignSystem {
   storage: {
-    [SIGNATURE_OPTIONS_KEY]: DefaultMap<
-      number | null, // Rem value
-      DefaultMap<SignatureFeatures, SignatureOptions>
-    >
+    [SIGNATURE_OPTIONS_KEY]: DefaultMap<RemValue, DefaultMap<SignatureFeatures, SignatureOptions>>
     [COMPARE_CANDIDATES_KEY]: DefaultMap<
       SignatureOptions,
       (a: Candidate | string, b: Candidate | string) => boolean
@@ -107,8 +106,8 @@ interface DesignSystem extends BaseDesignSystem {
       DefaultMap<string, DefaultMap<string, Set<string>>>
     >
     [PRE_COMPUTED_UTILITIES_KEY]: DefaultMap<SignatureOptions, DefaultMap<string, string[]>>
-    [VARIANT_SIGNATURE_KEY]: DefaultMap<string, string | symbol>
-    [PRE_COMPUTED_VARIANTS_KEY]: DefaultMap<string, string[]>
+    [VARIANT_SIGNATURE_KEY]: DefaultMap<RemValue, DefaultMap<string, string | symbol>>
+    [PRE_COMPUTED_VARIANTS_KEY]: DefaultMap<RemValue, DefaultMap<string, string[]>>
   }
 }
 
@@ -1537,8 +1536,8 @@ function arbitraryVariants(
   options: InternalCanonicalizeOptions,
 ): Variant | Variant[] {
   let designSystem = options.designSystem
-  let signatures = designSystem.storage[VARIANT_SIGNATURE_KEY]
-  let variants = designSystem.storage[PRE_COMPUTED_VARIANTS_KEY]
+  let signatures = designSystem.storage[VARIANT_SIGNATURE_KEY].get(options.signatureOptions.rem)
+  let variants = designSystem.storage[PRE_COMPUTED_VARIANTS_KEY].get(options.signatureOptions.rem)
 
   let iterator = walkVariants(variant)
   for (let [variant] of iterator) {
@@ -1549,7 +1548,11 @@ function arbitraryVariants(
     if (typeof targetSignature !== 'string') continue
 
     let foundVariants = variants.get(targetSignature)
-    if (foundVariants.length !== 1) continue
+    if (foundVariants.length === 0) continue
+
+    // The variant is already in a canonical form, e.g.: `min-lg` and `lg`
+    // produce the same CSS, but both are valid so we keep them as-is.
+    if (foundVariants.includes(targetString)) continue
 
     let foundVariant = foundVariants[0]
     let parsedVariant = designSystem.parseVariant(foundVariant)
@@ -1769,7 +1772,7 @@ function modernizeArbitraryValuesVariant(
 ): Variant | Variant[] {
   let result = [variant]
   let designSystem = options.designSystem
-  let signatures = designSystem.storage[VARIANT_SIGNATURE_KEY]
+  let signatures = designSystem.storage[VARIANT_SIGNATURE_KEY].get(options.signatureOptions.rem)
 
   let iterator = walkVariants(variant)
   for (let [variant, parent] of iterator) {
@@ -2785,100 +2788,110 @@ export const VARIANT_SIGNATURE_KEY = Symbol()
 function createVariantSignatureCache(
   designSystem: DesignSystem,
 ): DesignSystem['storage'][typeof VARIANT_SIGNATURE_KEY] {
-  return new DefaultMap<string, string | symbol>((variant) => {
-    try {
-      // Ensure the prefix is added to the utility if it is not already present.
-      variant =
-        designSystem.theme.prefix && !variant.startsWith(designSystem.theme.prefix)
-          ? `${designSystem.theme.prefix}:${variant}`
-          : variant
-
-      // Use `@apply` to normalize the selector to `.x`
-      let ast: AstNode[] = [styleRule('.x', [atRule('@apply', `${variant}:flex`)])]
-      substituteAtApply(ast, designSystem)
-
-      // Canonicalize selectors to their minimal form
-      walk(ast, (node) => {
-        // At-rules
-        if (node.kind === 'at-rule' && node.params.includes(' ')) {
-          node.params = node.params.replaceAll(' ', '')
-        }
+  return new DefaultMap((rem: number | null) => {
+    return new DefaultMap<string, string | symbol>((variant) => {
+      try {
+        // Ensure the prefix is added to the utility if it is not already present.
+        variant =
+          designSystem.theme.prefix && !variant.startsWith(designSystem.theme.prefix)
+            ? `${designSystem.theme.prefix}:${variant}`
+            : variant
 
-        // Style rules
-        else if (node.kind === 'rule') {
-          let selectorAst = SelectorParser.parse(node.selector)
-          let changed = false
-          walk(selectorAst, (node) => {
-            // Assumption: when we have a list of selectors: `.foo, .bar` we
-            // want to mark this as changed because this will be re-printed as
-            // `.foo,.bar`.
-            //
-            // Similarly, when we receive a combinator like `.foo + .bar`, this
-            // will be printed as `.foo+.bar`.
-            //
-            // It could be that this was already optimal, but then this would be
-            // a no-op situation.
-            if (node.kind === 'list' || node.kind === 'combinator') {
-              changed = true
+        // Use `@apply` to normalize the selector to `.x`
+        let ast: AstNode[] = [styleRule('.x', [atRule('@apply', `${variant}:flex`)])]
+        substituteAtApply(ast, designSystem)
+
+        // Canonicalize selectors to their minimal form
+        walk(ast, (node) => {
+          // At-rules
+          if (node.kind === 'at-rule') {
+            // Normalize dimensions such that equivalent values in different
+            // units are considered the same. E.g.: with a root font size of
+            // `16px`, `@media (width >= 64rem)` and `@media (width >= 1024px)`
+            // are equivalent.
+            node.params = constantFoldDeclaration(node.params, rem)
+
+            if (node.params.includes(' ')) {
+              node.params = node.params.replaceAll(' ', '')
             }
+          }
 
-            // Remove unnecessary `:is(…)` selectors
-            else if (node.kind === 'function' && node.value === ':is') {
-              // A single selector inside of `:is(…)` can be replaced with the
-              // selector itself.
+          // Style rules
+          else if (node.kind === 'rule') {
+            let selectorAst = SelectorParser.parse(node.selector)
+            let changed = false
+            walk(selectorAst, (node) => {
+              // Assumption: when we have a list of selectors: `.foo, .bar` we
+              // want to mark this as changed because this will be re-printed as
+              // `.foo,.bar`.
+              //
+              // Similarly, when we receive a combinator like `.foo + .bar`, this
+              // will be printed as `.foo+.bar`.
               //
-              // E.g.: `:is(.foo)` → `.foo`
-              if (node.nodes.length === 1) {
+              // It could be that this was already optimal, but then this would be
+              // a no-op situation.
+              if (node.kind === 'list' || node.kind === 'combinator') {
                 changed = true
-                return WalkAction.Replace(node.nodes)
               }
 
-              // A selector with the universal selector `*` followed by a pseudo
-              // class, can be replaced with the pseudo class itself.
+              // Remove unnecessary `:is(…)` selectors
+              else if (node.kind === 'function' && node.value === ':is') {
+                // A single selector inside of `:is(…)` can be replaced with the
+                // selector itself.
+                //
+                // E.g.: `:is(.foo)` → `.foo`
+                if (node.nodes.length === 1) {
+                  changed = true
+                  return WalkAction.Replace(node.nodes)
+                }
+
+                // A selector with the universal selector `*` followed by a pseudo
+                // class, can be replaced with the pseudo class itself.
+                else if (
+                  node.nodes.length === 2 &&
+                  node.nodes[0].kind === 'selector' &&
+                  node.nodes[0].value === '*' &&
+                  node.nodes[1].kind === 'selector' &&
+                  node.nodes[1].value[0] === ':'
+                ) {
+                  changed = true
+                  return WalkAction.Replace(node.nodes[1])
+                }
+              }
+
+              // Ensure `*` exists before pseudo selectors inside of `:not(…)`,
+              // `:where(…)`, …
+              //
+              // E.g.:
+              //
+              // `:not(:first-child)` → `:not(*:first-child)`
+              //
               else if (
-                node.nodes.length === 2 &&
-                node.nodes[0].kind === 'selector' &&
-                node.nodes[0].value === '*' &&
-                node.nodes[1].kind === 'selector' &&
-                node.nodes[1].value[0] === ':'
+                node.kind === 'function' &&
+                node.value[0] === ':' &&
+                node.nodes[0]?.kind === 'selector' &&
+                node.nodes[0]?.value[0] === ':'
               ) {
                 changed = true
-                return WalkAction.Replace(node.nodes[1])
+                node.nodes.unshift({ kind: 'selector', value: '*' })
               }
-            }
+            })
 
-            // Ensure `*` exists before pseudo selectors inside of `:not(…)`,
-            // `:where(…)`, …
-            //
-            // E.g.:
-            //
-            // `:not(:first-child)` → `:not(*:first-child)`
-            //
-            else if (
-              node.kind === 'function' &&
-              node.value[0] === ':' &&
-              node.nodes[0]?.kind === 'selector' &&
-              node.nodes[0]?.value[0] === ':'
-            ) {
-              changed = true
-              node.nodes.unshift({ kind: 'selector', value: '*' })
+            if (changed) {
+              node.selector = SelectorParser.toCss(selectorAst, true)
             }
-          })
-
-          if (changed) {
-            node.selector = SelectorParser.toCss(selectorAst, true)
           }
-        }
-      })
+        })
 
-      // Compute the final signature, by generating the CSS for the variant
-      let signature = toCss(ast)
-      return signature
-    } catch {
-      // A unique symbol is returned to ensure that 2 signatures resulting in
-      // `null` are not considered equal.
-      return Symbol()
-    }
+        // Compute the final signature, by generating the CSS for the variant
+        let signature = toCss(ast)
+        return signature
+      } catch {
+        // A unique symbol is returned to ensure that 2 signatures resulting in
+        // `null` are not considered equal.
+        return Symbol()
+      }
+    })
   })
 }
 
@@ -2886,19 +2899,31 @@ export const PRE_COMPUTED_VARIANTS_KEY = Symbol()
 function createPreComputedVariantsCache(
   designSystem: DesignSystem,
 ): DesignSystem['storage'][typeof PRE_COMPUTED_VARIANTS_KEY] {
-  let signatures = designSystem.storage[VARIANT_SIGNATURE_KEY]
-  let lookup = new DefaultMap<string, string[]>(() => [])
+  return new DefaultMap((rem: number | null) => {
+    let signatures = designSystem.storage[VARIANT_SIGNATURE_KEY].get(rem)
+    let lookup = new DefaultMap<string, string[]>(() => [])
 
-  // Actual static variants
-  for (let [root, variant] of designSystem.variants.entries()) {
-    if (variant.kind === 'static') {
-      let signature = signatures.get(root)
-      if (typeof signature !== 'string') continue
-      lookup.get(signature).push(root)
+    for (let [root, variant] of designSystem.variants.entries()) {
+      // Actual static variants
+      if (variant.kind === 'static') {
+        let signature = signatures.get(root)
+        if (typeof signature !== 'string') continue
+        lookup.get(signature).push(root)
+      }
+
+      // Functional variants with known values, e.g.: `max-lg`, `@min-md`, …
+      else if (variant.kind === 'functional') {
+        for (let value of designSystem.variants.getCompletions(root)) {
+          let name = root === '@' ? `@${value}` : `${root}-${value}`
+          let signature = signatures.get(name)
+          if (typeof signature !== 'string') continue
+          lookup.get(signature).push(name)
+        }
+      }
     }
-  }
 
-  return lookup
+    return lookup
+  })
 }
 
 function temporarilyDisableThemeInline<T>(designSystem: DesignSystem, cb: () => T): T {

```

## Touched files at the merge commit (window of up to 200 lines around the first changed hunk)

### packages/tailwindcss/src/canonicalize-candidates.ts (lines 13 to 212 of 3041)
```
   13| } from './candidate'
   14| import { canonicalizeCalcExpressionsAst } from './canonicalize-calc-expressions'
   15| import { keyPathToCssProperty } from './compat/apply-config-to-theme'
   16| import { constantFoldDeclaration, constantFoldDeclarationAst } from './constant-fold-declaration'
   17| import type { DesignSystem as BaseDesignSystem } from './design-system'
   18| import { CompileAstFlags } from './design-system'
   19| import { expandDeclaration } from './expand-declaration'
   20| import * as SelectorParser from './selector-parser'
   21| import { ThemeOptions } from './theme'
   22| import type { Writable } from './types'
   23| import { DefaultMap } from './utils/default-map'
   24| import { dimensions } from './utils/dimensions'
   25| import { isPositiveInteger, isValidSpacingMultiplier } from './utils/infer-data-type'
   26| import { replaceObject } from './utils/replace-object'
   27| import { segment } from './utils/segment'
   28| import { toKeyPath } from './utils/to-key-path'
   29| import * as ValueParser from './value-parser'
   30| import { walk, WalkAction } from './walk'
   31| 
   32| export interface CanonicalizeOptions {
   33|   /**
   34|    * The root font size in pixels. If provided, `rem` values will be normalized
   35|    * to `px` values.
   36|    *
   37|    * E.g.: `mt-[16px]` with `rem: 16` will become `mt-4` (assuming `--spacing: 0.25rem`).
   38|    */
   39|   rem?: number
   40| 
   41|   /**
   42|    * Whether to collapse multiple utilities into a single utility if possible.
   43|    *
   44|    * E.g.: `mt-2 mr-2 mb-2 ml-2` → `m-2`
   45|    */
   46|   collapse?: boolean
   47| 
   48|   /**
   49|    * Whether to convert between logical and physical properties when collapsing
   50|    * utilities.
   51|    *
   52|    * E.g.: `mr-2 ml-2` → `mx-2`
   53|    */
   54|   logicalToPhysical?: boolean
   55| }
   56| 
   57| enum Features {
   58|   /**
   59|    * No features enabled (default)
   60|    */
   61|   None = 0,
   62| 
   63|   /**
   64|    * Collapse multiple utilities into a single utility if possible.
   65|    */
   66|   CollapseUtilities = 1 << 0,
   67| }
   68| 
   69| interface InternalCanonicalizeOptions {
   70|   features: Features
   71|   designSystem: DesignSystem
   72|   signatureOptions: SignatureOptions
   73| }
   74| 
   75| type RemValue = number | null
   76| 
   77| interface DesignSystem extends BaseDesignSystem {
   78|   storage: {
   79|     [SIGNATURE_OPTIONS_KEY]: DefaultMap<RemValue, DefaultMap<SignatureFeatures, SignatureOptions>>
   80|     [COMPARE_CANDIDATES_KEY]: DefaultMap<
   81|       SignatureOptions,
   82|       (a: Candidate | string, b: Candidate | string) => boolean
   83|     >
   84|     [INTERNAL_OPTIONS_KEY]: DefaultMap<
   85|       SignatureOptions,
   86|       DefaultMap<Features, InternalCanonicalizeOptions>
   87|     >
   88|     [CANONICALIZE_CANDIDATE_KEY]: DefaultMap<
   89|       InternalCanonicalizeOptions,
   90|       DefaultMap<string, string>
   91|     >
   92|     [CANONICALIZE_VARIANT_KEY]: DefaultMap<
   93|       InternalCanonicalizeOptions,
   94|       DefaultMap<Variant, Variant[]>
   95|     >
   96|     [CANONICALIZE_UTILITY_KEY]: DefaultMap<InternalCanonicalizeOptions, DefaultMap<string, string>>
   97|     [CONVERTER_KEY]: (input: string, options?: Convert) => [string, CandidateModifier | null]
   98|     [SPACING_KEY]: DefaultMap<string, number | null> | null
   99|     [UTILITY_SIGNATURE_KEY]: DefaultMap<SignatureOptions, DefaultMap<string, string | symbol>>
  100|     [STATIC_UTILITIES_KEY]: DefaultMap<
  101|       SignatureOptions,
  102|       DefaultMap<string, DefaultMap<string, Set<string>>>
  103|     >
  104|     [UTILITY_PROPERTIES_KEY]: DefaultMap<
  105|       SignatureOptions,
  106|       DefaultMap<string, DefaultMap<string, Set<string>>>
  107|     >
  108|     [PRE_COMPUTED_UTILITIES_KEY]: DefaultMap<SignatureOptions, DefaultMap<string, string[]>>
  109|     [VARIANT_SIGNATURE_KEY]: DefaultMap<RemValue, DefaultMap<string, string | symbol>>
  110|     [PRE_COMPUTED_VARIANTS_KEY]: DefaultMap<RemValue, DefaultMap<string, string[]>>
  111|   }
  112| }
  113| 
  114| export function prepareDesignSystemStorage(
  115|   baseDesignSystem: BaseDesignSystem,
  116|   options?: CanonicalizeOptions,
  117| ): DesignSystem {
  118|   let designSystem = baseDesignSystem as DesignSystem
  119| 
  120|   designSystem.storage[SIGNATURE_OPTIONS_KEY] ??= createSignatureOptionsCache()
  121|   designSystem.storage[INTERNAL_OPTIONS_KEY] ??= createInternalOptionsCache(designSystem)
  122|   designSystem.storage[CANONICALIZE_CANDIDATE_KEY] ??= createCanonicalizeCandidateCache()
  123|   designSystem.storage[CANONICALIZE_VARIANT_KEY] ??= createCanonicalizeVariantCache()
  124|   designSystem.storage[CANONICALIZE_UTILITY_KEY] ??= createCanonicalizeUtilityCache()
  125|   designSystem.storage[CONVERTER_KEY] ??= createConverterCache(designSystem)
  126|   designSystem.storage[SPACING_KEY] ??= createSpacingCache(designSystem, options)
  127|   designSystem.storage[UTILITY_SIGNATURE_KEY] ??= createUtilitySignatureCache(designSystem)
  128|   designSystem.storage[STATIC_UTILITIES_KEY] ??= createStaticUtilitiesCache()
  129|   designSystem.storage[UTILITY_PROPERTIES_KEY] ??= createUtilityPropertiesCache(designSystem)
  130|   designSystem.storage[PRE_COMPUTED_UTILITIES_KEY] ??= createPreComputedUtilitiesCache(designSystem)
  131|   designSystem.storage[VARIANT_SIGNATURE_KEY] ??= createVariantSignatureCache(designSystem)
  132|   designSystem.storage[PRE_COMPUTED_VARIANTS_KEY] ??= createPreComputedVariantsCache(designSystem)
  133|   designSystem.storage[COMPARE_CANDIDATES_KEY] ??= createSignatureComparison(designSystem)
  134| 
  135|   return designSystem
  136| }
  137| 
  138| const SIGNATURE_OPTIONS_KEY = Symbol()
  139| function createSignatureOptionsCache(): DesignSystem['storage'][typeof SIGNATURE_OPTIONS_KEY] {
  140|   return new DefaultMap((rem: number | null) => {
  141|     return new DefaultMap((features: SignatureFeatures) => {
  142|       return { rem, features } satisfies SignatureOptions
  143|     })
  144|   })
  145| }
  146| 
  147| const COMPARE_CANDIDATES_KEY = Symbol()
  148| function createSignatureComparison(designSystem: DesignSystem) {
  149|   return new DefaultMap((options: SignatureOptions) => {
  150|     let signatures = designSystem.storage[UTILITY_SIGNATURE_KEY].get(options)
  151| 
  152|     return function hasSameSignature(a: Candidate | string, b: Candidate | string): boolean {
  153|       let aCandidateString = typeof a === 'string' ? a : designSystem.printCandidate(a)
  154|       let aSignature = signatures.get(aCandidateString)
  155|       if (typeof aSignature !== 'string') return false
  156| 
  157|       let bCandidateString = typeof b === 'string' ? b : designSystem.printCandidate(b)
  158|       let bSignature = signatures.get(bCandidateString)
  159|       if (typeof bSignature !== 'string') return false
  160| 
  161|       return aSignature === bSignature
  162|     }
  163|   })
  164| }
  165| 
  166| export function createSignatureOptions(
  167|   baseDesignSystem: BaseDesignSystem,
  168|   options?: CanonicalizeOptions,
  169| ): SignatureOptions {
  170|   let features = SignatureFeatures.None
  171|   if (options?.collapse) features |= SignatureFeatures.ExpandProperties
  172|   if (options?.logicalToPhysical) features |= SignatureFeatures.LogicalToPhysical
  173| 
  174|   let designSystem = prepareDesignSystemStorage(baseDesignSystem, options)
  175| 
  176|   return designSystem.storage[SIGNATURE_OPTIONS_KEY].get(options?.rem ?? null).get(features)
  177| }
  178| 
  179| const INTERNAL_OPTIONS_KEY = Symbol()
  180| function createInternalOptionsCache(
  181|   designSystem: DesignSystem,
  182| ): DesignSystem['storage'][typeof INTERNAL_OPTIONS_KEY] {
  183|   return new DefaultMap((signatureOptions: SignatureOptions) => {
  184|     return new DefaultMap((features: Features) => {
  185|       return { features, designSystem, signatureOptions } satisfies InternalCanonicalizeOptions
  186|     })
  187|   })
  188| }
  189| 
  190| function createCanonicalizeOptions(
  191|   baseDesignSystem: BaseDesignSystem,
  192|   signatureOptions: SignatureOptions,
  193|   options?: CanonicalizeOptions,
  194| ) {
  195|   let features = Features.None
  196|   if (options?.collapse) features |= Features.CollapseUtilities
  197| 
  198|   let designSystem = prepareDesignSystemStorage(baseDesignSystem)
  199| 
  200|   return designSystem.storage[INTERNAL_OPTIONS_KEY].get(signatureOptions).get(features)
  201| }
  202| 
  203| export function canonicalizeCandidates(
  204|   baseDesignSystem: BaseDesignSystem,
  205|   candidates: string[],
  206|   options?: CanonicalizeOptions,
  207| ): string[] {
  208|   let signatureOptions = createSignatureOptions(baseDesignSystem, options)
  209|   let canonicalizeOptions = createCanonicalizeOptions(baseDesignSystem, signatureOptions, options)
  210| 
  211|   let designSystem = prepareDesignSystemStorage(baseDesignSystem)
  212| 
```

### packages/tailwindcss/src/canonicalize-candidates.test.ts (lines 355 to 554 of 1642)
```
  355|         @import 'tailwindcss';
  356| 
  357|         @theme {
  358|           --*: initial;
  359|           --spacing: 0.25rem;
  360|           --color-red-500: red;
  361|           --color-white: #fff;
  362| 
  363|           /* Equivalent of blue-500/50 */
  364|           --color-primary: color-mix(in oklab, oklch(62.3% 0.214 259.815) 50%, transparent);
  365|         }
  366|       `
  367| 
  368|       await expectCanonicalization(input, candidate, expected)
  369|     })
  370|   })
  371| 
  372|   describe('arbitrary values', () => {
  373|     test.each([
  374|       // Convert to `var(…)` if we can resolve the path
  375|       ['bg-[theme(colors.red.500)]', 'bg-red-500'], // Arbitrary value
  376|       ['bg-[size:theme(spacing.4)]', 'bg-size-[--spacing(4)]'], // Arbitrary value + data type hint
  377| 
  378|       // Pretty print CSS functions preceded by an operator to prevent consecutive
  379|       // operator characters.
  380|       ['w-[calc(100dvh-theme(spacing.2))]', 'w-[calc(100dvh-(--spacing(2)))]'],
  381|       ['w-[calc(100dvh+theme(spacing.2))]', 'w-[calc(100dvh+(--spacing(2)))]'],
  382|       ['w-[calc(100dvh/theme(spacing.2))]', 'w-[calc(100dvh/(--spacing(2)))]'],
  383|       ['w-[calc(100dvh*theme(spacing.2))]', 'w-[calc(100dvh*(--spacing(2)))]'],
  384| 
  385|       // Convert to `var(…)` if we can resolve the path, but keep fallback values
  386|       ['bg-[theme(colors.red.500,red)]', 'bg-(--color-red-500,red)'],
  387| 
  388|       // Keep `theme(…)` if we can't resolve the path
  389|       ['bg-[theme(colors.foo.1000)]', 'bg-[theme(colors.foo.1000)]'],
  390| 
  391|       // Keep `theme(…)` if we can't resolve the path, but still try to convert the
  392|       // fallback value.
  393|       ['bg-[theme(colors.foo.1000,theme(colors.red.500))]', 'bg-red-500'],
  394| 
  395|       // Use `theme(…)` (deeply nested) inside of a `calc(…)` function
  396|       ['text-[calc(theme(fontSize.xs)*2)]', 'text-[calc(var(--text-xs)*2)]'],
  397| 
  398|       // Arbitrary value
  399|       ['bg-[theme(colors.red.500/75%)]', 'bg-red-500/75'],
  400|       ['bg-[theme(colors.red.500/12.34%)]', 'bg-red-500/[12.34%]'],
  401| 
  402|       // Arbitrary value with different casing
  403|       ['bg-[#fff]', 'bg-white'],
  404|       ['bg-[#FFF]', 'bg-white'],
  405| 
  406|       // Values that don't contain only `theme(…)` calls should not be converted to
  407|       // use a modifier since the color is not the whole value.
  408|       [
  409|         'shadow-[shadow:inset_0px_1px_theme(colors.white/15%)]',
  410|         'shadow-[inset_0px_1px_--theme(--color-white/15%)]',
  411|       ],
  412| 
  413|       // Arbitrary value, where the candidate already contains a modifier
  414|       // This should still migrate the `theme(…)` syntax to the modern syntax.
  415|       ['bg-[theme(colors.red.500/50%)]/50', 'bg-[--theme(--color-red-500/50%)]/50'],
  416| 
  417|       // Variants, we can't use `var(…)` especially inside of `@media(…)`. But
  418|       // since the value matches the `lg` breakpoint exactly, we can migrate to
  419|       // the `max-lg` variant.
  420|       ['max-[theme(screens.lg)]:flex', 'max-lg:flex'],
  421|       ['min-[theme(screens.lg)]:flex', 'lg:flex'], // We could also map to `min-lg:flex`
  422|       // There are no variables for `--spacing` multiples, so we can't convert this
  423|       ['max-[theme(spacing.4)]:flex', 'max-[theme(spacing.4)]:flex'],
  424| 
  425|       // This test in itself doesn't make much sense. But we need to make sure
  426|       // that this doesn't end up as the modifier in the candidate itself.
  427|       ['max-[theme(spacing.4/50)]:flex', 'max-[theme(spacing.4/50)]:flex'],
  428| 
  429|       // `theme(…)` calls in another CSS function is replaced correctly.
  430|       // Additionally we remove unnecessary whitespace.
  431|       ['grid-cols-[min(50%_,_theme(spacing.80))_auto]', 'grid-cols-[min(50%,--spacing(80))_auto]'],
  432| 
  433|       // `calc(var(--spacing)*…)` to `--spacing(…)`
  434|       ['pt-[min(20%,calc(var(--spacing)*8))]', 'pt-[min(20%,--spacing(8))]'],
  435|       ['pt-[min(20%,calc(var(--spacing)*var(--other)))]', 'pt-[min(20%,--spacing(var(--other)))]'],
  436|       ['pt-[calc(var(--spacing)*8)]', 'pt-8'],
  437|       ['pt-[calc(var(--spacing)*var(--other))]', 'pt-[--spacing(var(--other))]'],
  438| 
  439|       // Renamed theme keys
  440|       ['max-w-[theme(screens.md)]', 'max-w-(--breakpoint-md)'],
  441|       ['w-[theme(maxWidth.md)]', 'w-md'],
  442| 
  443|       // Arbitrary property to static utility
  444|       // Map number to keyword-like value
  445|       ['leading-[1]', 'leading-none'],
  446| 
  447|       // Arbitrary value to bare value
  448|       ['border-[2px]', 'border-2'],
  449|       ['border-[1234px]', 'border-1234'],
  450| 
  451|       // Arbitrary value with data type, to more specific arbitrary value
  452|       ['bg-[position:123px]', 'bg-position-[123px]'],
  453|       ['bg-[size:123px]', 'bg-size-[123px]'],
  454| 
  455|       // Arbitrary value with inferred data type, to more specific arbitrary value
  456|       ['bg-[123px]', 'bg-position-[123px]'],
  457| 
  458|       // Arbitrary value with spacing mul
  459|       ['w-[64rem]', 'w-256'],
  460| 
  461|       // Arbitrary value to bare value with percentage
  462|       ['from-[25%]', 'from-25%'],
  463| 
  464|       // Arbitrary percentage value must be a whole number. Should not migrate to
  465|       // a bare value.
  466|       ['from-[2.5%]', 'from-[2.5%]'],
  467| 
  468|       // Negative arbitrary values can be simplified
  469|       // 1. Try to move the sign _inside_ the arbitrary value
  470|       // 2. Try to move the sign _out_ of the arbitrary value
  471|       ['-mt-[12rem]', '-mt-48'], // Arbitrary value → bare value
  472|       ['-mt-[-12rem]', 'mt-48'], // Double negation
  473|       ['-mt-[12.34rem]', 'mt-[-12.34rem]'], // Move `-` inside
  474|       ['-mt-[-12.34rem]', 'mt-[12.34rem]'], // Move `-` inside, double negation
  475|       ['-mt-[12.34px]', 'mt-[-12.34px]'],
  476|       ['-mt-[-12.34px]', 'mt-[12.34px]'],
  477|       ['-mt-[492px]', '-mt-123'], // Moving inside, allows us to migrate to a bare value
  478|       ['-mt-[calc(-1*492px)]', 'mt-123'], // Double negation and constant folding into bare value
  479|       ['-mt-[-492px]', 'mt-123'],
  480|       ['-mt-[calc(-1*-492px)]', '-mt-123'], // Constant folding with calc expressions
  481|       ['-mt-(--my-var)', '-mt-(--my-var)'], // Keep as-is
  482|       ['-mt-[var(--my-var)]', '-mt-(--my-var)'], // Keep as-is, but convert to shorthand
  483|       ['mt-[calc(var(--my-var)*-1)]', '-mt-(--my-var)'], // Move `-` out
  484|       ['mt-[calc(-1*var(--my-var))]', '-mt-(--my-var)'], // Move `-` out
  485|       ['-mt-[calc(var(--my-var)*-1)]', 'mt-(--my-var)'], // Move `-` out
  486|       ['-mt-[calc(-1*var(--my-var))]', 'mt-(--my-var)'], // Move `-` out
  487|       ['mt-[calc(-1*calc(-1*var(--my-var)))]', 'mt-(--my-var)'], // Move `-` out
  488|       ['-mt-[calc(-1*calc(-1*var(--my-var)))]', '-mt-(--my-var)'], // Move `-` out
  489|     ])(testName, { timeout }, async (candidate, expected) => {
  490|       let input = css`
  491|         @import 'tailwindcss';
  492|         @theme {
  493|           --color-white: #fff;
  494|         }
  495|       `
  496| 
  497|       await expectCanonicalization(input, candidate, expected)
  498|     })
  499|   })
  500| 
  501|   describe('arbitrary utilities', () => {
  502|     test('migrate with custom static utility `@utility custom {…}`', { timeout }, async () => {
  503|       let candidate = '[--key:value]'
  504|       let expected = 'custom'
  505| 
  506|       let input = css`
  507|         @import 'tailwindcss';
  508|         @theme {
  509|           --*: initial;
  510|         }
  511|         @utility custom {
  512|           --key: value;
  513|         }
  514|       `
  515| 
  516|       await expectCanonicalization(input, candidate, expected)
  517|     })
  518| 
  519|     test(
  520|       'migrate with custom functional utility `@utility custom-* {…}`',
  521|       { timeout },
  522|       async () => {
  523|         let candidate = '[--key:value]'
  524|         let expected = 'custom-value'
  525| 
  526|         let input = css`
  527|           @import 'tailwindcss';
  528|           @theme {
  529|             --*: initial;
  530|           }
  531|           @utility custom-* {
  532|             --key: --value('value');
  533|           }
  534|         `
  535| 
  536|         await expectCanonicalization(input, candidate, expected)
  537|       },
  538|     )
  539| 
  540|     test(
  541|       'migrate with custom functional utility `@utility custom-* {…}` that supports bare values',
  542|       { timeout },
  543|       async () => {
  544|         let candidate = '[--resolved-value:4]'
  545|         let expected = 'example-4'
  546| 
  547|         let input = css`
  548|           @import 'tailwindcss';
  549|           @theme {
  550|             --*: initial;
  551|           }
  552|           @utility example-* {
  553|             --resolved-value: --value(integer);
  554|           }
```

### packages/@tailwindcss-upgrade/src/codemods/template/migrate-arbitrary-variants.ts (lines 1 to 56 of 56)
```
    1| import { cloneCandidate } from '../../../../tailwindcss/src/candidate'
    2| import {
    3|   PRE_COMPUTED_VARIANTS_KEY,
    4|   prepareDesignSystemStorage,
    5|   VARIANT_SIGNATURE_KEY,
    6| } from '../../../../tailwindcss/src/canonicalize-candidates'
    7| import type { Config } from '../../../../tailwindcss/src/compat/plugin-api'
    8| import type { DesignSystem } from '../../../../tailwindcss/src/design-system'
    9| import type { Writable } from '../../../../tailwindcss/src/types'
   10| import { replaceObject } from '../../../../tailwindcss/src/utils/replace-object'
   11| import { walkVariants } from '../../utils/walk-variants'
   12| 
   13| export function migrateArbitraryVariants(
   14|   baseDesignSystem: DesignSystem,
   15|   _userConfig: Config | null,
   16|   rawCandidate: string,
   17| ): string {
   18|   let designSystem = prepareDesignSystemStorage(baseDesignSystem)
   19|   let signatures = designSystem.storage[VARIANT_SIGNATURE_KEY].get(null)
   20|   let variants = designSystem.storage[PRE_COMPUTED_VARIANTS_KEY].get(null)
   21| 
   22|   for (let readonlyCandidate of designSystem.parseCandidate(rawCandidate)) {
   23|     // We are only interested in the variants
   24|     if (readonlyCandidate.variants.length <= 0) return rawCandidate
   25| 
   26|     // The below logic makes use of mutation. Since candidates in the
   27|     // DesignSystem are cached, we can't mutate them directly.
   28|     let candidate = cloneCandidate(readonlyCandidate) as Writable<typeof readonlyCandidate>
   29| 
   30|     for (let [variant] of walkVariants(candidate)) {
   31|       if (variant.kind === 'compound') continue
   32| 
   33|       let targetString = designSystem.printVariant(variant)
   34|       let targetSignature = signatures.get(targetString)
   35|       if (typeof targetSignature !== 'string') continue
   36| 
   37|       let foundVariants = variants.get(targetSignature)
   38|       if (foundVariants.length === 0) continue
   39| 
   40|       // The variant is already in a canonical form, e.g.: `min-lg` and `lg`
   41|       // produce the same CSS, but both are valid so we keep them as-is.
   42|       if (foundVariants.includes(targetString)) continue
   43| 
   44|       let foundVariant = foundVariants[0]
   45|       let parsedVariant = designSystem.parseVariant(foundVariant)
   46|       if (parsedVariant === null) continue
   47| 
   48|       replaceObject(variant, parsedVariant)
   49|     }
   50| 
   51|     return designSystem.printCandidate(candidate)
   52|   }
   53| 
   54|   return rawCandidate
   55| }
   56| 
```

### CHANGELOG.md (lines 1 to 200 of 4416)
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
   22| 
   23| ## [4.3.3] - 2026-07-16
   24| 
   25| ### Fixed
   26| 
   27| - Support `--watch --poll[=ms]` in `@tailwindcss/cli` when filesystem events are unreliable or unavailable ([#20297](https://github.com/tailwindlabs/tailwindcss/pull/20297))
   28| - Canonicalization: match arbitrary hex colors against theme colors case-insensitively (e.g. `bg-[#fff]` and `bg-[#FFF]` → `bg-white`) ([#20298](https://github.com/tailwindlabs/tailwindcss/pull/20298))
   29| - Prevent Preflight from overriding Firefox's native `iframe:focus-visible` outline styles ([#20292](https://github.com/tailwindlabs/tailwindcss/pull/20292))
   30| - Ensure `theme('colors.foo')` in JS plugins resolves correctly when both `--color-foo` and `--color-foo-bar` exist ([#20299](https://github.com/tailwindlabs/tailwindcss/pull/20299))
   31| - Ensure fractional opacity modifiers work with named shadow sizes like `shadow-sm/12.5`, `text-shadow-sm/12.5`, `drop-shadow-sm/12.5`, and `inset-shadow-sm/12.5` ([#20302](https://github.com/tailwindlabs/tailwindcss/pull/20302))
   32| - Parse selectors like `[data-foo]div` as two selectors instead of one ([#20303](https://github.com/tailwindlabs/tailwindcss/pull/20303))
   33| - Ensure `@tailwindcss/postcss` rebuilds when a preprocessor like Sass changes the input CSS without changing the input file on disk ([#20310](https://github.com/tailwindlabs/tailwindcss/pull/20310))
   34| - Ensure CSS nesting is handled even when Lightning CSS isn't run, such as in `@tailwindcss/browser` and Tailwind Play ([#20124](https://github.com/tailwindlabs/tailwindcss/pull/20124))
   35| - Prevent achromatic theme colors from shifting hue when mixed in polar color spaces like `oklch` ([#20314](https://github.com/tailwindlabs/tailwindcss/pull/20314))
   36| - Ensure `--spacing(0)` is optimized to `0px` instead of `0` so it remains a `<length>` when used in `calc(…)` ([#20319](https://github.com/tailwindlabs/tailwindcss/pull/20319))
   37| - Load `@parcel/watcher` only when needed in `@tailwindcss/cli --watch` mode, so one-off builds and `--watch --poll` work when `@parcel/watcher` can't be loaded ([#20325](https://github.com/tailwindlabs/tailwindcss/pull/20325))
   38| - Use explicit platform fonts instead of `system-ui` and `ui-sans-serif` so CJK text respects the page's `lang` attribute on Windows ([#20318](https://github.com/tailwindlabs/tailwindcss/pull/20318))
   39| - Prevent `@tailwindcss/upgrade` from rewriting ignored files when run from a subdirectory ([#20329](https://github.com/tailwindlabs/tailwindcss/pull/20329))
   40| - Ensure earlier `@source` rules pointing to nested files are scanned when later `@source` rules point to files in parent folders ([#20335](https://github.com/tailwindlabs/tailwindcss/pull/20335))
   41| - Prevent `@tailwindcss/vite` from triggering full page reloads when scanned files are processed by Vite but haven't been loaded as modules yet ([#20336](https://github.com/tailwindlabs/tailwindcss/pull/20336))
   42| 
   43| ## [4.3.2] - 2026-06-26
   44| 
   45| ### Fixed
   46| 
   47| - Support bare spacing values for `auto-rows-*` and `auto-cols-*` utilities (e.g. `auto-rows-12` and `auto-cols-16`) ([#20229](https://github.com/tailwindlabs/tailwindcss/pull/20229))
   48| - Prevent `@tailwindcss/cli` in `--watch` mode from crashing on Windows when `@source` points to a directory that doesn't exist ([#20242](https://github.com/tailwindlabs/tailwindcss/pull/20242))
   49| - Prevent `@tailwindcss/vite` from crashing in Deno v2.8.x when `context.parentURL` is not a valid URL ([#20245](https://github.com/tailwindlabs/tailwindcss/pull/20245))
   50| - Ensure `@tailwindcss/cli` in `--watch` mode rebuilds when the input CSS file changes in an ignored directory ([#20246](https://github.com/tailwindlabs/tailwindcss/pull/20246))
   51| - Allow `@variant` rules used in `addBase(…)` to use custom variants defined later ([#20247](https://github.com/tailwindlabs/tailwindcss/pull/20247))
   52| - Prevent `@tailwindcss/vite` from crashing during HMR when scanned files or directories are deleted ([#20259](https://github.com/tailwindlabs/tailwindcss/pull/20259))
   53| - Generate `font-size` instead of `color` declarations for `text-[--spacing(…)]` ([#20260](https://github.com/tailwindlabs/tailwindcss/pull/20260))
   54| - Prevent `@source` patterns from scanning unrelated sibling files and folders ([#20263](https://github.com/tailwindlabs/tailwindcss/pull/20263))
   55| - Extract class candidates adjacent to Template Toolkit delimiters like `%]…[%` in `.tt`, `.tt2`, and `.tx` files ([#20269](https://github.com/tailwindlabs/tailwindcss/pull/20269))
   56| - Extract class candidates from conditional Maud syntax like `p.text-black[condition]` ([#20269](https://github.com/tailwindlabs/tailwindcss/pull/20269))
   57| - Prevent `@position-try` rules from triggering unknown at-rule warnings when optimizing CSS ([#20277](https://github.com/tailwindlabs/tailwindcss/pull/20277))
   58| - Support class suggestions for named opacity modifiers from `--opacity` theme values ([#20287](https://github.com/tailwindlabs/tailwindcss/pull/20287))
   59| - Prevent type errors in `@tailwindcss/postcss` when used with newer PostCSS patch releases ([#20289](https://github.com/tailwindlabs/tailwindcss/pull/20289))
   60| 
   61| ## [4.3.1] - 2026-06-12
   62| 
   63| ### Added
   64| 
   65| - Add `--silent` option to suppress output in `@tailwindcss/cli` ([#20100](https://github.com/tailwindlabs/tailwindcss/pull/20100))
   66| 
   67| ### Fixed
   68| 
   69| - Remove deprecation warnings by using `Module#registerHooks` instead of `Module#register` on Node 26+ ([#20028](https://github.com/tailwindlabs/tailwindcss/pull/20028))
   70| - Canonicalization: don't crash when plugin utilities throw for unsupported values ([#20052](https://github.com/tailwindlabs/tailwindcss/pull/20052))
   71| - Allow `@apply` to be used with CSS mixins ([#19427](https://github.com/tailwindlabs/tailwindcss/pull/19427))
   72| - Ensure `not-*` correctly negates `@container` queries, including `style(…)` queries ([#20059](https://github.com/tailwindlabs/tailwindcss/pull/20059))
   73| - Ensure `drop-shadow-*` color utilities work with custom shadow values containing `calc(…)` ([#20080](https://github.com/tailwindlabs/tailwindcss/pull/20080))
   74| - Fix 'Sourcemap is likely to be incorrect' warnings when using `@tailwindcss/vite` ([#20103](https://github.com/tailwindlabs/tailwindcss/pull/20103))
   75| - Ensure `@tailwindcss/webpack` can be installed in Rspack projects without requiring `webpack` as a peer dependency ([#20027](https://github.com/tailwindlabs/tailwindcss/pull/20027))
   76| - Canonicalization: don't suggest invalid `calc(…)` expressions (e.g. `px-[calc(1rem+0px)]` → `px-[calc(1rem+0)]`) ([#20127](https://github.com/tailwindlabs/tailwindcss/pull/20127))
   77| - Canonicalization: avoid suggesting large spacing-scale values for arbitrary lengths (e.g. `left-[99999px]` → `left-[99999px]`, not `left-24999.75`) ([#20130](https://github.com/tailwindlabs/tailwindcss/pull/20130))
   78| - Ensure `@tailwindcss/cli` in `--watch` mode recovers when a tracked dependency is deleted and restored ([#20137](https://github.com/tailwindlabs/tailwindcss/pull/20137))
   79| - Ensure standalone `@tailwindcss/cli` binaries are ignored when scanning for class candidates ([#20139](https://github.com/tailwindlabs/tailwindcss/pull/20139))
   80| - Ensure class candidates are extracted from Twig `addClass(…)` and `removeClass(…)` calls ([#20198](https://github.com/tailwindlabs/tailwindcss/pull/20198))
   81| - Don't crash in the Ruby or Vue preprocessors when scanning files containing invalid UTF-8 bytes ([#19588](https://github.com/tailwindlabs/tailwindcss/pull/19588))
   82| - Allow `@variant` to be used inside `addBase` ([#19480](https://github.com/tailwindlabs/tailwindcss/pull/19480))
   83| - Ensure `@source` globs with symlinks are preserved ([#20203](https://github.com/tailwindlabs/tailwindcss/pull/20203))
   84| - Ensure later `@source` rules can re-include files excluded by earlier `@source not` rules ([#20203](https://github.com/tailwindlabs/tailwindcss/pull/20203))
   85| - Upgrade: don't migrate empty class rules to invalid `@utility` rules ([#20205](https://github.com/tailwindlabs/tailwindcss/pull/20205))
   86| - Ensure transitions between `inset-shadow-none` and other inset shadows work correctly ([#20208](https://github.com/tailwindlabs/tailwindcss/pull/20208))
   87| - Ensure explicitly referenced `@source` directories are scanned even when ignored by git ([#20214](https://github.com/tailwindlabs/tailwindcss/pull/20214))
   88| - Ensure `@source` globs ending in `**/*` preserve dynamic path segments to avoid scanning too many files ([#20217](https://github.com/tailwindlabs/tailwindcss/pull/20217))
   89| - Canonicalization: don't fold `calc(…)` divisions when the result would require high precision (e.g. `w-[calc(100%/3.5)]` → `w-[calc(100%/3.5)]`, not `w-[28.571428571428573%]`) ([#20221](https://github.com/tailwindlabs/tailwindcss/pull/20221))
   90| - Serve ESM type declarations to ESM importers of `@tailwindcss/postcss` ([#20228](https://github.com/tailwindlabs/tailwindcss/pull/20228))
   91| 
   92| ### Changed
   93| 
   94| - Generate `0` instead of `calc(var(--spacing) * 0)` for spacing utilities like `m-0` and `left-0` ([#20196](https://github.com/tailwindlabs/tailwindcss/pull/20196))
   95| - Generate `var(--spacing)` instead of `calc(var(--spacing) * 1)` for spacing utilities like `m-1` and `left-1` ([#20196](https://github.com/tailwindlabs/tailwindcss/pull/20196))
   96| 
   97| ## [4.3.0] - 2026-05-08
   98| 
   99| ### Added
  100| 
  101| - Add `@container-size` utility ([#18901](https://github.com/tailwindlabs/tailwindcss/pull/18901))
  102| - Add `scrollbar-{auto,thin,none}` utilities for `scrollbar-width`, and `scrollbar-thumb-*` / `scrollbar-track-*` color utilities for `scrollbar-color` ([#19981](https://github.com/tailwindlabs/tailwindcss/pull/19981), [#20019](https://github.com/tailwindlabs/tailwindcss/pull/20019))
  103| - Add `scrollbar-gutter-*` utilities ([#20018](https://github.com/tailwindlabs/tailwindcss/pull/20018))
  104| - Add `zoom-*` utilities ([#20020](https://github.com/tailwindlabs/tailwindcss/pull/20020))
  105| - Add `tab-*` utilities ([#20022](https://github.com/tailwindlabs/tailwindcss/pull/20022))
  106| - Allow using `@variant` with stacked variants (e.g. `@variant hover:focus { … }`) ([#19996](https://github.com/tailwindlabs/tailwindcss/pull/19996))
  107| - Allow using `@variant` with compound variants (e.g. `@variant hover, focus { … }`) ([#19996](https://github.com/tailwindlabs/tailwindcss/pull/19996))
  108| - Support `--default(…)` in `--value(…)` and `--modifier(…)` for functional `@utility` definitions ([#19989](https://github.com/tailwindlabs/tailwindcss/pull/19989))
  109| 
  110| ### Fixed
  111| 
  112| - Ensure `@plugin` resolves package JavaScript entries instead of browser CSS entries when using `@tailwindcss/vite` ([#19949](https://github.com/tailwindlabs/tailwindcss/pull/19949))
  113| - Fix relative `@import` and `@plugin` paths resolving from the wrong directory when using `@tailwindcss/vite` ([#19965](https://github.com/tailwindlabs/tailwindcss/pull/19965))
  114| - Ensure CSS files containing `@variant` are processed by `@tailwindcss/vite` ([#19966](https://github.com/tailwindlabs/tailwindcss/pull/19966))
  115| - Resolve imports relative to `base` when `result.opts.from` is not provided when using `@tailwindcss/postcss` ([#19980](https://github.com/tailwindlabs/tailwindcss/pull/19980))
  116| - Canonicalization: preserve significant `_` whitespace in arbitrary values ([#19986](https://github.com/tailwindlabs/tailwindcss/pull/19986))
  117| - Canonicalization: add parentheses when removing whitespace from arbitrary values would hurt readability (e.g. `w-[calc(100%---spacing(60))]` → `w-[calc(100%-(--spacing(60)))]`) ([#19986](https://github.com/tailwindlabs/tailwindcss/pull/19986))
  118| - Canonicalization: preserve the original unit in arbitrary values instead of normalizing to base units (e.g. `-mt-[20in]` → `mt-[-20in]`, not `mt-[-1920px]`) ([#19988](https://github.com/tailwindlabs/tailwindcss/pull/19988))
  119| - Canonicalization: migrate arbitrary `:has()` variants from `[&:has(…)]` to `has-[…]` ([#19991](https://github.com/tailwindlabs/tailwindcss/pull/19991))
  120| - Upgrade: don’t migrate inline `style` attributes (e.g. `style="flex-grow: 1"` → `style="flex-grow: 1"`, not `style="grow: 1"`) ([#19918](https://github.com/tailwindlabs/tailwindcss/pull/19918))
  121| - Allow multiple `@utility` definitions with the same name but different value types ([#19777](https://github.com/tailwindlabs/tailwindcss/pull/19777))
  122| - Export missing `PluginWithConfig` type from `tailwindcss/plugin` to fix errors when inferring plugin config types ([#19707](https://github.com/tailwindlabs/tailwindcss/pull/19707))
  123| - Ensure `start` and `end` legacy utilities without values do not generate CSS ([#20003](https://github.com/tailwindlabs/tailwindcss/pull/20003))
  124| - Ensure `--value(…)` is required in functional `@utility` definitions ([#20005](https://github.com/tailwindlabs/tailwindcss/pull/20005))
  125| - Canonicalization: preserve required whitespace around operators in negated arbitrary values (e.g. `-left-[(var(--a)+var(--b))]`) ([#20011](https://github.com/tailwindlabs/tailwindcss/pull/20011))
  126| 
  127| ## [4.2.4] - 2026-04-21
  128| 
  129| ### Fixed
  130| 
  131| - Ensure imports in `@import` and `@plugin` still resolve correctly when using Vite aliases in `@tailwindcss/vite` ([#19947](https://github.com/tailwindlabs/tailwindcss/pull/19947))
  132| 
  133| ## [4.2.3] - 2026-04-20
  134| 
  135| ### Fixed
  136| 
  137| - Canonicalization: improve canonicalization for `tracking-*` utilities by preferring non-negative utilities (e.g. `-tracking-tighter` → `tracking-wider`) ([#19827](https://github.com/tailwindlabs/tailwindcss/pull/19827))
  138| - Fix crash due to invalid characters in candidate (exceeding valid unicode code point range) ([#19829](https://github.com/tailwindlabs/tailwindcss/pull/19829))
  139| - Ensure query params in imports are considered unique resources when using `@tailwindcss/webpack` ([#19723](https://github.com/tailwindlabs/tailwindcss/pull/19723))
  140| - Canonicalization: collapse arbitrary values into shorthand utilities (e.g. `px-[1.2rem] py-[1.2rem]` → `p-[1.2rem]`) ([#19837](https://github.com/tailwindlabs/tailwindcss/pull/19837))
  141| - Canonicalization: collapse `border-{t,b}-*` into `border-y-*`, `border-{l,r}-*` into `border-x-*`, and `border-{t,r,b,l}-*` into `border-*` ([#19842](https://github.com/tailwindlabs/tailwindcss/pull/19842))
  142| - Canonicalization: collapse `scroll-m{t,b}-*` into `scroll-my-*`, `scroll-m{l,r}-*` into `scroll-mx-*`, and `scroll-m{t,r,b,l}-*` into `scroll-m-*` ([#19842](https://github.com/tailwindlabs/tailwindcss/pull/19842))
  143| - Canonicalization: collapse `scroll-p{t,b}-*` into `scroll-py-*`, `scroll-p{l,r}-*` into `scroll-px-*`, and `scroll-p{t,r,b,l}-*` into `scroll-p-*` ([#19842](https://github.com/tailwindlabs/tailwindcss/pull/19842))
  144| - Canonicalization: collapse `overflow-{x,y}-*` into `overflow-*` ([#19842](https://github.com/tailwindlabs/tailwindcss/pull/19842))
  145| - Canonicalization: collapse `overscroll-{x,y}-*` into `overscroll-*` ([#19842](https://github.com/tailwindlabs/tailwindcss/pull/19842))
  146| - Read from `--placeholder-color` instead of `--background-color` for `placeholder-*` utilities ([#19843](https://github.com/tailwindlabs/tailwindcss/pull/19843))
  147| - Upgrade: ensure files are not emptied out when killing the upgrade process while it's running ([#19846](https://github.com/tailwindlabs/tailwindcss/pull/19846))
  148| - Upgrade: use `config.content` when migrating from Tailwind CSS v3 to Tailwind CSS v4 ([#19846](https://github.com/tailwindlabs/tailwindcss/pull/19846))
  149| - Upgrade: never migrate files that are ignored by git ([#19846](https://github.com/tailwindlabs/tailwindcss/pull/19846))
  150| - Add `.env` and `.env.*` to default ignored content files ([#19846](https://github.com/tailwindlabs/tailwindcss/pull/19846))
  151| - Canonicalization: migrate `overflow-ellipsis` into `text-ellipsis` ([#19849](https://github.com/tailwindlabs/tailwindcss/pull/19849))
  152| - Canonicalization: migrate `start-full` → `inset-s-full`, `start-auto` → `inset-s-auto`, `start-px` → `inset-s-px`, and `start-<number>` → `inset-s-<number>` as well as negative versions ([#19849](https://github.com/tailwindlabs/tailwindcss/pull/19849))
  153| - Canonicalization: migrate `end-full` → `inset-e-full`, `end-auto` → `inset-e-auto`, `end-px` → `inset-e-px`, and `end-<number>` → `inset-e-<number>` as well as negative versions ([#19849](https://github.com/tailwindlabs/tailwindcss/pull/19849))
  154| - Canonicalization: move the `-` sign inside the arbitrary value `-left-[9rem]` → `left-[-9rem]` ([#19858](https://github.com/tailwindlabs/tailwindcss/pull/19858))
  155| - Canonicalization: move the `-` sign outside the arbitrary value `ml-[calc(-1*var(--width))]` → `-ml-(--width)` ([#19858](https://github.com/tailwindlabs/tailwindcss/pull/19858))
  156| - Improve performance when scanning JSONL / NDJSON files ([#19862](https://github.com/tailwindlabs/tailwindcss/pull/19862))
  157| - Support `NODE_PATH` environment variable in standalone CLI ([#19617](https://github.com/tailwindlabs/tailwindcss/pull/19617))
  158| 
  159| ## [4.2.2] - 2026-03-18
  160| 
  161| ### Fixed
  162| 
  163| - Don't crash when candidates contain prototype properties like `row-constructor` ([#19725](https://github.com/tailwindlabs/tailwindcss/pull/19725))
  164| - Canonicalize `calc(var(--spacing)*…)` expressions into `--spacing(…)` ([#19769](https://github.com/tailwindlabs/tailwindcss/pull/19769))
  165| - Fix crash in canonicalization step when handling utilities containing `@property` at-rules (e.g. `shadow-sm border`) ([#19727](https://github.com/tailwindlabs/tailwindcss/pull/19727))
  166| - Skip full reload for server only modules scanned by client CSS when using `@tailwindcss/vite` ([#19745](https://github.com/tailwindlabs/tailwindcss/pull/19745))
  167| - Add support for Vite 8 in `@tailwindcss/vite` ([#19790](https://github.com/tailwindlabs/tailwindcss/pull/19790))
  168| - Improve canonicalization for bare values exceeding default spacing scale suggestions (e.g. `w-1234 h-1234` → `size-1234`) ([#19809](https://github.com/tailwindlabs/tailwindcss/pull/19809))
  169| - Fix canonicalization resulting in empty list (e.g. `w-5 h-5 size-5` → `''` instead of `size-5`) ([#19812](https://github.com/tailwindlabs/tailwindcss/pull/19812))
  170| - Resolve tsconfig paths to allow for `@import '@/path/to/file';` when using `@tailwindcss/vite` ([#19803](https://github.com/tailwindlabs/tailwindcss/pull/19803))
  171| 
  172| ## [4.2.1] - 2026-02-23
  173| 
  174| ### Fixed
  175| 
  176| - Allow trailing dash in functional utility names for backwards compatibility ([#19696](https://github.com/tailwindlabs/tailwindcss/pull/19696))
  177| - Properly detect classes containing `.` characters within curly braces in MDX files ([#19711](https://github.com/tailwindlabs/tailwindcss/pull/19711))
  178| 
  179| ## [4.2.0] - 2026-02-18
  180| 
  181| ### Added
  182| 
  183| - Add mauve, olive, mist, and taupe color palettes to the default theme ([#19627](https://github.com/tailwindlabs/tailwindcss/pull/19627))
  184| - Add `@tailwindcss/webpack` package to run Tailwind CSS as a webpack plugin ([#19610](https://github.com/tailwindlabs/tailwindcss/pull/19610))
  185| - Add `pbs-*` and `pbe-*` utilities for `padding-block-start` and `padding-block-end` ([#19601](https://github.com/tailwindlabs/tailwindcss/pull/19601))
  186| - Add `mbs-*` and `mbe-*` utilities for `margin-block-start` and `margin-block-end` ([#19601](https://github.com/tailwindlabs/tailwindcss/pull/19601))
  187| - Add `scroll-pbs-*` and `scroll-pbe-*` utilities for `scroll-padding-block-start` and `scroll-padding-block-end` ([#19601](https://github.com/tailwindlabs/tailwindcss/pull/19601))
  188| - Add `scroll-mbs-*` and `scroll-mbe-*` utilities for `scroll-margin-block-start` and `scroll-margin-block-end` ([#19601](https://github.com/tailwindlabs/tailwindcss/pull/19601))
  189| - Add `border-bs-*` and `border-be-*` utilities for `border-block-start` and `border-block-end` ([#19601](https://github.com/tailwindlabs/tailwindcss/pull/19601))
  190| - Add `inline-*`, `min-inline-*`, `max-inline-*` utilities for `inline-size`, `min-inline-size`, and `max-inline-size` ([#19612](https://github.com/tailwindlabs/tailwindcss/pull/19612))
  191| - Add `block-*`, `min-block-*`, `max-block-*` utilities for `block-size`, `min-block-size`, and `max-block-size` ([#19612](https://github.com/tailwindlabs/tailwindcss/pull/19612))
  192| - Add `inset-s-*`, `inset-e-*`, `inset-bs-*`, `inset-be-*` utilities for `inset-inline-start`, `inset-inline-end`, `inset-block-start`, and `inset-block-end` ([#19613](https://github.com/tailwindlabs/tailwindcss/pull/19613))
  193| - Add `font-features-*` utility for `font-feature-settings` ([#19623](https://github.com/tailwindlabs/tailwindcss/pull/19623))
  194| 
  195| ### Fixed
  196| 
  197| - Prevent double `@supports` wrapper for `color-mix` values ([#19450](https://github.com/tailwindlabs/tailwindcss/pull/19450))
  198| - Allow whitespace around `@source inline()` argument ([#19461](https://github.com/tailwindlabs/tailwindcss/pull/19461))
  199| - Emit comment when source maps are saved to files when using `@tailwindcss/cli` ([#19447](https://github.com/tailwindlabs/tailwindcss/pull/19447))
  200| - Detect utilities containing capital letters followed by numbers ([#19465](https://github.com/tailwindlabs/tailwindcss/pull/19465))
```
