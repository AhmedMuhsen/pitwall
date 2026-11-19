# Deploying PitWall

Status: **not deployed.** Nothing in this file has been run against AWS. It is the checklist and the
two options for the decision CLAUDE.md asks for (EC2 or a container service, recorded in
`DECISIONS.md`). Check current prices and console screens yourself; they change.

## 0. Before anything else: a budget alert

In the AWS console: Billing and Cost Management -> Budgets -> Create budget -> "Cost budget" with a
small monthly amount you are happy to lose, and email alerts at 80% and 100% of actual spend and at
100% forecast. Do this on a new account first, before launching anything.

## 1. The app needs three small files that are not in git

`app.py` reads `data/processed/lap_dataset.parquet` (about 1 MB) and optionally
`data/processed/driver_names.json` and `data/processed/neutralisations.json` (without the last one,
the four races with a safety car are hidden). `.gitignore` excludes `data/processed/*`, so a fresh clone cannot
run the app. Options:

| | How | Trade-off |
|---|---|---|
| **A (recommended)** | Add `!data/processed/lap_dataset.parquet`, `!data/processed/driver_names.json` and `!data/processed/neutralisations.json` under `data/processed/*` in `.gitignore` and commit the three files | Tiny, reproducible, works on every host. The files are derived from public OpenF1 data; mention OpenF1 in the README (done) |
| B | Build on the server (about 350 API requests, ~20 minutes): `fetch_races.py`, `build_dataset.py`, `build_driver_names.py`, `build_neutralisations.py` | Slow, and depends on the API being up at deploy time |
| C | `scp` the three files to the server | Manual; easy to forget on redeploy |

Raw API responses (`data/raw/`, about 46 MB) stay out of git.

## 2. Hosting options

### EC2 (recommended for the learning goal; no Docker needed)

1. Launch a small Ubuntu instance (try the smallest size with at least 1 GB of memory; the app needs
   pandas, scikit-learn and Streamlit in memory). Create a key pair.
2. Security group: SSH (22) from your IP only; the app port (8501) from anywhere, or from your IP
   while testing.
3. On the instance: install uv, `git clone` the repo, `uv sync --frozen`.
4. Run: `uv run streamlit run app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true`.
5. Keep it running with a systemd unit (`ExecStart` = the command above, `WorkingDirectory` = the
   repo, `Restart=on-failure`).
6. HTTPS needs a domain plus a load balancer or a reverse proxy; for a portfolio demo plain HTTP on
   a stated URL is acceptable if you say so in the README.

You learn: instances, key pairs, security groups, systemd. You own patching and uptime.

### Container service (App Runner or ECS Fargate)

Needs a `Dockerfile` (not written yet; CLAUDE.md says Docker only if the chosen option needs it), an
ECR repository, and a service definition. More moving parts and a higher bill for something that
serves a handful of visitors, but you get HTTPS and restarts for free. Choose it if "containers on
AWS" is the thing you want on your CV.

### Fallback

Streamlit Community Cloud from a GitHub repo (option A above must be done so the data is in the repo).
Free, minutes to set up, no AWS learning. CLAUDE.md names it as the fallback if the AWS deploy runs
well past budget.

## 3. After deploying: test from a clean browser

- Private window, no logins, from a different network if possible.
- Open the app, pick a 2025 race and a car, check the verdict box, both charts and the "All numbers"
  table appear. Switch races twice. Tick "Add it to the comparison" with two identical tyres and
  confirm you get a message, not an error page.
- Open the "Assumptions and limitations" panel.
- Confirm no local file paths or stack traces are visible.

## 4. Known limits to state

- Cold start: the first visit fits the model (about 2 s here); later visits reuse it
  (`st.cache_resource`).
- One process serves everyone; there is no database and no accounts.
- Only the 15 cached races are available; there is no live data.
