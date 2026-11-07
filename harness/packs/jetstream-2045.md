# PR pack: jetstreamapp/jetstream#2045
Title: fix: ensure team is auto-created on upgrade
Merge commit: b98669309b4c5f32015e1a0cdc842393a7cfec10

## Diff
```diff
diff --git a/apps/api/src/app/services/__tests__/stripe.service.team-upgrade.spec.ts b/apps/api/src/app/services/__tests__/stripe.service.team-upgrade.spec.ts
new file mode 100644
index 000000000..c7c0a2870
--- /dev/null
+++ b/apps/api/src/app/services/__tests__/stripe.service.team-upgrade.spec.ts
@@ -0,0 +1,126 @@
+import { beforeEach, describe, expect, it, vi } from 'vitest';
+import type * as StripeService from '../stripe.service';
+
+// `stripe` v22 ships its types inline per module format, so `import type Stripe from 'stripe'` here
+// resolves to the ESM declarations while the service resolves to the CJS ones - structurally identical
+// but nominally distinct. Derive the fixture type from the service itself to stay on one identity.
+type StripeCustomer = Parameters<typeof StripeService.saveOrUpdateSubscription>[0]['customer'];
+
+const mocks = vi.hoisted(() => ({
+  customersRetrieve: vi.fn(),
+  customersUpdate: vi.fn(async () => ({ id: 'cus_1' })),
+  upsertTeamWithBillingAccount: vi.fn(async () => ({ id: 'team_new' })),
+  updateSubscriptionStateForCustomer: vi.fn(async () => ({})),
+  updateTeamSubscriptionStateForCustomer: vi.fn(async () => ({})),
+  findUserById: vi.fn(),
+}));
+
+vi.mock('stripe', () => ({
+  default: class {
+    customers = {
+      retrieve: mocks.customersRetrieve,
+      update: mocks.customersUpdate,
+      createFundingInstructions: vi.fn(async () => ({})),
+      search: vi.fn(),
+      create: vi.fn(),
+    };
+    entitlements = { activeEntitlements: { list: vi.fn(async () => ({ data: [] })) } };
+    webhooks = { constructEvent: vi.fn() };
+    prices = { list: vi.fn() };
+  },
+}));
+
+vi.mock('@jetstream/api-config', () => ({
+  ENV: { STRIPE_API_KEY: 'sk_test_x' },
+  logger: { error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() },
+  prisma: {},
+}));
+vi.mock('@jetstream/email', () => ({ sendWelcomeToProEmail: vi.fn() }));
+
+vi.mock('../../db/subscription.db', () => ({
+  updateSubscriptionStateForCustomer: mocks.updateSubscriptionStateForCustomer,
+  updateTeamSubscriptionStateForCustomer: mocks.updateTeamSubscriptionStateForCustomer,
+  updateUserEntitlements: vi.fn(async () => ({})),
+  updateTeamEntitlements: vi.fn(async () => ({})),
+}));
+vi.mock('../../db/team.db', () => ({
+  upsertTeamWithBillingAccount: mocks.upsertTeamWithBillingAccount,
+  createBillingAccountIfNotExists: vi.fn(async () => ({})),
+  findById: vi.fn(async () => ({ id: 'team_new' })),
+  findEntitlements: vi.fn(async () => ({})),
+  findSubscriptions: vi.fn(async () => []),
+}));
+vi.mock('../../db/user.db', () => ({
+  findById: mocks.findUserById,
+  upsertBillingAccount: vi.fn(async () => ({})),
+  findBillingAccountByCustomerId: vi.fn(),
+}));
+
+const subscriptionWithPrice = (lookupKey: string) => ({
+  id: 'sub_1',
+  status: 'active',
+  items: { object: 'list', data: [{ id: 'si_1', price: { id: `price_${lookupKey}`, lookup_key: lookupKey } }] },
+});
+
+const customerWithPlan = (lookupKey: string) =>
+  ({
+    id: 'cus_1',
+    deleted: undefined,
+    metadata: { userId: 'user_1', type: 'USER' },
+    subscriptions: { object: 'list', data: [subscriptionWithPrice(lookupKey)] },
+  }) as unknown as StripeCustomer;
+
+describe('personal -> team plan upgrade', () => {
+  let stripeService: typeof StripeService;
+
+  beforeEach(async () => {
+    vi.resetModules();
+    vi.clearAllMocks();
+    mocks.customersRetrieve.mockResolvedValue(customerWithPlan('TEAM_MONTHLY'));
+    // Jetstream still records the user as a personal subscriber whose entitlements already look
+    // correct - the state that made the sync path report "nothing to do" and never create a team.
+    mocks.findUserById.mockResolvedValue({
+      id: 'user_1',
+      billingAccount: { customerId: 'cus_1' },
+      subscriptions: [{ id: 'sub_row_1' }],
+      entitlements: { chromeExtension: true, googleDrive: true, desktop: true, recordSync: true },
+    });
+    stripeService = await import('../stripe.service');
+  });
+
+  it('creates the team from the subscription webhook', async () => {
+    await stripeService.saveOrUpdateSubscription({ customer: customerWithPlan('TEAM_MONTHLY'), sendWelcomeEmail: false });
+
+    expect(mocks.upsertTeamWithBillingAccount).toHaveBeenCalledWith(
+      expect.objectContaining({ userId: 'user_1', billingAccountCustomerId: 'cus_1' }),
+    );
+    expect(mocks.updateTeamSubscriptionStateForCustomer).toHaveBeenCalled();
+  });
+
+  it('creates the team from the billing page sync when the webhook was missed', async () => {
+    const result = await stripeService.synchronizeStripeWithJetstreamUserIfRequired({ userId: 'user_1' });
+
+    expect(mocks.upsertTeamWithBillingAccount).toHaveBeenCalledWith(
+      expect.objectContaining({ userId: 'user_1', billingAccountCustomerId: 'cus_1' }),
+    );
+    expect(result.success).toBe(true);
+    // The team subscription must not be recorded against the personal account
+    expect(mocks.updateSubscriptionStateForCustomer).not.toHaveBeenCalled();
+  });
+
+  it('leaves a personal plan on the personal account', async () => {
+    mocks.customersRetrieve.mockResolvedValue(customerWithPlan('PRO_MONTHLY'));
+    // Disagreeing subscription counts force the sync to actually run
+    mocks.findUserById.mockResolvedValue({
+      id: 'user_1',
+      billingAccount: { customerId: 'cus_1' },
+      subscriptions: [],
+      entitlements: { chromeExtension: true, googleDrive: true, desktop: true, recordSync: true },
+    });
+
+    await stripeService.synchronizeStripeWithJetstreamUserIfRequired({ userId: 'user_1' });
+
+    expect(mocks.upsertTeamWithBillingAccount).not.toHaveBeenCalled();
+    expect(mocks.updateSubscriptionStateForCustomer).toHaveBeenCalled();
+  });
+});
diff --git a/apps/api/src/app/services/stripe.service.ts b/apps/api/src/app/services/stripe.service.ts
index 9a85c6a70..a86f0fe34 100644
--- a/apps/api/src/app/services/stripe.service.ts
+++ b/apps/api/src/app/services/stripe.service.ts
@@ -100,6 +100,23 @@ function filterInactiveSubscriptions(subscriptions: Stripe.Subscription[]) {
   return subscriptions.filter((subscription) => activeSubscriptionStatuses.has(subscription.status));
 }
 
+function findTeamPlanSubscription(subscriptions: Stripe.Subscription[]) {
+  return subscriptions.find(({ items }) => items.data.some((item) => item.price.lookup_key?.startsWith('TEAM_')));
+}
+
+/**
+ * A team plan can be started either through checkout or by switching plans in the Stripe billing
+ * portal, and the portal never routes through checkout. Every path that observes a TEAM price on a
+ * customer funnels through here so that a delayed or failed webhook self-heals instead of leaving the
+ * user without a team.
+ */
+async function createTeamForTeamPlanCustomer({ userId, customerId }: { userId: string; customerId: string }) {
+  const team = await teamDbService.upsertTeamWithBillingAccount({ userId, billingAccountCustomerId: customerId });
+  // ensure stripe has proper metadata
+  await updateCustomerMetadata(customerId, { userId, teamId: team.id, type: 'TEAM' });
+  return team;
+}
+
 async function fetchCustomerWithSubscriptionsById({
   customerId,
 }: {
@@ -441,7 +458,17 @@ export async function synchronizeStripeWithJetstreamUserIfRequired({
     }
 
     const subscriptions = filterInactiveSubscriptions(stripeCustomer.subscriptions.data);
-    const priceRecordCount = subscriptions.flatMap((subscription) => subscription.items.data.length).length;
+
+    // The customer upgraded to a team plan without a team existing yet - most likely a plan switch in
+    // the billing portal, which never routes through checkout. Create the team and sync as a team,
+    // otherwise the team subscription would be recorded against the personal account and the checks
+    // below would then report the account as correctly synchronized forever.
+    if (findTeamPlanSubscription(subscriptions)) {
+      const team = await createTeamForTeamPlanCustomer({ userId, customerId });
+      return await synchronizeStripeWithJetstreamTeamIfRequired({ teamId: team.id, customerId });
+    }
+
+    const priceRecordCount = subscriptions.flatMap((subscription) => subscription.items.data).length;
 
     /**
      * Check if we need to synchronize
@@ -507,7 +534,7 @@ export async function synchronizeStripeWithJetstreamTeamIfRequired({
     }
 
     const subscriptions = filterInactiveSubscriptions(stripeCustomer.subscriptions.data);
-    const priceRecordCount = subscriptions.flatMap((subscription) => subscription.items.data.length).length;
+    const priceRecordCount = subscriptions.flatMap((subscription) => subscription.items.data).length;
 
     /**
      * Check if we need to synchronize
@@ -558,15 +585,13 @@ export async function saveOrUpdateSubscription({
 
   let { userId, teamId, type = 'USER' } = customer.metadata;
   const subscriptions = customer.subscriptions?.data ?? [];
-  const hasTeamPlan = subscriptions.find(({ items }) => items.data.find((item) => item.price.lookup_key?.startsWith('TEAM_')));
+  const hasTeamPlan = !!findTeamPlanSubscription(subscriptions);
 
   // Ensure team is auto-created if required and Stripe is updated to reflect this
   if (hasTeamPlan && userId && (!teamId || type !== 'TEAM')) {
     type = 'TEAM';
-    const team = await teamDbService.upsertTeamWithBillingAccount({ userId, billingAccountCustomerId: customer.id });
+    const team = await createTeamForTeamPlanCustomer({ userId, customerId: customer.id });
     teamId = team.id;
-    // ensure stripe has proper metadata
-    await updateCustomerMetadata(customer.id, { userId, teamId, type: 'TEAM' });
   }
 
   // customer does not have Jetstream id attached - update Stripe to ensure data integrity (if possible)

```

## Touched files at the merge commit (window of up to 200 lines around the first changed hunk)

### apps/api/src/app/services/__tests__/stripe.service.team-upgrade.spec.ts (lines 1 to 127 of 127)
```
    1| import { beforeEach, describe, expect, it, vi } from 'vitest';
    2| import type * as StripeService from '../stripe.service';
    3| 
    4| // `stripe` v22 ships its types inline per module format, so `import type Stripe from 'stripe'` here
    5| // resolves to the ESM declarations while the service resolves to the CJS ones - structurally identical
    6| // but nominally distinct. Derive the fixture type from the service itself to stay on one identity.
    7| type StripeCustomer = Parameters<typeof StripeService.saveOrUpdateSubscription>[0]['customer'];
    8| 
    9| const mocks = vi.hoisted(() => ({
   10|   customersRetrieve: vi.fn(),
   11|   customersUpdate: vi.fn(async () => ({ id: 'cus_1' })),
   12|   upsertTeamWithBillingAccount: vi.fn(async () => ({ id: 'team_new' })),
   13|   updateSubscriptionStateForCustomer: vi.fn(async () => ({})),
   14|   updateTeamSubscriptionStateForCustomer: vi.fn(async () => ({})),
   15|   findUserById: vi.fn(),
   16| }));
   17| 
   18| vi.mock('stripe', () => ({
   19|   default: class {
   20|     customers = {
   21|       retrieve: mocks.customersRetrieve,
   22|       update: mocks.customersUpdate,
   23|       createFundingInstructions: vi.fn(async () => ({})),
   24|       search: vi.fn(),
   25|       create: vi.fn(),
   26|     };
   27|     entitlements = { activeEntitlements: { list: vi.fn(async () => ({ data: [] })) } };
   28|     webhooks = { constructEvent: vi.fn() };
   29|     prices = { list: vi.fn() };
   30|   },
   31| }));
   32| 
   33| vi.mock('@jetstream/api-config', () => ({
   34|   ENV: { STRIPE_API_KEY: 'sk_test_x' },
   35|   logger: { error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() },
   36|   prisma: {},
   37| }));
   38| vi.mock('@jetstream/email', () => ({ sendWelcomeToProEmail: vi.fn() }));
   39| 
   40| vi.mock('../../db/subscription.db', () => ({
   41|   updateSubscriptionStateForCustomer: mocks.updateSubscriptionStateForCustomer,
   42|   updateTeamSubscriptionStateForCustomer: mocks.updateTeamSubscriptionStateForCustomer,
   43|   updateUserEntitlements: vi.fn(async () => ({})),
   44|   updateTeamEntitlements: vi.fn(async () => ({})),
   45| }));
   46| vi.mock('../../db/team.db', () => ({
   47|   upsertTeamWithBillingAccount: mocks.upsertTeamWithBillingAccount,
   48|   createBillingAccountIfNotExists: vi.fn(async () => ({})),
   49|   findById: vi.fn(async () => ({ id: 'team_new' })),
   50|   findEntitlements: vi.fn(async () => ({})),
   51|   findSubscriptions: vi.fn(async () => []),
   52| }));
   53| vi.mock('../../db/user.db', () => ({
   54|   findById: mocks.findUserById,
   55|   upsertBillingAccount: vi.fn(async () => ({})),
   56|   findBillingAccountByCustomerId: vi.fn(),
   57| }));
   58| 
   59| const subscriptionWithPrice = (lookupKey: string) => ({
   60|   id: 'sub_1',
   61|   status: 'active',
   62|   items: { object: 'list', data: [{ id: 'si_1', price: { id: `price_${lookupKey}`, lookup_key: lookupKey } }] },
   63| });
   64| 
   65| const customerWithPlan = (lookupKey: string) =>
   66|   ({
   67|     id: 'cus_1',
   68|     deleted: undefined,
   69|     metadata: { userId: 'user_1', type: 'USER' },
   70|     subscriptions: { object: 'list', data: [subscriptionWithPrice(lookupKey)] },
   71|   }) as unknown as StripeCustomer;
   72| 
   73| describe('personal -> team plan upgrade', () => {
   74|   let stripeService: typeof StripeService;
   75| 
   76|   beforeEach(async () => {
   77|     vi.resetModules();
   78|     vi.clearAllMocks();
   79|     mocks.customersRetrieve.mockResolvedValue(customerWithPlan('TEAM_MONTHLY'));
   80|     // Jetstream still records the user as a personal subscriber whose entitlements already look
   81|     // correct - the state that made the sync path report "nothing to do" and never create a team.
   82|     mocks.findUserById.mockResolvedValue({
   83|       id: 'user_1',
   84|       billingAccount: { customerId: 'cus_1' },
   85|       subscriptions: [{ id: 'sub_row_1' }],
   86|       entitlements: { chromeExtension: true, googleDrive: true, desktop: true, recordSync: true },
   87|     });
   88|     stripeService = await import('../stripe.service');
   89|   });
   90| 
   91|   it('creates the team from the subscription webhook', async () => {
   92|     await stripeService.saveOrUpdateSubscription({ customer: customerWithPlan('TEAM_MONTHLY'), sendWelcomeEmail: false });
   93| 
   94|     expect(mocks.upsertTeamWithBillingAccount).toHaveBeenCalledWith(
   95|       expect.objectContaining({ userId: 'user_1', billingAccountCustomerId: 'cus_1' }),
   96|     );
   97|     expect(mocks.updateTeamSubscriptionStateForCustomer).toHaveBeenCalled();
   98|   });
   99| 
  100|   it('creates the team from the billing page sync when the webhook was missed', async () => {
  101|     const result = await stripeService.synchronizeStripeWithJetstreamUserIfRequired({ userId: 'user_1' });
  102| 
  103|     expect(mocks.upsertTeamWithBillingAccount).toHaveBeenCalledWith(
  104|       expect.objectContaining({ userId: 'user_1', billingAccountCustomerId: 'cus_1' }),
  105|     );
  106|     expect(result.success).toBe(true);
  107|     // The team subscription must not be recorded against the personal account
  108|     expect(mocks.updateSubscriptionStateForCustomer).not.toHaveBeenCalled();
  109|   });
  110| 
  111|   it('leaves a personal plan on the personal account', async () => {
  112|     mocks.customersRetrieve.mockResolvedValue(customerWithPlan('PRO_MONTHLY'));
  113|     // Disagreeing subscription counts force the sync to actually run
  114|     mocks.findUserById.mockResolvedValue({
  115|       id: 'user_1',
  116|       billingAccount: { customerId: 'cus_1' },
  117|       subscriptions: [],
  118|       entitlements: { chromeExtension: true, googleDrive: true, desktop: true, recordSync: true },
  119|     });
  120| 
  121|     await stripeService.synchronizeStripeWithJetstreamUserIfRequired({ userId: 'user_1' });
  122| 
  123|     expect(mocks.upsertTeamWithBillingAccount).not.toHaveBeenCalled();
  124|     expect(mocks.updateSubscriptionStateForCustomer).toHaveBeenCalled();
  125|   });
  126| });
  127| 
```

### apps/api/src/app/services/stripe.service.ts (lines 41 to 240 of 916)
```
   41| 
   42| export type StripeSyncFailureReason = 'NO_CUSTOMER_ID' | 'CUSTOMER_IS_DELETED' | 'MISSING_SUBSCRIPTIONS' | 'UNKNOWN_ERROR';
   43| 
   44| /**
   45|  * Declared explicitly rather than inferred because the Stripe SDK's generated types are no longer
   46|  * nameable from an inferred position, which breaks declaration emit.
   47|  */
   48| export type StripeJetstreamSyncResult =
   49|   | { success: true; reason?: undefined; didUpdate: boolean; stripeCustomer?: Stripe.Customer }
   50|   | { success: false; reason: StripeSyncFailureReason; didUpdate?: boolean; stripeCustomer?: undefined };
   51| 
   52| export async function handleStripeWebhook({ signature, payload }: { signature?: string; payload: string | Buffer }) {
   53|   if (!ENV.STRIPE_API_KEY) {
   54|     throw new Error('Stripe API key not set');
   55|   }
   56| 
   57|   if (!ENV.STRIPE_WEBHOOK_SECRET) {
   58|     throw new Error('Stripe Webhook secret not set');
   59|   }
   60| 
   61|   if (!signature) {
   62|     throw new Error('Missing webhook signature');
   63|   }
   64| 
   65|   try {
   66|     const event = stripe.webhooks.constructEvent(payload, signature, ENV.STRIPE_WEBHOOK_SECRET);
   67| 
   68|     logger.info({ eventId: event.id, eventType: event.type }, '[STRIPE]: Handling event %s', event.type);
   69| 
   70|     switch (event.type) {
   71|       case 'entitlements.active_entitlement_summary.updated': {
   72|         await updateEntitlementsFromWebhook(event.data.object);
   73|         break;
   74|       }
   75|       case 'checkout.session.completed': {
   76|         await saveSubscriptionFromCompletedSession({ sessionId: event.data.object.id });
   77|         break;
   78|       }
   79|       case 'customer.subscription.created':
   80|       case 'customer.subscription.deleted':
   81|       case 'customer.subscription.paused':
   82|       case 'customer.subscription.resumed':
   83|       case 'customer.subscription.updated': {
   84|         const { customer: customerOrId } = event.data.object;
   85|         const customer = await fetchCustomerWithSubscriptionsById({ customerId: isString(customerOrId) ? customerOrId : customerOrId.id });
   86|         await saveOrUpdateSubscription({ customer, sendWelcomeEmail: false });
   87|         break;
   88|       }
   89|       default:
   90|         logger.info('Unhandled Stripe webhook event: %s', event.type);
   91|         break;
   92|     }
   93|   } catch (ex) {
   94|     logger.error({ ...getErrorMessageAndStackObj(ex) }, 'Unable to process webhook event');
   95|     throw new Error('Unable to process webhook event');
   96|   }
   97| }
   98| 
   99| function filterInactiveSubscriptions(subscriptions: Stripe.Subscription[]) {
  100|   return subscriptions.filter((subscription) => activeSubscriptionStatuses.has(subscription.status));
  101| }
  102| 
  103| function findTeamPlanSubscription(subscriptions: Stripe.Subscription[]) {
  104|   return subscriptions.find(({ items }) => items.data.some((item) => item.price.lookup_key?.startsWith('TEAM_')));
  105| }
  106| 
  107| /**
  108|  * A team plan can be started either through checkout or by switching plans in the Stripe billing
  109|  * portal, and the portal never routes through checkout. Every path that observes a TEAM price on a
  110|  * customer funnels through here so that a delayed or failed webhook self-heals instead of leaving the
  111|  * user without a team.
  112|  */
  113| async function createTeamForTeamPlanCustomer({ userId, customerId }: { userId: string; customerId: string }) {
  114|   const team = await teamDbService.upsertTeamWithBillingAccount({ userId, billingAccountCustomerId: customerId });
  115|   // ensure stripe has proper metadata
  116|   await updateCustomerMetadata(customerId, { userId, teamId: team.id, type: 'TEAM' });
  117|   return team;
  118| }
  119| 
  120| async function fetchCustomerWithSubscriptionsById({
  121|   customerId,
  122| }: {
  123|   customerId: string;
  124| }): Promise<Stripe.Response<Stripe.Customer | Stripe.DeletedCustomer>> {
  125|   return await stripe.customers.retrieve(customerId, {
  126|     expand: ['subscriptions'],
  127|   });
  128| }
  129| 
  130| export async function fetchPrices({ lookupKeys }: { lookupKeys: typeof STRIPE_PRICE_KEYS }): Promise<JetstreamPricesByLookupKey> {
  131|   const cache = priceCache.get(lookupKeys);
  132|   if (cache?.expiresAt && cache.expiresAt > Date.now()) {
  133|     return cache.prices;
  134|   }
  135| 
  136|   const prices = await stripe.prices
  137|     .list({
  138|       lookup_keys: lookupKeys as unknown as string[],
  139|       expand: ['data.product'],
  140|       type: 'recurring',
  141|       currency: 'usd',
  142|       active: true,
  143|     })
  144|     .then(({ data }) => data);
  145| 
  146|   const groupedPrices = groupByFlat(prices, 'lookup_key');
  147| 
  148|   function getPrice(key: string): JetstreamPrice {
  149|     const price = groupedPrices[key];
  150|     if (!price) {
  151|       throw new Error(`Price not found for lookup key: ${key}`);
  152|     }
  153|     const product = price.product as Stripe.Product;
  154|     return {
  155|       id: price.id,
  156|       billingScheme: price.billing_scheme,
  157|       lookupKey: key,
  158|       interval: price.recurring?.interval === 'year' ? 'ANNUAL' : 'MONTHLY',
  159|       amount: (price.unit_amount || 0) / 100,
  160|       tiersMode: price.tiers_mode || null,
  161|       tiers:
  162|         price.tiers?.map(
  163|           (tier) =>
  164|             ({
  165|               flatAmount: tier.flat_amount ? tier.flat_amount / 100 : null,
  166|               unitAmount: tier.unit_amount ? tier.unit_amount / 100 : null,
  167|               upTo: tier.up_to,
  168|             }) as JetstreamPriceTier,
  169|         ) || null,
  170|       product: {
  171|         id: product.id,
  172|         name: product.name,
  173|         description: product.description,
  174|         images: product.images,
  175|       },
  176|     };
  177|   }
  178| 
  179|   const pricesByKey = lookupKeys.reduce((acc, key) => {
  180|     acc[key] = getPrice(key);
  181|     return acc;
  182|   }, {} as JetstreamPricesByLookupKey);
  183| 
  184|   priceCache.set(lookupKeys, {
  185|     prices: pricesByKey,
  186|     expiresAt: Date.now() + 1000 * 60 * 60 * 6, // Cache for 6 hours
  187|   });
  188| 
  189|   return pricesByKey;
  190| }
  191| 
  192| export async function fetchCustomerEntitlements({
  193|   customerId,
  194| }: {
  195|   customerId: string;
  196| }): Promise<Stripe.Response<Stripe.ApiList<Stripe.Entitlements.ActiveEntitlement>>> {
  197|   return await stripe.entitlements.activeEntitlements.list({ customer: customerId });
  198| }
  199| 
  200| export async function fetchCustomerWithSubscriptionsByJetstreamId({ userId }: { userId: string }): Promise<Stripe.Customer> {
  201|   const customerWithSubscriptions = await stripe.customers.search({
  202|     query: `metadata["userId"]:"${userId}"`,
  203|     limit: 1,
  204|     expand: ['subscriptions', 'entitlements'],
  205|   });
  206|   return customerWithSubscriptions.data[0];
  207| }
  208| 
  209| export async function getUserFacingStripeCustomer({ customerId }: { customerId: string }): Promise<StripeUserFacingCustomer | null> {
  210|   try {
  211|     const stripeCustomer: Stripe.Customer | Stripe.DeletedCustomer = await fetchCustomerWithSubscriptionsById({ customerId });
  212|     if (stripeCustomer.deleted) {
  213|       return null;
  214|     }
  215|     return convertCustomerWithSubscriptionsToUserFacing(stripeCustomer);
  216|   } catch (ex) {
  217|     logger.warn({ customerId, ...getErrorMessageAndStackObj(ex) }, 'Unable to fetch or convert customer to user facing');
  218|     return null;
  219|   }
  220| }
  221| 
  222| export function convertCustomerWithSubscriptionsToUserFacing(stripeCustomer: Stripe.Customer) {
  223|   const customerWithSubscriptions: StripeUserFacingCustomer = {
  224|     id: stripeCustomer.id,
  225|     balance: stripeCustomer.balance / 100,
  226|     delinquent: !!stripeCustomer.delinquent,
  227|     subscriptions:
  228|       stripeCustomer.subscriptions?.data.map(
  229|         ({ id, billing_cycle_anchor, cancel_at, cancel_at_period_end, canceled_at, ended_at, items, start_date, status }) => ({
  230|           id,
  231|           // TODO: validate that the dates are correct (should be if server is on UTC I think?)
  232|           billingCycleAnchor: formatISO(fromUnixTime(billing_cycle_anchor)),
  233|           cancelAt: cancel_at ? formatISO(fromUnixTime(cancel_at)) : null,
  234|           cancelAtPeriodEnd: cancel_at_period_end,
  235|           canceledAt: canceled_at ? formatISO(fromUnixTime(canceled_at)) : null,
  236|           endedAt: ended_at ? formatISO(fromUnixTime(ended_at)) : null,
  237|           startDate: formatISO(fromUnixTime(start_date)),
  238|           status: status.toUpperCase() as Uppercase<Stripe.Subscription.Status>,
  239|           items: items.data.map(({ id, price, quantity, current_period_start, current_period_end }) => ({
  240|             id,
```
