# From a PM request to a refactor checklist

This walkthrough follows one real product decision through the whole
pipeline: edit the rules, validate, review the human diff, list the services
to refactor, and ship updated constants.

It uses the bundled examples so every command is reproducible:

```bash
cd business-semantic-layer
pip install -e ".[dev]"
```

## 1. The PM request

> “Free shipping on orders of $50 or more. Also, coupons should not stack
> with free shipping. And let’s raise the minimum order to $25.”

That request is still prose. The first job is to turn it into versioned
rule data, not tickets scattered across five boards.

## 2. Baseline: what we have today

`examples/checkout_v1.yaml` is the baseline:

```yaml
name: checkout-rules
version: "1.0.0"

rules:
  - id: checkout.min-order
    version: 1
    statement: Orders must be at least $10 before tax to checkout.
    ...
  - id: checkout.free-shipping
    version: 1
    statement: Free shipping is not offered.
    ...
  - id: inventory.hold-stock
    version: 1
    statement: Reserve stock for 15 minutes when checkout starts.
    ...
```

Sanity-check it:

```bash
bsl validate examples/checkout_v1.yaml
```

```text
OK: checkout-rules v1.0.0 — 3 rule(s) valid
```

## 3. Write the new rules

`examples/checkout_v2.yaml` applies the PM decision:

| Rule | What changed | Why |
| --- | --- | --- |
| `checkout.min-order` | `$10` → `$25`, version 1 → 2 | Meaning changed, so bump the rule version. |
| `checkout.free-shipping` | No free shipping → free over `$50`, version 1 → 2 | New threshold, new effect (`shipping_price` 0), extra service. |
| `checkout.coupon-stack` | **New** rule | Coupons cannot stack with free shipping. |
| `inventory.hold-stock` | Untouched | Not part of this decision. |

Notes that matter for engineers:

- Bump `version` when the *meaning* changes, not on every keystroke.
- `affected_services` is the contract for “who has to care”.
- `entities` names the domain objects the rule reads/writes.

Validate the new file:

```bash
bsl validate examples/checkout_v2.yaml
```

## 4. Review the human-readable diff

`bsl impact` answers *which rules changed* and *which services to refactor*.
`bsl diff` shows *what moved inside each rule* — the view a PR reviewer wants.

```bash
bsl diff examples/checkout_v1.yaml examples/checkout_v2.yaml
```

```text
RuleSet checkout-rules: 1.0.0 -> 1.1.0

+ checkout.coupon-stack v1
  statement: Coupons cannot be stacked with free shipping.
  ...

~ checkout.free-shipping v1 -> v2 (version, statement, when, then, affected_services)
  statement
    - Free shipping is not offered.
    + Orders of $50 or more ship free.
  when
    - cart.subtotal ge 0
    + cart.subtotal ge 50
  then
    - cart.shipping_price eq 5.99
    + cart.shipping_price eq 0
  affected_services
    + storefront-web
  ...

Services to refactor (4):
  - checkout-api
  - promo-service
  - shipping-service
  - storefront-web
```

Add `--show-unchanged` if you also want confirmation that
`inventory.hold-stock` did not move.

## 5. CI-oriented impact summary

```bash
bsl impact examples/checkout_v1.yaml examples/checkout_v2.yaml
```

```text
Impact: checkout-rules -> checkout-rules
  added:     1
  removed:   0
  changed:   2
  unchanged: 1
  rules to review:
    + checkout.coupon-stack v1
    ~ checkout.min-order v1 -> v2 (version, statement, when)
    ~ checkout.free-shipping v1 -> v2 (version, statement, when, then, affected_services)
  services to refactor (4):
    - checkout-api
    - promo-service
    - shipping-service
    - storefront-web
```

Gate merges in CI:

```bash
bsl impact old.yaml new.yaml --fail-on-impact   # exit 1 when anything drifted
```

Paste a Markdown report into the PR description:

```bash
bsl impact examples/checkout_v1.yaml examples/checkout_v2.yaml \
    --format markdown -o impact.md
```

## 6. Keep application code in sync

Export importable constants so services do not hand-copy thresholds:

```bash
bsl export examples/checkout_v2.yaml --lang python  -o rules.py
bsl export examples/checkout_v2.yaml --lang typescript -o rules.ts
```

Application code can then import `CHECKOUT_FREE_SHIPPING` (Python) or
`CheckoutFreeShipping` (TypeScript) instead of hard-coding `50` and `0`.

## 7. Refactor checklist

Use the services list from step 4 as the work breakdown:

| Service | Why it is on the list | Typical work |
| --- | --- | --- |
| `checkout-api` | min-order, free-shipping, coupon-stack | Threshold checks, shipping price, coupon guard |
| `shipping-service` | free-shipping | Quote free shipping when subtotal ≥ 50 |
| `storefront-web` | min-order, free-shipping | Messaging + checkout button states |
| `promo-service` | coupon-stack | Reject stacking when shipping is free |

Suggested PR sequence:

1. Land the rules file change (this repo or your rules store).
2. Open one PR per affected service, each linking the impact report.
3. Update unit/integration tests for the changed thresholds.
4. Confirm kill-switch / `enabled` behavior if a rule was disabled.
5. Re-run `bsl impact` in CI against the merged rule set.

## 8. What this workflow buys you

- One source of truth for the English the PM signed off on.
- Schema errors (`bsl validate`) before code review starts.
- A reviewable diff (`bsl diff`) instead of a ticket archaeology dig.
- An explicit service list instead of “whoever remembers free shipping”.
- Generated constants that fail loudly when someone hard-codes a number.

It is not a rules engine and it does not rewrite services for you — it makes
the *decision* and its blast radius impossible to miss.
