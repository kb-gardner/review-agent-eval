# PR pack: expressjs/express#7366
Title: feat: allow conditional revalidation for QUERY requests
Merge commit: ae6dd37680e3a00618d6c8a3e522f0ee4eeba1a4

## Diff
```diff
diff --git a/History.md b/History.md
index 9e6ee903f40..8a4293ab547 100644
--- a/History.md
+++ b/History.md
@@ -9,6 +9,16 @@
 
 ## 🚀 Improvements
 
+* Allow conditional revalidation for QUERY requests. `req.fresh` previously only validated freshness for GET and HEAD requests, so QUERY responses never returned 304 despite a matching validator. Since QUERY is a safe, idempotent, and cacheable method that supports conditional requests, it is now included in the freshness check - by [@Cherry](https://github.com/Cherry) in [#7366](https://github.com/expressjs/express/pull/7366)
+
+    ```js
+    // QUERY /reports with If-None-Match: "12345"
+    app.query('/reports', (req, res) => {
+      res.set('ETag', '"12345"');
+      res.send(results); // now responds 304 Not Modified
+    });
+    ```
+
 * Improve HTML structure in `res.redirect()` responses when HTML format is accepted by adding `<!DOCTYPE html>`, `<title>`, and `<body>` tags for better browser compatibility - by [@Bernice55231](https://github.com/Bernice55231) in [#5167](https://github.com/expressjs/express/pull/5167)
 
 * When calling `app.render` with options set to null, the locals object is handled correctly, preventing unexpected errors and making the method behave the same as when options is omitted or an empty object is passed - by [AkaHarshit](https://github.com/AkaHarshit) in [#6903](https://github.com/expressjs/express/pull/6903)
diff --git a/lib/request.js b/lib/request.js
index 68243f52b6d..1eb7f9ca16a 100644
--- a/lib/request.js
+++ b/lib/request.js
@@ -471,8 +471,8 @@ defineGetter(req, 'fresh', function(){
   var res = this.res
   var status = res.statusCode
 
-  // GET or HEAD for weak freshness validation only
-  if ('GET' !== method && 'HEAD' !== method) return false;
+  // GET, HEAD, or QUERY for weak freshness validation only
+  if ('GET' !== method && 'HEAD' !== method && 'QUERY' !== method) return false;
 
   // 2xx or 304 as per rfc2616 14.26
   if ((status >= 200 && status < 300) || 304 === status) {
diff --git a/test/req.fresh.js b/test/req.fresh.js
index 3bf6a1f65a7..318a651633f 100644
--- a/test/req.fresh.js
+++ b/test/req.fresh.js
@@ -2,6 +2,7 @@
 
 var express = require('../')
   , request = require('supertest');
+var shouldSkipQuery = require('./support/utils').shouldSkipQuery
 
 describe('req', function(){
   describe('.fresh', function(){
@@ -47,6 +48,43 @@ describe('req', function(){
       .expect(200, 'false', done);
     })
 
+    it('should return true for a QUERY request with a body when the resource is not modified', function(done){
+      if (shouldSkipQuery(process.versions.node)) {
+        this.skip()
+      }
+      var app = express();
+      var etag = '"12345"';
+
+      app.use(function(req, res){
+        res.set('ETag', etag);
+        res.send(req.fresh);
+      });
+
+      request(app)
+      .query('/')
+      .set('If-None-Match', etag)
+      .send({ ids: ['a', 'b'] })
+      .expect(304, done);
+    })
+
+    it('should return false for a QUERY request with a body when the resource is modified', function(done){
+      if (shouldSkipQuery(process.versions.node)) {
+        this.skip()
+      }
+      var app = express();
+
+      app.use(function(req, res){
+        res.set('ETag', '"123"');
+        res.send(req.fresh);
+      });
+
+      request(app)
+      .query('/')
+      .set('If-None-Match', '"12345"')
+      .send({ ids: ['a', 'b'] })
+      .expect(200, 'false', done);
+    })
+
     it('should ignore "If-Modified-Since" when "If-None-Match" is present', function(done) {
       var app = express();
       const etag = '"FooBar"'

```

## Touched files at the merge commit (window of up to 200 lines around the first changed hunk)

### test/req.fresh.js (lines 1 to 109 of 109)
```
    1| 'use strict'
    2| 
    3| var express = require('../')
    4|   , request = require('supertest');
    5| var shouldSkipQuery = require('./support/utils').shouldSkipQuery
    6| 
    7| describe('req', function(){
    8|   describe('.fresh', function(){
    9|     it('should return true when the resource is not modified', function(done){
   10|       var app = express();
   11|       var etag = '"12345"';
   12| 
   13|       app.use(function(req, res){
   14|         res.set('ETag', etag);
   15|         res.send(req.fresh);
   16|       });
   17| 
   18|       request(app)
   19|       .get('/')
   20|       .set('If-None-Match', etag)
   21|       .expect(304, done);
   22|     })
   23| 
   24|     it('should return false when the resource is modified', function(done){
   25|       var app = express();
   26| 
   27|       app.use(function(req, res){
   28|         res.set('ETag', '"123"');
   29|         res.send(req.fresh);
   30|       });
   31| 
   32|       request(app)
   33|       .get('/')
   34|       .set('If-None-Match', '"12345"')
   35|       .expect(200, 'false', done);
   36|     })
   37| 
   38|     it('should return false without response headers', function(done){
   39|       var app = express();
   40| 
   41|       app.disable('x-powered-by')
   42|       app.use(function(req, res){
   43|         res.send(req.fresh);
   44|       });
   45| 
   46|       request(app)
   47|       .get('/')
   48|       .expect(200, 'false', done);
   49|     })
   50| 
   51|     it('should return true for a QUERY request with a body when the resource is not modified', function(done){
   52|       if (shouldSkipQuery(process.versions.node)) {
   53|         this.skip()
   54|       }
   55|       var app = express();
   56|       var etag = '"12345"';
   57| 
   58|       app.use(function(req, res){
   59|         res.set('ETag', etag);
   60|         res.send(req.fresh);
   61|       });
   62| 
   63|       request(app)
   64|       .query('/')
   65|       .set('If-None-Match', etag)
   66|       .send({ ids: ['a', 'b'] })
   67|       .expect(304, done);
   68|     })
   69| 
   70|     it('should return false for a QUERY request with a body when the resource is modified', function(done){
   71|       if (shouldSkipQuery(process.versions.node)) {
   72|         this.skip()
   73|       }
   74|       var app = express();
   75| 
   76|       app.use(function(req, res){
   77|         res.set('ETag', '"123"');
   78|         res.send(req.fresh);
   79|       });
   80| 
   81|       request(app)
   82|       .query('/')
   83|       .set('If-None-Match', '"12345"')
   84|       .send({ ids: ['a', 'b'] })
   85|       .expect(200, 'false', done);
   86|     })
   87| 
   88|     it('should ignore "If-Modified-Since" when "If-None-Match" is present', function(done) {
   89|       var app = express();
   90|       const etag = '"FooBar"'
   91|       const now = Date.now()
   92| 
   93|       app.disable('x-powered-by')
   94|       app.use(function(req, res) {
   95|         res.set('Etag', etag)
   96|         res.set('Last-Modified', new Date(now).toUTCString())
   97|         res.send(req.fresh);
   98|       });
   99| 
  100|       request(app)
  101|         .get('/')
  102|         .set('If-Modified-Since', new Date(now - 1000).toUTCString)
  103|         .set('If-None-Match', etag)
  104|         .expect(304, done);
  105|     })
  106| 
  107|   })
  108| })
  109| 
```

### History.md (lines 1 to 200 of 3922)
```
    1| # Unreleased Changes
    2| 
    3| ## 🐞 Bug fixes
    4| 
    5| - Fixed HTTP header conflict between Content-Length and Transfer-Encoding in res.send - by [@YuryShkoda](https://github.com/YuryShkoda) in [#4893](https://github.com/expressjs/express/pull/4893)
    6| 
    7| 
    8|     Fixed the behavior of `res.send()` to prevent conflicts between `Content-Length` and `Transfer-Encoding` HTTP headers in responses. The `Content-Length` header in `res.send()` is now only added when a `Transfer-Encoding` header is not present, complying with the HTTP specification that states both headers should not coexist in the same response
    9| 
   10| ## 🚀 Improvements
   11| 
   12| * Allow conditional revalidation for QUERY requests. `req.fresh` previously only validated freshness for GET and HEAD requests, so QUERY responses never returned 304 despite a matching validator. Since QUERY is a safe, idempotent, and cacheable method that supports conditional requests, it is now included in the freshness check - by [@Cherry](https://github.com/Cherry) in [#7366](https://github.com/expressjs/express/pull/7366)
   13| 
   14|     ```js
   15|     // QUERY /reports with If-None-Match: "12345"
   16|     app.query('/reports', (req, res) => {
   17|       res.set('ETag', '"12345"');
   18|       res.send(results); // now responds 304 Not Modified
   19|     });
   20|     ```
   21| 
   22| * Improve HTML structure in `res.redirect()` responses when HTML format is accepted by adding `<!DOCTYPE html>`, `<title>`, and `<body>` tags for better browser compatibility - by [@Bernice55231](https://github.com/Bernice55231) in [#5167](https://github.com/expressjs/express/pull/5167)
   23| 
   24| * When calling `app.render` with options set to null, the locals object is handled correctly, preventing unexpected errors and making the method behave the same as when options is omitted or an empty object is passed - by [AkaHarshit](https://github.com/AkaHarshit) in [#6903](https://github.com/expressjs/express/pull/6903)
   25| 
   26|     ```js
   27|     app.render('index', null, callback); // now works as expected
   28|     ```
   29| 
   30| * Upgrade `content-type` to `^2.0.0`, bringing a faster parser (~1.5x quicker `Content-Type` parsing/formatting in `res.send()`) along with a behavior change: `res.send()` now keeps any existing parameters when adding the charset and no longer throws on a `Content-Type` that fails to parse - by [@blakeembrey](https://github.com/blakeembrey) in [#7234](https://github.com/expressjs/express/pull/7234)
   31| 
   32|     ```js
   33|     res.set('Content-Type', 'text/plain; foo=bar').send('hey');
   34|     // -> Content-Type: text/plain; foo=bar; charset=utf-8
   35|     ```
   36| 
   37| * The default error handler now logs the full error object instead of only its stack trace, so nested details such as `Error.cause` and library-specific properties (e.g. Sequelize's `parent`/`original`) are no longer swallowed - by [@Nitin-Mohapatra](https://github.com/Nitin-Mohapatra) in [#6464](https://github.com/expressjs/express/pull/6464)
   38| 
   39| * Upgrade `content-disposition` to `^2.0.0`, which changes the `Content-Disposition` header emitted by `res.download()`, `res.attachment()`, and `res.sendFile()`: file names that are valid HTTP tokens are no longer wrapped in quotes. This is equivalent per RFC 6266, but applications asserting on the exact header bytes should update their expectations - by [@blakeembrey](https://github.com/blakeembrey) in [#7233](https://github.com/expressjs/express/pull/7233)
   40| 
   41|     ```js
   42|     res.attachment('user.html');
   43|     // before -> Content-Disposition: attachment; filename="user.html"
   44|     // after  -> Content-Disposition: attachment; filename=user.html
   45|     ```
   46| 
   47| ## ⚡ Performance
   48| 
   49| * Avoid duplicate Content-Type header processing in `res.send()` when sending string responses without an explicit Content-Type header - by [@bjohansebas](https://github.com/bjohansebas) in [#6991](https://github.com/expressjs/express/pull/6991)
   50| 
   51| 5.2.1 / 2025-12-01
   52| =======================
   53| 
   54| * Revert security fix for [CVE-2024-51999](https://www.cve.org/CVERecord?id=CVE-2024-51999) ([GHSA-pj86-cfqh-vqx6](https://github.com/expressjs/express/security/advisories/GHSA-pj86-cfqh-vqx6))
   55|   * The prior release (5.2.0) included an erroneous breaking change related to the extended query parser. There is no actual security vulnerability associated with this behavior (CVE-2024-51999 has been rejected). The change has been fully reverted in this release.
   56| 
   57| 5.2.0 / 2025-12-01
   58| ========================
   59| 
   60| * Security fix for [CVE-2024-51999](https://www.cve.org/CVERecord?id=CVE-2024-51999) ([GHSA-pj86-cfqh-vqx6](https://github.com/expressjs/express/security/advisories/GHSA-pj86-cfqh-vqx6))
   61| * deps: `body-parser@^2.2.1`
   62| * A deprecation warning was added when using `res.redirect` with undefined arguments, Express now emits a warning to help detect calls that pass undefined as the status or URL and make them easier to fix.
   63| 
   64| 5.1.0 / 2025-03-31
   65| ========================
   66| 
   67| * Add support for `Uint8Array` in `res.send()`
   68| * Add support for ETag option in `res.sendFile()`
   69| * Add support for multiple links with the same rel in `res.links()`
   70| * Add funding field to package.json
   71| * perf: use loop for acceptParams
   72| * refactor: prefix built-in node module imports
   73| * deps: remove `setprototypeof`
   74| * deps: remove `safe-buffer`
   75| * deps: remove `utils-merge`
   76| * deps: remove `methods`
   77| * deps: remove `depd`
   78| * deps: `debug@^4.4.0`
   79| * deps: `body-parser@^2.2.0`
   80| * deps: `router@^2.2.0`
   81| * deps: `content-type@^1.0.5`
   82| * deps: `finalhandler@^2.1.0`
   83| * deps: `qs@^6.14.0`
   84| * deps: `server-static@2.2.0`
   85| * deps: `type-is@2.0.1`
   86| 
   87| 5.0.1 / 2024-10-08
   88| ==========
   89| 
   90| * Update `cookie` semver lock to address [CVE-2024-47764](https://nvd.nist.gov/vuln/detail/CVE-2024-47764)
   91| 
   92| 5.0.0 / 2024-09-10
   93| =========================
   94| * remove:
   95|   - `path-is-absolute` dependency - use `path.isAbsolute` instead
   96| * breaking:
   97|   * `res.status()` accepts only integers, and input must be greater than 99 and less than 1000
   98|     * will throw a `RangeError: Invalid status code: ${code}. Status code must be greater than 99 and less than 1000.` for inputs outside this range
   99|     * will throw a `TypeError: Invalid status code: ${code}. Status code must be an integer.` for non integer inputs
  100|   * deps: send@1.0.0
  101|   * `res.redirect('back')` and `res.location('back')` is no longer a supported magic string, explicitly use `req.get('Referrer') || '/'`.
  102| * change:
  103|   - `res.clearCookie` will ignore user provided `maxAge` and `expires` options
  104| * deps: cookie-signature@^1.2.1
  105| * deps: debug@4.3.6
  106| * deps: merge-descriptors@^2.0.0
  107| * deps: serve-static@^2.1.0
  108| * deps: qs@6.13.0
  109| * deps: accepts@^2.0.0
  110| * deps: mime-types@^3.0.0
  111|   - `application/javascript` => `text/javascript`
  112| * deps: type-is@^2.0.0
  113| * deps: content-disposition@^1.0.0
  114| * deps: finalhandler@^2.0.0
  115| * deps: fresh@^2.0.0
  116| * deps: body-parser@^2.0.1
  117| * deps: send@^1.1.0
  118| 
  119| 5.0.0-beta.3 / 2024-03-25
  120| =========================
  121| 
  122| This incorporates all changes after 4.19.1 up to 4.19.2.
  123| 
  124| 5.0.0-beta.2 / 2024-03-20
  125| =========================
  126| 
  127| This incorporates all changes after 4.17.2 up to 4.19.1.
  128| 
  129| 5.0.0-beta.1 / 2022-02-14
  130| =========================
  131| 
  132| This is the first Express 5.0 beta release, based off 4.17.2 and includes
  133| changes from 5.0.0-alpha.8.
  134| 
  135|   * change:
  136|     - Default "query parser" setting to `'simple'`
  137|     - Requires Node.js 4+
  138|     - Use `mime-types` for file to content type mapping
  139|   * deps: array-flatten@3.0.0
  140|   * deps: body-parser@2.0.0-beta.1
  141|     - `req.body` is no longer always initialized to `{}`
  142|     - `urlencoded` parser now defaults `extended` to `false`
  143|     - Use `on-finished` to determine when body read
  144|   * deps: router@2.0.0-beta.1
  145|     - Add new `?`, `*`, and `+` parameter modifiers
  146|     - Internalize private `router.process_params` method
  147|     - Matching group expressions are only RegExp syntax
  148|     - Named matching groups no longer available by position in `req.params`
  149|     - Regular expressions can only be used in a matching group
  150|     - Remove `debug` dependency
  151|     - Special `*` path segment behavior removed
  152|     - deps: array-flatten@3.0.0
  153|     - deps: parseurl@~1.3.3
  154|     - deps: path-to-regexp@3.2.0
  155|     - deps: setprototypeof@1.2.0
  156|   * deps: send@1.0.0-beta.1
  157|     - Change `dotfiles` option default to `'ignore'`
  158|     - Remove `hidden` option; use `dotfiles` option instead
  159|     - Use `mime-types` for file to content type mapping
  160|     - deps: debug@3.1.0
  161|   * deps: serve-static@2.0.0-beta.1
  162|     - Change `dotfiles` option default to `'ignore'`
  163|     - Remove `hidden` option; use `dotfiles` option instead
  164|     - Use `mime-types` for file to content type mapping
  165|     - Remove `express.static.mime` export; use `mime-types` package instead
  166|     - deps: send@1.0.0-beta.1
  167| 
  168| 5.0.0-alpha.8 / 2020-03-25
  169| ==========================
  170| 
  171| This is the eighth Express 5.0 alpha release, based off 4.17.1 and includes
  172| changes from 5.0.0-alpha.7.
  173| 
  174| 5.0.0-alpha.7 / 2018-10-26
  175| ==========================
  176| 
  177| This is the seventh Express 5.0 alpha release, based off 4.16.4 and includes
  178| changes from 5.0.0-alpha.6.
  179| 
  180| The major change with this alpha is the basic support for returned, rejected
  181| Promises in the router.
  182| 
  183|   * remove:
  184|     - `path-to-regexp` dependency
  185|   * deps: debug@3.1.0
  186|     - Add `DEBUG_HIDE_DATE` environment variable
  187|     - Change timer to per-namespace instead of global
  188|     - Change non-TTY date format
  189|     - Remove `DEBUG_FD` environment variable support
  190|     - Support 256 namespace colors
  191|   * deps: router@2.0.0-alpha.1
  192|     - Add basic support for returned, rejected Promises
  193|     - Fix JSDoc for `Router` constructor
  194|     - deps: debug@3.1.0
  195|     - deps: parseurl@~1.3.2
  196|     - deps: setprototypeof@1.1.0
  197|     - deps: utils-merge@1.0.1
  198| 
  199| 5.0.0-alpha.6 / 2017-09-24
  200| ==========================
```

### lib/request.js (lines 412 to 528 of 528)
```
  412|  * be trusted.
  413|  *
  414|  * @return {String}
  415|  * @public
  416|  */
  417| 
  418| defineGetter(req, 'host', function host(){
  419|   var trust = this.app.get('trust proxy fn');
  420|   var val = this.get('X-Forwarded-Host');
  421| 
  422|   if (!val || !trust(this.socket.remoteAddress, 0)) {
  423|     val = this.get('Host');
  424|   } else if (val.indexOf(',') !== -1) {
  425|     // Note: X-Forwarded-Host is normally only ever a
  426|     //       single value, but this is to be safe.
  427|     val = val.substring(0, val.indexOf(',')).trimEnd()
  428|   }
  429| 
  430|   return val || undefined;
  431| });
  432| 
  433| /**
  434|  * Parse the "Host" header field to a hostname.
  435|  *
  436|  * When the "trust proxy" setting trusts the socket
  437|  * address, the "X-Forwarded-Host" header field will
  438|  * be trusted.
  439|  *
  440|  * @return {String}
  441|  * @api public
  442|  */
  443| 
  444| defineGetter(req, 'hostname', function hostname(){
  445|   var host = this.host;
  446| 
  447|   if (!host) return;
  448| 
  449|   // IPv6 literal support
  450|   var offset = host[0] === '['
  451|     ? host.indexOf(']') + 1
  452|     : 0;
  453|   var index = host.indexOf(':', offset);
  454| 
  455|   return index !== -1
  456|     ? host.substring(0, index)
  457|     : host;
  458| });
  459| 
  460| /**
  461|  * Check if the request is fresh, aka
  462|  * Last-Modified or the ETag
  463|  * still match.
  464|  *
  465|  * @return {Boolean}
  466|  * @public
  467|  */
  468| 
  469| defineGetter(req, 'fresh', function(){
  470|   var method = this.method;
  471|   var res = this.res
  472|   var status = res.statusCode
  473| 
  474|   // GET, HEAD, or QUERY for weak freshness validation only
  475|   if ('GET' !== method && 'HEAD' !== method && 'QUERY' !== method) return false;
  476| 
  477|   // 2xx or 304 as per rfc2616 14.26
  478|   if ((status >= 200 && status < 300) || 304 === status) {
  479|     return fresh(this.headers, {
  480|       'etag': res.get('ETag'),
  481|       'last-modified': res.get('Last-Modified')
  482|     })
  483|   }
  484| 
  485|   return false;
  486| });
  487| 
  488| /**
  489|  * Check if the request is stale, aka
  490|  * "Last-Modified" and / or the "ETag" for the
  491|  * resource has changed.
  492|  *
  493|  * @return {Boolean}
  494|  * @public
  495|  */
  496| 
  497| defineGetter(req, 'stale', function stale(){
  498|   return !this.fresh;
  499| });
  500| 
  501| /**
  502|  * Check if the request was an _XMLHttpRequest_.
  503|  *
  504|  * @return {Boolean}
  505|  * @public
  506|  */
  507| 
  508| defineGetter(req, 'xhr', function xhr(){
  509|   var val = this.get('X-Requested-With') || '';
  510|   return val.toLowerCase() === 'xmlhttprequest';
  511| });
  512| 
  513| /**
  514|  * Helper function for creating a getter on an object.
  515|  *
  516|  * @param {Object} obj
  517|  * @param {String} name
  518|  * @param {Function} getter
  519|  * @private
  520|  */
  521| function defineGetter(obj, name, getter) {
  522|   Object.defineProperty(obj, name, {
  523|     configurable: true,
  524|     enumerable: true,
  525|     get: getter
  526|   });
  527| }
  528| 
```
