# D&A Feature Process KPI Dashboard

This repository supports the Data & Analytics (D&A) team in analysing the Feature process in Azure DevOps. It collects Azure DevOps work item data, transforms the backlog into an analysis-friendly structure, and provides a Jupyter notebook for wrangling the data into one big table to be exported to Power BI for KPI dashboarding.

The first use case is the retrospective with the domain teams on 5 October 2026. The analysis covers the period from 20 February 2025, the date of the previous retrospective, through the current date.

## Output

The output of the notebook is a single table of all Features with at least the following columns:

- Name and ID
- Epic
- Domain (area).
- Effort per feature (`Moeite Int`)
- Lead time based on state changes:
  - **Waiting time:** from `Geprioriteerd` to `In progress`.
  - **Work in progress:** from `In progress` to `Done`.
- Work-in-progress duration analysed:
  - Across all Features.
  - By effort category: `1-2`, `3-5`, and `8+`.
  - Per domain.

Some metrics depend on a reliable Azure DevOps history of state and field changes. In particular, effort determination time may require additional history API work because the current field value alone does not show when `Moeite Int` was entered.

## How It Works

Run the feature_analysis notebook. 
Within the notebook, the following steps are performed:

1. **Fetch 1:** `src/scripts/fetch_data_science_pool_backlog.py` authenticates with an Azure DevOps Personal Access Token and downloads work items through the Azure DevOps REST API.
2. **Transform:** `src/scripts/backlog_hierarchical_transformer.py` converts the raw export into an Epic -> Feature -> User Story -> Task hierarchy and adds summary statistics.
3. **Fetch 2:** `src/scripts/fetch_work_items.py` gets work item history and field changes for the Features in the backlog. This is necessary to determine when the effort was entered and to calculate lead times.

## Project Structure

```
azure_devops_data/  # Fetched backlog data (gitignored)
notebooks/          # Jupyter notebooks for analysis
src/
  scripts/          # Data fetching & processing scripts
```

## Getting Started

1. Create and activate a virtual environment:
   ```
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   ```
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Copy `example.env` to `.env` and add an Azure DevOps PAT with *Project and Team: Read* and *Work Items: Read* permissions:
   ```
   cp example.env .env
   ```
   Set the token in `.env`:
   ```
   AZURE_API=your_personal_access_token
   ```
4. Open the notebook and run its cells to analyse the data:
   ```
   jupyter notebook notebooks/features_analysis.ipynb
   ```

## GitHub Pages

A public landing page lives in [`docs/`](docs/index.html) and is served via GitHub Pages. Visuals built from the analysis will be added there in a follow-up step.

To enable it (one-time, repo admin): **Settings &rarr; Pages &rarr; Source: Deploy from a branch &rarr; Branch: `main`, folder: `/docs`**. The site is public by design, so only aggregated/non-sensitive outputs should be placed in `docs/` — never raw `azure_devops_data/` exports.

## Data and Security

- Raw exports are written to `azure_devops_data/` and should remain uncommitted.
- Never commit `.env` or expose the Azure DevOps Personal Access Token.
- The notebook and scripts expect the Azure DevOps field names and state names used by the Feature process. Changes in the process configuration may require updates to the analysis.