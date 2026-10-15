# Data sources

Every external dataset OpsLens uses, with where it came from and its licence.
Re-download with `mingw32-make data` (script: `scripts/download_data.py`).
Raw files live in `data/public/` and are not committed to git.

## 1. Bitext customer-support dataset (ticket text)

- **What:** 26,872 synthetic customer-support requests (`instruction`) with `category` and
  `intent` labels (27 intents in 11 groups, e.g. `REFUND/get_refund`, `PAYMENT/payment_issue`,
  `DELIVERY/delivery_period`, `ORDER/track_order`, `ACCOUNT/recover_password`). Includes
  realistic noise (typos, missing punctuation) and placeholders such as `{{Order Number}}`.
- **URL:** https://huggingface.co/datasets/bitext/Bitext-customer-support-llm-chatbot-training-dataset
- **File:** `Bitext_Sample_Customer_Support_Training_Dataset_27K_responses-v11.csv`
  → `data/public/bitext/bitext_customer_support_27k_v11.csv` (19.2 MB)
- **SHA-256:** `6f81102b0100b97b8468eb04368033a23206bf1fde9d53500d5806ec1001a434`
- **Licence:** CDLA-Sharing-1.0 (Community Data License Agreement – Sharing). Use and
  modification allowed; credit Bitext; share derived *data* under the same licence.
- **How we use it:** text for the categories it covers (refund, payment, account,
  delivery/tracking). It has no food-specific intents, so missing_item, wrong_item,
  restaurant_partner and app_bug text comes from our own template generator
  (`data/text_bank.py`). **The ticket text is partly synthetic, and we say so.**

## 2. UCI "Incident management process enriched event log" (real operations data)

- **What:** event log from a real ServiceNow instance of an IT company. 141,712 events for
  24,918 incidents (2016–2017), 36 columns including `made_sla`, `priority`,
  `assignment_group`, `reassignment_count`, `reopen_count`, `opened_at`, `resolved_at`.
  Categories and groups are anonymised codes ("Category 55", "Group 56").
- **URL:** https://archive.ics.uci.edu/dataset/498/incident+management+process+enriched+event+log
- **Files:** `incident_event_log.zip` (2.4 MB, SHA-256
  `6294e29a311647306bfdfc85783f7df66517c197b9cd49aa5ee36ba9c525d1d6`) →
  `incident_event_log.csv` (46.2 MB, SHA-256
  `fd184bbfd62329cfe093e99da2ea7071905f2ead91900b448eb2635870821bef`)
- **Licence:** CC BY 4.0. Citation: Amaral, C., Fantinato, M., Peres, S. (2018).
  Incident management process enriched event log. UCI Machine Learning Repository.
  https://doi.org/10.24432/C57S4H
- **How we use it:** real-data check for the risk model (`made_sla`), pattern findings
  (e.g. reassignment hot spots), forecast WAPE, and the ready example for Upload CSV.
  This is our answer to "you only found what you planted".

## 3. Generated operations data (ours)

- `data/generate_ops.py` creates timestamps, channels, priorities, agents, skills, shifts
  and SLAs for 56 days, with planted problems recorded in `data/planted.json`.
  Parameters: `config/generator.yaml`. Fixed seed. Public datasets do not contain this
  layer, so we generate it — **and say so openly in the pitch.**
