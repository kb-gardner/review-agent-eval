# PR pack: drizzle-team/drizzle-orm#6072
Title: new issues
Merge commit: 2ce46c263a3feb83a546a61b65a887592e1dcc93

## Diff
```diff
diff --git a/changelogs/drizzle-kit/1.0.0-rc.5.md b/changelogs/drizzle-kit/1.0.0-rc.5.md
index c889ff0485..990368bd23 100644
--- a/changelogs/drizzle-kit/1.0.0-rc.5.md
+++ b/changelogs/drizzle-kit/1.0.0-rc.5.md
@@ -7,4 +7,6 @@
 - [[BUG]: drizzle-kit pull error when there are comments in a view definition](https://github.com/drizzle-team/drizzle-orm/issues/5964)
 - [[BUG]: inArray/notInArray empty arrays do not work with SQL Server](https://github.com/drizzle-team/drizzle-orm/issues/5632)
 - [[BUG]: Invalid schema default value generated for sequence-based primary keys in Postgres](https://github.com/drizzle-team/drizzle-orm/issues/5413)
-- [Small typo in drizzle-kit/src/index.ts](https://github.com/drizzle-team/drizzle-orm/issues/4736)
\ No newline at end of file
+- [Small typo in drizzle-kit/src/index.ts](https://github.com/drizzle-team/drizzle-orm/issues/4736)
+- [[BUG]: drizzle-kit pull reports index_duplicate for valid MSSQL index names reused across tables](https://github.com/drizzle-team/drizzle-orm/issues/5993)
+- [[BUG]: drizzle-kit pull generates many() instead of one() for one-to-one relations (unique FK columns)](https://github.com/drizzle-team/drizzle-orm/issues/5478)
\ No newline at end of file
diff --git a/drizzle-kit/src/cli/commands/pull-common.ts b/drizzle-kit/src/cli/commands/pull-common.ts
index a3ba70b4cd..a690197a6c 100644
--- a/drizzle-kit/src/cli/commands/pull-common.ts
+++ b/drizzle-kit/src/cli/commands/pull-common.ts
@@ -173,8 +173,8 @@ export const relationsToTypeScript = (
 				// not matter if it's 1 column, 2 columns or more
 				if (
 					table.uniques.find((constraint) =>
-						constraint.columns.length === columnsFrom.length
-						&& constraint.columns.every((col, i) => col === columnsFrom[i])
+						constraint.columns.length === fk.columns.length // need to check without casing (name should be preserved)
+						&& constraint.columns.every((col, i) => col === fk.columns[i]) // need to check without casing (name should be preserved)
 					)
 				) {
 					// the difference between one and one-one is that one-one won't contain from and to
diff --git a/drizzle-kit/src/cli/validations/common.ts b/drizzle-kit/src/cli/validations/common.ts
index 614d16e9ab..539ddec1c3 100644
--- a/drizzle-kit/src/cli/validations/common.ts
+++ b/drizzle-kit/src/cli/validations/common.ts
@@ -138,12 +138,6 @@ export type CliConfig = TypeOf<typeof configCommonSchema> & {
 	schemaFilter?: string | string[];
 };
 
-export const configPull = configCommonSchema.extend({
-	casing,
-	migrations: configMigrations,
-	...entitiesParams,
-});
-
 export const configCheck = configCommonSchema;
 
 export const configGenerate = configCommonSchema.extend({
diff --git a/drizzle-kit/src/dialects/mssql/ddl.ts b/drizzle-kit/src/dialects/mssql/ddl.ts
index e75c8516e2..32b38e6ec5 100644
--- a/drizzle-kit/src/dialects/mssql/ddl.ts
+++ b/drizzle-kit/src/dialects/mssql/ddl.ts
@@ -297,9 +297,9 @@ export const interimToDDL = (interim: InterimSchema): { ddl: MssqlDDL; errors: S
 	}
 
 	for (const index of interim.indexes) {
-		const isConflictNamePerSchema = ddl.indexes.one({ schema: index.schema, name: index.name });
+		const res = ddl.indexes.push(index);
 
-		if (isConflictNamePerSchema) {
+		if (res.status === 'CONFLICT') {
 			errors.push({
 				type: 'index_duplicate',
 				schema: index.schema,
@@ -307,6 +307,7 @@ export const interimToDDL = (interim: InterimSchema): { ddl: MssqlDDL; errors: S
 				name: index.name,
 			});
 		}
+
 		ddl.indexes.push(index);
 	}
 
diff --git a/drizzle-kit/tests/mssql/mocks.ts b/drizzle-kit/tests/mssql/mocks.ts
index 4e3ff995bd..8b548500e6 100644
--- a/drizzle-kit/tests/mssql/mocks.ts
+++ b/drizzle-kit/tests/mssql/mocks.ts
@@ -150,6 +150,10 @@ export const diffIntrospect = async (
 	const { schema: schema2, errors: e2 } = fromDrizzleSchema(response, filter);
 	const { ddl: ddl2, errors: e3 } = interimToDDL(schema2);
 
+	if (e1.length > 0 || e2.length > 0 || e3.length > 0) {
+		throw new MockError([...e1, ...e2, ...e3]);
+	}
+
 	const {
 		sqlStatements: afterFileSqlStatements,
 		statements: afterFileStatements,
diff --git a/drizzle-kit/tests/mssql/pull.test.ts b/drizzle-kit/tests/mssql/pull.test.ts
index 209a79bfe9..9136928293 100644
--- a/drizzle-kit/tests/mssql/pull.test.ts
+++ b/drizzle-kit/tests/mssql/pull.test.ts
@@ -742,3 +742,92 @@ test('Issue #5964. View with comments', async () => {
 		},
 	]);
 });
+
+// https://github.com/drizzle-team/drizzle-orm/issues/5993
+test('Issue No5993', async () => {
+	await db.query(`CREATE TABLE dbo.duplicate_index_a (
+  id int NOT NULL,
+  value int NULL
+);`);
+	await db.query(
+		`CREATE TABLE dbo.duplicate_index_b (
+  id int NOT NULL,
+  value int NULL
+);`,
+	);
+	await db.query(
+		`CREATE INDEX IX_DUPLICATE_NAME ON dbo.duplicate_index_a(value);`,
+	);
+	await db.query(
+		`CREATE INDEX IX_DUPLICATE_NAME ON dbo.duplicate_index_b(value);`,
+	);
+
+	const { sqlStatements, statements, fromFileDDL, introspectDDL } = await diffIntrospect(
+		db,
+		{},
+		'#5993',
+	);
+
+	expect(sqlStatements).toStrictEqual([]);
+	expect(statements).toStrictEqual([]);
+	expect(introspectDDL.indexes.list()).toStrictEqual([
+		{
+			columns: [
+				{
+					isExpression: false,
+					value: 'value',
+				},
+			],
+			entityType: 'indexes',
+			isUnique: false,
+			name: 'IX_DUPLICATE_NAME',
+			schema: 'dbo',
+			table: 'duplicate_index_a',
+			where: null,
+		},
+		{
+			columns: [
+				{
+					isExpression: false,
+					value: 'value',
+				},
+			],
+			entityType: 'indexes',
+			isUnique: false,
+			name: 'IX_DUPLICATE_NAME',
+			schema: 'dbo',
+			table: 'duplicate_index_b',
+			where: null,
+		},
+	]);
+	expect(fromFileDDL.indexes.list()).toStrictEqual([
+		{
+			columns: [
+				{
+					isExpression: false,
+					value: 'value',
+				},
+			],
+			entityType: 'indexes',
+			isUnique: false,
+			name: 'IX_DUPLICATE_NAME',
+			schema: 'dbo',
+			table: 'duplicate_index_a',
+			where: null,
+		},
+		{
+			columns: [
+				{
+					isExpression: false,
+					value: 'value',
+				},
+			],
+			entityType: 'indexes',
+			isUnique: false,
+			name: 'IX_DUPLICATE_NAME',
+			schema: 'dbo',
+			table: 'duplicate_index_b',
+			where: null,
+		},
+	]);
+});
diff --git a/drizzle-orm/tests/sql-builder.test.ts b/drizzle-orm/tests/sql-builder.test.ts
index 3f327031a3..cbf5b1aac5 100644
--- a/drizzle-orm/tests/sql-builder.test.ts
+++ b/drizzle-orm/tests/sql-builder.test.ts
@@ -65,3 +65,33 @@ test.skipIf(Date.now() < +new Date('2026-07-29'))('NOT conditions deep filter em
 
 	expect(query).toBeUndefined();
 });
+
+// https://github.com/drizzle-team/drizzle-orm/issues/5994
+test(`Issue No5994. sqlToQuery with large parameter lists`, () => {
+	const parameterCount = 150_000;
+	const parameters = Array.from(
+		{ length: parameterCount },
+		(_, index) => index,
+	);
+
+	const result = dialect['sqlToQuery'](sql`${parameters}`);
+
+	expect(result.params).toHaveLength(parameterCount);
+	expect(
+		result.params.every((parameter, index) => parameter === index),
+	).toBe(true);
+});
+test(`Issue No5994. _sqlToQuery with large parameter lists`, () => {
+	const parameterCount = 150_000;
+	const parameters = Array.from(
+		{ length: parameterCount },
+		(_, index) => index,
+	);
+
+	const result = dialect['_sqlToQuery'](sql`${parameters}`);
+
+	expect(result.params).toHaveLength(parameterCount);
+	expect(
+		result.params.every((parameter, index) => parameter === index),
+	).toBe(true);
+});
diff --git a/integration-tests/tests/pg/common-pt2.ts b/integration-tests/tests/pg/common-pt2.ts
index f07a35861a..861e397dc4 100644
--- a/integration-tests/tests/pg/common-pt2.ts
+++ b/integration-tests/tests/pg/common-pt2.ts
@@ -6830,4 +6830,65 @@ export function tests(test: Test) {
 			expect(read).toEqual([{ id: 1, balance: 100 }]);
 		});
 	});
+
+	// https://github.com/drizzle-team/drizzle-orm/issues/5699
+	test('Issue No 5699', async ({ createDB, push }) => {
+		const firstTable = pgTable('first_table', {
+			id: serial().primaryKey(),
+			name: text().notNull(),
+			createdAt: text().notNull(),
+			updatedAt: text().notNull(),
+			deletedAt: text().notNull(),
+		});
+		const secondTable = pgTable('second_table', {
+			id: serial().primaryKey(),
+			sn: text().notNull(),
+			otherDate: text().notNull(),
+			myKey: text().notNull(),
+			fk_first_table: integer().references(() => firstTable.id),
+		});
+
+		const myView = pgView('my_view').as((qb) =>
+			qb
+				.select({
+					id: firstTable.id,
+					name: firstTable.name,
+					someName: secondTable.sn,
+					myKey: secondTable.myKey,
+					otherDate: secondTable.otherDate,
+					createdAt: firstTable.createdAt,
+					updatedAt: firstTable.updatedAt,
+				})
+				.from(firstTable)
+				.innerJoin(secondTable, ({ id }) => eq(secondTable.fk_first_table, id))
+				.where(isNull(firstTable.deletedAt))
+		);
+
+		await push({ firstTable, secondTable, myView });
+
+		const db = createDB({ firstTable, secondTable, myView }, (r) => ({
+			secondTable: {
+				firstTable: r.one.firstTable({
+					from: r.secondTable.fk_first_table,
+					to: r.firstTable.id,
+				}),
+			},
+		}));
+
+		const res = await db.query.firstTable.findFirst({
+			where: { id: { eq: 1 } },
+		});
+
+		const res2 = await db.query.secondTable.findFirst({
+			where: { id: { eq: 1 } },
+		});
+
+		const res3 = await db.query.myView.findFirst({
+			where: { id: { eq: 1 } },
+		});
+
+		expect(res).toStrictEqual(undefined);
+		expect(res2).toStrictEqual(undefined);
+		expect(res3).toStrictEqual(undefined);
+	});
 }

```

## Touched files at the merge commit (window of up to 200 lines around the first changed hunk)

### drizzle-kit/tests/mssql/pull.test.ts (lines 683 to 834 of 834)
```
  683| 		{
  684| 			entityType: 'tables',
  685| 			name: 'users',
  686| 			schema: 'dbo',
  687| 		},
  688| 		{
  689| 			columns: [
  690| 				'id',
  691| 			],
  692| 			entityType: 'pks',
  693| 			name: 'users_pkey',
  694| 			nameExplicit: true,
  695| 			schema: 'custom',
  696| 			table: 'users',
  697| 		},
  698| 		{
  699| 			columns: [
  700| 				'id',
  701| 			],
  702| 			entityType: 'pks',
  703| 			name: 'users_pkey',
  704| 			nameExplicit: true,
  705| 			schema: 'dbo',
  706| 			table: 'users',
  707| 		},
  708| 	]);
  709| });
  710| 
  711| // https://github.com/drizzle-team/drizzle-orm/issues/5964
  712| test('Issue #5964. View with comments', async () => {
  713| 	await db.query(`CREATE TABLE [dbo].[Customer]
  714| (
  715|     CustomerId INT NOT NULL IDENTITY(1, 1),
  716|       CONSTRAINT [PK_Customer_CustomerId] PRIMARY KEY (CustomerId),
  717|     Name VARCHAR(50) NOT NULL,
  718|         CONSTRAINT [CK_Customer_Name_not_blank_string] CHECK (LEN(Name) > 0)
  719| )`);
  720| 	await db.query(
  721| 		`CREATE VIEW dbo.vCustomer WITH SCHEMABINDING AS /* comment */ SELECT CustomerId, Name FROM dbo.Customer`,
  722| 	);
  723| 
  724| 	const { sqlStatements, statements, fromFileDDL, introspectDDL } = await diffIntrospect(
  725| 		db,
  726| 		{},
  727| 		'#5964',
  728| 	);
  729| 
  730| 	expect(sqlStatements).toStrictEqual([]);
  731| 	expect(statements).toStrictEqual([]);
  732| 	expect(introspectDDL.views.list()).toStrictEqual([
  733| 		{
  734| 			checkOption: false,
  735| 			definition: `/* comment */ SELECT CustomerId, Name FROM dbo.Customer`,
  736| 			encryption: false,
  737| 			entityType: 'views',
  738| 			name: 'vCustomer',
  739| 			schema: 'dbo',
  740| 			schemaBinding: true,
  741| 			viewMetadata: false,
  742| 		},
  743| 	]);
  744| });
  745| 
  746| // https://github.com/drizzle-team/drizzle-orm/issues/5993
  747| test('Issue No5993', async () => {
  748| 	await db.query(`CREATE TABLE dbo.duplicate_index_a (
  749|   id int NOT NULL,
  750|   value int NULL
  751| );`);
  752| 	await db.query(
  753| 		`CREATE TABLE dbo.duplicate_index_b (
  754|   id int NOT NULL,
  755|   value int NULL
  756| );`,
  757| 	);
  758| 	await db.query(
  759| 		`CREATE INDEX IX_DUPLICATE_NAME ON dbo.duplicate_index_a(value);`,
  760| 	);
  761| 	await db.query(
  762| 		`CREATE INDEX IX_DUPLICATE_NAME ON dbo.duplicate_index_b(value);`,
  763| 	);
  764| 
  765| 	const { sqlStatements, statements, fromFileDDL, introspectDDL } = await diffIntrospect(
  766| 		db,
  767| 		{},
  768| 		'#5993',
  769| 	);
  770| 
  771| 	expect(sqlStatements).toStrictEqual([]);
  772| 	expect(statements).toStrictEqual([]);
  773| 	expect(introspectDDL.indexes.list()).toStrictEqual([
  774| 		{
  775| 			columns: [
  776| 				{
  777| 					isExpression: false,
  778| 					value: 'value',
  779| 				},
  780| 			],
  781| 			entityType: 'indexes',
  782| 			isUnique: false,
  783| 			name: 'IX_DUPLICATE_NAME',
  784| 			schema: 'dbo',
  785| 			table: 'duplicate_index_a',
  786| 			where: null,
  787| 		},
  788| 		{
  789| 			columns: [
  790| 				{
  791| 					isExpression: false,
  792| 					value: 'value',
  793| 				},
  794| 			],
  795| 			entityType: 'indexes',
  796| 			isUnique: false,
  797| 			name: 'IX_DUPLICATE_NAME',
  798| 			schema: 'dbo',
  799| 			table: 'duplicate_index_b',
  800| 			where: null,
  801| 		},
  802| 	]);
  803| 	expect(fromFileDDL.indexes.list()).toStrictEqual([
  804| 		{
  805| 			columns: [
  806| 				{
  807| 					isExpression: false,
  808| 					value: 'value',
  809| 				},
  810| 			],
  811| 			entityType: 'indexes',
  812| 			isUnique: false,
  813| 			name: 'IX_DUPLICATE_NAME',
  814| 			schema: 'dbo',
  815| 			table: 'duplicate_index_a',
  816| 			where: null,
  817| 		},
  818| 		{
  819| 			columns: [
  820| 				{
  821| 					isExpression: false,
  822| 					value: 'value',
  823| 				},
  824| 			],
  825| 			entityType: 'indexes',
  826| 			isUnique: false,
  827| 			name: 'IX_DUPLICATE_NAME',
  828| 			schema: 'dbo',
  829| 			table: 'duplicate_index_b',
  830| 			where: null,
  831| 		},
  832| 	]);
  833| });
  834| 
```

### integration-tests/tests/pg/common-pt2.ts (lines 6771 to 6895 of 6895)
```
 6771| 			await db.insert(users).values({ balance: 100 });
 6772| 
 6773| 			await expect(
 6774| 				db.transaction(async (tx) => {
 6775| 					await tx.insert(users).values({ balance: 200 });
 6776| 				}, { accessMode: 'read only' }),
 6777| 			).rejects.toSatisfy((e: any) => /read-only transaction/i.test(String(e?.cause?.message ?? e?.message)));
 6778| 
 6779| 			const read = await db.transaction(async (tx) => {
 6780| 				const [row] = await tx.execute(sql`show transaction_read_only`, 'objects');
 6781| 				expect(row!['transaction_read_only']).toBe('on');
 6782| 				return tx.select().from(users);
 6783| 			}, { accessMode: 'read only' });
 6784| 			expect(read).toEqual([{ id: 1, balance: 100 }]);
 6785| 
 6786| 			await db.transaction(async (tx) => {
 6787| 				const [row] = await tx.execute(sql`show transaction_read_only`, 'objects');
 6788| 				expect(row!['transaction_read_only']).toBe('off');
 6789| 			}, { accessMode: 'read write' });
 6790| 		});
 6791| 
 6792| 		test('transaction with options (deferrable)', async ({ db, push }) => {
 6793| 			const users = pgTable('users_tx_cfg_deferrable', {
 6794| 				id: serial('id').primaryKey(),
 6795| 				balance: integer('balance').notNull(),
 6796| 			});
 6797| 
 6798| 			await push({ users });
 6799| 			await db.insert(users).values({ balance: 100 });
 6800| 
 6801| 			await db.transaction(async (tx) => {
 6802| 				const [row] = await tx.execute(sql`show transaction_deferrable`, 'objects');
 6803| 				expect(row!['transaction_deferrable']).toBe('on');
 6804| 			}, {
 6805| 				isolationLevel: 'serializable',
 6806| 				accessMode: 'read only',
 6807| 				deferrable: true,
 6808| 			});
 6809| 
 6810| 			await db.transaction(async (tx) => {
 6811| 				const [row] = await tx.execute(sql`show transaction_deferrable`, 'objects');
 6812| 				expect(row!['transaction_deferrable']).toBe('off');
 6813| 			}, {
 6814| 				isolationLevel: 'serializable',
 6815| 				accessMode: 'read only',
 6816| 				deferrable: false,
 6817| 			});
 6818| 		});
 6819| 
 6820| 		test('transaction with an empty options object', async ({ db, push }) => {
 6821| 			const users = pgTable('users_tx_cfg_empty', {
 6822| 				id: serial('id').primaryKey(),
 6823| 				balance: integer('balance').notNull(),
 6824| 			});
 6825| 
 6826| 			await push({ users });
 6827| 			await db.insert(users).values({ balance: 100 });
 6828| 
 6829| 			const read = await db.transaction(async (tx) => tx.select().from(users), {});
 6830| 			expect(read).toEqual([{ id: 1, balance: 100 }]);
 6831| 		});
 6832| 	});
 6833| 
 6834| 	// https://github.com/drizzle-team/drizzle-orm/issues/5699
 6835| 	test('Issue No 5699', async ({ createDB, push }) => {
 6836| 		const firstTable = pgTable('first_table', {
 6837| 			id: serial().primaryKey(),
 6838| 			name: text().notNull(),
 6839| 			createdAt: text().notNull(),
 6840| 			updatedAt: text().notNull(),
 6841| 			deletedAt: text().notNull(),
 6842| 		});
 6843| 		const secondTable = pgTable('second_table', {
 6844| 			id: serial().primaryKey(),
 6845| 			sn: text().notNull(),
 6846| 			otherDate: text().notNull(),
 6847| 			myKey: text().notNull(),
 6848| 			fk_first_table: integer().references(() => firstTable.id),
 6849| 		});
 6850| 
 6851| 		const myView = pgView('my_view').as((qb) =>
 6852| 			qb
 6853| 				.select({
 6854| 					id: firstTable.id,
 6855| 					name: firstTable.name,
 6856| 					someName: secondTable.sn,
 6857| 					myKey: secondTable.myKey,
 6858| 					otherDate: secondTable.otherDate,
 6859| 					createdAt: firstTable.createdAt,
 6860| 					updatedAt: firstTable.updatedAt,
 6861| 				})
 6862| 				.from(firstTable)
 6863| 				.innerJoin(secondTable, ({ id }) => eq(secondTable.fk_first_table, id))
 6864| 				.where(isNull(firstTable.deletedAt))
 6865| 		);
 6866| 
 6867| 		await push({ firstTable, secondTable, myView });
 6868| 
 6869| 		const db = createDB({ firstTable, secondTable, myView }, (r) => ({
 6870| 			secondTable: {
 6871| 				firstTable: r.one.firstTable({
 6872| 					from: r.secondTable.fk_first_table,
 6873| 					to: r.firstTable.id,
 6874| 				}),
 6875| 			},
 6876| 		}));
 6877| 
 6878| 		const res = await db.query.firstTable.findFirst({
 6879| 			where: { id: { eq: 1 } },
 6880| 		});
 6881| 
 6882| 		const res2 = await db.query.secondTable.findFirst({
 6883| 			where: { id: { eq: 1 } },
 6884| 		});
 6885| 
 6886| 		const res3 = await db.query.myView.findFirst({
 6887| 			where: { id: { eq: 1 } },
 6888| 		});
 6889| 
 6890| 		expect(res).toStrictEqual(undefined);
 6891| 		expect(res2).toStrictEqual(undefined);
 6892| 		expect(res3).toStrictEqual(undefined);
 6893| 	});
 6894| }
 6895| 
```

### drizzle-orm/tests/sql-builder.test.ts (lines 6 to 98 of 98)
```
    6| 	id: serial('id').primaryKey(),
    7| 	name: text('name').notNull(),
    8| });
    9| 
   10| // Dialect type is irrelevant
   11| const dialect = new PgDialect();
   12| 
   13| test('OR conditions wrapped in parentheses', () => {
   14| 	const query = or(eq(users.id, 1), sql`never`.if(false), sql`users.id = post.user_id AND posts.is_deleted = false`);
   15| 	const { sql: text } = dialect.sqlToQuery(query!.inlineParams());
   16| 
   17| 	expect(text).toStrictEqual(`(("users"."id" = 1) or (users.id = post.user_id AND posts.is_deleted = false))`);
   18| });
   19| 
   20| test('AND conditions wrapped in parentheses', () => {
   21| 	const query = and(eq(users.id, 1), sql`never`.if(false), sql`users.id = post.user_id AND posts.is_deleted = false`);
   22| 	const { sql: text } = dialect.sqlToQuery(query!.inlineParams());
   23| 
   24| 	expect(text).toStrictEqual(`(("users"."id" = 1) and (users.id = post.user_id AND posts.is_deleted = false))`);
   25| });
   26| 
   27| test('NOT conditions wrapped in parentheses for SQL', () => {
   28| 	const query = not(sql`users.id = post.user_id AND posts.is_deleted = false`);
   29| 	const { sql: text } = dialect.sqlToQuery(query!.inlineParams());
   30| 
   31| 	expect(text).toStrictEqual(`not (users.id = post.user_id AND posts.is_deleted = false)`);
   32| });
   33| 
   34| test('NOT conditions not wrapped in parentheses for non-SQL', () => {
   35| 	const query = not(users.id);
   36| 	const { sql: text } = dialect.sqlToQuery(query!.inlineParams());
   37| 
   38| 	expect(text).toStrictEqual(`not "users"."id"`);
   39| });
   40| 
   41| test.skipIf(Date.now() < +new Date('2026-07-29'))('OR conditions deep filter empty queries', () => {
   42| 	const query = or(
   43| 		eq(users.id, 1),
   44| 		sql`${sql`never`.if(false)}`,
   45| 		sql`users.id = post.user_id AND posts.is_deleted = false`,
   46| 	);
   47| 	const { sql: text } = dialect.sqlToQuery(query!.inlineParams());
   48| 
   49| 	expect(text).toStrictEqual(`(("users"."id" = 1) or (users.id = post.user_id AND posts.is_deleted = false))`);
   50| });
   51| 
   52| test.skipIf(Date.now() < +new Date('2026-07-29'))('AND conditions deep filter empty queries', () => {
   53| 	const query = and(
   54| 		eq(users.id, 1),
   55| 		sql`${sql`never`.if(false)}`,
   56| 		sql`users.id = post.user_id AND posts.is_deleted = false`,
   57| 	);
   58| 	const { sql: text } = dialect.sqlToQuery(query!.inlineParams());
   59| 
   60| 	expect(text).toStrictEqual(`(("users"."id" = 1) and (users.id = post.user_id AND posts.is_deleted = false))`);
   61| });
   62| 
   63| test.skipIf(Date.now() < +new Date('2026-07-29'))('NOT conditions deep filter empty queries', () => {
   64| 	const query = not(sql`${sql`never`.if(false)}`);
   65| 
   66| 	expect(query).toBeUndefined();
   67| });
   68| 
   69| // https://github.com/drizzle-team/drizzle-orm/issues/5994
   70| test(`Issue No5994. sqlToQuery with large parameter lists`, () => {
   71| 	const parameterCount = 150_000;
   72| 	const parameters = Array.from(
   73| 		{ length: parameterCount },
   74| 		(_, index) => index,
   75| 	);
   76| 
   77| 	const result = dialect['sqlToQuery'](sql`${parameters}`);
   78| 
   79| 	expect(result.params).toHaveLength(parameterCount);
   80| 	expect(
   81| 		result.params.every((parameter, index) => parameter === index),
   82| 	).toBe(true);
   83| });
   84| test(`Issue No5994. _sqlToQuery with large parameter lists`, () => {
   85| 	const parameterCount = 150_000;
   86| 	const parameters = Array.from(
   87| 		{ length: parameterCount },
   88| 		(_, index) => index,
   89| 	);
   90| 
   91| 	const result = dialect['_sqlToQuery'](sql`${parameters}`);
   92| 
   93| 	expect(result.params).toHaveLength(parameterCount);
   94| 	expect(
   95| 		result.params.every((parameter, index) => parameter === index),
   96| 	).toBe(true);
   97| });
   98| 
```

### drizzle-kit/src/cli/validations/common.ts (lines 79 to 224 of 224)
```
   79| export type CasingType = (typeof casingTypes)[number];
   80| 
   81| export const sqliteDriver = union(sqliteDriversLiterals);
   82| export const postgresDriver = union(postgresqlDriversLiterals);
   83| export const driver = union([sqliteDriver, postgresDriver]);
   84| 
   85| export const drivers = ['d1-http', 'expo', 'aws-data-api', 'pglite', 'durable-sqlite', 'sqlite-cloud'] as const;
   86| 
   87| export type Casing = TypeOf<typeof casing>;
   88| 
   89| export const configMigrations = object({
   90| 	table: string().default('__drizzle_migrations'),
   91| 	schema: string().default('drizzle'),
   92| }).default({ table: '__drizzle_migrations', schema: 'drizzle' });
   93| 
   94| export const casing = union([literal('camel'), literal('preserve')]).default(
   95| 	'camel',
   96| );
   97| 
   98| export type Driver = (typeof drivers)[number];
   99| 
  100| export const entitiesParams = {
  101| 	tablesFilter: union([string(), string().array()]).optional(),
  102| 	schemaFilter: union([string(), string().array()])
  103| 		.optional(),
  104| 	extensionsFilters: literal('postgis').array().optional(),
  105| 	entities: object({
  106| 		roles: boolean().or(object({
  107| 			provider: string().optional(),
  108| 			include: string().array().optional(),
  109| 			exclude: string().array().optional(),
  110| 		})).optional().default(false),
  111| 	}).optional(),
  112| };
  113| export type EntitiesFilter = TypeOf<typeof entitiesParams['entities']>;
  114| export type TablesFilter = TypeOf<typeof entitiesParams['tablesFilter']>;
  115| export type SchemasFilter = TypeOf<typeof entitiesParams['schemaFilter']>;
  116| export type ExtensionsFilter = TypeOf<typeof entitiesParams['extensionsFilters']>;
  117| export type EntitiesFilterConfig = {
  118| 	schemas: SchemasFilter;
  119| 	tables: TablesFilter;
  120| 	entities: EntitiesFilter;
  121| 	extensions: ExtensionsFilter;
  122| };
  123| 
  124| export const configCommonSchema = object({
  125| 	dialect: dialect.optional(),
  126| 	out: string().default('drizzle'),
  127| 	breakpoints: boolean().optional().default(true),
  128| 	verbose: boolean().optional().default(false),
  129| 	driver: driver.optional(),
  130| 	dbCredentials: any().optional(),
  131| }).passthrough();
  132| 
  133| export type CliConfig = TypeOf<typeof configCommonSchema> & {
  134| 	schema?: string | string[];
  135| 	sql?: boolean;
  136| 	migrations?: TypeOf<typeof configMigrations>;
  137| 	tablesFilter?: string | string[];
  138| 	schemaFilter?: string | string[];
  139| };
  140| 
  141| export const configCheck = configCommonSchema;
  142| 
  143| export const configGenerate = configCommonSchema.extend({
  144| 	schema: union([string(), string().array()]),
  145| });
  146| 
  147| export const configPush = configCommonSchema.extend({
  148| 	schema: union([string(), string().array()]),
  149| 	explain: boolean().optional(),
  150| 	migrations: configMigrations,
  151| 	...entitiesParams,
  152| });
  153| 
  154| export const configExport = configCommonSchema.extend({
  155| 	schema: union([string(), string().array()]),
  156| });
  157| 
  158| export const studioCliParams = object({
  159| 	port: coerce.number().optional().default(4983),
  160| 	host: string().optional().default('127.0.0.1'),
  161| 	config: string().optional(),
  162| });
  163| 
  164| export const configStudio = configCommonSchema.extend({
  165| 	schema: union([string(), string().array()]).optional(),
  166| });
  167| 
  168| export const configMigrate = configCommonSchema.extend({
  169| 	migrations: configMigrations,
  170| });
  171| 
  172| export const pushParams = object({
  173| 	dialect: dialect,
  174| 	schema: union([string(), string().array()]),
  175| 	verbose: boolean().optional(),
  176| 	explain: boolean().optional(),
  177| 	hints: string().optional(),
  178| 	hintsFile: string().optional(),
  179| 	migrations: configMigrations,
  180| 	...entitiesParams,
  181| }).passthrough();
  182| 
  183| export type PushParams = TypeOf<typeof pushParams>;
  184| 
  185| export const pullParams = object({
  186| 	config: string().optional(),
  187| 	dialect: dialect,
  188| 	out: string().optional().default('drizzle'),
  189| 	casing,
  190| 	breakpoints: boolean().optional().default(true),
  191| 	migrations: configMigrations,
  192| 	...entitiesParams,
  193| }).passthrough();
  194| 
  195| export const studioConfig = object({
  196| 	dialect,
  197| 	schema: union([string(), string().array()]).optional(),
  198| });
  199| 
  200| export const wrapParam = (
  201| 	name: string,
  202| 	param: any | undefined,
  203| 	optional: boolean = false,
  204| 	type?: 'url' | 'secret',
  205| ) => {
  206| 	const check = `[${chalk.green('✓')}]`;
  207| 	const cross = `[${chalk.red('x')}]`;
  208| 	if (typeof param === 'string') {
  209| 		if (param.length === 0) {
  210| 			return `    ${cross} ${name}: ''`;
  211| 		}
  212| 		if (type === 'secret') {
  213| 			return `    ${check} ${name}: '*****'`;
  214| 		} else if (type === 'url') {
  215| 			return `    ${check} ${name}: '${param.replace(/(?<=:\/\/[^:\n]*:)([^@]*)/, '****')}'`;
  216| 		}
  217| 		return `    ${check} ${name}: '${param}'`;
  218| 	}
  219| 	if (optional) {
  220| 		return chalk.gray(`        ${name}?: `);
  221| 	}
  222| 	return `    ${cross} ${name}: ${chalk.gray('undefined')}`;
  223| };
  224| 
```

### drizzle-kit/src/dialects/mssql/ddl.ts (lines 238 to 415 of 415)
```
  238| 
  239| export type SchemaError = {
  240| 	type: 'table_duplicate';
  241| 	name: string;
  242| 	schema: string;
  243| } | {
  244| 	type: 'column_duplicate';
  245| 	table: string;
  246| 	name: string;
  247| 	schema: string;
  248| } | {
  249| 	type: 'view_name_duplicate';
  250| 	schema: string;
  251| 	name: string;
  252| } | {
  253| 	type: 'schema_duplicate';
  254| 	name: string;
  255| } | {
  256| 	type: 'index_duplicate';
  257| 	schema: string;
  258| 	table: string;
  259| 	name: string;
  260| } | {
  261| 	type: 'index_no_name';
  262| 	schema: string;
  263| 	table: string;
  264| 	sql: string;
  265| } | {
  266| 	type: 'constraint_duplicate';
  267| 	schema: string;
  268| 	table: string;
  269| 	name: string;
  270| };
  271| 
  272| export const interimToDDL = (interim: InterimSchema): { ddl: MssqlDDL; errors: SchemaError[] } => {
  273| 	const errors = [] as SchemaError[];
  274| 	const ddl = createDDL();
  275| 
  276| 	for (const it of interim.schemas) {
  277| 		const res = ddl.schemas.push(it);
  278| 		if (res.status === 'CONFLICT') {
  279| 			errors.push({ type: 'schema_duplicate', name: it.name });
  280| 		}
  281| 	}
  282| 
  283| 	for (const table of interim.tables) {
  284| 		const res = ddl.tables.push(table);
  285| 		if (res.status === 'CONFLICT') {
  286| 			errors.push({ type: 'table_duplicate', name: table.name, schema: res.data.schema });
  287| 		}
  288| 	}
  289| 
  290| 	for (const column of interim.columns) {
  291| 		const { isPK: _1, isUnique: _2, pkName: _3, uniqueName: _4, ...rest } = column;
  292| 
  293| 		const res = ddl.columns.push(rest);
  294| 		if (res.status === 'CONFLICT') {
  295| 			errors.push({ type: 'column_duplicate', table: column.table, name: column.name, schema: res.data.schema });
  296| 		}
  297| 	}
  298| 
  299| 	for (const index of interim.indexes) {
  300| 		const res = ddl.indexes.push(index);
  301| 
  302| 		if (res.status === 'CONFLICT') {
  303| 			errors.push({
  304| 				type: 'index_duplicate',
  305| 				schema: index.schema,
  306| 				table: index.table,
  307| 				name: index.name,
  308| 			});
  309| 		}
  310| 
  311| 		ddl.indexes.push(index);
  312| 	}
  313| 
  314| 	for (const unique of interim.uniques) {
  315| 		const isConflictNamePerSchema = ddl.uniques.one({ schema: unique.schema, name: unique.name });
  316| 
  317| 		if (isConflictNamePerSchema) {
  318| 			errors.push({
  319| 				type: 'constraint_duplicate',
  320| 				schema: unique.schema,
  321| 				table: unique.table,
  322| 				name: unique.name,
  323| 			});
  324| 		}
  325| 		ddl.uniques.push(unique);
  326| 	}
  327| 
  328| 	for (const fk of interim.fks) {
  329| 		const isConflictNamePerSchema = ddl.fks.one({ schema: fk.schema, name: fk.name });
  330| 
  331| 		if (isConflictNamePerSchema) {
  332| 			errors.push({ type: 'constraint_duplicate', name: fk.name, table: fk.table, schema: fk.schema });
  333| 		}
  334| 
  335| 		ddl.fks.push(fk);
  336| 	}
  337| 
  338| 	for (const pk of interim.pks) {
  339| 		const isConflictNamePerSchema = ddl.pks.one({ schema: pk.schema, name: pk.name });
  340| 
  341| 		if (isConflictNamePerSchema) {
  342| 			errors.push({ type: 'constraint_duplicate', name: pk.name, table: pk.table, schema: pk.schema });
  343| 		}
  344| 		ddl.pks.push(pk);
  345| 	}
  346| 
  347| 	for (const column of interim.columns.filter((it) => it.isPK)) {
  348| 		const name = column.pkName !== null ? column.pkName : defaultNameForPK(column.table);
  349| 		const exists = ddl.pks.one({ schema: column.schema, table: column.table, name: name }) !== null;
  350| 		if (exists) continue;
  351| 
  352| 		ddl.pks.push({
  353| 			table: column.table,
  354| 			name,
  355| 			nameExplicit: column.pkName !== null,
  356| 			columns: [column.name],
  357| 			schema: column.schema,
  358| 		});
  359| 	}
  360| 
  361| 	for (const column of interim.columns.filter((it) => it.isUnique)) {
  362| 		const name = column.uniqueName !== null ? column.uniqueName : defaultNameForUnique(column.table, [column.name]);
  363| 		const exists = ddl.uniques.one({ schema: column.schema, table: column.table, name: name }) !== null;
  364| 		if (exists) continue;
  365| 
  366| 		ddl.uniques.push({
  367| 			schema: column.schema,
  368| 			table: column.table,
  369| 			name,
  370| 			nameExplicit: column.uniqueName !== null,
  371| 			columns: [column.name],
  372| 		});
  373| 	}
  374| 
  375| 	for (const columnDefault of interim.defaults) {
  376| 		const res = ddl.defaults.push(columnDefault);
  377| 		if (res.status === 'CONFLICT') {
  378| 			errors.push({
  379| 				type: 'constraint_duplicate',
  380| 				schema: columnDefault.schema,
  381| 				table: columnDefault.table,
  382| 				name: columnDefault.name,
  383| 			});
  384| 		}
  385| 	}
  386| 
  387| 	for (const check of interim.checks) {
  388| 		const isConflictNamePerSchema = ddl.checks.one({ schema: check.schema, name: check.name });
  389| 
  390| 		if (isConflictNamePerSchema) {
  391| 			errors.push({
  392| 				type: 'constraint_duplicate',
  393| 				schema: check.schema,
  394| 				table: check.table,
  395| 				name: check.name,
  396| 			});
  397| 		}
  398| 
  399| 		ddl.checks.push(check);
  400| 	}
  401| 
  402| 	for (const view of interim.views) {
  403| 		const res = ddl.views.push(view);
  404| 		if (res.status === 'CONFLICT') {
  405| 			errors.push({
  406| 				type: 'view_name_duplicate',
  407| 				schema: view.schema,
  408| 				name: view.name,
  409| 			});
  410| 		}
  411| 	}
  412| 
  413| 	return { ddl, errors };
  414| };
  415| 
```

### changelogs/drizzle-kit/1.0.0-rc.5.md (lines 1 to 12 of 12)
```
    1| # v1.0.0-rc.5
    2| 
    3| - [[BUG]: SQLite push glues the table's FOREIGN KEY clause onto a generated-column ALTER ADD, breaking all inserts](https://github.com/drizzle-team/drizzle-orm/issues/6061)
    4| - [[BUG]: SQLite push table recreate silently drops UNIQUE from a column that also has a plain index](https://github.com/drizzle-team/drizzle-orm/issues/6060)
    5| - [[BUG]:drizzle-kit generates DROP COLUMN before DROP INDEX causing PostgreSQL error 42704](https://github.com/drizzle-team/drizzle-orm/issues/6045)- [[BUG]: false positve detection of schema changes for default values](https://github.com/drizzle-team/drizzle-orm/issues/5569)
    6| - [[BUG]: drizzle-kit pull rewrites "character" inside public enum type names to "char"](https://github.com/drizzle-team/drizzle-orm/issues/5932)
    7| - [[BUG]: drizzle-kit pull error when there are comments in a view definition](https://github.com/drizzle-team/drizzle-orm/issues/5964)
    8| - [[BUG]: inArray/notInArray empty arrays do not work with SQL Server](https://github.com/drizzle-team/drizzle-orm/issues/5632)
    9| - [[BUG]: Invalid schema default value generated for sequence-based primary keys in Postgres](https://github.com/drizzle-team/drizzle-orm/issues/5413)
   10| - [Small typo in drizzle-kit/src/index.ts](https://github.com/drizzle-team/drizzle-orm/issues/4736)
   11| - [[BUG]: drizzle-kit pull reports index_duplicate for valid MSSQL index names reused across tables](https://github.com/drizzle-team/drizzle-orm/issues/5993)
   12| - [[BUG]: drizzle-kit pull generates many() instead of one() for one-to-one relations (unique FK columns)](https://github.com/drizzle-team/drizzle-orm/issues/5478)
```

### drizzle-kit/src/cli/commands/pull-common.ts (lines 114 to 313 of 328)
```
  114| 					type: 'through',
  115| 					tableFrom: toTable1,
  116| 					columnsFrom: columnsTo1,
  117| 					tableTo: toTable2,
  118| 					columnsTo: columnsTo2,
  119| 					tableThrough,
  120| 					columnsThroughFrom,
  121| 					columnsThroughTo,
  122| 				});
  123| 
  124| 				if (!tableRelations[toTable2]) {
  125| 					tableRelations[toTable2] = [];
  126| 				}
  127| 
  128| 				tableRelations[toTable2].push({
  129| 					name: prepareNameFor(plural(toTable1), tableColumns),
  130| 					// this type is used for .many() side of relation, when another side has .through() with from and to fields
  131| 					type: 'many-through',
  132| 					tableFrom: toTable2,
  133| 					columnsFrom: columnsTo2,
  134| 					tableTo: toTable1,
  135| 					columnsTo: columnsTo1,
  136| 					tableThrough,
  137| 					columnsThroughFrom,
  138| 					columnsThroughTo,
  139| 				});
  140| 			}
  141| 		} else {
  142| 			fks.forEach((fk) => {
  143| 				const tableNameFrom = paramNameFor(fk.table, table.schema);
  144| 				const tableNameTo = paramNameFor(fk.tableTo, fk.schemaTo);
  145| 				const tableFrom = withCasing(tableNameFrom.replace(/:+/g, ''), casing);
  146| 				const tableTo = withCasing(tableNameTo.replace(/:+/g, ''), casing);
  147| 				const columnsFrom = fk.columns.map((it) => withCasing(it, casing));
  148| 				const columnsTo = fk.columnsTo.map((it) => withCasing(it, casing));
  149| 
  150| 				imports.push(tableTo, tableFrom);
  151| 
  152| 				const keyFrom = tableFrom;
  153| 				if (!tableRelations[keyFrom]) {
  154| 					tableRelations[keyFrom] = [];
  155| 				}
  156| 
  157| 				tableRelations[keyFrom].push({
  158| 					name: prepareNameFor(singular(tableTo), tableColumns),
  159| 					type: 'one',
  160| 					tableFrom,
  161| 					columnsFrom,
  162| 					tableTo,
  163| 					columnsTo,
  164| 				});
  165| 
  166| 				const keyTo = tableTo;
  167| 				if (!tableRelations[keyTo]) {
  168| 					tableRelations[keyTo] = [];
  169| 				}
  170| 
  171| 				// if this table has a unique on a column, that is used for 1-m, then we can assume that it's 1-1 relation
  172| 				// we will check that all of the fk columns are unique, so we can assume it's 1-1
  173| 				// not matter if it's 1 column, 2 columns or more
  174| 				if (
  175| 					table.uniques.find((constraint) =>
  176| 						constraint.columns.length === fk.columns.length // need to check without casing (name should be preserved)
  177| 						&& constraint.columns.every((col, i) => col === fk.columns[i]) // need to check without casing (name should be preserved)
  178| 					)
  179| 				) {
  180| 					// the difference between one and one-one is that one-one won't contain from and to
  181| 					// maybe it can be done by introducing some sort of flag or just not providing columnsFrom and columnsTo
  182| 					// but I decided just to have a different type field here
  183| 					tableRelations[keyTo].push({
  184| 						name: prepareNameFor(plural(tableFrom), tableColumns),
  185| 						type: 'one-one',
  186| 						tableFrom: tableTo,
  187| 						columnsFrom: columnsTo,
  188| 						tableTo: tableFrom,
  189| 						columnsTo: columnsFrom,
  190| 					});
  191| 				} else {
  192| 					tableRelations[keyTo].push({
  193| 						name: prepareNameFor(plural(tableFrom), tableColumns),
  194| 						type: 'many',
  195| 						tableFrom: tableTo,
  196| 						columnsFrom: columnsTo,
  197| 						tableTo: tableFrom,
  198| 						columnsTo: columnsFrom,
  199| 					});
  200| 				}
  201| 			});
  202| 		}
  203| 	});
  204| 
  205| 	const importsTs = `import { defineRelations } from "drizzle-orm";\nimport * as schema from "${
  206| 		schemaPath ?? './schema'
  207| 	}";\n\n`;
  208| 
  209| 	let relationString = `export const relations = defineRelations(schema, (r) => ({`;
  210| 
  211| 	Object.entries(tableRelations).forEach(([table, relations]) => {
  212| 		// Adjust duplicate names if needed.
  213| 		const preparedRelations = relations.map(
  214| 			(relation, relationIndex, originArray) => {
  215| 				let name = relation.name;
  216| 				let relationName;
  217| 				const hasMultipleRelations = originArray.some(
  218| 					(it, originIndex) => relationIndex !== originIndex && it.tableTo === relation.tableTo,
  219| 				);
  220| 				if (hasMultipleRelations) {
  221| 					// if one relation - we need to name a relation from this table to "many" table
  222| 					if (relation.type === 'one') {
  223| 						relationName = `${relation.tableFrom}_${relation.columnsFrom.join('_')}_${relation.tableTo}_${
  224| 							relation.columnsTo.join('_')
  225| 						}`;
  226| 						// if many relation - name in in different order, so alias names will match
  227| 					} else if (relation.type === 'many' || relation.type === 'one-one') {
  228| 						relationName = `${relation.tableTo}_${relation.columnsTo.join('_')}_${relation.tableFrom}_${
  229| 							relation.columnsFrom.join('_')
  230| 						}`;
  231| 						// if through relation - we need to name a relation from this table to "many" table and include "via"
  232| 					} else if (relation.type === 'through') {
  233| 						relationName = `${relation.tableFrom}_${relation.columnsFrom.join('_')}_${relation.tableTo}_${
  234| 							relation.columnsTo.join('_')
  235| 						}_via_${relation.tableThrough}`;
  236| 						// else is for many-through, meaning we need to reverse the order for tables and columns, but leave "via" the same
  237| 					} else {
  238| 						relationName = `${relation.tableTo}_${relation.columnsTo.join('_')}_${relation.tableFrom}_${
  239| 							relation.columnsFrom.join('_')
  240| 						}_via_${relation.tableThrough}`;
  241| 					}
  242| 				}
  243| 				const hasDuplicatedRelation = originArray.some(
  244| 					(it, originIndex) => relationIndex !== originIndex && it.name === relation.name,
  245| 				);
  246| 				if (hasDuplicatedRelation) {
  247| 					name = `${relation.name}_${
  248| 						relation.type === 'through'
  249| 							? `via_${relation.tableThrough}`
  250| 							: relation.type === 'many-through'
  251| 							? `via_${relation.tableThrough}`
  252| 							: relation.type === 'one'
  253| 							? relation.columnsFrom.join('_')
  254| 							: relation.columnsTo.join('_')
  255| 					}`;
  256| 				}
  257| 				return {
  258| 					...relation,
  259| 					name: withCasing(name, casing),
  260| 					relationName,
  261| 				};
  262| 			},
  263| 		);
  264| 
  265| 		relationString += `\n\t${table}: {`;
  266| 		preparedRelations.forEach((relation) => {
  267| 			if (relation.type === 'one') {
  268| 				const from = relation.columnsFrom.length === 1
  269| 					? `r.${relation.tableFrom}.${relation.columnsFrom[0]}`
  270| 					: `[${
  271| 						relation.columnsFrom
  272| 							.map((it) => `r.${relation.tableFrom}.${it}`)
  273| 							.join(', ')
  274| 					}]`;
  275| 				const to = relation.columnsTo.length === 1
  276| 					? `r.${relation.tableTo}.${relation.columnsTo[0]}`
  277| 					: `[${
  278| 						relation.columnsTo
  279| 							.map((it) => `r.${relation.tableTo}.${it}`)
  280| 							.join(', ')
  281| 					}]`;
  282| 
  283| 				relationString += `\n\t\t${relation.name}: r.one.${relation.tableTo}({\n\t\t\tfrom: ${from},\n\t\t\tto: ${to}`
  284| 					+ (relation.relationName ? `,\n\t\t\talias: "${relation.relationName}"` : '')
  285| 					+ `\n\t\t}),`;
  286| 			} else if (relation.type === 'many' || relation.type === 'many-through') {
  287| 				relationString += `\n\t\t${relation.name}: r.many.${relation.tableTo}(`
  288| 					+ (relation.relationName ? `{\n\t\t\talias: "${relation.relationName}"\n\t\t}` : '')
  289| 					+ `),`;
  290| 			} else if (relation.type === 'one-one') {
  291| 				relationString += `\n\t\t${relation.name}: r.one.${relation.tableTo}(`
  292| 					+ (relation.relationName ? `{\n\t\t\talias: "${relation.relationName}"\n\t\t}` : '')
  293| 					+ `),`;
  294| 			} else {
  295| 				const from = relation.columnsThroughFrom!.length === 1
  296| 					? `r.${relation.tableFrom}.${relation.columnsFrom[0]}.through(r.${relation.tableThrough}.${
  297| 						relation.columnsThroughFrom![0]
  298| 					})`
  299| 					: `[${
  300| 						relation.columnsThroughFrom!
  301| 							.map((it) => `r.${relation.tableFrom}.${it}.through(${relation.tableThrough}.${it})`)
  302| 							.join(', ')
  303| 					}]`;
  304| 				const to = relation.columnsThroughTo!.length === 1
  305| 					? `r.${relation.tableTo}.${relation.columnsTo![0]}.through(r.${relation.tableThrough}.${
  306| 						relation.columnsThroughTo![0]
  307| 					})`
  308| 					: `[${
  309| 						relation.columnsThroughTo!
  310| 							.map((it) => `r.${relation.tableTo}.${it}.through(${relation.tableThrough}.${it})`)
  311| 							.join(', ')
  312| 					}]`;
  313| 
```

### drizzle-kit/tests/mssql/mocks.ts (lines 91 to 290 of 506)
```
   91| 		mockResolver(renames),
   92| 		mockResolver(renames),
   93| 		mockResolver(renames), // uniques
   94| 		mockResolver(renames), // indexes
   95| 		mockResolver(renames), // checks
   96| 		mockResolver(renames), // pks
   97| 		mockResolver(renames), // fks
   98| 		mockResolver(renames), // defaults
   99| 		'default',
  100| 	);
  101| 
  102| 	return { sqlStatements, statements, groupedStatements, next: ddl2 };
  103| };
  104| 
  105| export const diffIntrospect = async (
  106| 	db: DB,
  107| 	initSchema: MssqlDBSchema,
  108| 	testName: string,
  109| 	schemas: string[] = [],
  110| 	entities?: EntitiesFilter,
  111| ) => {
  112| 	const filterConfig: EntitiesFilterConfig = {
  113| 		schemas,
  114| 		entities,
  115| 		tables: [],
  116| 		extensions: [],
  117| 	};
  118| 
  119| 	const { ddl: initDDL, existing } = drizzleToDDL(initSchema, filterConfig);
  120| 	const { sqlStatements: init } = await ddlDiffDry(createDDL(), initDDL, 'default');
  121| 
  122| 	for (const st of init) await db.query(st);
  123| 
  124| 	const filter = prepareEntityFilter('mssql', filterConfig, existing);
  125| 
  126| 	const schema = await fromDatabaseForDrizzle(db, filter, () => true, {
  127| 		table: '__drizzle_migrations',
  128| 		schema: 'drizzle',
  129| 	});
  130| 
  131| 	const { ddl: ddl1, errors: e1 } = interimToDDL(schema);
  132| 
  133| 	const file = ddlToTypeScript(ddl1, schema.viewColumns, 'camel');
  134| 
  135| 	const filePath = `tests/mssql/tmp/${testName}.ts`;
  136| 
  137| 	writeFileSync(filePath, file.file);
  138| 	await tsc(file.file);
  139| 
  140| 	const typeCheckResult = await $`pnpm exec tsc --noEmit --skipLibCheck ${filePath}`.nothrow();
  141| 	if (typeCheckResult.exitCode !== 0) {
  142| 		throw new Error(typeCheckResult.stderr || typeCheckResult.stdout);
  143| 	}
  144| 
  145| 	// generate snapshot from ts file
  146| 	const response = await prepareFromSchemaFiles([
  147| 		filePath,
  148| 	]);
  149| 
  150| 	const { schema: schema2, errors: e2 } = fromDrizzleSchema(response, filter);
  151| 	const { ddl: ddl2, errors: e3 } = interimToDDL(schema2);
  152| 
  153| 	if (e1.length > 0 || e2.length > 0 || e3.length > 0) {
  154| 		throw new MockError([...e1, ...e2, ...e3]);
  155| 	}
  156| 
  157| 	const {
  158| 		sqlStatements: afterFileSqlStatements,
  159| 		statements: afterFileStatements,
  160| 	} = await ddlDiffDry(ddl1, ddl2, 'push');
  161| 
  162| 	rmSync(`tests/mssql/tmp/${testName}.ts`);
  163| 
  164| 	return {
  165| 		introspectDDL: ddl1,
  166| 		fromFileDDL: ddl2,
  167| 		sqlStatements: afterFileSqlStatements,
  168| 		statements: afterFileStatements,
  169| 	};
  170| };
  171| 
  172| // init schema flush to db -> introspect db to ddl -> compare ddl with destination schema
  173| export const push = async (config: {
  174| 	db: DB;
  175| 	to: MssqlDBSchema | MssqlDDL;
  176| 	renames?: string[];
  177| 	schemas?: string[];
  178| 	log?: 'statements' | 'none';
  179| 	force?: boolean;
  180| 	expectError?: boolean;
  181| 	ignoreSubsequent?: boolean;
  182| 	explain?: boolean;
  183| 	migrationsConfig?: {
  184| 		schema?: string;
  185| 		table?: string;
  186| 	};
  187| }) => {
  188| 	const { db, to, log } = config;
  189| 
  190| 	const migrations = configMigrations.parse(config.migrationsConfig);
  191| 
  192| 	const filterConfig: EntitiesFilterConfig = {
  193| 		schemas: config.schemas,
  194| 		entities: undefined,
  195| 		tables: [],
  196| 		extensions: [],
  197| 	};
  198| 	const { ddl: ddl2, errors: err2, existing } = 'entities' in to && '_' in to
  199| 		? { ddl: to as MssqlDDL, errors: [], existing: [] }
  200| 		: drizzleToDDL(to, filterConfig);
  201| 
  202| 	const filter = prepareEntityFilter('mssql', filterConfig, existing);
  203| 
  204| 	const { schema } = await introspect(
  205| 		db,
  206| 		filter,
  207| 		new EmptyProgressView(),
  208| 		migrations,
  209| 	);
  210| 
  211| 	const { ddl: ddl1, errors: err3 } = interimToDDL(schema);
  212| 
  213| 	if (err2.length > 0) {
  214| 		throw new MockError(err2);
  215| 	}
  216| 
  217| 	if (err3.length > 0) {
  218| 		throw new MockError(err3);
  219| 	}
  220| 
  221| 	const renames = new Set(config.renames ?? []);
  222| 
  223| 	const { sqlStatements, statements, groupedStatements } = await ddlDiff(
  224| 		ddl1,
  225| 		ddl2,
  226| 		mockResolver(renames),
  227| 		mockResolver(renames),
  228| 		mockResolver(renames),
  229| 		mockResolver(renames), // views
  230| 		mockResolver(renames), // uniques
  231| 		mockResolver(renames), // indexes
  232| 		mockResolver(renames), // checks
  233| 		mockResolver(renames), // pks
  234| 		mockResolver(renames), // fks
  235| 		mockResolver(renames), // defaults
  236| 		'push',
  237| 	);
  238| 
  239| 	const hints = await runWithCliContext(
  240| 		{ output: 'text', interactive: true },
  241| 		() => suggestions(db, statements, ddl2, new HintsHandler()),
  242| 	);
  243| 
  244| 	if (config.explain) {
  245| 		const explainMessage = explain('mssql', groupedStatements, []);
  246| 		console.log(explainMessage);
  247| 		return { sqlStatements, statements, hints };
  248| 	}
  249| 
  250| 	let error: Error | null = null;
  251| 	for (const sql of sqlStatements) {
  252| 		if (log === 'statements') console.log(sql);
  253| 		try {
  254| 			await db.query(sql);
  255| 		} catch (e) {
  256| 			if (!config.expectError) throw e;
  257| 			error = e as Error;
  258| 			break;
  259| 		}
  260| 	}
  261| 
  262| 	// subsequent push
  263| 	if (!config.ignoreSubsequent) {
  264| 		{
  265| 			const { schema } = await introspect(
  266| 				db,
  267| 				filter,
  268| 				new EmptyProgressView(),
  269| 				migrations,
  270| 			);
  271| 			const { ddl: ddl1, errors: err3 } = interimToDDL(schema);
  272| 
  273| 			const { sqlStatements, statements } = await ddlDiff(
  274| 				ddl1,
  275| 				ddl2,
  276| 				mockResolver(renames),
  277| 				mockResolver(renames),
  278| 				mockResolver(renames),
  279| 				mockResolver(renames),
  280| 				mockResolver(renames),
  281| 				mockResolver(renames),
  282| 				mockResolver(renames),
  283| 				mockResolver(renames),
  284| 				mockResolver(renames),
  285| 				mockResolver(renames),
  286| 				'push',
  287| 			);
  288| 			if (sqlStatements.length > 0) {
  289| 				console.error('---- subsequent push is not empty ----');
  290| 				expect(sqlStatements.join('\n')).toBe('');
```
