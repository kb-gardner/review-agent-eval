# PR pack: expressjs/express#7377
Title: feat: allow conditional revalidation for QUERY requests (v4)
Merge commit: 61ccf2ea8c1bd19cbca6acfb7cd276c5fcd410d3

## Diff
```diff
diff --git a/History.md b/History.md
index 1505356e8d0..bbbc2534d0b 100644
--- a/History.md
+++ b/History.md
@@ -1,3 +1,9 @@
+unreleased
+==========
+
+  * Allow conditional revalidation for QUERY requests
+    - `req.fresh` now includes QUERY in the freshness check, so QUERY responses can return 304 when a validator matches
+
 4.22.2 / 2026-05-11
 ==========
 
diff --git a/lib/request.js b/lib/request.js
index 3f1eeca6c1a..e33262f20df 100644
--- a/lib/request.js
+++ b/lib/request.js
@@ -469,8 +469,8 @@ defineGetter(req, 'fresh', function(){
   var res = this.res
   var status = res.statusCode
 
-  // GET or HEAD for weak freshness validation only
-  if ('GET' !== method && 'HEAD' !== method) return false;
+  // GET, HEAD, or QUERY for weak freshness validation only
+  if ('GET' !== method && 'HEAD' !== method && 'QUERY' !== method) return false;
 
   // 2xx or 304 as per rfc2616 14.26
   if ((status >= 200 && status < 300) || 304 === status) {
diff --git a/test/req.fresh.js b/test/req.fresh.js
index 9160e2caaf6..f22ce3f3062 100644
--- a/test/req.fresh.js
+++ b/test/req.fresh.js
@@ -2,6 +2,7 @@
 
 var express = require('../')
   , request = require('supertest');
+var shouldSkipQuery = require('./support/utils').shouldSkipQuery
 
 describe('req', function(){
   describe('.fresh', function(){
@@ -46,5 +47,42 @@ describe('req', function(){
       .get('/')
       .expect(200, 'false', done);
     })
+
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
   })
 })

```

## Touched files at the merge commit (window of up to 200 lines around the first changed hunk)

### test/req.fresh.js (lines 1 to 89 of 89)
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
   87|   })
   88| })
   89| 
```

### History.md (lines 1 to 200 of 3683)
```
    1| unreleased
    2| ==========
    3| 
    4|   * Allow conditional revalidation for QUERY requests
    5|     - `req.fresh` now includes QUERY in the freshness check, so QUERY responses can return 304 when a validator matches
    6| 
    7| 4.22.2 / 2026-05-11
    8| ==========
    9| 
   10| * fix: restore >20 array parsing for `req.query` repeated keys ([`8d09bfe6`](https://github.com/expressjs/express/commit/8d09bfe6d88983da5c3e12cfdd54782c4dc675db))
   11|   * This also unifies array-cap behavior across notations. Indexed notation (`a[0]=...`) was historically capped at qs's default `arrayLimit` of 20 even in older qs versions; after this change it also allows up to 1000 items.
   12| * deps: qs@~6.15.1
   13| * deps: body-parser@~1.20.5
   14| 
   15| 4.22.1 / 2025-12-01
   16| ==========
   17| 
   18|   * Revert security fix for [CVE-2024-51999](https://www.cve.org/CVERecord?id=CVE-2024-51999) ([GHSA-pj86-cfqh-vqx6](https://github.com/expressjs/express/security/advisories/GHSA-pj86-cfqh-vqx6))
   19|     * The prior release (4.22.0) included an erroneous breaking change related to the extended query parser. There is no actual security vulnerability associated with this behavior (CVE-2024-51999 has been rejected). The change has been fully reverted in this release.
   20| 
   21| 4.22.0 / 2025-12-01
   22| ==========
   23|   * Security fix for [CVE-2024-51999](https://www.cve.org/CVERecord?id=CVE-2024-51999) ([GHSA-pj86-cfqh-vqx6](https://github.com/expressjs/express/security/advisories/GHSA-pj86-cfqh-vqx6))
   24|   * deps: use tilde notation for dependencies
   25|   * deps: qs@6.14.0
   26| 
   27| 4.21.2 / 2024-11-06
   28| ==========
   29| 
   30|   * deps: path-to-regexp@0.1.12
   31|     - Fix backtracking protection
   32|   * deps: path-to-regexp@0.1.11
   33|     - Throws an error on invalid path values
   34| 
   35| 4.21.1 / 2024-10-08
   36| ==========
   37| 
   38|   * Backported a fix for [CVE-2024-47764](https://nvd.nist.gov/vuln/detail/CVE-2024-47764)
   39| 
   40| 
   41| 4.21.0 / 2024-09-11
   42| ==========
   43| 
   44|   * Deprecate `res.location("back")` and `res.redirect("back")` magic string
   45|   * deps: serve-static@1.16.2
   46|     * includes send@0.19.0
   47|   * deps: finalhandler@1.3.1
   48|   * deps: qs@6.13.0
   49| 
   50| 4.20.0 / 2024-09-10
   51| ==========
   52|   * deps: serve-static@0.16.0
   53|     * Remove link renderization in html while redirecting
   54|   * deps: send@0.19.0
   55|     * Remove link renderization in html while redirecting
   56|   * deps: body-parser@0.6.0
   57|     * add `depth` option to customize the depth level in the parser
   58|     * IMPORTANT: The default `depth` level for parsing URL-encoded data is now `32` (previously was `Infinity`)
   59|   * Remove link renderization in html while using `res.redirect`
   60|   * deps: path-to-regexp@0.1.10
   61|     - Adds support for named matching groups in the routes using a regex
   62|     - Adds backtracking protection to parameters without regexes defined
   63|   * deps: encodeurl@~2.0.0
   64|     - Removes encoding of `\`, `|`, and `^` to align better with URL spec
   65|   * Deprecate passing `options.maxAge` and `options.expires` to `res.clearCookie`
   66|     - Will be ignored in v5, clearCookie will set a cookie with an expires in the past to instruct clients to delete the cookie
   67| 
   68| 4.19.2 / 2024-03-25
   69| ==========
   70| 
   71|   * Improved fix for open redirect allow list bypass
   72| 
   73| 4.19.1 / 2024-03-20
   74| ==========
   75| 
   76|   * Allow passing non-strings to res.location with new encoding handling checks
   77| 
   78| 4.19.0 / 2024-03-20
   79| ==========
   80| 
   81|   * Prevent open redirect allow list bypass due to encodeurl
   82|   * deps: cookie@0.6.0
   83| 
   84| 4.18.3 / 2024-02-29
   85| ==========
   86| 
   87|   * Fix routing requests without method
   88|   * deps: body-parser@1.20.2
   89|     - Fix strict json error message on Node.js 19+
   90|     - deps: content-type@~1.0.5
   91|     - deps: raw-body@2.5.2
   92|   * deps: cookie@0.6.0
   93|     - Add `partitioned` option
   94| 
   95| 4.18.2 / 2022-10-08
   96| ===================
   97| 
   98|   * Fix regression routing a large stack in a single route
   99|   * deps: body-parser@1.20.1
  100|     - deps: qs@6.11.0
  101|     - perf: remove unnecessary object clone
  102|   * deps: qs@6.11.0
  103| 
  104| 4.18.1 / 2022-04-29
  105| ===================
  106| 
  107|   * Fix hanging on large stack of sync routes
  108| 
  109| 4.18.0 / 2022-04-25
  110| ===================
  111| 
  112|   * Add "root" option to `res.download`
  113|   * Allow `options` without `filename` in `res.download`
  114|   * Deprecate string and non-integer arguments to `res.status`
  115|   * Fix behavior of `null`/`undefined` as `maxAge` in `res.cookie`
  116|   * Fix handling very large stacks of sync middleware
  117|   * Ignore `Object.prototype` values in settings through `app.set`/`app.get`
  118|   * Invoke `default` with same arguments as types in `res.format`
  119|   * Support proper 205 responses using `res.send`
  120|   * Use `http-errors` for `res.format` error
  121|   * deps: body-parser@1.20.0
  122|     - Fix error message for json parse whitespace in `strict`
  123|     - Fix internal error when inflated body exceeds limit
  124|     - Prevent loss of async hooks context
  125|     - Prevent hanging when request already read
  126|     - deps: depd@2.0.0
  127|     - deps: http-errors@2.0.0
  128|     - deps: on-finished@2.4.1
  129|     - deps: qs@6.10.3
  130|     - deps: raw-body@2.5.1
  131|   * deps: cookie@0.5.0
  132|     - Add `priority` option
  133|     - Fix `expires` option to reject invalid dates
  134|   * deps: depd@2.0.0
  135|     - Replace internal `eval` usage with `Function` constructor
  136|     - Use instance methods on `process` to check for listeners
  137|   * deps: finalhandler@1.2.0
  138|     - Remove set content headers that break response
  139|     - deps: on-finished@2.4.1
  140|     - deps: statuses@2.0.1
  141|   * deps: on-finished@2.4.1
  142|     - Prevent loss of async hooks context
  143|   * deps: qs@6.10.3
  144|   * deps: send@0.18.0
  145|     - Fix emitted 416 error missing headers property
  146|     - Limit the headers removed for 304 response
  147|     - deps: depd@2.0.0
  148|     - deps: destroy@1.2.0
  149|     - deps: http-errors@2.0.0
  150|     - deps: on-finished@2.4.1
  151|     - deps: statuses@2.0.1
  152|   * deps: serve-static@1.15.0
  153|     - deps: send@0.18.0
  154|   * deps: statuses@2.0.1
  155|     - Remove code 306
  156|     - Rename `425 Unordered Collection` to standard `425 Too Early`
  157| 
  158| 4.17.3 / 2022-02-16
  159| ===================
  160| 
  161|   * deps: accepts@~1.3.8
  162|     - deps: mime-types@~2.1.34
  163|     - deps: negotiator@0.6.3
  164|   * deps: body-parser@1.19.2
  165|     - deps: bytes@3.1.2
  166|     - deps: qs@6.9.7
  167|     - deps: raw-body@2.4.3
  168|   * deps: cookie@0.4.2
  169|   * deps: qs@6.9.7
  170|     * Fix handling of `__proto__` keys
  171|   * pref: remove unnecessary regexp for trust proxy
  172| 
  173| 4.17.2 / 2021-12-16
  174| ===================
  175| 
  176|   * Fix handling of `undefined` in `res.jsonp`
  177|   * Fix handling of `undefined` when `"json escape"` is enabled
  178|   * Fix incorrect middleware execution with unanchored `RegExp`s
  179|   * Fix `res.jsonp(obj, status)` deprecation message
  180|   * Fix typo in `res.is` JSDoc
  181|   * deps: body-parser@1.19.1
  182|     - deps: bytes@3.1.1
  183|     - deps: http-errors@1.8.1
  184|     - deps: qs@6.9.6
  185|     - deps: raw-body@2.4.2
  186|     - deps: safe-buffer@5.2.1
  187|     - deps: type-is@~1.6.18
  188|   * deps: content-disposition@0.5.4
  189|     - deps: safe-buffer@5.2.1
  190|   * deps: cookie@0.4.1
  191|     - Fix `maxAge` option to reject invalid values
  192|   * deps: proxy-addr@~2.0.7
  193|     - Use `req.socket` over deprecated `req.connection`
  194|     - deps: forwarded@0.2.0
  195|     - deps: ipaddr.js@1.9.1
  196|   * deps: qs@6.9.6
  197|   * deps: safe-buffer@5.2.1
  198|   * deps: send@0.17.2
  199|     - deps: http-errors@1.8.1
  200|     - deps: ms@2.1.3
```

### lib/request.js (lines 410 to 526 of 526)
```
  410|  */
  411| 
  412| defineGetter(req, 'path', function path() {
  413|   return parse(this).pathname;
  414| });
  415| 
  416| /**
  417|  * Parse the "Host" header field to a hostname.
  418|  *
  419|  * When the "trust proxy" setting trusts the socket
  420|  * address, the "X-Forwarded-Host" header field will
  421|  * be trusted.
  422|  *
  423|  * @return {String}
  424|  * @public
  425|  */
  426| 
  427| defineGetter(req, 'hostname', function hostname(){
  428|   var trust = this.app.get('trust proxy fn');
  429|   var host = this.get('X-Forwarded-Host');
  430| 
  431|   if (!host || !trust(this.connection.remoteAddress, 0)) {
  432|     host = this.get('Host');
  433|   } else if (host.indexOf(',') !== -1) {
  434|     // Note: X-Forwarded-Host is normally only ever a
  435|     //       single value, but this is to be safe.
  436|     host = host.substring(0, host.indexOf(',')).trimRight()
  437|   }
  438| 
  439|   if (!host) return;
  440| 
  441|   // IPv6 literal support
  442|   var offset = host[0] === '['
  443|     ? host.indexOf(']') + 1
  444|     : 0;
  445|   var index = host.indexOf(':', offset);
  446| 
  447|   return index !== -1
  448|     ? host.substring(0, index)
  449|     : host;
  450| });
  451| 
  452| // TODO: change req.host to return host in next major
  453| 
  454| defineGetter(req, 'host', deprecate.function(function host(){
  455|   return this.hostname;
  456| }, 'req.host: Use req.hostname instead'));
  457| 
  458| /**
  459|  * Check if the request is fresh, aka
  460|  * Last-Modified and/or the ETag
  461|  * still match.
  462|  *
  463|  * @return {Boolean}
  464|  * @public
  465|  */
  466| 
  467| defineGetter(req, 'fresh', function(){
  468|   var method = this.method;
  469|   var res = this.res
  470|   var status = res.statusCode
  471| 
  472|   // GET, HEAD, or QUERY for weak freshness validation only
  473|   if ('GET' !== method && 'HEAD' !== method && 'QUERY' !== method) return false;
  474| 
  475|   // 2xx or 304 as per rfc2616 14.26
  476|   if ((status >= 200 && status < 300) || 304 === status) {
  477|     return fresh(this.headers, {
  478|       'etag': res.get('ETag'),
  479|       'last-modified': res.get('Last-Modified')
  480|     })
  481|   }
  482| 
  483|   return false;
  484| });
  485| 
  486| /**
  487|  * Check if the request is stale, aka
  488|  * "Last-Modified" and / or the "ETag" for the
  489|  * resource has changed.
  490|  *
  491|  * @return {Boolean}
  492|  * @public
  493|  */
  494| 
  495| defineGetter(req, 'stale', function stale(){
  496|   return !this.fresh;
  497| });
  498| 
  499| /**
  500|  * Check if the request was an _XMLHttpRequest_.
  501|  *
  502|  * @return {Boolean}
  503|  * @public
  504|  */
  505| 
  506| defineGetter(req, 'xhr', function xhr(){
  507|   var val = this.get('X-Requested-With') || '';
  508|   return val.toLowerCase() === 'xmlhttprequest';
  509| });
  510| 
  511| /**
  512|  * Helper function for creating a getter on an object.
  513|  *
  514|  * @param {Object} obj
  515|  * @param {String} name
  516|  * @param {Function} getter
  517|  * @private
  518|  */
  519| function defineGetter(obj, name, getter) {
  520|   Object.defineProperty(obj, name, {
  521|     configurable: true,
  522|     enumerable: true,
  523|     get: getter
  524|   });
  525| }
  526| 
```
