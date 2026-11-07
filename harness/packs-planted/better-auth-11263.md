# PR pack: better-auth/better-auth#11263
Title: fix(drizzle-adapter): defer relation metadata access
Merge commit: e18bc83172dca1804f0c5c3eff41d65e2849c557

## Diff
```diff
diff --git a/.changeset/lazy-drizzle-metadata.md b/.changeset/lazy-drizzle-metadata.md
new file mode 100644
index 00000000000..8ee1a157031
--- /dev/null
+++ b/.changeset/lazy-drizzle-metadata.md
@@ -0,0 +1,5 @@
+---
+"@better-auth/drizzle-adapter": patch
+---
+
+Defer Drizzle relation metadata access until a relational query runs, preserving lazy database initialization during application builds.
diff --git a/packages/drizzle-adapter/src/drizzle-adapter.test.ts b/packages/drizzle-adapter/src/drizzle-adapter.test.ts
index 13ab40d4b54..33539b314f7 100644
--- a/packages/drizzle-adapter/src/drizzle-adapter.test.ts
+++ b/packages/drizzle-adapter/src/drizzle-adapter.test.ts
@@ -7,7 +7,9 @@ import {
 	timestamp,
 } from "drizzle-orm/pg-core";
 import { describe, expect, it, vi } from "vitest";
+import type { DB } from "./drizzle-adapter";
 import { drizzleAdapter } from "./drizzle-adapter";
+import { drizzleAdapter as drizzleRelationsV2Adapter } from "./relations-v2";
 
 describe("drizzle-adapter", () => {
 	it("should create drizzle adapter", () => {
@@ -23,6 +25,94 @@ describe("drizzle-adapter", () => {
 		expect(adapter).toBeDefined();
 	});
 
+	/**
+	 * @see https://github.com/better-auth/better-auth/issues/11258
+	 */
+	describe("lazy database initialization", () => {
+		const adapterFactories = [
+			{
+				relations: "Relations v1",
+				createAdapter: drizzleAdapter,
+				relationMetadata: { schema: {} },
+			},
+			{
+				relations: "Relations v2",
+				createAdapter: drizzleRelationsV2Adapter,
+				relationMetadata: { relations: {} },
+			},
+		] as const;
+
+		it.for(
+			adapterFactories,
+		)("should not initialize a lazy database during $relations adapter construction", ({
+			createAdapter,
+		}) => {
+			const db = new Proxy({} as DB, {
+				get() {
+					throw new Error("DATABASE_URL is not set");
+				},
+			});
+
+			expect(() =>
+				createAdapter(db, { provider: "pg" })({
+					secret: "test-secret-that-is-at-least-32-chars-long!!",
+				}),
+			).not.toThrow();
+		});
+
+		it.for(
+			adapterFactories,
+		)("should support a first $relations joined read inside a transaction", async ({
+			createAdapter,
+			relationMetadata,
+		}) => {
+			const findFirst = vi.fn().mockResolvedValue(null);
+			const transactionDatabase = new Proxy(
+				{
+					query: { user: { findFirst } },
+				} as DB,
+				{
+					get(target, property, receiver) {
+						if (property === "_") {
+							throw new Error("Transaction metadata should not be read");
+						}
+						return Reflect.get(target, property, receiver);
+					},
+				},
+			);
+			const database = {
+				_: relationMetadata,
+				transaction: (callback: (transactionDatabase: DB) => unknown) =>
+					callback(transactionDatabase),
+			} as DB;
+			const user = pgTable("user", { id: text("id") });
+			const adapter = createAdapter(database, {
+				provider: "pg",
+				schema: { user },
+				transaction: true,
+			})({
+				advanced: {
+					database: { joins: true, validateSchema: false },
+				},
+			});
+
+			if (!adapter.transaction) {
+				throw new Error("Transaction support should be enabled");
+			}
+
+			await expect(
+				adapter.transaction((transactionAdapter) =>
+					transactionAdapter.findOne({
+						model: "user",
+						where: [],
+						join: { session: true },
+					}),
+				),
+			).resolves.toBeNull();
+			expect(findFirst).toHaveBeenCalledOnce();
+		});
+	});
+
 	it("should use unique column fallback for MySQL creates without an id", async () => {
 		const userRow = {
 			id: 42,
diff --git a/packages/drizzle-adapter/src/drizzle-adapter.ts b/packages/drizzle-adapter/src/drizzle-adapter.ts
index f86446ba819..5e928371d4c 100644
--- a/packages/drizzle-adapter/src/drizzle-adapter.ts
+++ b/packages/drizzle-adapter/src/drizzle-adapter.ts
@@ -36,6 +36,7 @@ import {
 	or,
 	sql,
 } from "drizzle-orm";
+import type { RelationKeysByModel } from "./join-relation-key";
 import {
 	buildRelationKeysByModel,
 	getOneToOneRelationKey,
@@ -184,7 +185,9 @@ export interface DrizzleAdapterConfig {
 export const drizzleAdapter = (db: DB, config: DrizzleAdapterConfig) => {
 	let lazyOptions: BetterAuthOptions | null = null;
 	let mysqlNoIdWarned = false;
-	const relationKeysByModel = buildRelationKeysByModel(db._?.schema);
+	let relationKeysByModel: RelationKeysByModel | undefined;
+	const getRelationKeysByModel = () =>
+		relationKeysByModel ?? buildRelationKeysByModel(db._?.schema);
 	const createCustomAdapter =
 		(db: DB, inTransaction = false): AdapterFactoryCustomizeAdapterCreator =>
 		({
@@ -803,7 +806,7 @@ export const drizzleAdapter = (db: DB, config: DrizzleAdapterConfig) => {
 								| undefined;
 
 							const renamedJoinResults: { key: string; target: string }[] = [];
-							const relationKeys = relationKeysByModel.get(queryModel);
+							const relationKeys = getRelationKeysByModel().get(queryModel);
 							includes = {};
 							const joinEntries = Object.entries(join);
 							for (const [joinModel, joinAttr] of joinEntries) {
@@ -890,7 +893,7 @@ export const drizzleAdapter = (db: DB, config: DrizzleAdapterConfig) => {
 								| undefined;
 
 							const renamedJoinResults: { key: string; target: string }[] = [];
-							const relationKeys = relationKeysByModel.get(queryModel);
+							const relationKeys = getRelationKeysByModel().get(queryModel);
 							includes = {};
 							const joinEntries = Object.entries(join);
 							for (const [joinModel, joinAttr] of joinEntries) {
diff --git a/packages/drizzle-adapter/src/relations-v2/index.ts b/packages/drizzle-adapter/src/relations-v2/index.ts
index f279a4cc5d2..1c4a531cbbe 100644
--- a/packages/drizzle-adapter/src/relations-v2/index.ts
+++ b/packages/drizzle-adapter/src/relations-v2/index.ts
@@ -33,6 +33,7 @@ import {
 	or,
 	sql,
 } from "drizzle-orm";
+import type { RelationKeysByModel } from "../join-relation-key";
 import {
 	buildRelationKeysByModel,
 	getOneToOneRelationKey,
@@ -274,7 +275,9 @@ export interface DrizzleAdapterConfig {
 export const drizzleAdapter = (db: DB, config: DrizzleAdapterConfig) => {
 	let lazyOptions: BetterAuthOptions | null = null;
 	let mysqlNoIdWarned = false;
-	const relationKeysByModel = buildRelationKeysByModel(db._?.relations);
+	let relationKeysByModel: RelationKeysByModel | undefined;
+	const getRelationKeysByModel = () =>
+		(relationKeysByModel ??= buildRelationKeysByModel(db._?.schema));
 	const createCustomAdapter =
 		(db: DB, inTransaction = false): AdapterFactoryCustomizeAdapterCreator =>
 		({ getFieldName, getDefaultModelName, options, schema: baSchema }) => {
@@ -724,7 +727,7 @@ export const drizzleAdapter = (db: DB, config: DrizzleAdapterConfig) => {
 								| undefined;
 
 							const renamedJoinResults: { key: string; target: string }[] = [];
-							const relationKeys = relationKeysByModel.get(queryModel);
+							const relationKeys = getRelationKeysByModel().get(queryModel);
 							includes = {};
 							const joinEntries = Object.entries(join);
 							for (const [joinModel, joinAttr] of joinEntries) {
@@ -812,7 +815,7 @@ export const drizzleAdapter = (db: DB, config: DrizzleAdapterConfig) => {
 								| undefined;
 
 							const renamedJoinResults: { key: string; target: string }[] = [];
-							const relationKeys = relationKeysByModel.get(queryModel);
+							const relationKeys = getRelationKeysByModel().get(queryModel);
 							includes = {};
 							const joinEntries = Object.entries(join);
 							for (const [joinModel, joinAttr] of joinEntries) {

```

## Touched files at the merge commit (window of up to 200 lines around the first changed hunk)

### packages/drizzle-adapter/src/drizzle-adapter.test.ts (lines 1 to 200 of 690)
```
    1| import { is, Param, SQL, sql } from "drizzle-orm";
    2| import {
    3| 	boolean,
    4| 	integer,
    5| 	pgTable,
    6| 	text,
    7| 	timestamp,
    8| } from "drizzle-orm/pg-core";
    9| import { describe, expect, it, vi } from "vitest";
   10| import type { DB } from "./drizzle-adapter";
   11| import { drizzleAdapter } from "./drizzle-adapter";
   12| import { drizzleAdapter as drizzleRelationsV2Adapter } from "./relations-v2";
   13| 
   14| describe("drizzle-adapter", () => {
   15| 	it("should create drizzle adapter", () => {
   16| 		const db = {
   17| 			_: {
   18| 				fullSchema: {},
   19| 			},
   20| 		} as any;
   21| 		const config = {
   22| 			provider: "sqlite" as const,
   23| 		};
   24| 		const adapter = drizzleAdapter(db, config);
   25| 		expect(adapter).toBeDefined();
   26| 	});
   27| 
   28| 	/**
   29| 	 * @see https://github.com/better-auth/better-auth/issues/11258
   30| 	 */
   31| 	describe("lazy database initialization", () => {
   32| 		const adapterFactories = [
   33| 			{
   34| 				relations: "Relations v1",
   35| 				createAdapter: drizzleAdapter,
   36| 				relationMetadata: { schema: {} },
   37| 			},
   38| 			{
   39| 				relations: "Relations v2",
   40| 				createAdapter: drizzleRelationsV2Adapter,
   41| 				relationMetadata: { relations: {} },
   42| 			},
   43| 		] as const;
   44| 
   45| 		it.for(
   46| 			adapterFactories,
   47| 		)("should not initialize a lazy database during $relations adapter construction", ({
   48| 			createAdapter,
   49| 		}) => {
   50| 			const db = new Proxy({} as DB, {
   51| 				get() {
   52| 					throw new Error("DATABASE_URL is not set");
   53| 				},
   54| 			});
   55| 
   56| 			expect(() =>
   57| 				createAdapter(db, { provider: "pg" })({
   58| 					secret: "test-secret-that-is-at-least-32-chars-long!!",
   59| 				}),
   60| 			).not.toThrow();
   61| 		});
   62| 
   63| 		it.for(
   64| 			adapterFactories,
   65| 		)("should support a first $relations joined read inside a transaction", async ({
   66| 			createAdapter,
   67| 			relationMetadata,
   68| 		}) => {
   69| 			const findFirst = vi.fn().mockResolvedValue(null);
   70| 			const transactionDatabase = new Proxy(
   71| 				{
   72| 					query: { user: { findFirst } },
   73| 				} as DB,
   74| 				{
   75| 					get(target, property, receiver) {
   76| 						if (property === "_") {
   77| 							throw new Error("Transaction metadata should not be read");
   78| 						}
   79| 						return Reflect.get(target, property, receiver);
   80| 					},
   81| 				},
   82| 			);
   83| 			const database = {
   84| 				_: relationMetadata,
   85| 				transaction: (callback: (transactionDatabase: DB) => unknown) =>
   86| 					callback(transactionDatabase),
   87| 			} as DB;
   88| 			const user = pgTable("user", { id: text("id") });
   89| 			const adapter = createAdapter(database, {
   90| 				provider: "pg",
   91| 				schema: { user },
   92| 				transaction: true,
   93| 			})({
   94| 				advanced: {
   95| 					database: { joins: true, validateSchema: false },
   96| 				},
   97| 			});
   98| 
   99| 			if (!adapter.transaction) {
  100| 				throw new Error("Transaction support should be enabled");
  101| 			}
  102| 
  103| 			await expect(
  104| 				adapter.transaction((transactionAdapter) =>
  105| 					transactionAdapter.findOne({
  106| 						model: "user",
  107| 						where: [],
  108| 						join: { session: true },
  109| 					}),
  110| 				),
  111| 			).resolves.toBeNull();
  112| 			expect(findFirst).toHaveBeenCalledOnce();
  113| 		});
  114| 	});
  115| 
  116| 	it("should use unique column fallback for MySQL creates without an id", async () => {
  117| 		const userRow = {
  118| 			id: 42,
  119| 			name: "Test",
  120| 			email: "test@example.com",
  121| 			emailVerified: false,
  122| 			image: null,
  123| 			createdAt: new Date(),
  124| 			updatedAt: new Date(),
  125| 		};
  126| 		const userTable = {
  127| 			id: { name: "id" },
  128| 			name: { name: "name" },
  129| 			email: { name: "email" },
  130| 			emailVerified: { name: "emailVerified" },
  131| 			image: { name: "image" },
  132| 			createdAt: { name: "createdAt" },
  133| 			updatedAt: { name: "updatedAt" },
  134| 		};
  135| 
  136| 		const selectFromWhere = vi.fn().mockReturnValue({
  137| 			limit: vi.fn().mockReturnValue({
  138| 				execute: vi.fn().mockResolvedValue([userRow]),
  139| 			}),
  140| 		});
  141| 		const selectFrom = vi.fn().mockReturnValue({
  142| 			from: vi.fn().mockReturnValue({
  143| 				where: selectFromWhere,
  144| 			}),
  145| 		});
  146| 
  147| 		const txProxy = new Proxy(
  148| 			{},
  149| 			{
  150| 				get(_target, prop) {
  151| 					if (prop === "select") return selectFrom;
  152| 					return undefined;
  153| 				},
  154| 			},
  155| 		);
  156| 
  157| 		const db = {
  158| 			_: { fullSchema: { user: userTable } },
  159| 			insert: vi.fn().mockReturnValue({
  160| 				values: vi.fn().mockReturnValue({
  161| 					config: { values: [{ name: { value: "Test" } }] },
  162| 					execute: vi.fn().mockResolvedValue(undefined),
  163| 				}),
  164| 			}),
  165| 			transaction: vi.fn().mockImplementation((fn: any) => fn(txProxy)),
  166| 		} as any;
  167| 		const factory = drizzleAdapter(db, { provider: "mysql" });
  168| 		const adapter = factory({
  169| 			secret: "test-secret-that-is-at-least-32-chars-long!!",
  170| 			advanced: {
  171| 				database: {
  172| 					generateId: false,
  173| 				},
  174| 			},
  175| 		});
  176| 
  177| 		const result = await adapter.create({
  178| 			model: "user",
  179| 			data: {
  180| 				name: "Test",
  181| 				email: "test@example.com",
  182| 			},
  183| 		});
  184| 
  185| 		expect(result).toBeDefined();
  186| 		expect(db.transaction).toHaveBeenCalled();
  187| 	});
  188| 
  189| 	describe("checkMissingFields", () => {
  190| 		function createMockDb(schema: Record<string, Record<string, any>>) {
  191| 			return {
  192| 				_: { fullSchema: schema },
  193| 				insert: vi.fn().mockReturnValue({
  194| 					values: vi.fn().mockReturnValue({
  195| 						returning: vi.fn().mockResolvedValue([{ id: "1", name: "test" }]),
  196| 					}),
  197| 				}),
  198| 			} as any;
  199| 		}
  200| 
```

### packages/drizzle-adapter/src/drizzle-adapter.ts (lines 1 to 200 of 1236)
```
    1| import type { BetterAuthOptions } from "@better-auth/core";
    2| import type {
    3| 	AdapterFactoryCustomizeAdapterCreator,
    4| 	AdapterFactoryOptions,
    5| 	DBAdapter,
    6| 	DBAdapterDebugLogOption,
    7| 	Where,
    8| } from "@better-auth/core/db/adapter";
    9| import { createAdapterFactory } from "@better-auth/core/db/adapter";
   10| import {
   11| 	checksSchema,
   12| 	createSchemaCheck,
   13| 	registerSchemaCheck,
   14| } from "@better-auth/core/db/internal";
   15| import { logger } from "@better-auth/core/env";
   16| import { BetterAuthError } from "@better-auth/core/error";
   17| import type { SQL } from "drizzle-orm";
   18| import {
   19| 	and,
   20| 	asc,
   21| 	Column,
   22| 	count,
   23| 	desc,
   24| 	eq,
   25| 	gt,
   26| 	gte,
   27| 	inArray,
   28| 	is,
   29| 	isNotNull,
   30| 	isNull,
   31| 	like,
   32| 	lt,
   33| 	lte,
   34| 	ne,
   35| 	notInArray,
   36| 	or,
   37| 	sql,
   38| } from "drizzle-orm";
   39| import type { RelationKeysByModel } from "./join-relation-key";
   40| import {
   41| 	buildRelationKeysByModel,
   42| 	getOneToOneRelationKey,
   43| } from "./join-relation-key";
   44| import {
   45| 	insensitiveEq,
   46| 	insensitiveIlike,
   47| 	insensitiveInArray,
   48| 	insensitiveNe,
   49| 	insensitiveNotInArray,
   50| } from "./query-builders";
   51| import { findDrizzleSchemaProblems } from "./schema-check";
   52| 
   53| export interface DB {
   54| 	[key: string]: any;
   55| }
   56| 
   57| /**
   58|  * Derive the number of affected rows from a Drizzle write result.
   59|  *
   60|  * Drizzle returns the raw per-driver result for a non-returning write, so the
   61|  * count lives under a different field per driver: node-postgres / neon expose
   62|  * `rowCount`, postgres-js / bun-sql carry `count` on an Array subclass, mysql2
   63|  * reports `affectedRows` (in a result-header array), planetscale and other
   64|  * serverless drivers use `rowsAffected`, better-sqlite3 uses `changes`, and
   65|  * Cloudflare D1 nests the count under `meta.changes`. This normalizes them so
   66|  * write methods that depend on affected rows honor the adapter contract instead
   67|  * of leaking the raw driver result.
   68|  */
   69| function getAffectedRowCount(
   70| 	result: unknown,
   71| 	operation: "updateMany" | "deleteMany" | "consumeOne",
   72| 	context: { model: string; where: Where[] },
   73| ): number {
   74| 	let count: unknown = 0;
   75| 	if (result && typeof result === "object" && "rowCount" in result) {
   76| 		// node-postgres / neon expose `rowCount`.
   77| 		count = (result as { rowCount: unknown }).rowCount;
   78| 	} else if (
   79| 		result &&
   80| 		typeof result === "object" &&
   81| 		typeof (result as { count?: unknown }).count === "number"
   82| 	) {
   83| 		// postgres-js / bun-sql return an Array subclass carrying `count`.
   84| 		// A non-returning write has length 0, so read this before the Array
   85| 		// branch falls back to `result.length`.
   86| 		count = (result as { count: number }).count;
   87| 	} else if (Array.isArray(result)) {
   88| 		// mysql2 returns a `[ResultSetHeader]` tuple.
   89| 		count =
   90| 			result.length > 0 && hasDriverRowCount(result[0])
   91| 				? readDriverRowCount(result[0])
   92| 				: result.length;
   93| 	} else if (hasDriverRowCount(result)) {
   94| 		count = readDriverRowCount(result);
   95| 	}
   96| 	if (typeof count !== "number" || !Number.isFinite(count)) {
   97| 		logger.error(
   98| 			`[Drizzle Adapter] The result of the ${operation} operation is not a finite number. This is likely a bug in the adapter. Please report this issue to the Better Auth team.`,
   99| 			{ result, ...context },
  100| 		);
  101| 		throw new BetterAuthError(
  102| 			`Drizzle adapter ${operation} returned an invalid affected row count`,
  103| 		);
  104| 	}
  105| 	return count;
  106| }
  107| 
  108| function readDriverRowCount(result: unknown): unknown {
  109| 	if (!result || typeof result !== "object") return undefined;
  110| 	const driverResult = result as Record<string, unknown>;
  111| 	if ("affectedRows" in driverResult) return driverResult.affectedRows;
  112| 	if ("rowsAffected" in driverResult) return driverResult.rowsAffected;
  113| 	if ("changes" in driverResult) return driverResult.changes;
  114| 
  115| 	// Cloudflare D1 nests the affected-row count under `meta.changes`.
  116| 	// @see https://developers.cloudflare.com/d1/worker-api/return-object/
  117| 	if ("meta" in driverResult) {
  118| 		const meta = driverResult.meta;
  119| 		if (meta && typeof meta === "object" && "changes" in meta) {
  120| 			return meta.changes;
  121| 		}
  122| 	}
  123| 
  124| 	return undefined;
  125| }
  126| 
  127| function hasDriverRowCount(result: unknown): boolean {
  128| 	return readDriverRowCount(result) !== undefined;
  129| }
  130| 
  131| export interface DrizzleAdapterConfig {
  132| 	/**
  133| 	 * The schema object that defines the tables and fields
  134| 	 */
  135| 	schema?: Record<string, any> | undefined;
  136| 	/**
  137| 	 * The database provider
  138| 	 */
  139| 	provider: "pg" | "mysql" | "sqlite";
  140| 	/**
  141| 	 * If the table names in the schema are plural
  142| 	 * set this to true. For example, if the schema
  143| 	 * has an object with a key "users" instead of "user"
  144| 	 */
  145| 	usePlural?: boolean | undefined;
  146| 	/**
  147| 	 * Enable debug logs for the adapter
  148| 	 *
  149| 	 * @default false
  150| 	 */
  151| 	debugLogs?: DBAdapterDebugLogOption | undefined;
  152| 	/**
  153| 	 * By default snake case is used for table and field names
  154| 	 * when the CLI is used to generate the schema. If you want
  155| 	 * to use camel case, set this to true.
  156| 	 * @default false
  157| 	 */
  158| 	camelCase?: boolean | undefined;
  159| 	/**
  160| 	 * Whether to execute multiple operations in a transaction.
  161| 	 *
  162| 	 * If the database doesn't support transactions,
  163| 	 * set this to `false` and operations will be executed sequentially.
  164| 	 * @default false
  165| 	 */
  166| 	transaction?: boolean | undefined;
  167| 	/**
  168| 	 * Database schema namespace, used during the Better Auth CLI to generate the schema.
  169| 	 *
  170| 	 * Only applies to PostgreSQL. It will generate something like this:
  171| 	 *
  172| 	 * ```ts
  173| 	 * export const authSchema = pgSchema("auth");
  174| 	 *
  175| 	 * export const user = authSchema.table("user", {...});
  176| 	 * export const session = authSchema.table("session", {...});
  177| 	 * ```
  178| 	 *
  179| 	 * @example "auth"
  180| 	 * @default undefined
  181| 	 */
  182| 	schemaName?: string | undefined;
  183| }
  184| 
  185| export const drizzleAdapter = (db: DB, config: DrizzleAdapterConfig) => {
  186| 	let lazyOptions: BetterAuthOptions | null = null;
  187| 	let mysqlNoIdWarned = false;
  188| 	let relationKeysByModel: RelationKeysByModel | undefined;
  189| 	const getRelationKeysByModel = () =>
  190| 		relationKeysByModel ?? buildRelationKeysByModel(db._?.schema);
  191| 	const createCustomAdapter =
  192| 		(db: DB, inTransaction = false): AdapterFactoryCustomizeAdapterCreator =>
  193| 		({
  194| 			getFieldName,
  195| 			getDefaultFieldName,
  196| 			getDefaultModelName,
  197| 			options,
  198| 			schema: baSchema,
  199| 		}) => {
  200| 			if (
```

### packages/drizzle-adapter/src/relations-v2/index.ts (lines 1 to 200 of 1164)
```
    1| import type { BetterAuthOptions } from "@better-auth/core";
    2| import type {
    3| 	AdapterFactoryCustomizeAdapterCreator,
    4| 	AdapterFactoryOptions,
    5| 	DBAdapter,
    6| 	DBAdapterDebugLogOption,
    7| 	Where,
    8| } from "@better-auth/core/db/adapter";
    9| import { createAdapterFactory } from "@better-auth/core/db/adapter";
   10| import {
   11| 	checksSchema,
   12| 	createSchemaCheck,
   13| 	registerSchemaCheck,
   14| } from "@better-auth/core/db/internal";
   15| import { logger } from "@better-auth/core/env";
   16| import { BetterAuthError } from "@better-auth/core/error";
   17| import type { SQL } from "drizzle-orm";
   18| import {
   19| 	and,
   20| 	asc,
   21| 	count,
   22| 	desc,
   23| 	eq,
   24| 	gt,
   25| 	gte,
   26| 	inArray,
   27| 	isNotNull,
   28| 	isNull,
   29| 	lt,
   30| 	lte,
   31| 	ne,
   32| 	notInArray,
   33| 	or,
   34| 	sql,
   35| } from "drizzle-orm";
   36| import type { RelationKeysByModel } from "../join-relation-key";
   37| import {
   38| 	buildRelationKeysByModel,
   39| 	getOneToOneRelationKey,
   40| } from "../join-relation-key";
   41| import {
   42| 	escapedLike,
   43| 	insensitiveEq,
   44| 	insensitiveInArray,
   45| 	insensitiveNe,
   46| 	insensitiveNotInArray,
   47| } from "../query-builders";
   48| import { findDrizzleSchemaProblems } from "../schema-check";
   49| 
   50| export interface DB {
   51| 	[key: string]: any;
   52| }
   53| 
   54| function escapeLikePattern(
   55| 	value: string | number | boolean | string[] | number[] | Date | null,
   56| ): string {
   57| 	if (value == null) return "";
   58| 	// Escape the backslash first so the `\` added for `%` and `_` is not
   59| 	// re-escaped, and a literal backslash in the input stays literal under the
   60| 	// `ESCAPE '\'` clause.
   61| 	return String(value)
   62| 		.replace(/\\/g, "\\\\")
   63| 		.replace(/%/g, "\\%")
   64| 		.replace(/_/g, "\\_");
   65| }
   66| 
   67| function readDriverRowCount(result: unknown): unknown {
   68| 	if (!result || typeof result !== "object") return undefined;
   69| 	if ("affectedRows" in result) return result.affectedRows;
   70| 	if ("rowsAffected" in result) return result.rowsAffected;
   71| 	if ("changes" in result) return result.changes;
   72| 
   73| 	// Cloudflare D1 nests the affected-row count under `meta.changes`.
   74| 	// @see https://developers.cloudflare.com/d1/worker-api/return-object/
   75| 	if ("meta" in result) {
   76| 		const meta = result.meta;
   77| 		if (meta && typeof meta === "object" && "changes" in meta) {
   78| 			return meta.changes;
   79| 		}
   80| 	}
   81| 
   82| 	return undefined;
   83| }
   84| 
   85| function hasDriverRowCount(result: unknown): boolean {
   86| 	return readDriverRowCount(result) !== undefined;
   87| }
   88| 
   89| function getAffectedRowCount(
   90| 	result: unknown,
   91| 	operation: "updateMany" | "deleteMany" | "consumeOne",
   92| 	context: { model: string; where: Where[] },
   93| ): number {
   94| 	let count: unknown = 0;
   95| 	if (result && typeof result === "object" && "rowCount" in result) {
   96| 		// node-postgres / neon expose `rowCount`.
   97| 		count = (result as { rowCount: unknown }).rowCount;
   98| 	} else if (
   99| 		result &&
  100| 		typeof result === "object" &&
  101| 		typeof (result as { count?: unknown }).count === "number"
  102| 	) {
  103| 		// postgres-js / bun-sql return an Array subclass carrying `count`.
  104| 		count = (result as { count: number }).count;
  105| 	} else if (Array.isArray(result)) {
  106| 		// mysql2 returns a `[ResultSetHeader]` tuple.
  107| 		count =
  108| 			result.length > 0 && hasDriverRowCount(result[0])
  109| 				? readDriverRowCount(result[0])
  110| 				: result.length;
  111| 	} else if (hasDriverRowCount(result)) {
  112| 		count = readDriverRowCount(result);
  113| 	}
  114| 	if (typeof count !== "number" || !Number.isFinite(count)) {
  115| 		logger.error(
  116| 			`[Drizzle Adapter] The result of the ${operation} operation is not a finite number. This is likely a bug in the adapter. Please report this issue to the Better Auth team.`,
  117| 			{ result, ...context },
  118| 		);
  119| 		throw new BetterAuthError(
  120| 			`Drizzle adapter ${operation} returned an invalid affected row count`,
  121| 		);
  122| 	}
  123| 	return count;
  124| }
  125| 
  126| /**
  127|  * Maps a single Where entry to a drizzle SQL expression.
  128|  * Shared by convertWhereClause across single / AND / OR branches.
  129|  */
  130| function applyWhereOperator(
  131| 	column: any,
  132| 	w: Where,
  133| 	fieldLabel: string,
  134| 	provider: "pg" | "mysql" | "sqlite",
  135| ): SQL<unknown> {
  136| 	const mode = w.mode ?? "sensitive";
  137| 	const isInsensitive =
  138| 		mode === "insensitive" &&
  139| 		(typeof w.value === "string" ||
  140| 			(Array.isArray(w.value) && w.value.every((v) => typeof v === "string")));
  141| 
  142| 	if (w.operator === "in") {
  143| 		if (!Array.isArray(w.value)) {
  144| 			throw new BetterAuthError(
  145| 				`The value for the field "${fieldLabel}" must be an array when using the "in" operator.`,
  146| 			);
  147| 		}
  148| 		if (isInsensitive) {
  149| 			return insensitiveInArray(column, w.value as string[]);
  150| 		}
  151| 		return inArray(column, w.value);
  152| 	}
  153| 	if (w.operator === "not_in") {
  154| 		if (!Array.isArray(w.value)) {
  155| 			throw new BetterAuthError(
  156| 				`The value for the field "${fieldLabel}" must be an array when using the "not_in" operator.`,
  157| 			);
  158| 		}
  159| 		if (isInsensitive) {
  160| 			return insensitiveNotInArray(column, w.value as string[]);
  161| 		}
  162| 		return notInArray(column, w.value);
  163| 	}
  164| 	const likeMode =
  165| 		isInsensitive && typeof w.value === "string" ? "insensitive" : "sensitive";
  166| 	if (w.operator === "contains") {
  167| 		return escapedLike(
  168| 			column,
  169| 			`%${escapeLikePattern(w.value)}%`,
  170| 			provider,
  171| 			likeMode,
  172| 		);
  173| 	}
  174| 	if (w.operator === "starts_with") {
  175| 		return escapedLike(
  176| 			column,
  177| 			`${escapeLikePattern(w.value)}%`,
  178| 			provider,
  179| 			likeMode,
  180| 		);
  181| 	}
  182| 	if (w.operator === "ends_with") {
  183| 		return escapedLike(
  184| 			column,
  185| 			`%${escapeLikePattern(w.value)}`,
  186| 			provider,
  187| 			likeMode,
  188| 		);
  189| 	}
  190| 	if (w.operator === "lt") {
  191| 		return lt(column, w.value);
  192| 	}
  193| 	if (w.operator === "lte") {
  194| 		return lte(column, w.value);
  195| 	}
  196| 	if (w.operator === "ne") {
  197| 		if (w.value === null) {
  198| 			return isNotNull(column);
  199| 		}
  200| 		if (isInsensitive && typeof w.value === "string") {
```

### .changeset/lazy-drizzle-metadata.md (lines 1 to 6 of 6)
```
    1| ---
    2| "@better-auth/drizzle-adapter": patch
    3| ---
    4| 
    5| Defer Drizzle relation metadata access until a relational query runs, preserving lazy database initialization during application builds.
    6| 
```
