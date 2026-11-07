# PR pack: tailwindlabs/tailwindcss#20397
Title: Don't scan ignored folders using `.gitignore` safelist setup
Merge commit: 46df7ee2fc4ae822d414d35bbd48be024e5cb1c0

## Diff
```diff
diff --git a/CHANGELOG.md b/CHANGELOG.md
index 64c0ea940f13..79baa9c65ccb 100644
--- a/CHANGELOG.md
+++ b/CHANGELOG.md
@@ -23,6 +23,7 @@ and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0
 - Ensure `@tailwindcss/oxide` falls back to WASM on platforms without native bindings ([#20383](https://github.com/tailwindlabs/tailwindcss/pull/20383))
 - Detect classes in Ruby percent literals using angle brackets or custom delimiters (e.g. `%w<flex>`, `%w|flex|`), including in Slim and Haml templates ([#20387](https://github.com/tailwindlabs/tailwindcss/pull/20387))
 - Preserve whitespace in `--default(…)` values in custom functional utilities (e.g. `--default(box alphabetic)` no longer becomes `boxalphabetic`) ([#20392](https://github.com/tailwindlabs/tailwindcss/pull/20392))
+- Don't scan gitignored directories (e.g. `node_modules` and `.git`) when the project uses a safelist-style `.gitignore` (e.g. `/*` followed by `!/…` negations) ([#20397](https://github.com/tailwindlabs/tailwindcss/discussions/20397))
 
 ## [4.3.3] - 2026-07-16
 
diff --git a/crates/oxide/src/scanner/sources.rs b/crates/oxide/src/scanner/sources.rs
index 4a8c6ddf59df..53c09387fd6b 100644
--- a/crates/oxide/src/scanner/sources.rs
+++ b/crates/oxide/src/scanner/sources.rs
@@ -763,12 +763,11 @@ pub fn public_source_entries_to_private_source_entries(
         .collect::<Vec<_>>();
 
     // Compiled `.gitignore` matchers are cached per directory so we read and parse each
-    // `.gitignore` file at most once, even though entries commonly share ancestor directories
-    // (e.g. the repository root). A cached `None` means the directory has no `.gitignore` file.
+    // `.gitignore` file at most once, even though entries commonly share ancestor directories (e.g.
+    // the repository root). A cached `None` means the directory has no `.gitignore` file.
     let mut gitignores: FxHashMap<PathBuf, Option<Gitignore>> = FxHashMap::default();
 
-    // Boundary for the `.gitignore` walk when a source is not inside a git repository (see
-    // below).
+    // Boundary for the `.gitignore` walk when a source is not inside a git repository (see below).
     let cwd = std::env::current_dir()
         .map(|cwd| dunce::canonicalize(&cwd).unwrap_or(cwd))
         .ok();
@@ -790,18 +789,39 @@ pub fn public_source_entries_to_private_source_entries(
                     let gitignore = gitignores.entry(dir.to_path_buf()).or_insert_with(|| {
                         let path = dir.join(".gitignore");
 
-                        // `Gitignore::new` roots the matcher at the directory
-                        // containing the file, so patterns match relative to it.
+                        // `Gitignore::new` roots the matcher at the directory containing the file,
+                        // so patterns match relative to it.
                         path.is_file().then(|| Gitignore::new(&path).0)
                     });
 
-                    if let Some(gitignore) = gitignore {
-                        if gitignore
-                            .matched_path_or_any_parents(&base, true)
-                            .is_ignore()
-                        {
-                            source = SourceEntry::External { base: base.into() };
-                            break;
+                    // Only `.gitignore` files in ancestors of `base` can ignore `base` itself.
+                    // Patterns in `base`'s own `.gitignore` only match paths _inside_ `base`, never
+                    // `base` itself (the file walker still applies them to `base`'s contents).
+                    //
+                    // Skipping `base`'s own `.gitignore` also prevents a false positive for
+                    // whitelist style `.gitignore` files, because relativizing `base` against
+                    // itself yields the empty path, which incorrectly matches `/*`.
+                    //
+                    // E.g.:
+                    //
+                    // ```gitignore
+                    // /*
+                    // !/.gitignore
+                    // !/app
+                    // !/public
+                    // ```
+                    //
+                    // Everything inside `base` except `.gitignore`, `app` and `public` is ignored,
+                    // but `base` itself is not.
+                    if dir != base {
+                        if let Some(gitignore) = gitignore {
+                            if gitignore
+                                .matched_path_or_any_parents(&base, true)
+                                .is_ignore()
+                            {
+                                source = SourceEntry::External { base: base.into() };
+                                break;
+                            }
                         }
                     }
 
@@ -810,12 +830,11 @@ pub fn public_source_entries_to_private_source_entries(
                         break;
                     }
 
-                    // Without a git repository there is no repository root to stop at. Stop
-                    // once the directory contains the current working directory instead, so
-                    // `.gitignore` files outside of the project (e.g. in the user's home
-                    // directory) can never promote a source to an external source. Note that
-                    // the file walker still applies those `.gitignore` files when deciding
-                    // which files to scan.
+                    // Without a git repository there is no repository root to stop at. Stop once
+                    // the directory contains the current working directory instead, so `.gitignore`
+                    // files outside of the project (e.g. in the user's home directory) can never
+                    // promote a source to an external source. Note that the file walker still
+                    // applies those `.gitignore` files when deciding which files to scan.
                     if !inside_git_repo && cwd.as_ref().is_some_and(|cwd| cwd.starts_with(dir)) {
                         break;
                     }
diff --git a/crates/oxide/tests/scanner.rs b/crates/oxide/tests/scanner.rs
index 2c3ca86b500d..f1f3b8bde867 100644
--- a/crates/oxide/tests/scanner.rs
+++ b/crates/oxide/tests/scanner.rs
@@ -1604,6 +1604,107 @@ mod scanner {
         assert_eq!(normalized_sources, vec!["web/**/*", "web/ignore-1.html"]);
     }
 
+    #[test]
+    fn it_respects_gitignore_files_with_whitelist_patterns() {
+        // https://github.com/tailwindlabs/tailwindcss/discussions/20382
+        //
+        // A `.gitignore` that ignores everything (`/*`) and then whitelists specific
+        // directories and files using negated patterns.
+        let ScanResult {
+            files, candidates, ..
+        } = scan(&[
+            (
+                ".gitignore",
+                "/*\n!/app\n!/public\n!/package.json\n!/.gitignore\n",
+            ),
+            ("app/index.html", "content-['app/index.html']"),
+            ("public/index.html", "content-['public/index.html']"),
+            ("package.json", ""),
+            // These are all ignored by the `/*` rule because they are not whitelisted
+            ("build/generated.html", "content-['build/generated.html']"),
+            ("logs/dev.log", "content-['logs/dev.log']"),
+            (
+                "node_modules/my-ui-lib/index.html",
+                "content-['node_modules/my-ui-lib/index.html']",
+            ),
+        ]);
+
+        assert_eq!(
+            files,
+            vec!["app/index.html", "package.json", "public/index.html"]
+        );
+        assert_eq!(
+            candidates,
+            vec![
+                "content-['app/index.html']",
+                "content-['public/index.html']"
+            ]
+        );
+    }
+
+    #[test]
+    fn it_respects_gitignore_files_with_nested_whitelist_patterns() {
+        // Example from the official `.gitignore` documentation:
+        //
+        // ```gitignore
+        // # exclude everything except directory foo/bar
+        // /*
+        // !/foo
+        // /foo/*
+        // !/foo/bar
+        // ```
+        let ScanResult {
+            files, candidates, ..
+        } = scan(&[
+            (
+                ".gitignore",
+                "# exclude everything except directory foo/bar\n/*\n!/foo\n/foo/*\n!/foo/bar\n",
+            ),
+            ("foo/bar/index.html", "content-['foo/bar/index.html']"),
+            (
+                "foo/bar/nested/index.html",
+                "content-['foo/bar/nested/index.html']",
+            ),
+            // These are all ignored because they are not inside `foo/bar`
+            ("index.html", "content-['index.html']"),
+            ("foo/index.html", "content-['foo/index.html']"),
+            ("foo/baz/index.html", "content-['foo/baz/index.html']"),
+        ]);
+
+        assert_eq!(
+            files,
+            vec!["foo/bar/index.html", "foo/bar/nested/index.html"]
+        );
+        assert_eq!(
+            candidates,
+            vec![
+                "content-['foo/bar/index.html']",
+                "content-['foo/bar/nested/index.html']"
+            ]
+        );
+    }
+
+    #[test]
+    fn explicit_source_directories_respect_their_own_gitignore() {
+        // A directory referenced via `@source` behaves like an auto source detection
+        // root. The `.gitignore` file _inside_ that directory still applies to its
+        // contents. Only when the directory itself is ignored (by an ancestor
+        // `.gitignore`, see the tests above) do we bypass the ignore rules.
+        let ScanResult {
+            files, candidates, ..
+        } = scan_with_globs(
+            &[
+                ("vendor/.gitignore", "ignored.html"),
+                ("vendor/index.html", "content-['vendor/index.html']"),
+                ("vendor/ignored.html", "content-['vendor/ignored.html']"),
+            ],
+            vec!["@source 'vendor'"],
+        );
+
+        assert_eq!(files, vec!["vendor/index.html"]);
+        assert_eq!(candidates, vec!["content-['vendor/index.html']"]);
+    }
+
     #[test]
     fn explicit_sources_can_include_files_inside_gitignored_parent_directories() {
         let ScanResult {
diff --git a/integrations/cli/index.test.ts b/integrations/cli/index.test.ts
index 310086802779..07f8bcb68860 100644
--- a/integrations/cli/index.test.ts
+++ b/integrations/cli/index.test.ts
@@ -2276,6 +2276,70 @@ test(
   },
 )
 
+// https://github.com/tailwindlabs/tailwindcss/discussions/20382
+test(
+  'auto source detection respects allow-list .gitignore files',
+  {
+    fs: {
+      'package.json': json`
+        {
+          "dependencies": {
+            "tailwindcss": "workspace:^",
+            "@tailwindcss/cli": "workspace:^"
+          }
+        }
+      `,
+      '.gitignore': txt`
+        /*
+        !/.gitignore
+        !/app
+        !/public
+        !/package.json
+      `,
+      'app/root.css': css` @import 'tailwindcss/utilities'; `,
+      // Included by the `!/app` pattern in `.gitignore`
+      //
+      // → Should be included
+      'app/index.html': html`
+        <div class="content-['app/index.html']"></div>
+      `,
+      // Included by the `!/public` pattern in `.gitignore`
+      //
+      // → Should be included
+      'public/index.html': html`
+        <div class="content-['public/index.html']"></div>
+      `,
+      // Ignored by the `/*` in `.gitignore`
+      //
+      // → Should be ignored
+      'build/index.html': html`
+        <div class="content-['build/index.html']"></div>
+      `,
+      // Ignored by the `/*` in `.gitignore` and the default `node_modules` rules
+      //
+      // → Should be ignored
+      'node_modules/my-ui-lib/index.html': html`
+        <div
+          class="content-['node_modules/my-ui-lib/index.html']"
+        ></div>
+      `,
+    },
+  },
+  async ({ fs, exec }) => {
+    await exec('pnpm tailwindcss --input app/root.css --output dist/out.css')
+
+    await fs.expectFileToContain('dist/out.css', [
+      candidate`content-['app/index.html']`,
+      candidate`content-['public/index.html']`,
+    ])
+
+    await fs.expectFileNotToContain('dist/out.css', [
+      candidate`content-['build/index.html']`,
+      candidate`content-['node_modules/my-ui-lib/index.html']`,
+    ])
+  },
+)
+
 test(
   '@source works with symlinks (referencing folder in current folder)',
   {

```

## Touched files at the merge commit (window of up to 200 lines around the first changed hunk)

### crates/oxide/tests/scanner.rs (lines 1545 to 1744 of 2679)
```
 1545|             candidates,
 1546|             vec!["content-['src/index.html']", "content-['web/index.html']",]
 1547|         );
 1548| 
 1549|         assert_eq!(files, vec!["src/index.html", "web/index.html",]);
 1550|         assert_eq!(globs, vec!["src/*", "web/*",]);
 1551|         assert_eq!(normalized_sources, vec!["src/**/*", "web/**/*",]);
 1552|     }
 1553| 
 1554|     #[test]
 1555|     fn it_includes_skipped_by_default_extensions_with_a_specific_source() {
 1556|         let ScanResult {
 1557|             candidates,
 1558|             files,
 1559|             globs,
 1560|             normalized_sources,
 1561|         } = scan_with_globs(
 1562|             &[
 1563|                 ("src/logo.jpg", "content-['/src/logo.jpg']"),
 1564|                 ("src/logo.png", "content-['/src/logo.png']"),
 1565|             ],
 1566|             vec!["@source './src/logo.{jpg,png}'"],
 1567|         );
 1568| 
 1569|         assert_eq!(
 1570|             candidates,
 1571|             vec!["content-['/src/logo.jpg']", "content-['/src/logo.png']"]
 1572|         );
 1573|         assert_eq!(files, vec!["src/logo.jpg", "src/logo.png"]);
 1574|         assert!(globs.is_empty());
 1575|         assert_eq!(normalized_sources, vec!["src/logo.jpg", "src/logo.png"]);
 1576|     }
 1577| 
 1578|     #[test]
 1579|     fn it_respects_gitignore_in_workspace_root_for_manual_globs() {
 1580|         let ScanResult {
 1581|             candidates,
 1582|             files,
 1583|             globs,
 1584|             normalized_sources,
 1585|         } = scan_with_globs(
 1586|             &[
 1587|                 (".gitignore", "ignore-1.html\n/web/ignore-2.html"),
 1588|                 ("web/index.html", "content-['web/index.html']"),
 1589|                 ("web/ignore-1.html", "content-['web/ignore-1.html']"),
 1590|                 ("web/ignore-2.html", "content-['web/ignore-2.html']"),
 1591|             ],
 1592|             vec!["@source './web'", "@source './web/ignore-1.html'"],
 1593|         );
 1594|         assert_eq!(
 1595|             candidates,
 1596|             vec![
 1597|                 "content-['web/ignore-1.html']",
 1598|                 "content-['web/index.html']",
 1599|             ]
 1600|         );
 1601| 
 1602|         assert_eq!(files, vec!["web/ignore-1.html", "web/index.html",]);
 1603|         assert_eq!(globs, vec!["web/*"]);
 1604|         assert_eq!(normalized_sources, vec!["web/**/*", "web/ignore-1.html"]);
 1605|     }
 1606| 
 1607|     #[test]
 1608|     fn it_respects_gitignore_files_with_whitelist_patterns() {
 1609|         // https://github.com/tailwindlabs/tailwindcss/discussions/20382
 1610|         //
 1611|         // A `.gitignore` that ignores everything (`/*`) and then whitelists specific
 1612|         // directories and files using negated patterns.
 1613|         let ScanResult {
 1614|             files, candidates, ..
 1615|         } = scan(&[
 1616|             (
 1617|                 ".gitignore",
 1618|                 "/*\n!/app\n!/public\n!/package.json\n!/.gitignore\n",
 1619|             ),
 1620|             ("app/index.html", "content-['app/index.html']"),
 1621|             ("public/index.html", "content-['public/index.html']"),
 1622|             ("package.json", ""),
 1623|             // These are all ignored by the `/*` rule because they are not whitelisted
 1624|             ("build/generated.html", "content-['build/generated.html']"),
 1625|             ("logs/dev.log", "content-['logs/dev.log']"),
 1626|             (
 1627|                 "node_modules/my-ui-lib/index.html",
 1628|                 "content-['node_modules/my-ui-lib/index.html']",
 1629|             ),
 1630|         ]);
 1631| 
 1632|         assert_eq!(
 1633|             files,
 1634|             vec!["app/index.html", "package.json", "public/index.html"]
 1635|         );
 1636|         assert_eq!(
 1637|             candidates,
 1638|             vec![
 1639|                 "content-['app/index.html']",
 1640|                 "content-['public/index.html']"
 1641|             ]
 1642|         );
 1643|     }
 1644| 
 1645|     #[test]
 1646|     fn it_respects_gitignore_files_with_nested_whitelist_patterns() {
 1647|         // Example from the official `.gitignore` documentation:
 1648|         //
 1649|         // ```gitignore
 1650|         // # exclude everything except directory foo/bar
 1651|         // /*
 1652|         // !/foo
 1653|         // /foo/*
 1654|         // !/foo/bar
 1655|         // ```
 1656|         let ScanResult {
 1657|             files, candidates, ..
 1658|         } = scan(&[
 1659|             (
 1660|                 ".gitignore",
 1661|                 "# exclude everything except directory foo/bar\n/*\n!/foo\n/foo/*\n!/foo/bar\n",
 1662|             ),
 1663|             ("foo/bar/index.html", "content-['foo/bar/index.html']"),
 1664|             (
 1665|                 "foo/bar/nested/index.html",
 1666|                 "content-['foo/bar/nested/index.html']",
 1667|             ),
 1668|             // These are all ignored because they are not inside `foo/bar`
 1669|             ("index.html", "content-['index.html']"),
 1670|             ("foo/index.html", "content-['foo/index.html']"),
 1671|             ("foo/baz/index.html", "content-['foo/baz/index.html']"),
 1672|         ]);
 1673| 
 1674|         assert_eq!(
 1675|             files,
 1676|             vec!["foo/bar/index.html", "foo/bar/nested/index.html"]
 1677|         );
 1678|         assert_eq!(
 1679|             candidates,
 1680|             vec![
 1681|                 "content-['foo/bar/index.html']",
 1682|                 "content-['foo/bar/nested/index.html']"
 1683|             ]
 1684|         );
 1685|     }
 1686| 
 1687|     #[test]
 1688|     fn explicit_source_directories_respect_their_own_gitignore() {
 1689|         // A directory referenced via `@source` behaves like an auto source detection
 1690|         // root. The `.gitignore` file _inside_ that directory still applies to its
 1691|         // contents. Only when the directory itself is ignored (by an ancestor
 1692|         // `.gitignore`, see the tests above) do we bypass the ignore rules.
 1693|         let ScanResult {
 1694|             files, candidates, ..
 1695|         } = scan_with_globs(
 1696|             &[
 1697|                 ("vendor/.gitignore", "ignored.html"),
 1698|                 ("vendor/index.html", "content-['vendor/index.html']"),
 1699|                 ("vendor/ignored.html", "content-['vendor/ignored.html']"),
 1700|             ],
 1701|             vec!["@source 'vendor'"],
 1702|         );
 1703| 
 1704|         assert_eq!(files, vec!["vendor/index.html"]);
 1705|         assert_eq!(candidates, vec!["content-['vendor/index.html']"]);
 1706|     }
 1707| 
 1708|     #[test]
 1709|     fn explicit_sources_can_include_files_inside_gitignored_parent_directories() {
 1710|         let ScanResult {
 1711|             candidates,
 1712|             files,
 1713|             globs,
 1714|             ..
 1715|         } = scan_with_globs(
 1716|             &[
 1717|                 (".gitignore", "src/efgh/"),
 1718|                 ("src/efgh/index.html", "content-['src/efgh/index.html']"),
 1719|                 ("src/efgh/ignore.js", "content-['src/efgh/ignore.js']"),
 1720|                 ("src/abcd/index.html", "content-['src/abcd/index.html']"),
 1721|             ],
 1722|             vec!["@source './src/ef*/*.html'"],
 1723|         );
 1724| 
 1725|         assert_eq!(candidates, vec!["content-['src/efgh/index.html']"]);
 1726|         assert_eq!(files, vec!["src/efgh/index.html"]);
 1727|         assert_eq!(globs, vec!["src/ef*/*.html"]);
 1728|     }
 1729| 
 1730|     #[test]
 1731|     fn skips_ignore_files_outside_of_a_repo() {
 1732|         // Create a temporary working directory
 1733|         let dir = tempdir().unwrap().into_path();
 1734| 
 1735|         // Create files
 1736|         create_files_in(
 1737|             &dir,
 1738|             &[
 1739|                 // This file should always be picked up
 1740|                 ("home/project/apps/web/index.html", "content-['index.html']"),
 1741|                 // Set up various ignore rules
 1742|                 ("home/.gitignore", "ignore-home.html"),
 1743|                 ("home/project/.gitignore", "ignore-project.html"),
 1744|                 ("home/project/apps/.gitignore", "ignore-apps.html"),
```

### integrations/cli/index.test.ts (lines 2217 to 2416 of 3187)
```
 2217|             "tailwindcss": "workspace:^",
 2218|             "@tailwindcss/cli": "workspace:^"
 2219|           }
 2220|         }
 2221|       `,
 2222|       '.gitignore': txt`
 2223|         *
 2224|         !/app
 2225|         !/app/design
 2226|         !/app/design/**
 2227|       `,
 2228|       'src/index.css': css`
 2229|         @import 'tailwindcss/utilities' source(none);
 2230|         @source '../vendor/acme/theme';
 2231|       `,
 2232|       // 1. Ignored by the `*` in `.gitignore`
 2233|       // 2. Included by the `!` pattern in `.gitignore`
 2234|       // 3. Ignored by `source(none)`
 2235|       //
 2236|       // → Should be ignored
 2237|       'app/design/frontend/theme/templates/component.phtml': html`
 2238|         <div
 2239|           class="content-['app/design/frontend/theme/templates/component.phtml']"
 2240|         ></div>
 2241|       `,
 2242|       // 1. Ignored by the `*` in `.gitignore`
 2243|       // 2. Included by the `!` pattern in `.gitignore`
 2244|       // 3. Ignored by `source(none)`
 2245|       // 4. Included by the `@source` directive
 2246|       //
 2247|       // → Should be included
 2248|       'vendor/acme/theme/module/templates/component.phtml': html`
 2249|         <div
 2250|           class="content-['vendor/acme/theme/module/templates/component.phtml']"
 2251|         ></div>
 2252|       `,
 2253|     },
 2254|   },
 2255|   async ({ fs, exec }) => {
 2256|     await exec('pnpm tailwindcss --input src/index.css --output dist/out.css')
 2257| 
 2258|     // 1. Ignored by the `*` in `.gitignore`
 2259|     // 2. Included by the `!` pattern in `.gitignore`
 2260|     // 3. Ignored by `source(none)`
 2261|     //
 2262|     // → Should be ignored
 2263|     await fs.expectFileNotToContain('dist/out.css', [
 2264|       candidate`content-['app/design/frontend/theme/templates/component.phtml']`,
 2265|     ])
 2266| 
 2267|     // 1. Ignored by the `*` in `.gitignore`
 2268|     // 2. Included by the `!` pattern in `.gitignore`
 2269|     // 3. Ignored by `source(none)`
 2270|     // 4. Included by the `@source` directive
 2271|     //
 2272|     // → Should be included
 2273|     await fs.expectFileToContain('dist/out.css', [
 2274|       candidate`content-['vendor/acme/theme/module/templates/component.phtml']`,
 2275|     ])
 2276|   },
 2277| )
 2278| 
 2279| // https://github.com/tailwindlabs/tailwindcss/discussions/20382
 2280| test(
 2281|   'auto source detection respects allow-list .gitignore files',
 2282|   {
 2283|     fs: {
 2284|       'package.json': json`
 2285|         {
 2286|           "dependencies": {
 2287|             "tailwindcss": "workspace:^",
 2288|             "@tailwindcss/cli": "workspace:^"
 2289|           }
 2290|         }
 2291|       `,
 2292|       '.gitignore': txt`
 2293|         /*
 2294|         !/.gitignore
 2295|         !/app
 2296|         !/public
 2297|         !/package.json
 2298|       `,
 2299|       'app/root.css': css` @import 'tailwindcss/utilities'; `,
 2300|       // Included by the `!/app` pattern in `.gitignore`
 2301|       //
 2302|       // → Should be included
 2303|       'app/index.html': html`
 2304|         <div class="content-['app/index.html']"></div>
 2305|       `,
 2306|       // Included by the `!/public` pattern in `.gitignore`
 2307|       //
 2308|       // → Should be included
 2309|       'public/index.html': html`
 2310|         <div class="content-['public/index.html']"></div>
 2311|       `,
 2312|       // Ignored by the `/*` in `.gitignore`
 2313|       //
 2314|       // → Should be ignored
 2315|       'build/index.html': html`
 2316|         <div class="content-['build/index.html']"></div>
 2317|       `,
 2318|       // Ignored by the `/*` in `.gitignore` and the default `node_modules` rules
 2319|       //
 2320|       // → Should be ignored
 2321|       'node_modules/my-ui-lib/index.html': html`
 2322|         <div
 2323|           class="content-['node_modules/my-ui-lib/index.html']"
 2324|         ></div>
 2325|       `,
 2326|     },
 2327|   },
 2328|   async ({ fs, exec }) => {
 2329|     await exec('pnpm tailwindcss --input app/root.css --output dist/out.css')
 2330| 
 2331|     await fs.expectFileToContain('dist/out.css', [
 2332|       candidate`content-['app/index.html']`,
 2333|       candidate`content-['public/index.html']`,
 2334|     ])
 2335| 
 2336|     await fs.expectFileNotToContain('dist/out.css', [
 2337|       candidate`content-['build/index.html']`,
 2338|       candidate`content-['node_modules/my-ui-lib/index.html']`,
 2339|     ])
 2340|   },
 2341| )
 2342| 
 2343| test(
 2344|   '@source works with symlinks (referencing folder in current folder)',
 2345|   {
 2346|     fs: {
 2347|       'package.json': json`
 2348|         {
 2349|           "dependencies": {
 2350|             "tailwindcss": "workspace:^",
 2351|             "@tailwindcss/cli": "workspace:^"
 2352|           }
 2353|         }
 2354|       `,
 2355|       'src/index.css': css`
 2356|         @import 'tailwindcss/utilities' source(none);
 2357| 
 2358|         /* Same as the previous test, but using symlinks instead */
 2359|         @source '../lib';
 2360|         @source not '../lib/ignored';
 2361|         @source '../lib/ignored/except.html';
 2362|       `,
 2363| 
 2364|       'lib/keep/keep.html': html`<div class="content-['GOOD-1']"></div>`,
 2365|       'vendor/ignored/ignored.html': html`<div class="content-['BAD-1']"></div>`,
 2366|       'vendor/ignored/except.html': html`<div class="content-['GOOD-2']"></div>`,
 2367| 
 2368|       // Symlink the ignored folder to another folder
 2369|       'lib/ignored': 'symlink:../../vendor/ignored/',
 2370|     },
 2371|   },
 2372|   async ({ fs, exec, expect }) => {
 2373|     await exec('pnpm tailwindcss --input src/index.css --output dist/out.css')
 2374| 
 2375|     expect(await fs.dumpFiles('./dist/*.css')).toMatchInlineSnapshot(`
 2376|       "
 2377|       --- ./dist/out.css ---
 2378|       @layer properties;
 2379|       .content-\\[\\'GOOD-1\\'\\] {
 2380|         --tw-content: 'GOOD-1';
 2381|         content: var(--tw-content);
 2382|       }
 2383|       .content-\\[\\'GOOD-2\\'\\] {
 2384|         --tw-content: 'GOOD-2';
 2385|         content: var(--tw-content);
 2386|       }
 2387|       @property --tw-content {
 2388|         syntax: "*";
 2389|         inherits: false;
 2390|         initial-value: "";
 2391|       }
 2392|       @layer properties {
 2393|         @supports ((-webkit-hyphens: none) and (not (margin-trim: inline))) or ((-moz-orient: inline) and (not (color:rgb(from red r g b)))) {
 2394|           *, ::before, ::after, ::backdrop {
 2395|             --tw-content: "";
 2396|           }
 2397|         }
 2398|       }
 2399|       "
 2400|     `)
 2401|   },
 2402| )
 2403| 
 2404| test(
 2405|   'auto source detection disabled',
 2406|   {
 2407|     fs: {
 2408|       'package.json': json`
 2409|         {
 2410|           "dependencies": {
 2411|             "tailwindcss": "workspace:^",
 2412|             "@tailwindcss/cli": "workspace:^"
 2413|           }
 2414|         }
 2415|       `,
 2416|       'index.css': css`
```

### crates/oxide/src/scanner/sources.rs (lines 704 to 903 of 939)
```
  704|     #[test]
  705|     fn folders_not_ignored_by_gitignore_stay_auto_sources() {
  706|         let dir = tempdir().unwrap();
  707|         fs::create_dir_all(dir.path().join(".git")).unwrap();
  708|         fs::write(dir.path().join(".gitignore"), "dist/\n").unwrap();
  709| 
  710|         let base = dir.path().join("src");
  711|         fs::create_dir_all(&base).unwrap();
  712|         let base = dunce::canonicalize(&base).unwrap();
  713| 
  714|         assert_eq!(auto_source_entry(&base), SourceEntry::Auto { base });
  715|     }
  716| }
  717| 
  718| /// For each public source entry:
  719| ///
  720| /// 1. Perform brace expansion
  721| ///
  722| /// ```diff
  723| /// - { base: '/', pattern: 'src/{foo,bar}.html'}
  724| /// + { base: '/', pattern: 'src/foo.html'}
  725| /// + { base: '/', pattern: 'src/bar.html'}
  726| /// ```
  727| ///
  728| /// 2. Hoist static parts, e.g.:
  729| ///
  730| /// ```diff
  731| /// - { base: '/', pattern: 'src/**/*.html'}
  732| /// + { base: '/src', pattern: '**/*.html'}
  733| /// ```
  734| ///
  735| /// 3. Convert to private SourceEntry
  736| ///
  737| pub fn public_source_entries_to_private_source_entries(
  738|     sources: Vec<PublicSourceEntry>,
  739| ) -> Vec<SourceEntry> {
  740|     // Perform brace expansion
  741|     let expanded_globs = sources
  742|         .into_iter()
  743|         .flat_map(|source| {
  744|             let expression: Result<Expression, _> = source.pattern[..].try_into();
  745|             let Ok(expression) = expression else {
  746|                 return vec![source];
  747|             };
  748| 
  749|             expression
  750|                 .into_iter()
  751|                 .filter_map(Result::ok)
  752|                 .map(move |pattern| PublicSourceEntry {
  753|                     base: source.base.clone(),
  754|                     pattern: pattern.into(),
  755|                     negated: source.negated,
  756|                 })
  757|                 .collect::<Vec<_>>()
  758|         })
  759|         .map(|mut public_source| {
  760|             public_source.optimize();
  761|             public_source
  762|         })
  763|         .collect::<Vec<_>>();
  764| 
  765|     // Compiled `.gitignore` matchers are cached per directory so we read and parse each
  766|     // `.gitignore` file at most once, even though entries commonly share ancestor directories (e.g.
  767|     // the repository root). A cached `None` means the directory has no `.gitignore` file.
  768|     let mut gitignores: FxHashMap<PathBuf, Option<Gitignore>> = FxHashMap::default();
  769| 
  770|     // Boundary for the `.gitignore` walk when a source is not inside a git repository (see below).
  771|     let cwd = std::env::current_dir()
  772|         .map(|cwd| dunce::canonicalize(&cwd).unwrap_or(cwd))
  773|         .ok();
  774| 
  775|     // Convert from public SourceEntry to private SourceEntry
  776|     let sources = expanded_globs
  777|         .into_iter()
  778|         .map(|public_source| {
  779|             let mut source: SourceEntry = public_source.into();
  780| 
  781|             // Promote auto-sources to external sources if they were gitignored
  782|             if let SourceEntry::Auto { ref base } = source {
  783|                 let inside_git_repo = base.ancestors().any(|dir| dir.join(".git").exists());
  784| 
  785|                 // Walk up from the folder, applying each `.gitignore` relative to the directory
  786|                 // that contains it (matching git), and stop at the git repository root so
  787|                 // `.gitignore` files outside of the repo are not considered.
  788|                 for dir in base.ancestors() {
  789|                     let gitignore = gitignores.entry(dir.to_path_buf()).or_insert_with(|| {
  790|                         let path = dir.join(".gitignore");
  791| 
  792|                         // `Gitignore::new` roots the matcher at the directory containing the file,
  793|                         // so patterns match relative to it.
  794|                         path.is_file().then(|| Gitignore::new(&path).0)
  795|                     });
  796| 
  797|                     // Only `.gitignore` files in ancestors of `base` can ignore `base` itself.
  798|                     // Patterns in `base`'s own `.gitignore` only match paths _inside_ `base`, never
  799|                     // `base` itself (the file walker still applies them to `base`'s contents).
  800|                     //
  801|                     // Skipping `base`'s own `.gitignore` also prevents a false positive for
  802|                     // whitelist style `.gitignore` files, because relativizing `base` against
  803|                     // itself yields the empty path, which incorrectly matches `/*`.
  804|                     //
  805|                     // E.g.:
  806|                     //
  807|                     // ```gitignore
  808|                     // /*
  809|                     // !/.gitignore
  810|                     // !/app
  811|                     // !/public
  812|                     // ```
  813|                     //
  814|                     // Everything inside `base` except `.gitignore`, `app` and `public` is ignored,
  815|                     // but `base` itself is not.
  816|                     if dir != base {
  817|                         if let Some(gitignore) = gitignore {
  818|                             if gitignore
  819|                                 .matched_path_or_any_parents(&base, true)
  820|                                 .is_ignore()
  821|                             {
  822|                                 source = SourceEntry::External { base: base.into() };
  823|                                 break;
  824|                             }
  825|                         }
  826|                     }
  827| 
  828|                     // Stop at the git repository root.
  829|                     if dir.join(".git").exists() {
  830|                         break;
  831|                     }
  832| 
  833|                     // Without a git repository there is no repository root to stop at. Stop once
  834|                     // the directory contains the current working directory instead, so `.gitignore`
  835|                     // files outside of the project (e.g. in the user's home directory) can never
  836|                     // promote a source to an external source. Note that the file walker still
  837|                     // applies those `.gitignore` files when deciding which files to scan.
  838|                     if !inside_git_repo && cwd.as_ref().is_some_and(|cwd| cwd.starts_with(dir)) {
  839|                         break;
  840|                     }
  841|                 }
  842|             }
  843| 
  844|             source
  845|         })
  846|         .collect::<Vec<SourceEntry>>();
  847| 
  848|     expand_restricted_patterns(sources)
  849| }
  850| 
  851| /// Convert a public source entry to a source entry
  852| impl From<PublicSourceEntry> for SourceEntry {
  853|     fn from(value: PublicSourceEntry) -> Self {
  854|         if value.negated {
  855|             return SourceEntry::Ignored {
  856|                 base: value.base.into(),
  857|                 pattern: value.pattern,
  858|             };
  859|         }
  860| 
  861|         let auto =
  862|             value.pattern == "/**/*" || PathBuf::from(&value.base).join(&value.pattern).is_dir();
  863| 
  864|         if !auto {
  865|             return SourceEntry::Pattern {
  866|                 base: value.base.into(),
  867|                 pattern: value.pattern,
  868|             };
  869|         }
  870| 
  871|         let inside_ignored_content_dir = IGNORED_CONTENT_DIRS.iter().any(|dir| {
  872|             value.base.contains(&format!(
  873|                 "{}{}{}",
  874|                 std::path::MAIN_SEPARATOR,
  875|                 dir,
  876|                 std::path::MAIN_SEPARATOR
  877|             )) || value
  878|                 .base
  879|                 .ends_with(&format!("{}{}", std::path::MAIN_SEPARATOR, dir))
  880|         });
  881| 
  882|         match inside_ignored_content_dir {
  883|             false => SourceEntry::Auto {
  884|                 base: value.base.into(),
  885|             },
  886|             true => SourceEntry::External {
  887|                 base: value.base.into(),
  888|             },
  889|         }
  890|     }
  891| }
  892| 
  893| impl From<GlobEntry> for SourceEntry {
  894|     fn from(value: GlobEntry) -> Self {
  895|         SourceEntry::Pattern {
  896|             base: PathBuf::from(value.base),
  897|             pattern: value.pattern,
  898|         }
  899|     }
  900| }
  901| 
  902| impl From<SourceEntry> for GlobEntry {
  903|     fn from(value: SourceEntry) -> Self {
```

### CHANGELOG.md (lines 1 to 200 of 4421)
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
   27| 
   28| ## [4.3.3] - 2026-07-16
   29| 
   30| ### Fixed
   31| 
   32| - Support `--watch --poll[=ms]` in `@tailwindcss/cli` when filesystem events are unreliable or unavailable ([#20297](https://github.com/tailwindlabs/tailwindcss/pull/20297))
   33| - Canonicalization: match arbitrary hex colors against theme colors case-insensitively (e.g. `bg-[#fff]` and `bg-[#FFF]` → `bg-white`) ([#20298](https://github.com/tailwindlabs/tailwindcss/pull/20298))
   34| - Prevent Preflight from overriding Firefox's native `iframe:focus-visible` outline styles ([#20292](https://github.com/tailwindlabs/tailwindcss/pull/20292))
   35| - Ensure `theme('colors.foo')` in JS plugins resolves correctly when both `--color-foo` and `--color-foo-bar` exist ([#20299](https://github.com/tailwindlabs/tailwindcss/pull/20299))
   36| - Ensure fractional opacity modifiers work with named shadow sizes like `shadow-sm/12.5`, `text-shadow-sm/12.5`, `drop-shadow-sm/12.5`, and `inset-shadow-sm/12.5` ([#20302](https://github.com/tailwindlabs/tailwindcss/pull/20302))
   37| - Parse selectors like `[data-foo]div` as two selectors instead of one ([#20303](https://github.com/tailwindlabs/tailwindcss/pull/20303))
   38| - Ensure `@tailwindcss/postcss` rebuilds when a preprocessor like Sass changes the input CSS without changing the input file on disk ([#20310](https://github.com/tailwindlabs/tailwindcss/pull/20310))
   39| - Ensure CSS nesting is handled even when Lightning CSS isn't run, such as in `@tailwindcss/browser` and Tailwind Play ([#20124](https://github.com/tailwindlabs/tailwindcss/pull/20124))
   40| - Prevent achromatic theme colors from shifting hue when mixed in polar color spaces like `oklch` ([#20314](https://github.com/tailwindlabs/tailwindcss/pull/20314))
   41| - Ensure `--spacing(0)` is optimized to `0px` instead of `0` so it remains a `<length>` when used in `calc(…)` ([#20319](https://github.com/tailwindlabs/tailwindcss/pull/20319))
   42| - Load `@parcel/watcher` only when needed in `@tailwindcss/cli --watch` mode, so one-off builds and `--watch --poll` work when `@parcel/watcher` can't be loaded ([#20325](https://github.com/tailwindlabs/tailwindcss/pull/20325))
   43| - Use explicit platform fonts instead of `system-ui` and `ui-sans-serif` so CJK text respects the page's `lang` attribute on Windows ([#20318](https://github.com/tailwindlabs/tailwindcss/pull/20318))
   44| - Prevent `@tailwindcss/upgrade` from rewriting ignored files when run from a subdirectory ([#20329](https://github.com/tailwindlabs/tailwindcss/pull/20329))
   45| - Ensure earlier `@source` rules pointing to nested files are scanned when later `@source` rules point to files in parent folders ([#20335](https://github.com/tailwindlabs/tailwindcss/pull/20335))
   46| - Prevent `@tailwindcss/vite` from triggering full page reloads when scanned files are processed by Vite but haven't been loaded as modules yet ([#20336](https://github.com/tailwindlabs/tailwindcss/pull/20336))
   47| 
   48| ## [4.3.2] - 2026-06-26
   49| 
   50| ### Fixed
   51| 
   52| - Support bare spacing values for `auto-rows-*` and `auto-cols-*` utilities (e.g. `auto-rows-12` and `auto-cols-16`) ([#20229](https://github.com/tailwindlabs/tailwindcss/pull/20229))
   53| - Prevent `@tailwindcss/cli` in `--watch` mode from crashing on Windows when `@source` points to a directory that doesn't exist ([#20242](https://github.com/tailwindlabs/tailwindcss/pull/20242))
   54| - Prevent `@tailwindcss/vite` from crashing in Deno v2.8.x when `context.parentURL` is not a valid URL ([#20245](https://github.com/tailwindlabs/tailwindcss/pull/20245))
   55| - Ensure `@tailwindcss/cli` in `--watch` mode rebuilds when the input CSS file changes in an ignored directory ([#20246](https://github.com/tailwindlabs/tailwindcss/pull/20246))
   56| - Allow `@variant` rules used in `addBase(…)` to use custom variants defined later ([#20247](https://github.com/tailwindlabs/tailwindcss/pull/20247))
   57| - Prevent `@tailwindcss/vite` from crashing during HMR when scanned files or directories are deleted ([#20259](https://github.com/tailwindlabs/tailwindcss/pull/20259))
   58| - Generate `font-size` instead of `color` declarations for `text-[--spacing(…)]` ([#20260](https://github.com/tailwindlabs/tailwindcss/pull/20260))
   59| - Prevent `@source` patterns from scanning unrelated sibling files and folders ([#20263](https://github.com/tailwindlabs/tailwindcss/pull/20263))
   60| - Extract class candidates adjacent to Template Toolkit delimiters like `%]…[%` in `.tt`, `.tt2`, and `.tx` files ([#20269](https://github.com/tailwindlabs/tailwindcss/pull/20269))
   61| - Extract class candidates from conditional Maud syntax like `p.text-black[condition]` ([#20269](https://github.com/tailwindlabs/tailwindcss/pull/20269))
   62| - Prevent `@position-try` rules from triggering unknown at-rule warnings when optimizing CSS ([#20277](https://github.com/tailwindlabs/tailwindcss/pull/20277))
   63| - Support class suggestions for named opacity modifiers from `--opacity` theme values ([#20287](https://github.com/tailwindlabs/tailwindcss/pull/20287))
   64| - Prevent type errors in `@tailwindcss/postcss` when used with newer PostCSS patch releases ([#20289](https://github.com/tailwindlabs/tailwindcss/pull/20289))
   65| 
   66| ## [4.3.1] - 2026-06-12
   67| 
   68| ### Added
   69| 
   70| - Add `--silent` option to suppress output in `@tailwindcss/cli` ([#20100](https://github.com/tailwindlabs/tailwindcss/pull/20100))
   71| 
   72| ### Fixed
   73| 
   74| - Remove deprecation warnings by using `Module#registerHooks` instead of `Module#register` on Node 26+ ([#20028](https://github.com/tailwindlabs/tailwindcss/pull/20028))
   75| - Canonicalization: don't crash when plugin utilities throw for unsupported values ([#20052](https://github.com/tailwindlabs/tailwindcss/pull/20052))
   76| - Allow `@apply` to be used with CSS mixins ([#19427](https://github.com/tailwindlabs/tailwindcss/pull/19427))
   77| - Ensure `not-*` correctly negates `@container` queries, including `style(…)` queries ([#20059](https://github.com/tailwindlabs/tailwindcss/pull/20059))
   78| - Ensure `drop-shadow-*` color utilities work with custom shadow values containing `calc(…)` ([#20080](https://github.com/tailwindlabs/tailwindcss/pull/20080))
   79| - Fix 'Sourcemap is likely to be incorrect' warnings when using `@tailwindcss/vite` ([#20103](https://github.com/tailwindlabs/tailwindcss/pull/20103))
   80| - Ensure `@tailwindcss/webpack` can be installed in Rspack projects without requiring `webpack` as a peer dependency ([#20027](https://github.com/tailwindlabs/tailwindcss/pull/20027))
   81| - Canonicalization: don't suggest invalid `calc(…)` expressions (e.g. `px-[calc(1rem+0px)]` → `px-[calc(1rem+0)]`) ([#20127](https://github.com/tailwindlabs/tailwindcss/pull/20127))
   82| - Canonicalization: avoid suggesting large spacing-scale values for arbitrary lengths (e.g. `left-[99999px]` → `left-[99999px]`, not `left-24999.75`) ([#20130](https://github.com/tailwindlabs/tailwindcss/pull/20130))
   83| - Ensure `@tailwindcss/cli` in `--watch` mode recovers when a tracked dependency is deleted and restored ([#20137](https://github.com/tailwindlabs/tailwindcss/pull/20137))
   84| - Ensure standalone `@tailwindcss/cli` binaries are ignored when scanning for class candidates ([#20139](https://github.com/tailwindlabs/tailwindcss/pull/20139))
   85| - Ensure class candidates are extracted from Twig `addClass(…)` and `removeClass(…)` calls ([#20198](https://github.com/tailwindlabs/tailwindcss/pull/20198))
   86| - Don't crash in the Ruby or Vue preprocessors when scanning files containing invalid UTF-8 bytes ([#19588](https://github.com/tailwindlabs/tailwindcss/pull/19588))
   87| - Allow `@variant` to be used inside `addBase` ([#19480](https://github.com/tailwindlabs/tailwindcss/pull/19480))
   88| - Ensure `@source` globs with symlinks are preserved ([#20203](https://github.com/tailwindlabs/tailwindcss/pull/20203))
   89| - Ensure later `@source` rules can re-include files excluded by earlier `@source not` rules ([#20203](https://github.com/tailwindlabs/tailwindcss/pull/20203))
   90| - Upgrade: don't migrate empty class rules to invalid `@utility` rules ([#20205](https://github.com/tailwindlabs/tailwindcss/pull/20205))
   91| - Ensure transitions between `inset-shadow-none` and other inset shadows work correctly ([#20208](https://github.com/tailwindlabs/tailwindcss/pull/20208))
   92| - Ensure explicitly referenced `@source` directories are scanned even when ignored by git ([#20214](https://github.com/tailwindlabs/tailwindcss/pull/20214))
   93| - Ensure `@source` globs ending in `**/*` preserve dynamic path segments to avoid scanning too many files ([#20217](https://github.com/tailwindlabs/tailwindcss/pull/20217))
   94| - Canonicalization: don't fold `calc(…)` divisions when the result would require high precision (e.g. `w-[calc(100%/3.5)]` → `w-[calc(100%/3.5)]`, not `w-[28.571428571428573%]`) ([#20221](https://github.com/tailwindlabs/tailwindcss/pull/20221))
   95| - Serve ESM type declarations to ESM importers of `@tailwindcss/postcss` ([#20228](https://github.com/tailwindlabs/tailwindcss/pull/20228))
   96| 
   97| ### Changed
   98| 
   99| - Generate `0` instead of `calc(var(--spacing) * 0)` for spacing utilities like `m-0` and `left-0` ([#20196](https://github.com/tailwindlabs/tailwindcss/pull/20196))
  100| - Generate `var(--spacing)` instead of `calc(var(--spacing) * 1)` for spacing utilities like `m-1` and `left-1` ([#20196](https://github.com/tailwindlabs/tailwindcss/pull/20196))
  101| 
  102| ## [4.3.0] - 2026-05-08
  103| 
  104| ### Added
  105| 
  106| - Add `@container-size` utility ([#18901](https://github.com/tailwindlabs/tailwindcss/pull/18901))
  107| - Add `scrollbar-{auto,thin,none}` utilities for `scrollbar-width`, and `scrollbar-thumb-*` / `scrollbar-track-*` color utilities for `scrollbar-color` ([#19981](https://github.com/tailwindlabs/tailwindcss/pull/19981), [#20019](https://github.com/tailwindlabs/tailwindcss/pull/20019))
  108| - Add `scrollbar-gutter-*` utilities ([#20018](https://github.com/tailwindlabs/tailwindcss/pull/20018))
  109| - Add `zoom-*` utilities ([#20020](https://github.com/tailwindlabs/tailwindcss/pull/20020))
  110| - Add `tab-*` utilities ([#20022](https://github.com/tailwindlabs/tailwindcss/pull/20022))
  111| - Allow using `@variant` with stacked variants (e.g. `@variant hover:focus { … }`) ([#19996](https://github.com/tailwindlabs/tailwindcss/pull/19996))
  112| - Allow using `@variant` with compound variants (e.g. `@variant hover, focus { … }`) ([#19996](https://github.com/tailwindlabs/tailwindcss/pull/19996))
  113| - Support `--default(…)` in `--value(…)` and `--modifier(…)` for functional `@utility` definitions ([#19989](https://github.com/tailwindlabs/tailwindcss/pull/19989))
  114| 
  115| ### Fixed
  116| 
  117| - Ensure `@plugin` resolves package JavaScript entries instead of browser CSS entries when using `@tailwindcss/vite` ([#19949](https://github.com/tailwindlabs/tailwindcss/pull/19949))
  118| - Fix relative `@import` and `@plugin` paths resolving from the wrong directory when using `@tailwindcss/vite` ([#19965](https://github.com/tailwindlabs/tailwindcss/pull/19965))
  119| - Ensure CSS files containing `@variant` are processed by `@tailwindcss/vite` ([#19966](https://github.com/tailwindlabs/tailwindcss/pull/19966))
  120| - Resolve imports relative to `base` when `result.opts.from` is not provided when using `@tailwindcss/postcss` ([#19980](https://github.com/tailwindlabs/tailwindcss/pull/19980))
  121| - Canonicalization: preserve significant `_` whitespace in arbitrary values ([#19986](https://github.com/tailwindlabs/tailwindcss/pull/19986))
  122| - Canonicalization: add parentheses when removing whitespace from arbitrary values would hurt readability (e.g. `w-[calc(100%---spacing(60))]` → `w-[calc(100%-(--spacing(60)))]`) ([#19986](https://github.com/tailwindlabs/tailwindcss/pull/19986))
  123| - Canonicalization: preserve the original unit in arbitrary values instead of normalizing to base units (e.g. `-mt-[20in]` → `mt-[-20in]`, not `mt-[-1920px]`) ([#19988](https://github.com/tailwindlabs/tailwindcss/pull/19988))
  124| - Canonicalization: migrate arbitrary `:has()` variants from `[&:has(…)]` to `has-[…]` ([#19991](https://github.com/tailwindlabs/tailwindcss/pull/19991))
  125| - Upgrade: don’t migrate inline `style` attributes (e.g. `style="flex-grow: 1"` → `style="flex-grow: 1"`, not `style="grow: 1"`) ([#19918](https://github.com/tailwindlabs/tailwindcss/pull/19918))
  126| - Allow multiple `@utility` definitions with the same name but different value types ([#19777](https://github.com/tailwindlabs/tailwindcss/pull/19777))
  127| - Export missing `PluginWithConfig` type from `tailwindcss/plugin` to fix errors when inferring plugin config types ([#19707](https://github.com/tailwindlabs/tailwindcss/pull/19707))
  128| - Ensure `start` and `end` legacy utilities without values do not generate CSS ([#20003](https://github.com/tailwindlabs/tailwindcss/pull/20003))
  129| - Ensure `--value(…)` is required in functional `@utility` definitions ([#20005](https://github.com/tailwindlabs/tailwindcss/pull/20005))
  130| - Canonicalization: preserve required whitespace around operators in negated arbitrary values (e.g. `-left-[(var(--a)+var(--b))]`) ([#20011](https://github.com/tailwindlabs/tailwindcss/pull/20011))
  131| 
  132| ## [4.2.4] - 2026-04-21
  133| 
  134| ### Fixed
  135| 
  136| - Ensure imports in `@import` and `@plugin` still resolve correctly when using Vite aliases in `@tailwindcss/vite` ([#19947](https://github.com/tailwindlabs/tailwindcss/pull/19947))
  137| 
  138| ## [4.2.3] - 2026-04-20
  139| 
  140| ### Fixed
  141| 
  142| - Canonicalization: improve canonicalization for `tracking-*` utilities by preferring non-negative utilities (e.g. `-tracking-tighter` → `tracking-wider`) ([#19827](https://github.com/tailwindlabs/tailwindcss/pull/19827))
  143| - Fix crash due to invalid characters in candidate (exceeding valid unicode code point range) ([#19829](https://github.com/tailwindlabs/tailwindcss/pull/19829))
  144| - Ensure query params in imports are considered unique resources when using `@tailwindcss/webpack` ([#19723](https://github.com/tailwindlabs/tailwindcss/pull/19723))
  145| - Canonicalization: collapse arbitrary values into shorthand utilities (e.g. `px-[1.2rem] py-[1.2rem]` → `p-[1.2rem]`) ([#19837](https://github.com/tailwindlabs/tailwindcss/pull/19837))
  146| - Canonicalization: collapse `border-{t,b}-*` into `border-y-*`, `border-{l,r}-*` into `border-x-*`, and `border-{t,r,b,l}-*` into `border-*` ([#19842](https://github.com/tailwindlabs/tailwindcss/pull/19842))
  147| - Canonicalization: collapse `scroll-m{t,b}-*` into `scroll-my-*`, `scroll-m{l,r}-*` into `scroll-mx-*`, and `scroll-m{t,r,b,l}-*` into `scroll-m-*` ([#19842](https://github.com/tailwindlabs/tailwindcss/pull/19842))
  148| - Canonicalization: collapse `scroll-p{t,b}-*` into `scroll-py-*`, `scroll-p{l,r}-*` into `scroll-px-*`, and `scroll-p{t,r,b,l}-*` into `scroll-p-*` ([#19842](https://github.com/tailwindlabs/tailwindcss/pull/19842))
  149| - Canonicalization: collapse `overflow-{x,y}-*` into `overflow-*` ([#19842](https://github.com/tailwindlabs/tailwindcss/pull/19842))
  150| - Canonicalization: collapse `overscroll-{x,y}-*` into `overscroll-*` ([#19842](https://github.com/tailwindlabs/tailwindcss/pull/19842))
  151| - Read from `--placeholder-color` instead of `--background-color` for `placeholder-*` utilities ([#19843](https://github.com/tailwindlabs/tailwindcss/pull/19843))
  152| - Upgrade: ensure files are not emptied out when killing the upgrade process while it's running ([#19846](https://github.com/tailwindlabs/tailwindcss/pull/19846))
  153| - Upgrade: use `config.content` when migrating from Tailwind CSS v3 to Tailwind CSS v4 ([#19846](https://github.com/tailwindlabs/tailwindcss/pull/19846))
  154| - Upgrade: never migrate files that are ignored by git ([#19846](https://github.com/tailwindlabs/tailwindcss/pull/19846))
  155| - Add `.env` and `.env.*` to default ignored content files ([#19846](https://github.com/tailwindlabs/tailwindcss/pull/19846))
  156| - Canonicalization: migrate `overflow-ellipsis` into `text-ellipsis` ([#19849](https://github.com/tailwindlabs/tailwindcss/pull/19849))
  157| - Canonicalization: migrate `start-full` → `inset-s-full`, `start-auto` → `inset-s-auto`, `start-px` → `inset-s-px`, and `start-<number>` → `inset-s-<number>` as well as negative versions ([#19849](https://github.com/tailwindlabs/tailwindcss/pull/19849))
  158| - Canonicalization: migrate `end-full` → `inset-e-full`, `end-auto` → `inset-e-auto`, `end-px` → `inset-e-px`, and `end-<number>` → `inset-e-<number>` as well as negative versions ([#19849](https://github.com/tailwindlabs/tailwindcss/pull/19849))
  159| - Canonicalization: move the `-` sign inside the arbitrary value `-left-[9rem]` → `left-[-9rem]` ([#19858](https://github.com/tailwindlabs/tailwindcss/pull/19858))
  160| - Canonicalization: move the `-` sign outside the arbitrary value `ml-[calc(-1*var(--width))]` → `-ml-(--width)` ([#19858](https://github.com/tailwindlabs/tailwindcss/pull/19858))
  161| - Improve performance when scanning JSONL / NDJSON files ([#19862](https://github.com/tailwindlabs/tailwindcss/pull/19862))
  162| - Support `NODE_PATH` environment variable in standalone CLI ([#19617](https://github.com/tailwindlabs/tailwindcss/pull/19617))
  163| 
  164| ## [4.2.2] - 2026-03-18
  165| 
  166| ### Fixed
  167| 
  168| - Don't crash when candidates contain prototype properties like `row-constructor` ([#19725](https://github.com/tailwindlabs/tailwindcss/pull/19725))
  169| - Canonicalize `calc(var(--spacing)*…)` expressions into `--spacing(…)` ([#19769](https://github.com/tailwindlabs/tailwindcss/pull/19769))
  170| - Fix crash in canonicalization step when handling utilities containing `@property` at-rules (e.g. `shadow-sm border`) ([#19727](https://github.com/tailwindlabs/tailwindcss/pull/19727))
  171| - Skip full reload for server only modules scanned by client CSS when using `@tailwindcss/vite` ([#19745](https://github.com/tailwindlabs/tailwindcss/pull/19745))
  172| - Add support for Vite 8 in `@tailwindcss/vite` ([#19790](https://github.com/tailwindlabs/tailwindcss/pull/19790))
  173| - Improve canonicalization for bare values exceeding default spacing scale suggestions (e.g. `w-1234 h-1234` → `size-1234`) ([#19809](https://github.com/tailwindlabs/tailwindcss/pull/19809))
  174| - Fix canonicalization resulting in empty list (e.g. `w-5 h-5 size-5` → `''` instead of `size-5`) ([#19812](https://github.com/tailwindlabs/tailwindcss/pull/19812))
  175| - Resolve tsconfig paths to allow for `@import '@/path/to/file';` when using `@tailwindcss/vite` ([#19803](https://github.com/tailwindlabs/tailwindcss/pull/19803))
  176| 
  177| ## [4.2.1] - 2026-02-23
  178| 
  179| ### Fixed
  180| 
  181| - Allow trailing dash in functional utility names for backwards compatibility ([#19696](https://github.com/tailwindlabs/tailwindcss/pull/19696))
  182| - Properly detect classes containing `.` characters within curly braces in MDX files ([#19711](https://github.com/tailwindlabs/tailwindcss/pull/19711))
  183| 
  184| ## [4.2.0] - 2026-02-18
  185| 
  186| ### Added
  187| 
  188| - Add mauve, olive, mist, and taupe color palettes to the default theme ([#19627](https://github.com/tailwindlabs/tailwindcss/pull/19627))
  189| - Add `@tailwindcss/webpack` package to run Tailwind CSS as a webpack plugin ([#19610](https://github.com/tailwindlabs/tailwindcss/pull/19610))
  190| - Add `pbs-*` and `pbe-*` utilities for `padding-block-start` and `padding-block-end` ([#19601](https://github.com/tailwindlabs/tailwindcss/pull/19601))
  191| - Add `mbs-*` and `mbe-*` utilities for `margin-block-start` and `margin-block-end` ([#19601](https://github.com/tailwindlabs/tailwindcss/pull/19601))
  192| - Add `scroll-pbs-*` and `scroll-pbe-*` utilities for `scroll-padding-block-start` and `scroll-padding-block-end` ([#19601](https://github.com/tailwindlabs/tailwindcss/pull/19601))
  193| - Add `scroll-mbs-*` and `scroll-mbe-*` utilities for `scroll-margin-block-start` and `scroll-margin-block-end` ([#19601](https://github.com/tailwindlabs/tailwindcss/pull/19601))
  194| - Add `border-bs-*` and `border-be-*` utilities for `border-block-start` and `border-block-end` ([#19601](https://github.com/tailwindlabs/tailwindcss/pull/19601))
  195| - Add `inline-*`, `min-inline-*`, `max-inline-*` utilities for `inline-size`, `min-inline-size`, and `max-inline-size` ([#19612](https://github.com/tailwindlabs/tailwindcss/pull/19612))
  196| - Add `block-*`, `min-block-*`, `max-block-*` utilities for `block-size`, `min-block-size`, and `max-block-size` ([#19612](https://github.com/tailwindlabs/tailwindcss/pull/19612))
  197| - Add `inset-s-*`, `inset-e-*`, `inset-bs-*`, `inset-be-*` utilities for `inset-inline-start`, `inset-inline-end`, `inset-block-start`, and `inset-block-end` ([#19613](https://github.com/tailwindlabs/tailwindcss/pull/19613))
  198| - Add `font-features-*` utility for `font-feature-settings` ([#19623](https://github.com/tailwindlabs/tailwindcss/pull/19623))
  199| 
  200| ### Fixed
```
